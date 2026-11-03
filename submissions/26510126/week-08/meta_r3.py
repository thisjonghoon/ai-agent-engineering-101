"""Round 3 meta-harness: Claude haiku sets the shop's strategy (prices, stock) from how the last versions did.

    python meta_r3.py            # every 15 min, forever
    python meta_r3.py --once     # one decision, then exit

Each cycle:
  1. Measure the version that just ran, from files the kit and the seller already write: .market/inventory.json
     (balance, profit, stock at cost, units by kind and age), the seller's OPEN/DEAL/WALK lines and the kit's
     "[acp] settled" lines in logs/market-kit.log (visits, receipts, settled sales and revenue, refused checkouts,
     walk-aways, price as a share of list, margin over cost), and the market's last settled deals (price as a
     share of list across all shops). A receipt that never settles earns nothing, so settled is what counts.
  2. Ask the harness for the next strategy_r3.json, showing it the bounds, the current numbers and the last 30
     versions with their outcomes (logs/strategies_r3.jsonl, nothing re-measured).
  3. Code guards the answer: every number is clamped to its bounds and to a step from the current value (so
     min_margin keeps the floor at cost plus 2% or more, except food near its date and the round's last hours, where
     the seller's clearance rules apply), and an unusable answer keeps the current strategy.
  4. A/B test (ab_r3.py): while an experiment runs, its numbers per arm are shown to the harness; once one arm is
     better with probability p_win after min_n negotiations each, code writes that value into the strategy and
     turns the experiment off (the harness does not pick the winner; it only sees the result).
seller_r3.py and restock_r3.py read strategy_r3.json on every request and run, so a change applies at once.
"""
import argparse
import asyncio
import json
import re
import time
from pathlib import Path

import ab_r3
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
          "warranty_hours": (0, 6, 2), "max_turns": (3, 8, 1),
          "reserve_cash": (700_000, 3_000_000, 250_000), "stock_value": (500_000, 4_300_000, 500_000),
          "max_list": (30_000, 400_000, 50_000), "min_shelf_hours": (24, 720, 48), "depth": (1, 6, 1),
          "endgame_hours": (12, 24, 6), "endgame_frac": (1.0, 1.2, 0.1), "final_hours": (2, 12, 2),
          "final_frac": (0.3, 1.0, 0.1), "ask_frac_food": (0.70, 1.00, 0.05), "floor_frac_food": (0.45, 0.95, 0.05),
          "fresh_premium": (0.0, 0.2, 0.05), "spread_low": (0.5, 0.9, 0.1), "spread_high": (1.1, 1.5, 0.1),
          "sku_depth": (1, 6, 1), "goods_frac": (0.1, 0.8, 0.1), "food_first": (0.0, 1.0, 0.25),
          "goods_age_days": (2, 10, 1), "aged_margin": (0.0, 0.2, 0.03), "window_depth": (1.0, 4.0, 0.5), "order_weight": (0.0, 3.0, 0.5)}
SETTLED = re.compile(r"\[acp\] settled .* at (\d+), ledger")         # our shop's sale the market settled
SETTLE_REFUSED = re.compile(r"\[acp\] (settle refused|checkout refused: (?:no |unit ))")  # shop side only
SELLER_LINE = re.compile(r"(OPEN|DEAL|WALK) \S+ (\S+)(?: at (\d+) \(cost (\d+), list (\d+))?")

PROMPT = """GOAL: the highest Players rank we can reach (shop ALL + buyer ALL), and above the instructor's own agent q00,
while staying honest: true grade claims, the market's certificate shown, no votes against others, no selling below
cost except to clear stock that would otherwise be lost. `players` in the numbers below shows our rank, q00's, and the
part with the most to gain; push the shop's part of that.

You set the strategy of an online shop in a market of AI buyers. Profit is the shop's balance minus its
starting capital at the end of the round, so stock that never sells is a loss; the shop is also ranked by revenue
and by stars. The shop buys units (cost is 25-75% of list price, set by a random grade) and sells them by haggling.
Food loses its grade as it ages and is thrown away at its date; goods pay 1% of cost a day in storage and some break
after the sale (a warranty refunds the whole price from the shop). Buyers gain when they pay less than list price.

The strategy (numbers only; bounds are [low, high], max change per cycle in parentheses):
{bounds}
ask = list x ask_frac (food: ask_frac_food, scaled up to +/- fresh_premium by shelf life left).
floor = max(cost x (1 + min_margin), list x floor_frac (food: floor_frac_food)). Each counter moves `step` of the way
to the buyer's offer. Food with under clear_hours left (or grade C) may go down to cost x clear_frac. In the last endgame_hours of the
round the floor drops to cost x endgame_frac, in the last final_hours to cost x final_frac (stock left at the end is lost).
Restock keeps at most stock_value of stock at cost and never spends below reserve_cash (code also keeps 700,000, and
1,000,000 while a warranty is on: below 500,000 a shop goes bankrupt and the 5,000,000 it gets comes off profit; more
stock means more chances to sell but also more food that can expire and goods that pay storage); it skips goods listed above
max_list and food that keeps less than min_shelf_hours, and holds up to `depth` units where things sell, plus a
cheaper and a dearer SKU (spread_low/spread_high x the category median) there, and up to sku_depth units of SKUs the
market keeps settling. Categories that buyers ask for on the forum come first. Food plans rank food_first higher and
goods at cost stay under goods_frac of stock_value (goods pay storage and may break; start with food, give goods more
room once they are seen to sell). Goods older than goods_age_days may sell down to cost x (1 + aged_margin).

Now ("deals" are signed receipts; only "settled" sales earn money, a receipt the buyer's kit refuses to pay earns
nothing; market_price_list_* is where all shops' settled prices sit as a share of list price): {now}

ab, when present, is an A/B test running inside the shop: each new negotiation of its kind draws one of two values
of `param` (arms), whatever the strategy says, and mean_reward is margin over list price per negotiation (0 for a lost
one). Code ends it and keeps the better value; until then a change to that number does not reach those negotiations.

The market's rules can change while the round runs; `rules` holds the values the market's files state now (the
bankruptcy line, storage per day, the supply window), and restock scales its depth up when its runs come less often.
Supply opens once every 20 minutes for 3 minutes: inside a window restock buys window_depth times its usual depth,
since stock has to last until the next window (more depth: fewer sales lost to an empty shelf, more food that may
expire and goods that pay storage).

The shop's rank (the midterm's score) is 0.5 x profit percentile + 0.3 x revenue percentile + 0.2 x stars percentile,
each among all shops on the board; `standing` shows ours. Percentiles reward being above the others, not the size of
the lead: once profit sits high, a little margin given up for more sales or better stars can raise the score more,
and a loss of profit percentile costs the most.

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
    out = {"opens": 0, "deals": 0, "walks": 0, "settled": 0, "revenue": 0, "settle_refused": 0,
           "price_list": [], "margin": []}
    try:
        lines = KIT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-20000:]
    except OSError:
        lines = []
    # HH:MM:SS has no date: read backwards from now and step back a day each time the clock jumps forward
    # (passing midnight), so yesterday's lines at the same clock time are not counted as today's (review, 11/2)
    day0, back, prev, keep = time.time(), 0, None, []
    for line in reversed(lines):
        t = re.match(r"(\d\d:\d\d:\d\d)", line)
        if not t:
            continue
        hms = t.group(1)
        if prev is not None and hms > prev and hms[:2] > "12" >= prev[:2]:
            back += 1
        prev = hms
        ts = time.mktime(time.strptime(time.strftime("%Y-%m-%d", time.localtime(day0 - back * 86400)) + " " + hms,
                                       "%Y-%m-%d %H:%M:%S"))
        if ts < since:
            break
        keep.append((ts, line))
    for ts, line in reversed(keep):
        if ts > time.time() + 60:
            continue
        s = SETTLED.search(line)
        if s:
            out["settled"] += 1
            out["revenue"] += int(s.group(1))
        if SETTLE_REFUSED.search(line):
            out["settle_refused"] += 1
        m = SELLER_LINE.search(line)
        if not m:
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


def market_prices():
    """The market's last settled deals: price as a share of list (median, quartiles) and how many, so the
    harness can see where other shops sell. One ledger page, no cache."""
    try:
        import httpx
        cat = read_json(MD / "catalog.json", {})
        page = httpx.get("https://market.ourolabs.ai/api/ledger", params={"after": -500}, timeout=8).json()
        rows = [(cat[e["data"]["item"]]["kind"], e["data"]["amount"] / cat[e["data"]["item"]]["list_price"]) for e in page
                if e.get("kind") == "settle" and e["data"].get("item") in cat and e["data"].get("amount")]
    except Exception:
        return {}
    out = {"market_settles": len(rows)}
    for kind in ("food", "goods"):                       # food and goods sell at different shares of list price
        r = sorted(x for k, x in rows if k == kind)
        if r:
            q = lambda f: round(r[min(len(r) - 1, int(f * len(r)))], 3)
            out[f"market_{kind}_price_list"] = {"n": len(r), "p25": q(0.25), "median": q(0.5), "p75": q(0.75)}
    return out


def percentile(x, xs):
    """Share of the values in xs at or below x (the board ranks each part as a percentile among all shops)."""
    xs = [v for v in xs if isinstance(v, (int, float))]
    return round(sum(v <= x for v in xs) / len(xs), 3) if xs and isinstance(x, (int, float)) else None


def standing():
    """Our shop's percentile on each ranked part (profit, revenue, stars) among all shops on the board, the weighted
    score the midterm uses (0.5 / 0.3 / 0.2), and where the other shops' stars sit, so the harness can trade a little
    margin for stars or revenue when that moves the score more."""
    try:
        import httpx
        board = httpx.get("https://market.ourolabs.ai/api/board", timeout=8).json()
        rows = board.get("shops") or []
    except Exception:
        return {}
    ours = next((r for r in rows if r.get("name") == "thisjonghoon"), None)
    if not ours or len(rows) < 2:
        return {}
    pct = {k: percentile(ours.get(k), [r.get(k) for r in rows]) for k in ("profit", "revenue", "stars")}
    if None in pct.values():
        return {"standing_parts": pct}
    stars = sorted(r["stars"] for r in rows if isinstance(r.get("stars"), (int, float)) and r.get("reviews"))
    q = lambda f: stars[min(len(stars) - 1, int(f * len(stars)))] if stars else None
    out = {"standing": {"shops": len(rows), "profit_pct": pct["profit"], "revenue_pct": pct["revenue"],
                        "stars_pct": pct["stars"], "score": round(0.5 * pct["profit"] + 0.3 * pct["revenue"] + 0.2 * pct["stars"], 3),
                        "our_stars": ours.get("stars"), "market_stars_p25_median_p75": [q(0.25), q(0.5), q(0.75)]}}
    try:
        import rank_r3                                   # Players rank and the gap to the instructor's q00
        out["players"] = rank_r3.standing(board)
    except Exception:
        pass
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
            # the market's rules as its own files state them now (the instructor changes them while the round runs)
            "rules": {k: inv.get(k) for k in ("bankrupt_line", "storage_per_day", "bankruptcies_left", "restock")},
            "minutes": round((now - since) / 60)}
    snap.update(seller_lines(since))
    snap.update(market_prices())
    snap.update(standing())
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
    exp = ab_r3.experiment()
    if exp:
        now["ab"] = ab_r3.summary(exp)
    if (now.get("round") or 0) < 3:
        harness.log("META", f"round {now.get('round')}: no Round 3 stock yet, strategy unchanged")
        return
    bounds = "\n".join(f"  {k}: [{lo}, {hi}] ({st}), now {cur[k]}" for k, (lo, hi, st) in BOUNDS.items())
    # a version's outcome is the "before" stored with the decision after it (the last one's is `now`)
    after = [h["before"] for h in hist[1:]] + [now]
    shown = "\n".join(json.dumps({"strategy": h["strategy"], "after": a}, ensure_ascii=False)
                      for h, a in list(zip(hist, after))[-30:])
    # our own measurements only (no other agent's text), 30 versions can pass the default cap: allow more
    ans = await harness.ask(PROMPT.format(bounds=bounds, now=json.dumps(now, ensure_ascii=False), history=shown or "(none)"),
                            max_chars=200_000)
    new = (ans or {}).get("strategy") if isinstance((ans or {}).get("strategy"), dict) else None
    s = guard(new or {}, cur)
    # receipts that never settle: the buyer's kit refused to pay (its accept policy: certificate, shelf life, grade,
    # warranty). We cannot see why from the shop, so when most of a busy window does not settle and we offer no
    # warranty, code tries a short one on grade-A goods; the harness sees the result next cycle and may undo it
    probe = None
    if (now.get("deals") or 0) >= 5 and (now.get("settled") or 0) < 0.6 * now["deals"] and s["warranty_hours"] == 0:
        s["warranty_hours"], probe = 2, f"{now['settled']} of {now['deals']} receipts settled: trying a 2 h warranty"
    ab_done = None
    win = ab_r3.winner(exp) if exp else None
    if win and exp["param"] in BOUNDS:
        lo, hi, _ = BOUNDS[exp["param"]]
        s[exp["param"]] = min(max(exp["arms"][win], lo), hi)     # the test's own evidence, not a step from now
        ab_done = dict(exp, on=False, result={"winner": win, "summary": now["ab"], "time": time.time()})
        ab_r3.EXPERIMENT.write_text(json.dumps(ab_done, ensure_ascii=False, indent=1), encoding="utf-8")
    changed = {k: (cur[k], s[k]) for k in s if s[k] != cur[k]}
    STRATEGY.write_text(json.dumps(s, indent=1), encoding="utf-8")
    HISTORY.parent.mkdir(exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.time(), "strategy": s, "before": now, "reason": (ans or {}).get("reason"),
                            "harness_ok": new is not None, "probe": probe,
                            "ab_result": ab_done and ab_done["result"]}, ensure_ascii=False) + "\n")
    harness.log("META", f"{'kept' if not changed else 'changed ' + json.dumps(changed)}: {(ans or {}).get('reason')}"
                + (f"; A/B {exp['id']} won by {win} ({exp['param']} = {exp['arms'][win]})" if ab_done else ""))


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
