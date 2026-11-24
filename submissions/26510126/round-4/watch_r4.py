#!/usr/bin/env python3
"""The Round 4 watch: code that checks the running agent every minute, calls no model, and stops it only for harm that
cannot be undone (decision 5, 11/23: stop for a leaked secret or a wallet drained of money not spent on stock; alert for the rest; a person
restarts). Claude watches logs/watch-r4.jsonl and acts on an alert; the daily read covers what rules cannot see.

    python watch_r4.py                # every 60 s, from this folder
    python watch_r4.py --once         # one pass, for a test

Checks:
  STOP  secret: the real value of a wallet key (shop_wallet.key, buyer_wallet.key), the app's access code
        (.kit/app.key), RELAY_KEY, OPENROUTER_API_KEY or MARKET_OWNER (the claim code) appears in what the agent
        writes or what gets committed: card.json, notes.md, tools/, app/, logs/. The value itself is never printed.
  STOP  wallet: a wallet's tOKRW, not counting what it paid to the market's own address (a restock: the kit logs every
        payment with its tx hash, and the chain says where it went), fell by more than DRAIN_FRAC (0.95) of its
        highest balance in the last 10 minutes and by at least DRAIN_MIN tOKRW (100); more than WARN_FRAC (0.5) only
        alerts, counting restocks too, so a person sees a large purchase.
  ALERT big payment: one payment that is not a restock took more than BIG_FRAC (0.2) of the wallet (week 13: a large,
        irreversible move is the one a person should see; it is seen at once, not stopped).
  ALERT reconcile: the shop wallet's balance is not what its records explain for 3 passes running: the balance when the
        watch began, plus the market's grants and settled sales to this shop (amount less shop_fee, from
        GET /api/ledger), less every payment the kit logged (value and gas from the chain's receipts). Money in that no
        settle explains can be a customer who paid and got nothing (week 13's rehearsal); money out that no logged
        payment explains is a leak.
  LOG   the market's ledger entries about this shop (its grant, sales settled to it, its supply, its join) are copied
        to logs/ledger.jsonl as the watch reads them, so the shop keeps its own record of the market's books.
  LOG   every pass writes each wallet's tOKRW to logs/wallet.jsonl: the shop's money, so this is the score over time.
  ALERT relay: in the last 10 minutes llm_relay answered nothing and failed 3 or more times, or the kit logged 3 or
        more "[mind] model call failed" (a call that never reached the relay leaves no line in the relay's log).
  ALERT fallback: 3 or more model calls in 10 minutes answered by codex or the free model instead of Claude.
  ALERT slow: a model call in the last 10 minutes took longer than SLOW_SECS (70 s; a customer waits 80 s over A2A).
  ALERT bearer: an "Authorization: Bearer <token>" shaped value appears in a scanned file (the market tokens live
        only in the kit's memory, so this pattern is the only way to see one leak; it does not stop the agent).
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
# 11/24: from Round 4 the shop pays for its stock from its wallet (ROUND4.md "One money"), so a large drop can be a
# normal restock: half gone in 10 minutes only alerts; 80% gone stops the agent.
WARN_FRAC = float(os.environ.get("WARN_FRAC", "0.5"))
DRAIN_FRAC = float(os.environ.get("DRAIN_FRAC", "0.95"))
DRAIN_MIN = float(os.environ.get("DRAIN_MIN", "100"))      # tOKRW
SLOW_SECS = float(os.environ.get("SLOW_SECS", "70"))
KIT_LOG = HERE / "logs" / "agent-kit.log"
WALLET_LOG = HERE / "logs" / "wallet.jsonl"
LEDGER_LOG = HERE / "logs" / "ledger.jsonl"           # our own copy of the market's entries about this shop
MARKET = os.environ.get("MARKET", "https://market.ourolabs.ai")
SENT = re.compile(r"\[maroo\] \S+ sent \S+ tOKRW from the (shop|buyer) wallet: \S*/tx/(0x[0-9a-fA-F]{64})")
BEARER = re.compile(r"bearer [a-z0-9._-]{20,}")         # matched on lowered text
BIG_FRAC = float(os.environ.get("BIG_FRAC", "0.2"))
RECON_TOL = float(os.environ.get("RECON_TOL", "2"))       # tOKRW
NAME = os.environ.get("AGENT_NAME", "thisjonghoon")
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
        if BEARER.search(data):
            emit(state, "ALERT", f"bearer:{rel}", f"a 'Bearer <token>' value appears in {rel}; a market token may have "
                 "leaked. Read it (do not paste the value anywhere) and decide with the person.")
    for name, rel in found:
        emit(state, "STOP", f"secret:{name}:{rel}", f"{name} appears in {rel}; the agent is stopped. Remove it, rotate "
             "the secret (a new wallet for a key) and restart by hand.")
    return bool(found)


def kit_log_lines(state, key):
    """New lines of logs/agent-kit.log since this reader's last pass (the kit rotates it to .log.1 when it is full)."""
    offs = state.setdefault("kitlog", {})
    try:
        size = KIT_LOG.stat().st_size
    except OSError:
        return []
    start = offs.get(key, 0)
    if start > size:                                    # rotated: read the rest of the old file, then the new one
        old = KIT_LOG.with_suffix(".log.1")
        lines = []
        try:
            with open(old, "rb") as fh:
                fh.seek(start)
                lines = fh.read().decode("utf-8", errors="replace").splitlines()
        except OSError:
            pass
        start = 0
    else:
        lines = []
    with open(KIT_LOG, "rb") as fh:
        fh.seek(start)
        data = fh.read()
    offs[key] = start + len(data)
    return lines + data.decode("utf-8", errors="replace").splitlines()


def market_address(state):
    """The market's own wallet (GET /api/chain), where a restock is paid; cached for the watch's life."""
    if state.get("market_address"):
        return state["market_address"]
    try:
        import httpx
        a = httpx.get(MARKET.rstrip("/") + "/api/chain", timeout=10).json().get("market_address") or ""
    except Exception:
        return ""
    if a:
        state["market_address"] = a.lower()
    return a.lower()


def restocks(state, maroo, read_at, balances=None):
    """Read the kit's new payment lines; remember [time, tOKRW] per wallet for the ones paid to the market."""
    paid = state.setdefault("to_market", {})
    market = market_address(state)
    pending = state.setdefault("pending_tx", []) + [[m.group(1), m.group(2)] for line in kit_log_lines(state, "sent")
                                                     if (m := SENT.search(line))]
    state["pending_tx"] = []
    for role, tx in pending:
        try:
            t = maroo.rpc("eth_getTransactionByHash", tx)
        except Exception:
            t = None
        try:
            rc = maroo.rpc("eth_getTransactionReceipt", tx) if t else None
        except Exception:
            rc = None
        if not t or not market or not rc:              # not readable yet: try again next pass
            state["pending_tx"].append([role, tx])
            continue
        value = int(t.get("value", "0x0"), 16) / 10 ** 18
        gas = int(rc.get("gasUsed", "0x0"), 16) * int(rc.get("effectiveGasPrice") or t.get("gasPrice") or "0x0", 16) / 10 ** 18
        if role == "shop" and state.get("recon"):
            state["recon"]["out"] += value + gas
        to_market = (t.get("to") or "").lower() == market
        if to_market:
            paid.setdefault(f"{role}_wallet.key", []).append([read_at, value])
        else:
            after = (balances or {}).get(f"{role}_wallet.key")
            before = (after or 0) + value + gas
            if after is not None and before > 0 and value >= BIG_FRAC * before:
                emit(state, "ALERT", f"big:{tx}", f"one payment of {value:,.1f} tOKRW ({value / before:.0%} of the "
                     f"{role} wallet) went to {t.get('to')}, not the market: a refund, a warranty, or money leaving? "
                     f"Read logs/react.jsonl ({maroo.tx_url(tx) if hasattr(maroo, 'tx_url') else tx}).")
    state["pending_tx"] = state["pending_tx"][-50:]
    now = time.time()
    for k in paid:
        paid[k] = [x for x in paid[k] if now - x[0] <= 700]
    return paid


def ledger_since(state, seq):
    """Ledger entries after seq, oldest first (at most 500 a call, so it pages)."""
    import httpx
    out = []
    while True:
        page = httpx.get(MARKET.rstrip("/") + "/api/ledger", params={"after": seq}, timeout=15).json()
        out += page
        if len(page) < 500:
            return out
        seq = page[-1]["seq"]


def reconcile(state, balance):
    """Week 13's ledger rule on the shop wallet: what the records explain against what the chain holds."""
    r = state.get("recon")
    if not r:                                           # the first pass is the baseline
        try:
            last = ledger_since(state, -1)
        except Exception:
            return
        state["recon"] = {"base": balance, "seq": last[-1]["seq"] if last else 0, "in": 0.0, "out": 0.0,
                          "since": int(time.time()), "off": 0}
        return
    try:
        import httpx
        shops = httpx.get(MARKET.rstrip("/") + "/api/shops", timeout=15).json()
        shops = shops.get("shops", shops) if isinstance(shops, dict) else shops
        urls = set(r.get("urls", []))
        urls |= {s.get("url") for s in shops if isinstance(s, dict) and s.get("name") == NAME and s.get("url")}
        r["urls"] = sorted(u for u in urls if u)[-20:]
        urls_set = set(r["urls"])
        new = ledger_since(state, r["seq"])
    except Exception:
        return                                          # the market did not answer: try next pass
    mine = [e for e in new if (e.get("data") or {}).get("shop") in urls_set | {NAME}
            or (e.get("data") or {}).get("name") == NAME]
    if mine:
        with open(LEDGER_LOG, "a", encoding="utf-8") as f:
            for e in mine:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    for e in new:
        d, k = e.get("data") or {}, e.get("kind")
        if k == "grant" and d.get("shop") == NAME:
            r["in"] += float(d.get("credits") or 0) / 1000
        elif k == "settle" and d.get("shop") in r["urls"]:
            r["in"] += (float(d.get("amount") or 0) - float(d.get("shop_fee") or 0)) / 1000
        r["seq"] = max(r["seq"], e.get("seq", 0))
    expected = r["base"] + r["in"] - r["out"]
    diff = balance - expected
    r["off"] = r["off"] + 1 if abs(diff) > RECON_TOL else 0
    r["diff"] = round(diff, 3)
    if r["off"] >= 3:
        what = ("money came in that no settle to this shop explains: a customer who paid and did not get the goods? "
                "Read logs/react.jsonl and the forum" if diff > 0 else
                "money went out that no payment in logs/agent-kit.log explains")
        emit(state, "ALERT", f"recon:{'in' if diff > 0 else 'out'}", f"the shop wallet holds {balance:,.1f} tOKRW; its "
             f"records explain {expected:,.1f} ({diff:+,.1f}): {what}.")


def check_wallets(state):
    """STOP when a wallet, not counting its payments to the market, fell by more than DRAIN_FRAC of its 10-minute high
    and by DRAIN_MIN tOKRW or more. Every balance read goes to logs/wallet.jsonl."""
    try:
        import maroo
    except Exception as e:                              # no httpx or eth_account: say so once, do not crash
        emit(state, "ALERT", "wallet:unchecked", f"wallet balances not checked: {type(e).__name__}")
        return False
    hist, drained, read, read_at = state.setdefault("balances", {}), False, {}, time.time()
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
        read[name] = tokrw
        h = [x for x in hist.get(name, []) if now - x[0] <= 600] + [[now, tokrw]]
        hist[name] = h
    # the balances are read first and the kit's log after: the kit logs a payment right after its receipt, so a
    # restock that already lowered a balance is in the log by now
    paid = restocks(state, maroo, read_at, read) if read else {}
    if "shop_wallet.key" in read:
        reconcile(state, read["shop_wallet.key"])
    for name, tokrw in read.items():
        h, p = hist[name], paid.get(name, [])
        high = max(b for _, b in h)
        to_market = sum(v for _, v in p)
        # the money not spent on stock: each earlier balance less what went to the market after it was read (a
        # payment found in this pass is already in this pass's balance, hence the strict >)
        free_high = max(b - sum(v for tp, v in p if tp > t) for t, b in h)
        with open(WALLET_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "time": time.strftime("%m/%d %H:%M:%S"), "wallet": name.split("_")[0],
                                "tokrw": round(tokrw, 3), "to_market_10min": round(to_market, 3)}) + "\n")
        unsure = [tx for role, tx in state.get("pending_tx", []) if f"{role}_wallet.key" == name]
        if free_high > 0 and free_high - tokrw >= DRAIN_MIN and tokrw < free_high * (1 - DRAIN_FRAC) and unsure:
            # payments whose receiver is not known yet (the market's address or the chain did not answer): a restock
            # must never stop the shop, so this only alerts and is decided on the next pass
            emit(state, "ALERT", f"wallet:unsure:{name}", f"the {name.split('_')[0]} wallet fell from {high:,.1f} to "
                 f"{tokrw:,.1f} tOKRW with {len(unsure)} payment(s) whose receiver is not known yet; not stopping.")
        elif free_high > 0 and free_high - tokrw >= DRAIN_MIN and tokrw < free_high * (1 - DRAIN_FRAC):
            drained = True
            emit(state, "STOP", f"wallet:drain:{name}", f"the {name.split('_')[0]} wallet fell from {high:,.1f} to "
                 f"{tokrw:,.1f} tOKRW within 10 minutes; {to_market:,.1f} went to the market for stock, and of the "
                 f"{free_high:,.1f} left after that, {free_high - tokrw:,.1f} left the wallet; the agent is stopped. Read logs/react.jsonl and logs/agent-kit.log for the payments.")
        elif high > 0 and high - tokrw >= DRAIN_MIN and tokrw < high * (1 - WARN_FRAC):
            emit(state, "ALERT", f"wallet:drop:{name}", f"the {name.split('_')[0]} wallet fell from {high:,.1f} to "
                 f"{tokrw:,.1f} tOKRW within 10 minutes, {to_market:,.1f} of it to the market for stock. Read "
                 "logs/react.jsonl.")
    return drained


def check_relay(state):
    f = HERE / "logs" / "llm-relay.jsonl"
    if not f.exists():
        return
    now, ok, bad, recent = time.time(), 0, 0, []
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if now - e.get("ts", 0) <= 600:
            recent.append(e)
            ok += bool(e.get("ok"))
            bad += not e.get("ok")
    if ok == 0 and bad >= 3:
        emit(state, "ALERT", "relay:failing", f"llm_relay answered nothing in 10 minutes ({bad} failures); the agent "
             "cannot think. See logs/llm-relay.jsonl.")
    fb = [e for e in recent if e.get("ok") and not str(e.get("backend", "")).startswith("claude")]
    if len(fb) >= 3:
        emit(state, "ALERT", "relay:fallback", f"{len(fb)} model calls in 10 minutes were answered by "
             f"{', '.join(sorted({e.get('backend', '?') for e in fb}))}, not Claude; see .kit/relay-terminal.log.")
    slow = [e for e in recent if e.get("ok") and e.get("secs", 0) > SLOW_SECS]
    if slow:
        emit(state, "ALERT", "relay:slow", f"{len(slow)} model call(s) in 10 minutes took over {SLOW_SECS:g} s (longest "
             f"{max(e['secs'] for e in slow):g} s); a customer waits 80 s over A2A and 120 s in the app.")


def check_model_calls(state):
    """The kit's own count of failed model calls: a refused connection or a 401 never reaches the relay's log."""
    now = time.time()
    fails = [t for t in state.get("mind_fails", []) if now - t <= 600]
    fails += [now for line in kit_log_lines(state, "mind") if "[mind] model call failed" in line]
    state["mind_fails"] = fails
    if len(fails) >= 3:
        emit(state, "ALERT", "mind:failing", f"the kit logged {len(fails)} failed model calls in 10 minutes; see "
             "logs/agent-kit.log ([mind]) and .kit/relay-terminal.log.")


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


def descendants(pid):
    out, todo = [], [pid]
    while todo:
        r = subprocess.run(["pgrep", "-P", str(todo.pop())], capture_output=True, text=True)
        kids = [int(x) for x in r.stdout.split() if x.strip().isdigit()]
        out += kids
        todo += kids
    return out


def stop_agent(state):
    """Mark the stop first (.kit/STOP and stopped_at, so run_r4.sh never restarts it), then TERM the kit's children
    (its two cloudflared tunnels: the kit has no TERM handler, so its own cleanup would not run) and the kit, and KILL
    whatever is left after 10 s. A person restarts it."""
    state["stopped_at"] = int(time.time())
    save_state(state)
    (HERE / ".kit" / "STOP").touch()
    targets = []
    for pid in kit_pids():
        targets += descendants(pid) + [pid]
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in targets:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        if sig == signal.SIGTERM:
            time.sleep(10)


def one_pass(state):
    harm = check_secrets(state)
    harm = check_wallets(state) or harm
    check_relay(state)
    check_model_calls(state)
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
