"""Round 3 meta-harness: Claude haiku sets the shop's strategy (prices, stock) from how the last versions did.

    python meta_r3.py            # every 15 min, forever
    python meta_r3.py --once     # one decision, then exit

Each cycle:
  1. Measure the version that just ran, from files the kit and the seller already write: .market/inventory.json
     (balance, profit, stock at cost, units by kind and age) and the seller's OPEN/DEAL/WALK lines in
     logs/market-kit.log (visits, deals, walk-aways, price as a share of list, margin over cost).
  2. Ask the harness for the next strategy_r3.json, showing it the bounds, the current numbers and the last 30
     versions with their outcomes (logs/strategies_r3.jsonl, nothing re-measured).
  3. Code guards the answer: every number is clamped to its bounds and to a step from the current value, the floor
     stays at or above cost plus 2%, and an unusable answer keeps the current strategy.
seller_r3.py and restock_r3.py read strategy_r3.json on every request and run, so a change applies at once.
"""
import argparse
import asyncio
import json
import re
import time
from pathlib import Path

import harness

HERE = Path(__file__).resolve().parent
MD = HERE / ".market"
STRATEGY = HERE / "strategy_r3.json"
HISTORY = HERE / "logs" / "strategies_r3.jsonl"
KIT_LOG = HERE / "logs" / "market-kit.log"
EVERY = 15 * 60
# key: (low, high, largest change per cycle)
BOUNDS = {"ask_frac": (0.70, 1.00, 0.05), "floor_frac": (0.45, 0.95, 0.05), "min_margin": (0.02, 0.40, 0.04),
          "step": (0.2, 0.7, 0.1), "clear_hours": (2, 24, 4), "clear_frac": (0.3, 1.0, 0.1),
          "warranty_hours": (0, 6, 6), "max_turns": (3, 8, 1),
          "reserve_cash": (1_000_000, 3_000_000, 250_000), "stock_value": (500_000, 3_500_000, 500_000),
          "max_list": (30_000, 400_000, 50_000), "min_shelf_hours": (24, 720, 48), "depth": (1, 6, 1)}
SELLER_LINE = re.compile(r"(OPEN|DEAL|WALK) \S+ (\S+)(?: at (\d+) \(cost (\d+), list (\d+))?")

PROMPT = """You set the strategy of an online shop in a market of AI buyers. Profit is the shop's balance minus its
starting capital at the end of the round, so stock that never sells is a loss; the shop is also ranked by revenue
and by stars. The shop buys units (cost is 25-75% of list price, set by a random grade) and sells them by haggling.
Food loses its grade as it ages and is thrown away at its date; goods pay 1% of cost a day in storage and some break
after the sale (a warranty refunds the whole price from the shop). Buyers gain when they pay less than list price.

The strategy (numbers only; bounds are [low, high], max change per cycle in parentheses):
{bounds}
ask = list x ask_frac. floor = max(cost x (1 + min_margin), list x floor_frac). Each counter moves `step` of the way
to the buyer's offer. Food with under clear_hours left (or grade C) may go down to cost x clear_frac.
Restock keeps at most stock_value of stock at cost and never spends below reserve_cash; it skips goods listed above
max_list and food that keeps less than min_shelf_hours, and holds up to `depth` units where things sell.

Now: {now}

Last versions, oldest first (each with how it did while it ran):
{history}

Answer with JSON only: {{"strategy": {{...every key...}}, "reason": "<one sentence>"}}"""


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def current():
    import seller_r3, restock_r3                         # their defaults are the starting point
    s = dict(seller_r3.DEFAULTS, **{k: v for k, v in restock_r3.DEFAULTS.items() if k in BOUNDS})
    s.update({k: v for k, v in read_json(STRATEGY, {}).items() if k in BOUNDS})
    return s


def seller_lines(since):
    """OPEN/DEAL/WALK counts and deal prices from the kit log since `since` (the log's own HH:MM:SS stamps)."""
    out = {"opens": 0, "deals": 0, "walks": 0, "price_list": [], "margin": []}
    try:
        lines = KIT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-20000:]
    except OSError:
        lines = []
    day = time.strftime("%Y-%m-%d")
    for line in lines:
        m = SELLER_LINE.search(line)
        t = re.match(r"(\d\d:\d\d:\d\d)", line)
        if not m or not t:
            continue
        ts = time.mktime(time.strptime(f"{day} {t.group(1)}", "%Y-%m-%d %H:%M:%S"))
        if ts < since or ts > time.time() + 60:
            continue
        kind = m.group(1)
        out[{"OPEN": "opens", "DEAL": "deals", "WALK": "walks"}[kind]] += 1
        if kind == "DEAL":
            price, cost, lp = int(m.group(3)), int(m.group(4)), int(m.group(5))
            out["price_list"].append(price / lp)
            out["margin"].append((price - cost) / cost if cost else 0)
    for k in ("price_list", "margin"):
        v = out[k]
        out[k] = round(sum(v) / len(v), 3) if v else None
    return out


def snapshot(since):
    inv = read_json(MD / "inventory.json", {})
    units = inv.get("units", [])
    now = time.time()
    snap = {"round": inv.get("round"), "balance": inv.get("balance"),
            "profit": (inv.get("balance") or 0) - (inv.get("start") or 0) - (inv.get("injected") or 0),
            "stock_at_cost": sum(u["cost"] for u in units), "units": len(units),
            "food_units": sum(u["kind"] == "food" for u in units),
            "older_than_24h": sum(now - u["supplied_at"] > 86400 for u in units),
            "expired": sum(u["grade"] == "expired" for u in units),
            "minutes": round((now - since) / 60)}
    snap.update(seller_lines(since))
    return snap


def guard(new, cur):
    out = {}
    for k, (lo, hi, step) in BOUNDS.items():
        v = new.get(k, cur[k])
        if not isinstance(v, (int, float)):
            v = cur[k]
        v = min(max(v, cur[k] - step), cur[k] + step, hi)
        v = max(v, lo)
        out[k] = int(round(v)) if isinstance(lo, int) and isinstance(hi, int) else round(v, 3)
    if out["floor_frac"] > out["ask_frac"]:
        out["floor_frac"] = out["ask_frac"]
    return out


async def cycle():
    cur = current()
    hist = [json.loads(l) for l in HISTORY.read_text(encoding="utf-8").splitlines() if l.strip()] if HISTORY.exists() else []
    since = hist[-1]["time"] if hist else time.time() - EVERY
    now = snapshot(since)
    if (now.get("round") or 0) < 3:
        harness.log("META", f"round {now.get('round')}: no Round 3 stock yet, strategy unchanged")
        return
    bounds = "\n".join(f"  {k}: [{lo}, {hi}] ({st}), now {cur[k]}" for k, (lo, hi, st) in BOUNDS.items())
    # a version's outcome is the "before" stored with the decision after it (the last one's is `now`)
    after = [h["before"] for h in hist[1:]] + [now]
    shown = "\n".join(json.dumps({"strategy": h["strategy"], "after": a}, ensure_ascii=False)
                      for h, a in list(zip(hist, after))[-30:])
    ans = await harness.ask(PROMPT.format(bounds=bounds, now=json.dumps(now, ensure_ascii=False), history=shown or "(none)"))
    new = (ans or {}).get("strategy") if isinstance((ans or {}).get("strategy"), dict) else None
    s = guard(new or {}, cur)
    changed = {k: (cur[k], s[k]) for k in s if s[k] != cur[k]}
    STRATEGY.write_text(json.dumps(s, indent=1), encoding="utf-8")
    HISTORY.parent.mkdir(exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.time(), "strategy": s, "before": now, "reason": (ans or {}).get("reason"),
                            "harness_ok": new is not None}, ensure_ascii=False) + "\n")
    harness.log("META", f"{'kept' if not changed else 'changed ' + json.dumps(changed)}: {(ans or {}).get('reason')}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    once = ap.parse_args().once
    while True:
        try:
            await cycle()
        except Exception as e:                          # never stop the loop on one bad cycle
            harness.log("META", f"cycle failed: {type(e).__name__}: {e}")
        if once:
            return
        await asyncio.sleep(EVERY)


if __name__ == "__main__":
    asyncio.run(main())
