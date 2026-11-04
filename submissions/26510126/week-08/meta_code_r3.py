"""The meta-harness changes its own code (the user, 11/4 17:10: the market is not real money, so give the harness more
room to act on its own ideas; the supervisor keeps watching).

meta_r3 runs `python meta_code_r3.py` in the background after a cycle. One run does at most one of two things:

1. check: an automatic change at least CHECK_AFTER old gets a verdict. Paid buyer deals and closed shop deals per hour
   after it are compared with the hour before; when either fell by more than DROP, the files go back to the commit
   before the change (a new commit, history kept) and the verdict says why.
2. build: the newest code idea of the team that no run has tried yet is handed to a coding agent (Claude Code,
   `claude -p` on the user's subscription, sonnet) in a copy of the agent folder outside the repository. Code then
   gates its work: only ALLOWED files may change, no added line may touch payments, keys or processes (FORBIDDEN),
   at most MAX_LINES added, and every test suite has to pass in the copy. A change that passes is copied into the
   live folder file by file (write, then rename), committed, and logged in logs/code_changes_r3.jsonl as
   "meta (auto)" with the hour before as its baseline; one that fails is logged in logs/code_attempts_r3.jsonl.

Never changed by this: the kit (market_kit.py, payments, mandates, checkout), the seller (a long-running process:
its ideas go to the supervisor), meta_r3 / meta_code_r3 themselves (the gate does not rewrite its own gate).
At most one build every BUILD_EVERY and MAX_PER_DAY a day; a lock keeps two runs from overlapping.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKET = Path.home() / "Developer" / "agent-market"
PY = Path(os.environ.get("META_CODE_PY") or MARKET / ".venv" / "bin" / "python")
WORK = Path(os.environ.get("META_CODE_WORK") or MARKET / "staging" / "auto")
LOGS = HERE / "logs"
CHANGES = LOGS / "code_changes_r3.jsonl"
ATTEMPTS = LOGS / "code_attempts_r3.jsonl"
STRATEGIES = LOGS / "strategies_r3.jsonl"
LOCK = WORK.parent / "meta_code_r3.lock"

ALLOWED = {"buyer_r3.py", "buyer.py", "forum_r3.py", "restock_r3.py", "prices_r3.py", "demand_r3.py",
           "test_buyer_r3.py", "test_forum_r3.py", "test_restock_r3.py", "test_prices_r3.py"}
TESTS = ["test_buyer_r3.py", "test_forum_r3.py", "test_restock_r3.py", "test_prices_r3.py", "test_team_r3.py",
         "test_seller_r3.py"]
FORBIDDEN = re.compile(r"market_kit|checkout|mandate|private_key|\.pem|admin_token|secret|api_key|ANTHROPIC|"
                       r"subprocess|os\.system|shutil\.rmtree|\brm\b|unlink\(|/api/supply|/api/settle|signing",
                       re.I)
MAX_LINES = 150
BUILD_EVERY = 90 * 60
MAX_PER_DAY = 8
CHECK_AFTER = 60 * 60
DROP = 0.4
AGENT_TIMEOUT = 15 * 60

CODER = """You are the coding hand of a trading agent's meta-harness (a Round 3 market of AI shops and buyers; the money
is a classroom game). The team proposed this code idea from its evidence:

IDEA: {idea}

Recent results the idea came from (the team's own notes):
{context}

Make the smallest change in this folder that carries the idea out, in these files only: {allowed}.
Rules:
- Do not touch payments, checkout, mandates, keys, the kit (market_kit.py) or the seller; do not start processes,
  delete files or call new network hosts. Honesty rules stay: never claim a grade, shelf life or price that is not
  true, never pay above the budget.
- Match the code around it: same comment density, naming and style; a comment says why, with the evidence.
- Add one test case for the change to the matching test_*.py, in the style of the cases there.
- Run that test file with: {py} <test file>   and fix until it passes.
- If the idea cannot be done safely in these files, change nothing and say why in one line.
End with one line: CHANGED: <what you changed, in one sentence> or SKIPPED: <why>."""


def jl(path):
    try:
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def append(path, row):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] CODE: {msg}", flush=True)


def git(*args):
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, timeout=120)


def rates(t0, t1):
    """(buyer paid deals per hour, shop closed deals per hour) between t0 and t1."""
    hours = max((t1 - t0) / 3600, 0.25)
    paid = 0
    for m in jl(HERE / "memory.jsonl"):
        if m.get("kind") == "payment" and m.get("paid"):
            try:
                t = time.mktime(time.strptime(m["time"], "%Y-%m-%d %H:%M:%S"))
            except (KeyError, ValueError, TypeError):
                continue
            paid += t0 <= t < t1
    sold = sum(1 for x in jl(LOGS / "talks_r3.jsonl") if x.get("price") and t0 <= x.get("t", 0) < t1)
    return round(paid / hours, 1), round(sold / hours, 1)


def deploy(files, src):
    for f in files:
        tmp = HERE / f".{f}.auto"
        shutil.copyfile(src / f, tmp)
        os.replace(tmp, HERE / f)


def check():
    """Verdict on automatic changes old enough; True when one was judged."""
    rows = jl(CHANGES)
    for i, r in enumerate(rows):
        if r.get("source") != "meta (auto)" or r.get("verdict") or time.time() - r["t"] < CHECK_AFTER:
            continue
        before, after = r.get("baseline") or rates(r["t"] - 3600, r["t"]), rates(r["t"], r["t"] + CHECK_AFTER)
        worse = [n for n, b, a in zip(("buyer paid/h", "shop deals/h"), before, after) if b and a < b * (1 - DROP)]
        if worse:
            prev = git("rev-parse", f"{r['commit']}^").stdout.strip()
            for f in r.get("files", []):
                old = git("show", f"{prev}:submissions/26510126/week-08/{f}")
                if old.returncode == 0:
                    tmp = HERE / f".{f}.auto"
                    tmp.write_text(old.stdout, encoding="utf-8")
                    os.replace(tmp, HERE / f)
            git("add", *r.get("files", []))
            git("commit", "-q", "-m", f"week-08: [auto revert] {r['change'][:80]} - {', '.join(worse)} fell more than "
                f"{DROP:.0%} in the hour after ({before} -> {after})")
            r["verdict"] = f"reverted: {', '.join(worse)} {before} -> {after}"
        else:
            r["verdict"] = f"kept: {before} -> {after} (buyer paid/h, shop deals/h)"
        r["after"] = r["verdict"]
        rows[i] = r
        CHANGES.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
        log(r["verdict"] + f" for {r['commit']}")
        return True
    return False


def next_idea():
    tried = {a.get("key") for a in jl(ATTEMPTS)}
    for s in reversed(jl(STRATEGIES)[-8:]):
        for idea in s.get("code_ideas") or []:
            if not isinstance(idea, str) or len(idea) < 20:
                continue
            key = hashlib.sha1(idea[:120].lower().encode()).hexdigest()[:12]
            if key not in tried:
                return idea, key, s.get("reason") or ""
    return None, None, None


def gate(work):
    changed, added = [], []
    for f in sorted(p.name for p in work.glob("*.py")):
        live = HERE / f
        new = (work / f).read_text(encoding="utf-8")
        old = live.read_text(encoding="utf-8") if live.exists() else ""
        if new == old:
            continue
        changed.append(f)
        olds = set(old.splitlines())
        added += [x for x in new.splitlines() if x not in olds]
    if not changed:
        return [], "no change"
    bad = [f for f in changed if f not in ALLOWED]
    if bad:
        return changed, f"files outside the allowed set: {bad}"
    hit = [x.strip()[:80] for x in added if FORBIDDEN.search(x)]
    if hit:
        return changed, f"forbidden lines: {hit[:3]}"
    if len(added) > MAX_LINES:
        return changed, f"{len(added)} added lines, more than {MAX_LINES}"
    for t in TESTS:
        r = subprocess.run([str(PY), t], cwd=work, capture_output=True, text=True, timeout=600)
        last = (r.stdout.strip().splitlines() or ["?"])[-1]
        m = re.match(r"(\d+)/(\d+) passed", last)
        if r.returncode or not m or m.group(1) != m.group(2):
            return changed, f"{t}: {last[:80]}"
    return changed, None


def build():
    day = [a for a in jl(ATTEMPTS) if time.time() - a.get("t", 0) < 86400]
    if len(day) >= MAX_PER_DAY or (day and time.time() - day[-1]["t"] < BUILD_EVERY):
        return
    idea, key, context = next_idea()
    if not idea:
        return
    work = WORK / time.strftime("%m%d-%H%M")
    if work.exists():
        return
    work.mkdir(parents=True)
    for p in HERE.iterdir():
        if p.is_file() and (p.suffix == ".py" or (p.suffix == ".json" and p.stat().st_size < 200_000)):
            shutil.copy2(p, work / p.name)
    (work / "logs").mkdir()
    log(f"building {key}: {idea[:120]}")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    prompt = CODER.format(idea=idea, context=str(context)[:3000], allowed=", ".join(sorted(ALLOWED)), py=PY)
    # the agent works in the copy; if it wrote to the live folder anyway, those files go back before the gate
    snap = {p.name: p.read_bytes() for p in HERE.glob("*.py")}
    t0 = time.time()
    try:
        r = subprocess.run(["claude", "-p", "--model", "sonnet", "--setting-sources", "", "--no-session-persistence",
                            "--allowedTools", f"Read,Edit,Write,Glob,Grep,Bash({PY} test_*)"],
                           input=prompt, cwd=work, env=env, capture_output=True, text=True, timeout=AGENT_TIMEOUT)
        # the prompt goes on stdin: --allowedTools takes every argument after it as a tool name
        said = (r.stdout.strip().splitlines() or [r.stderr.strip()[-300:]])[-1][:300]
    except subprocess.TimeoutExpired:
        said = "timeout"
    strayed = [n for n, b in snap.items() if (HERE / n).read_bytes() != b]
    for n in strayed:
        tmp = HERE / f".{n}.auto"
        tmp.write_bytes(snap[n])
        os.replace(tmp, HERE / n)
    changed, why = gate(work)
    if strayed:
        why = f"the agent wrote to the live folder ({strayed}); restored"
    row = {"t": time.time(), "key": key, "idea": idea[:400], "agent": said, "secs": round(time.time() - t0),
           "files": changed, "work": str(work)}
    if not why and os.environ.get("META_CODE_DRY") == "1":
        why = "dry run (META_CODE_DRY=1)"
    if why:
        row["result"] = f"not deployed: {why}"
        append(ATTEMPTS, row)
        log(row["result"])
        return
    baseline = rates(time.time() - 3600, time.time())
    deploy(changed, work)
    git("add", *changed)
    what = said.split("CHANGED:", 1)[-1].strip() if "CHANGED:" in said else idea[:160]
    c = git("commit", "-q", "-m", f"week-08: [auto] {what[:120]}\n\nThe meta-harness's code idea, built by its coding "
            f"agent and passed by the gate (allowed files, no forbidden lines, all tests): {idea[:400]}")
    commit = git("rev-parse", "--short", "HEAD").stdout.strip() if c.returncode == 0 else "uncommitted"
    row["result"] = f"deployed {commit}"
    append(ATTEMPTS, row)
    append(CHANGES, {"t": time.time(), "commit": commit, "source": "meta (auto)", "change": what[:300],
                     "evidence": idea[:300], "after": "", "files": changed, "baseline": baseline})
    log(f"deployed {commit}: {what[:120]} ({', '.join(changed)})")


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - LOCK.stat().st_mtime < AGENT_TIMEOUT + 600:
            return
        LOCK.unlink()          # a run that died long ago left it
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        if not check():
            build()
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
