"""The outer loop: the meta-harness changes its own code (the user, 11/4 17:10: the market is not real money, so give
the harness more room to act on its own ideas; the supervisor keeps watching).

The inner loop (meta_r3, every 15 min) moves numbers inside bounds. This loop changes what no number can: one
hypothesis at a time, from the grade back to the code.

    goal      metrics_r3.score_gap(): the points each board term (shop book/revenue/stars, buyer saved/votes/
              deals/posts) costs us, from the live board, by the midterm's own weights
    engineer  a coding agent that reads the code, the raw traces (talks, payments, scouts, orders) and the ledger of
              past hypotheses with their results, and writes ONE hypothesis for the costliest term it can move: the
              change, the files, the metric that should move (metrics_r3.METRICS) and by how much. The team's own
              code ideas are inputs, not orders; an idea the code already does, or one tried before, is skipped.
    coder     a second agent that makes the change and a test in a copy of the folder outside the repository
    gate      code: only ALLOWED files, no line touching payments, keys or processes, at most MAX_LINES added, every
              suite passing in the copy; then the files go live (write, rename) and are committed
    verdict   code compares the named metric between the two halves of the orders (a per-order change, at least an
              hour) or SPAN before against SPAN after (restock, forum) (metrics_r3.window): kept, or
              reverted in a new commit when it moved the wrong way by more than WORSE, or when the guard metrics
              (buyer paid deals, shop deals per hour) fell by more than DROP. Expected and measured go into the
              ledger (logs/code_changes_r3.jsonl), which both loops and the next engineer read.

meta_r3 starts `python meta_code_r3.py` in the background after each cycle; one run gives a verdict or builds one
hypothesis. Never changed here: the kit (payments, mandates, checkout), the seller (a long-running process), meta_r3
and this file (the gate does not rewrite itself). One build per BUILD_EVERY, MAX_PER_DAY a day, behind a lock.
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

import code_ab_r3
import digest_r3
import metrics_r3

HERE = Path(__file__).resolve().parent
MARKET = Path.home() / "Developer" / "agent-market"
PY = Path(os.environ.get("META_CODE_PY") or MARKET / ".venv" / "bin" / "python")
WORK = Path(os.environ.get("META_CODE_WORK") or MARKET / "staging" / "auto")
LOGS = HERE / "logs"
CHANGES = LOGS / "code_changes_r3.jsonl"
ATTEMPTS = LOGS / "code_attempts_r3.jsonl"
STRATEGIES = LOGS / "strategies_r3.jsonl"
ADVICE = HERE / "advice_r3.json"
LOCK = WORK.parent / "meta_code_r3.lock"

ALLOWED = {"buyer_r3.py", "buyer.py", "forum_r3.py", "restock_r3.py", "prices_r3.py", "demand_r3.py",
           "test_buyer_r3.py", "test_forum_r3.py", "test_restock_r3.py", "test_prices_r3.py"}
# the seller's suite signs receipts with the shop key, which is never copied out of the live folder; the seller is
# outside ALLOWED anyway
TESTS = ["test_buyer_r3.py", "test_forum_r3.py", "test_restock_r3.py", "test_prices_r3.py", "test_team_r3.py"]
FORBIDDEN = re.compile(r"market_kit|checkout|mandate|private_key|\.pem|admin_token|secret|api_key|ANTHROPIC|"
                       r"subprocess|os\.system|shutil\.rmtree|\brm\b|unlink\(|/api/supply|/api/settle|signing",
                       re.I)
MAX_LINES = 150
BUILD_EVERY = 90 * 60
MAX_PER_DAY = 16       # one every BUILD_EVERY at most; 8 held the loop idle 03:02-09:05 on 11/5 with every verdict in
CHECK_AFTER = 60 * 60
# an A/B arm needs this many orders before its verdict, waiting up to CHECK_MAX: on 11/4 0abcb4b read +243% surplus
# per order on 70 orders an arm, because 10 dear-item talks fell in its arm and 4 in the other (its dear close rate
# was in fact lower, 40% against 50%); a few dear orders swing a small arm
MIN_ORDERS = 150
CHECK_MAX = 3 * 3600
# a change that cannot be split by order (restock, forum) is judged on SPAN before against SPAN after: one hour each
# read e6ff70b +107%, c6e5c61 -53% (reverted) and 15b2ee4 +354% on 11/5-6, a few dear sales either way
SPAN = 3 * 3600
DROP = 0.4          # a guard metric falling this much reverts any change
WORSE = 0.15        # the hypothesis' own metric moving this much the wrong way reverts it
# an A/B compares the same hours, so its noise is far smaller (saved/deal over ~150 orders a side: about 3%); 11/8 three buyer
# changes measured -2%, -2% and -6% and were all kept at the 15% bar, code paths that did not help left in the buyer
WORSE_AB = 0.03
AGENT_TIMEOUT = 15 * 60
TRACES = {"logs/talks_r3.jsonl": 3000, "memory.jsonl": 3000, ".market/payments.jsonl": 500,
          "logs/demand_r3.jsonl": 3000, "logs/market-kit.log": 6000, "logs/strategies_r3.jsonl": 6}

ENGINEER = """You are the engineer of a trading agent's meta-harness: an online market of AI shops and buyers (Round 3;
the money is a classroom game). Our place on the board is shop ALL + buyer ALL, each a weighted sum of percentiles.
What each term costs us now (points lost = weight x (1 - our percentile)):
{gap}

Our own metrics, per hour, oldest first (the metric names a hypothesis may use: {metrics}):
{windows}

Code changes so far, with what was expected and what was measured (newest last):
{ledger}

Code ideas the tuning team wrote lately (inputs, not orders; some describe what the code already does):
{ideas}

Notes from the supervisor (Claude, watching for the user), newest last; findings from the traces, not orders:
{advice}

This folder is a copy of the agent: the code, and raw traces under traces/ (talks_r3.jsonl: every negotiation our
shop had; memory.jsonl: our buyer's trades and payments; payments.jsonl; demand_r3.jsonl: orders and asks;
market-kit.log: the buyer's and kit's lines with SCOUT, CAND, GUARD, ASK, OUT). Read the code before you claim it
lacks something. Find ONE change, in these files only: {allowed}, that should move a costly term, backed by numbers
you counted in the traces. Read the ledger first: when changes aimed at one metric keep measuring flat or worse, aim
at another term.

Counted by code from the same traces (you cannot run scripts, so start from these numbers and check them in the
traces); the areas are ranked by the board points they lose, discounted by what the loop already tried this day.
Look at the top area first, but take the change the numbers back best in any area:
{digest}

The market's rules of 11/6 06:02 score the buyer by saved: the sum over deals of (list - price) / list, divided by
deals + 100, a deal whose goods broke or whose food did not last counting -1 (0 if refunded). A snack and a sofa at 30%
off score the same, so the buyer gains by a deeper discount on every order and by never buying a unit likely to break
or spoil, not by dear orders (buyer_saved_deal is that per deal). Forum votes now count one stance per voting account
per author, from voters with 50 settled deals.

The tuning team moves the numbers in strategy_r3.json; the code around them is yours. In the stock area that is how
restock_r3.py ranks SKUs and categories, which lines a window buys and in what order, what demand_r3.py and
prices_r3.py count: changing what the code does with a number is a code change, setting the number is not. Before
you skip, read the top area's files and say which of the counts above you checked and why none points to a code
change (on 11/5 20:18 an engineer skipped the top area, stock, in 22 s without reading restock_r3.py).

Not: a change already in the code or in the list above, a number the tuning team can set
(it already moves those), anything about payments, keys or the seller.

Answer with one JSON object on the last line, nothing after it:
{{"hypothesis": "<the change, one sentence>", "why": "<the counts from the traces that back it>",
  "files": ["<file>"], "metric": "<one of the metric names>", "expected": <signed relative change, e.g. 0.1>,
  "term": "<the board term it serves>"}}
or {{"skip": "<why no change is worth making now>"}}"""

CODER = """You are the coding hand of a trading agent's meta-harness (an online market of AI shops and buyers; the
money is a classroom game). The engineer wrote this hypothesis from the traces:

{spec}

Make the smallest change in this folder that carries it out, in these files only: {allowed}.
Rules:
- Do not touch payments, checkout, mandates, keys, the kit (market_kit.py) or the seller; do not start processes,
  delete files or call new network hosts. Honesty rules stay: never claim a grade, shelf life or price that is not
  true, never pay above the budget.
- Match the code around it: same comment density, naming and style; a comment says why, with the engineer's numbers.
- Merge before adding: if the function already has a rule on the same thing (a depth, a bar, a share of the room),
  change that rule rather than add another layer beside it, so the next engineer reads one rule, not five.
- When the change acts per buyer order, put the new behaviour behind
      if code_ab_r3.on("{key}", <the order id, e.g. order.get("order")>):
  (import code_ab_r3): while it is on trial it runs on half the orders, so its verdict compares the same hours.
  A change that is not per order (forum, restock) needs no flag.
- Add one test case for the change to the matching test_*.py, in the style of the cases there.
- Run that test file with: {py} <test file>   and fix until it passes.
- If it cannot be done safely in these files, change nothing and say why in one line.
End with one line: CHANGED: <what you changed, in one sentence> or SKIPPED: <why>."""


def jl(path):
    try:
        return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def append(path, row):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] CODE: {msg}", flush=True)


def git(*args):
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, timeout=120)


def deploy(files, src):
    for f in files:
        tmp = HERE / f".{f}.auto"
        shutil.copyfile(src / f, tmp)
        os.replace(tmp, HERE / f)


# 11/9: 4d10151 (deeper stock of hot 300k+ lines) was reverted at 11:15 for shop margin/h -20% over 3 h before and
# after, while revenue/h went 2.0M -> 3.8M, board points/h +3% and our share of the market's paid value 0.38% -> 0.70%:
# the engineer's own metric decided alone, and raw shop numbers before vs after read the hour of day. Before/after
# shop numbers are now divided by the market's own change over the same hours (paid value for margin, revenue and
# board points, paid count for deals), and the one aim (board points/h) decides when it can be measured
BY_VALUE = ("shop_margin_h", "shop_revenue_h", "shop_pts_h")   # the market's paid value scales the shop's terms only
NUMBER_TRIALS = HERE / "logs" / "number_trials_r3.json"
SHOP_FILES = {"restock_r3.py", "demand_r3.py", "prices_r3.py", "seller_r3.py"}
BY_COUNT = ("shop_deals_h",)


def market_adjust(after, market):
    """`after` with its shop numbers divided by the market's after/before ratio (value, count); None ratios skip."""
    rv, rn = market or (None, None)
    out = dict(after)
    for keys, ratio in ((BY_VALUE, rv), (BY_COUNT, rn)):
        for k in keys:
            if ratio and isinstance(out.get(k), (int, float)):
                out[k] = out[k] / ratio
    return out


def judge(r, before, after, market=None):
    """(verdict text, reasons to revert) for one change: the aim (board points/h) when measurable, else its own metric, then the guards.
    `market`: (paid value, paid count) after over before for the market, for before/after verdicts."""
    why = []
    if market:
        after = market_adjust(after, market)
    own = metrics_r3.change(r.get("metric"), before, after) if r.get("metric") else None
    # the aim is the side the change works on: the buyer's saved was 82-91% of board points/h, so a shop change judged
    # on the total read the buyer's swings (11/9 review)
    side = "shop_pts_h" if set(r.get("files") or []) & SHOP_FILES else "buyer_pts_h"
    aim = None if r.get("ab_key") else metrics_r3.change(side, before, after)
    if aim is not None and aim < -WORSE:
        why.append(f"{side} {aim:+.0%}")
    # one aim: when board points/h can be measured they decide, the engineer's own metric is context; it reverts
    # alone only when the aim cannot be measured (buyer-only numbers, A/B arms)
    if own is not None and own < -(WORSE_AB if r.get("ab_key") else WORSE) and r.get("metric") not in ("board_pts_h", side) \
            and aim is None:
        why.append(f"{r['metric']} {own:+.0%}")
    for g in ("buyer_paid_h", "shop_revenue_h"):     # revenue, not sale count: dearer stock sells fewer units
        b, a = before.get(g), after.get(g)
        if b and a is not None and a < b * (1 - DROP):
            why.append(f"guard {g} {b} -> {a}")
    expected = r.get("expected")
    text = (f"{r.get('metric')}: expected {expected:+.0%}, measured {own:+.0%}" if isinstance(expected, (int, float))
            and own is not None else f"{r.get('metric')}: {before.get(r.get('metric'))} -> {after.get(r.get('metric'))}")
    if aim is not None:
        text += f"; {side.replace('_pts_h', ' points/h')} {aim:+.0%}"
    if market:
        text += "; shop numbers net of the market's own change" + (
            f" (paid value x{market[0]:.2f}, count x{market[1]:.2f})" if all(market) else "")
    return text, why


def check():
    """Verdict on the automatic change once its trial has run; True when one was judged."""
    rows = jl(CHANGES)
    for i, r in enumerate(rows):
        if r.get("source") != "meta (auto)" or r.get("verdict") or \
                time.time() - r["t"] < (CHECK_AFTER if r.get("ab_key") else SPAN):
            continue
        if r.get("ab_key"):                         # the same hours, orders without the change against orders with it
            # a trial cut short (trial_end: another trial took the slot) is judged on the hours it ran split
            k, end = r["ab_key"], min(time.time(), r["t"] + CHECK_MAX, r.get("trial_end") or time.time())
            before = metrics_r3.window(r["t"], end, keep=lambda o: code_ab_r3.arm(k, o) == "A")
            after = metrics_r3.window(r["t"], end, keep=lambda o: code_ab_r3.arm(k, o) == "B")
            if min(before.get("orders") or 0, after.get("orders") or 0) < MIN_ORDERS and \
                    time.time() < r["t"] + CHECK_MAX and not r.get("trial_end"):
                continue                            # too few orders an arm yet: the trial runs on
            code_ab_r3.stop()
        else:
            before = metrics_r3.window(r["t"] - SPAN, r["t"])
            after = metrics_r3.window(r["t"], r["t"] + SPAN)
            ma, mb = metrics_r3.market_share(r["t"] - SPAN, r["t"]), metrics_r3.market_share(r["t"], r["t"] + SPAN)
            market = (mb["market_value"] / ma["market_value"] if ma.get("market_value") else None,
                      mb["market"] / ma["market"] if ma.get("market") else None)
        text, why = judge(r, before, after, market if not r.get("ab_key") else None)
        # another change inside a before/after window makes it MIXED (11/9: dc04325 read +398% revenue over hours that
        # also held the 130M stock cap and the warranty on every grade): recorded, and not reverted on that reading
        mixed = [] if r.get("ab_key") else [
            str(x.get("change", ""))[:50] for x in rows if x is not r and abs(x.get("t", 0) - r["t"]) < SPAN
            and x.get("source") in ("inner loop (number)", "supervisor", "meta (auto)")
            and not str(x.get("change", "")).startswith("fast guard")]
        if mixed:
            text += f"; MIXED with {', '.join(mixed[:3])}"
            why = [w for w in why if w.startswith("guard")]   # only a collapse (a guard) still reverts it
        text += (f" (A/B: same hours, {before.get('orders')} and {after.get('orders')} orders)" if r.get("ab_key")
                 else f" ({SPAN // 3600} h before against {SPAN // 3600} h after)")
        if why:
            # undo this commit's own lines, not the whole file as it was before it: a hand fix made to the same file
            # in the hours before the verdict went with it (11/9 review); a conflict leaves the change and says so
            rv = git("revert", "--no-edit", r["commit"])
            if rv.returncode == 0:
                git("commit", "--amend", "-q", "-m",
                    f"week-08: [auto revert] {r['change'][:80]} - {'; '.join(why)} in the hours after")
                r["verdict"] = f"reverted ({'; '.join(why)}); {text}"
            else:
                git("revert", "--abort")
                r["verdict"] = f"should be reverted ({'; '.join(why)}) but its lines changed since: left for the supervisor; {text}"
        else:
            r["verdict"] = f"kept; {text}"
        r["after"], r["measured"] = r["verdict"], after
        # write back this row only, into the file as it is now: rows other writers appended meanwhile stay
        fresh = jl(CHANGES)
        for j, x in enumerate(fresh):
            if x.get("t") == r["t"] and x.get("commit") == r.get("commit") and x.get("source") == r.get("source"):
                fresh[j] = r
                break
        tmp = CHANGES.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in fresh), encoding="utf-8")
        os.replace(tmp, CHANGES)
        log(r["verdict"] + f" for {r['commit']}")
        return True
    return False


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


def agent(prompt, work, tools):
    """What a `claude -p` agent printed in `work` (stderr when it printed nothing), or "timeout"."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    try:
        # the prompt goes on stdin: --allowedTools takes every argument after it as a tool name
        r = subprocess.run(["claude", "-p", "--model", "sonnet", "--setting-sources", "", "--no-session-persistence",
                            "--allowedTools", tools], input=prompt, cwd=work, env=env, capture_output=True,
                           text=True, timeout=AGENT_TIMEOUT)
        return r.stdout.strip() or r.stderr.strip()[-300:]
    except subprocess.TimeoutExpired:
        return "timeout"


def last_json(text):
    for line in reversed((text or "").splitlines()):
        line = line.strip().strip("`")
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def copy_folder(work):
    work.mkdir(parents=True)
    for p in HERE.iterdir():
        if p.is_file() and (p.suffix == ".py" or (p.suffix == ".json" and p.stat().st_size < 200_000)):
            shutil.copy2(p, work / p.name)
    (work / "logs").mkdir()
    (work / "traces").mkdir()
    for rel, n in TRACES.items():                       # the newest lines of each trace, read-only evidence
        try:
            lines = (HERE / rel).read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
        except OSError:
            continue
        (work / "traces" / Path(rel).name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def area_digest():
    # 11/5: the prompt named one area (the forum, then buyer surplus) and the engineer read only that; it also had no
    # counts of its own. digest_r3 counts every area and ranks them by the points they lose
    try:
        return digest_r3.for_prompt(HERE)
    except Exception as e:
        return f"(the digest failed: {type(e).__name__})"


def engineer_prompt():
    now = time.time()
    windows = "\n".join(f"- {time.strftime('%H:%M', time.localtime(now - h * 3600))}-"
                        f"{time.strftime('%H:%M', time.localtime(now - (h - 1) * 3600))}: "
                        f"{json.dumps(metrics_r3.window(now - h * 3600, now - (h - 1) * 3600))}" for h in (3, 2, 1))
    ledger = "\n".join(f"- [{x.get('source')}] {str(x.get('change'))[:140]} | metric {x.get('metric', '-')}, "
                       f"expected {x.get('expected', '-')} | {str(x.get('after') or 'not judged yet')[:140]}"
                       for x in jl(CHANGES)[-12:]) or "(none)"
    # the supervisor's notes reached only the tuning team; on 11/5 the finding that orders of 300k or more give half
    # our surplus had no way into the hypotheses
    try:
        advice = json.loads(ADVICE.read_text(encoding="utf-8")).get("notes") or []
    except (OSError, ValueError, AttributeError):
        advice = []
    ideas = [i for s in jl(STRATEGIES)[-3:] for i in (s.get("code_ideas") or []) if isinstance(i, str)]
    return ENGINEER.format(gap=metrics_r3.gap_text(), metrics=", ".join(metrics_r3.METRICS), windows=windows,
                           ledger=ledger, ideas="\n".join(f"- {i[:300]}" for i in ideas[-6:]) or "(none)",
                           advice="\n".join(f"- {n.get('text', '')[:900]}" for n in advice[-3:]) or "(none)",
                           allowed=", ".join(sorted(ALLOWED)), digest=area_digest())


def build():
    # one code trial at a time: on 11/5 00:24 a new build took the A/B slot while 0a26016 still waited for its 150
    # orders an arm, so 0a26016 ran on every order from then on
    if any(r.get("source") == "meta (auto)" and not r.get("verdict") for r in jl(CHANGES)):
        return
    day = [a for a in jl(ATTEMPTS) if time.time() - a.get("t", 0) < 86400]
    if len(day) >= MAX_PER_DAY or (day and time.time() - day[-1]["t"] < BUILD_EVERY):
        return
    work = WORK / time.strftime("%m%d-%H%M")
    if work.exists():
        return
    copy_folder(work)
    t0 = time.time()
    log("engineer reading the code and traces")
    said = agent(engineer_prompt(), work, "Read,Glob,Grep")
    spec = last_json(said)
    row = {"t": time.time(), "secs": round(time.time() - t0), "work": str(work)}
    if not spec or spec.get("skip") or spec.get("metric") not in metrics_r3.METRICS or not spec.get("hypothesis"):
        row.update(key=f"engineer-{time.strftime('%m%d%H%M')}",
                   result=f"no hypothesis: {(spec or {}).get('skip') or said[-200:]}")
        append(ATTEMPTS, row)
        log(row["result"])
        return
    key = hashlib.sha1(spec["hypothesis"][:120].lower().encode()).hexdigest()[:12]
    row.update(key=key, idea=spec["hypothesis"][:400], spec=spec)
    log(f"hypothesis {key}: {spec['hypothesis'][:140]} (metric {spec['metric']}, expected {spec.get('expected')})")
    # the coder works in the copy; if it wrote to the live folder anyway, those files go back before the gate
    snap = {p.name: p.read_bytes() for p in HERE.glob("*.py")}
    said = agent(CODER.format(spec=json.dumps(spec, ensure_ascii=False, indent=1), allowed=", ".join(sorted(ALLOWED)),
                              py=PY, key=key), work, f"Read,Edit,Write,Glob,Grep,Bash({PY} test_*)")
    row["agent"] = said.splitlines()[-1][:300] if said else ""
    strayed = [n for n, b in snap.items() if (HERE / n).read_bytes() != b]
    for n in strayed:
        tmp = HERE / f".{n}.auto"
        tmp.write_bytes(snap[n])
        os.replace(tmp, HERE / n)
    changed, why = gate(work)
    if strayed:
        why = f"the agent wrote to the live folder ({strayed}); restored"
    if not why and os.environ.get("META_CODE_DRY") == "1":
        why = "dry run (META_CODE_DRY=1)"
    row["files"], row["secs"] = changed, round(time.time() - t0)
    if why:
        row["result"] = f"not deployed: {why}"
        append(ATTEMPTS, row)
        log(row["result"])
        return
    pending = json.loads(NUMBER_TRIALS.read_text(encoding="utf-8")) if NUMBER_TRIALS.exists() else []
    if pending and set(changed) & SHOP_FILES:
        # shop changes run one at a time: a shop number is being judged, so a change to the shop's files waits (its
        # hours would mix with the number's); the attempt is logged and the engineer may try again later
        row["result"] = "not deployed: a shop number verdict is pending; shop files wait for it"
        append(ATTEMPTS, row)
        log(row["result"])
        return
    baseline = metrics_r3.window(time.time() - 3600, time.time())
    flagged = any(f'code_ab_r3.on("{key}"' in (work / f).read_text(encoding="utf-8") for f in changed)
    if flagged:
        code_ab_r3.start(key)                       # half the orders from now, judged arm against arm
    deploy(changed, work)
    git("add", *changed)
    what = row["agent"].split("CHANGED:", 1)[-1].strip() if "CHANGED:" in row["agent"] else spec["hypothesis"]
    c = git("commit", "-q", "-m", f"week-08: [auto] {what[:120]}\n\nThe engineer's hypothesis ({spec.get('term')}): "
            f"{spec['hypothesis'][:300]}\nWhy: {str(spec.get('why'))[:400]}\nMetric {spec['metric']}, expected "
            f"{spec.get('expected')}; built by the coding agent, passed the gate (allowed files, no forbidden lines, "
            f"all suites).")
    commit = git("rev-parse", "--short", "HEAD").stdout.strip() if c.returncode == 0 else "uncommitted"
    row["result"] = f"deployed {commit}"
    append(ATTEMPTS, row)
    append(CHANGES, {"t": time.time(), "commit": commit, "source": "meta (auto)", "change": what[:300],
                     "evidence": str(spec.get("why"))[:300], "after": "", "files": changed, "metric": spec["metric"],
                     "expected": spec.get("expected"), "term": spec.get("term"), "baseline": baseline,
                     "ab_key": key if flagged else None})
    log(f"deployed {commit}: {what[:120]} ({', '.join(changed)})")


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - LOCK.stat().st_mtime < 2 * AGENT_TIMEOUT + 600:
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
