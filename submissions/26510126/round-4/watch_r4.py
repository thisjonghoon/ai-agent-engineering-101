#!/usr/bin/env python3
"""The Round 4 watch: code that checks the running agent every minute, calls no model, and stops it only for harm that
cannot be undone (decision 5, 11/23: stop for a leaked secret or a draining wallet; alert for the rest; a person
restarts). Claude watches logs/watch-r4.jsonl and acts on an alert; the daily read covers what rules cannot see.

    python watch_r4.py                # every 60 s, from this folder
    python watch_r4.py --once         # one pass, for a test

Checks:
  STOP  secret: the real value of a wallet key (shop_wallet.key, buyer_wallet.key), the app's access code
        (.kit/app.key), RELAY_KEY, OPENROUTER_API_KEY or MARKET_OWNER (the claim code) appears in what the agent
        writes or what gets committed: card.json, notes.md, tools/, app/, logs/. The value itself is never printed.
  STOP  wallet: a wallet's tOKRW fell by more than DRAIN_FRAC (0.5) of its highest balance in the last 10 minutes and
        by at least DRAIN_MIN tOKRW (100).
  ALERT relay: in the last 10 minutes llm_relay answered nothing and failed 3 or more times.
  ALERT process: the kit (agent_kit.py run) or the relay is not running.
Not checked yet (needs the market's real logs, after Round 4 opens): false claims, a fall in credits per hour,
repeated complaints. The market tokens live only in the kit's memory, so they cannot be matched by value; a JWT pattern
would also match the checkout_jwt the shop hands to customers, so it is not used.
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "round4"))
OUT = HERE / "logs" / "watch-r4.jsonl"
STATE = HERE / ".kit" / "watch-state.json"         # .kit/ is git-ignored
DRAIN_FRAC = float(os.environ.get("DRAIN_FRAC", "0.5"))
DRAIN_MIN = float(os.environ.get("DRAIN_MIN", "100"))      # tOKRW
REPEAT = 30 * 60                                        # the same alert at most once in 30 minutes
SCAN = ["card.json", "notes.md", "tools", "app", "logs"]


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(s):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(s), encoding="utf-8")


def emit(state, level, key, text):
    """One line in logs/watch-r4.jsonl, unless the same key was written in the last 30 minutes."""
    seen = state.setdefault("sent", {})
    if time.time() - seen.get(key, 0) < REPEAT:
        return
    seen[key] = time.time()
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": int(time.time()), "time": time.strftime("%m/%d %H:%M:%S"), "level": level,
                            "what": key.split(":")[0], "text": text}, ensure_ascii=False) + "\n")
    print(f"[watch] {level}: {text}", flush=True)


def secrets():
    """{name: value} for every secret this computer holds for the agent; values stay in this process."""
    out = {}
    for name in ("shop_wallet.key", "buyer_wallet.key"):
        p = HERE / name
        if p.exists():
            k = p.read_text(encoding="utf-8").strip().lower()
            k = k[2:] if k.startswith("0x") else k
            if len(k) >= 32:
                out[name] = k
    p = HERE / ".kit" / "app.key"
    if p.exists() and len(p.read_text(encoding="utf-8").strip()) >= 8:
        out["app access code"] = p.read_text(encoding="utf-8").strip()
    for env in ("RELAY_KEY", "OPENROUTER_API_KEY", "MARKET_OWNER"):
        if len(os.environ.get(env, "")) >= 8:
            out[env] = os.environ[env]
    return out


def files_to_scan():
    for name in SCAN:
        p = HERE / name
        if p.is_file():
            yield p
        elif p.is_dir():
            yield from (f for f in p.rglob("*") if f.is_file() and f != OUT)   # old tool versions included


def check_secrets(state):
    """STOP when a secret's value appears in a scanned file. Append-only logs are read from where the last pass ended."""
    found, sec = [], secrets()
    offsets = state.setdefault("offsets", {})
    for f in files_to_scan():
        rel = str(f.relative_to(HERE))
        try:
            size = f.stat().st_size
            start = offsets.get(rel, 0) if f.suffix in (".jsonl", ".log") and offsets.get(rel, 0) <= size else 0
            with open(f, "rb") as fh:
                fh.seek(max(0, start - 200))           # overlap, so a value cut across two passes is still seen
                data = fh.read().decode("utf-8", errors="replace").lower()
            offsets[rel] = size
        except OSError:
            continue
        for name, value in sec.items():
            if value.lower() in data:
                found.append((name, rel))
    for name, rel in found:
        emit(state, "STOP", f"secret:{name}:{rel}", f"{name} appears in {rel}; the agent is stopped. Remove it, rotate "
             "the secret (a new wallet for a key) and restart by hand.")
    return bool(found)


def check_wallets(state):
    """STOP when a wallet fell by more than DRAIN_FRAC of its 10-minute high and by DRAIN_MIN tOKRW or more."""
    try:
        import maroo
    except Exception as e:                              # no httpx or eth_account: say so once, do not crash
        emit(state, "ALERT", "wallet:unchecked", f"wallet balances not checked: {type(e).__name__}")
        return False
    hist, drained = state.setdefault("balances", {}), False
    for name in ("shop_wallet.key", "buyer_wallet.key"):
        p = HERE / name
        if not p.exists():
            continue
        try:
            w = maroo.Wallet.from_hex(p.read_text(encoding="utf-8"))
            tokrw = maroo.balance(w.address) / 10 ** 18
        except Exception as e:
            emit(state, "ALERT", f"wallet:rpc:{name}", f"balance of {name.split('_')[0]} wallet not read: "
                 f"{type(e).__name__}: {str(e)[:120]}")
            continue
        now = time.time()
        h = [x for x in hist.get(name, []) if now - x[0] <= 600] + [[now, tokrw]]
        hist[name] = h
        high = max(b for _, b in h)
        if high > 0 and high - tokrw >= DRAIN_MIN and tokrw < high * (1 - DRAIN_FRAC):
            drained = True
            emit(state, "STOP", f"wallet:drain:{name}", f"the {name.split('_')[0]} wallet fell from {high:,.1f} to "
                 f"{tokrw:,.1f} tOKRW within 10 minutes; the agent is stopped. Read logs/react.jsonl for the payments.")
    return drained


def check_relay(state):
    f = HERE / "logs" / "llm-relay.jsonl"
    if not f.exists():
        return
    now, ok, bad = time.time(), 0, 0
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if now - e.get("ts", 0) <= 600:
            ok += bool(e.get("ok"))
            bad += not e.get("ok")
    if ok == 0 and bad >= 3:
        emit(state, "ALERT", "relay:failing", f"llm_relay answered nothing in 10 minutes ({bad} failures); the agent "
             "cannot think. See logs/llm-relay.jsonl.")


def pids(pattern):
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split() if x.strip().isdigit() and int(x) != os.getpid()]


def kit_pids():
    return pids(f"agent_kit.py run --dir .*{re.escape(HERE.name)}")


def check_processes(state):
    if not kit_pids():
        emit(state, "ALERT", "process:kit", "the agent (agent_kit.py run) is not running")
    if not pids("llm_relay.py"):
        emit(state, "ALERT", "process:relay", "llm_relay.py is not running")


def stop_agent(state):
    """Ctrl-C to the kit (it closes its endpoint and app), then TERM after 10 s. A person restarts it."""
    for pid in kit_pids():
        try:
            os.kill(pid, signal.SIGINT)
        except OSError:
            pass
    time.sleep(10)
    for pid in kit_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    state["stopped_at"] = int(time.time())


def one_pass(state):
    harm = check_secrets(state)
    harm = check_wallets(state) or harm
    check_relay(state)
    if harm and kit_pids():
        stop_agent(state)
    elif state.get("stopped_at") and kit_pids():
        state.pop("stopped_at")                         # a person restarted it: watch the processes again
    if not state.get("stopped_at"):
        check_processes(state)
    state["last_pass"] = int(time.time())
    save_state(state)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--every", type=int, default=60)
    a = ap.parse_args()
    print(f"[watch] {HERE}, every {a.every} s, alerts to {OUT}", flush=True)
    while True:
        state = load_state()
        try:
            one_pass(state)
        except Exception as e:                          # the watch must not die on one bad pass
            emit(state, "ALERT", "watch:error", f"a watch pass failed: {type(e).__name__}: {str(e)[:160]}")
            save_state(state)
        if a.once:
            return
        time.sleep(a.every)


if __name__ == "__main__":
    main()
