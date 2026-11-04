"""Round 3 restock hook: what the shop buys next. The kit runs it every 60 s and buys what it prints.

    python restock_r3.py --state .market        # prints {"buy": [{"sku": ..., "qty": ...}, ...]}

Code only; the meta-harness (meta_r3.py) moves the numbers in strategy_r3.json. The idea:
  - Profit is the balance at the end, so stock is cash waiting to come back. Spend only down to `reserve_cash` and
    hold at most `stock_value` of stock at cost.
  - Be in many categories: a buyer only sees shops that hold something of the ordered category (shops.json offers),
    so one unit in each category is the first claim on the money. A unit's SKU is the one whose list price is
    closest to the category's median (orders take SKUs 0.5-1.5x a reference price), skipping goods above
    `max_list` and food that keeps less than `min_shelf_hours`.
  - Then depth where things sell: settled deals in the market's ledger (the market publishes no demand weights)
    and our own sales add to a category's score; a category with a score keeps up to `depth` units.
  - A cheaper and a dearer SKU (spread_low, spread_high x the median) in categories that sell, since an order only
    takes SKUs within 0.5-1.5x a reference price we cannot see.
  - The SKUs that settle again and again in the ledger, bought by themselves (up to sku_depth units).
  - "Wanted" posts on the forum (구합니다, looking for ...) that name one of our categories or SKUs raise that
    category for this run.
  - Food first (11/3, the instructor's hint: get a feel for the market with food). Goods pay 1% of cost a day while
    they wait and may break, food costs nothing to hold until its date; so goods at cost stay under `goods_frac` of
    `stock_value`, goods above `max_list` are skipped, and food plans rank `food_first` higher. The meta-harness
    can move all three once goods are seen to sell.
  - Supply windows (agent.md, 11/3 20:23): supply opens once every 20 minutes for 3 minutes, and inventory.json
    carries `restock` (open, opens_at, closes_at). Outside a window we print no lines (the kit would wait up to 90 s
    per line and stall), and inside one the depth is `window_depth` times larger, since what is bought must last
    until the next window. Lines that sell (depth, best sellers) rank before breadth.
  - Stop buying `stop_hours` before the round ends: unsold stock at the end is a loss.
The state between runs (last units seen, ledger position, scores) is in .market/restock_state.json.
"""
import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

import demand_r3

HERE = Path(__file__).resolve().parent
MARKET = "https://market.ourolabs.ai"
STRATEGY = Path(os.environ.get("STRATEGY_FILE") or HERE / "strategy_r3.json")   # tests: the defaults, not the live file
DEFAULTS = {"dear_first": 1.0, "reserve_cash": 1_500_000, "stock_value": 2_000_000, "max_list": 80_000, "min_shelf_hours": 96,
            "goods_frac": 0.35, "food_first": 0.5,
            "depth": 3, "half_life_hours": 12, "stop_hours": 36, "spread_low": 0.7, "spread_high": 1.3, "sku_depth": 3, "round_end": 1794927540,
            "window_depth": 2.0, "order_weight": 1.0, "surge_max": 1.15}    # 2026-11-17 23:59 KST
BANKRUPT_LINE = 500_000  # below this a shop may file, and the 5,000,000 it gets comes off profit
CASH_FLOOR = 700_000     # code's own floor under any reserve_cash the meta-harness sets: the line plus a cushion
CUSHION = CASH_FLOOR - BANKRUPT_LINE   # kept above inventory.json's bankrupt_line, which the market may change
BASE_GAP = 60            # seconds between restock runs the depths are tuned for (agent.md, 11/3: every 60 s)
WARRANTY_CUSHION = 300_000  # more while goods are sold with a warranty: a break refunds the whole price
EST_COST = 0.6          # expected cost as a share of list price before the grade is drawn (A 55-75, B 40-60, C 25-45)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def strategy():
    s = dict(DEFAULTS)
    s.update({k: v for k, v in read_json(STRATEGY, {}).items() if k in DEFAULTS and isinstance(v, (int, float))})
    return s


def ledger_settles(after):
    """New settle entries since `after` (at most a few pages), and the last seq seen."""
    out = []
    try:
        with httpx.Client(timeout=8) as c:
            params = {"after": after} if after else {"after": -500}
            for _ in range(4):
                page = c.get(f"{MARKET}/api/ledger", params=params).json()
                if not page:
                    break
                out += [e for e in page if e.get("kind") == "settle"]
                after = page[-1]["seq"]
                if len(page) < 500:
                    break
                params = {"after": after}
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    return out, after


US = "thisjonghoon"
WANT_CAP, WANT_LEN, WANT_CATS = 3, 1000, 3
WANT = re.compile(r"구합니다|구해요|구함|삽니다|찾습니다|찾아요|사고\s*싶|있나요|있으신|\bWTB\b|\bwant(?:ed)?\b|looking for|\bneed\b",
                  re.I)


def forum_wanted(md, demand, catalog, now, hours=6):
    """Categories that "wanted" posts of the last `hours` name (by category word, product name or SKU), with counts.
    Posts are other agents' text: only matched against our own category and SKU lists, never acted on otherwise.
    Unasked posts can also be noise or bait (a flood of "wanted" posts to make shops buy stock that will not sell), so
    a category counts each author once, at most WANT_CAP authors, a post longer than WANT_LEN characters or naming
    more than WANT_CATS categories is skipped, and our own posts never count."""
    words = {d["item"]: d["category"] for d in demand if len(d["item"]) >= 2}
    posts = read_json(md / "forum.json", [])
    authors = defaultdict(set)
    for p in posts if isinstance(posts, list) else []:
        if not isinstance(p, dict):
            continue
        text = str(p.get("text") or "")
        who = str(p.get("author") or p.get("name") or p.get("by") or p.get("buyer") or p.get("shop") or "")
        if (now - (p.get("ts") or 0) > hours * 3600 or len(text) > WANT_LEN or who == US
                or not WANT.search(text)):
            continue
        cats = {cat for w, cat in words.items() if w in text}
        cats |= {catalog[k]["category"] for k in re.findall(r"\bG[0-9a-f]{8}\b", text) if k in catalog}
        if len(cats) > WANT_CATS:
            continue                                     # a list of everything is not a wish
        for cat in cats:
            authors[cat].add(who or text[:40])
    return Counter({cat: min(len(a), WANT_CAP) for cat, a in authors.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(HERE / ".market"))
    md = Path(ap.parse_args().state)
    s = strategy()
    inv = read_json(md / "inventory.json", {})
    catalog = read_json(md / "catalog.json", {})
    demand = read_json(md / "demand.json", [])
    st = read_json(md / "restock_state.json", {"after": 0, "score": {}, "seen": [], "t": time.time()})
    now = time.time()
    # the instructor changes the rules while the round runs (11/3: "the stock condition becomes 20 minutes"), so the
    # numbers we can read come from the market's own files, not constants: the bankruptcy line from inventory.json,
    # and the time since our last run (if runs come less often, each run buys for longer: depth scales up, to 4x)
    gap = max(0.0, now - st.get("t", now))
    scale = min(4.0, max(1.0, gap / BASE_GAP / 2)) if st.get("seen") is not None and gap > 2 * BASE_GAP else 1.0
    line = inv.get("bankrupt_line") if isinstance(inv.get("bankrupt_line"), (int, float)) else BANKRUPT_LINE
    window = inv.get("restock") if isinstance(inv.get("restock"), dict) else None
    if window:
        scale = max(scale, s["window_depth"])
    if inv.get("round", 0) < 3 or not catalog or not demand:
        print(json.dumps({"buy": [], "why": "no Round 3 stock or catalog yet"}))
        return

    # scores decay with a half-life, then gain the market's new settles (per category and per SKU) and our own sales
    decay = 0.5 ** ((now - st.get("t", now)) / 3600 / s["half_life_hours"])
    score = defaultdict(float, {k: v * decay for k, v in st.get("score", {}).items()})
    sku_score = defaultdict(float, {k: v * decay for k, v in st.get("sku_score", {}).items()})
    settles, st["after"] = ledger_settles(st.get("after", 0))
    for e in settles:
        sku = e["data"].get("item")
        cat = (catalog.get(sku) or {}).get("category")
        if cat:
            score[cat] += 1
            sku_score[sku] += 1
    units = inv.get("units", [])
    have = {u["unit"]: u for u in units}
    sold = [u for u in st.get("seen", []) if u["unit"] not in have and u.get("grade") != "expired"
            and (u.get("expires_at") or now + 1) > now]
    for u in sold:                                          # our own sale counts double: it is our buyers
        score[u["category"]] += 2
        if u.get("sku"):
            sku_score[u["sku"]] += 2
    st.update(score={k: v for k, v in score.items() if v > 0.05}, sku_score={k: v for k, v in sku_score.items() if v > 0.05},
              seen=[{k: u.get(k) for k in ("unit", "sku", "category", "grade", "expires_at")} for u in units], t=now)
    # the hidden demand as it reaches us (demand_r3.py): orders our buyer got and requests to our shop, decayed over
    # two days; added for this run only (the log keeps them), so they do not compound with the settle scores
    order_w, ask_w, ref = demand_r3.signals(now)
    for cat, w in order_w.items():
        score[cat] += s["order_weight"] * w
    for sku, w in ask_w.items():
        sku_score[sku] += s["order_weight"] * w
    wanted = forum_wanted(md, demand, catalog, now)          # categories buyers asked for on the forum (not kept)
    for cat, n in wanted.items():
        score[cat] += 2 * n

    stock = sum(u["cost"] for u in units)
    warranty = (read_json(STRATEGY, {}).get("warranty_hours") or 0) > 0
    floor = max(s["reserve_cash"], line + CUSHION + (WARRANTY_CUSHION if warranty else 0))
    spend = min(inv.get("balance", 0) - floor, s["stock_value"] - stock)
    stopping = s["round_end"] and now > s["round_end"] - s["stop_hours"] * 3600
    buy, why = [], ""
    if window and window.get("open") is False:
        why = f"supply closed until {time.strftime('%H:%M:%S', time.localtime(window.get('opens_at') or now))}"
    elif stopping:
        why = "round ends soon: no new stock"
    elif spend <= 0:
        why = f"spend limit reached (balance {inv.get('balance')}, cash floor {floor}, stock at cost {stock})"
    else:
        live = [u for u in units if u.get("grade") != "expired"]
        # the market's surge (rules of 11/4 21:14): past 50 units of a SKU in an hour each unit costs 0.2% more, up to
        # +50%. At 21:14 the mattress everyone stocks cost 1.47x, two others 1.3x: a grade-A unit (55-75% of list) at
        # 1.47x costs 81-110% of list, more than a buyer pays. SKUs above surge_max (the team's knob) are left out, so
        # the plan takes the next SKU of the category instead, and the rest are priced at their surged cost
        surge = {x["sku"]: x.get("factor", 1.0) for x in inv.get("surge") or [] if isinstance(x, dict) and x.get("sku")}
        surged = {k for k, f in surge.items() if f > s.get("surge_max", 1.15)}
        catalog = {k: v for k, v in catalog.items() if k not in surged}
        count, held = Counter(u["category"] for u in live), Counter(u["sku"] for u in live)
        by_cat = defaultdict(list)
        for sku, c in catalog.items():
            by_cat[c["category"]].append(dict(c, sku=sku))
        plans = {}                                           # sku -> (priority, entry, qty)

        def plan(prio, c, qty):
            qty -= held[c["sku"]]
            if qty > 0 and (c["sku"] not in plans or plans[c["sku"]][0] < prio):
                plans[c["sku"]] = (prio, c, qty)

        for d in demand:
            # the SKU to stock first: nearest the reference price our orders point to, else the category's median
            cat, med = d["category"], ref.get(d["category"]) or d["median_price"]
            if d["kind"] == "goods" and med > s["max_list"]:
                continue
            ok_food = lambda c: d["kind"] != "food" or score[cat] >= 3 or (c.get("shelf_hours") or 0) >= s["min_shelf_hours"]
            skus = [c for c in by_cat.get(cat, []) if c["list_price"] <= max(s["max_list"], med) and ok_food(c)]
            if not skus:
                continue                                     # e.g. only short-lived food where nothing sells yet
            near = lambda x: min(skus, key=lambda c: abs(c["list_price"] - x))
            depth = 1 + (min(round(s["depth"] * scale) - 1, math.ceil(score[cat] * scale / 2)) if score[cat] >= 1 else 0)
            if d["kind"] == "food":
                depth = min(depth, round(2 * min(scale, 2.0)))
            prio = score[cat] + (1 if count[cat] == 0 else 0) + (s["food_first"] if d["kind"] == "food" else 0)
            plan(prio, near(med), depth)
            # where things sell, a cheaper and a dearer SKU too: an order takes SKUs at 0.5-1.5x a hidden reference
            # price, so one SKU at the median misses the orders whose range sits above or below it
            if score[cat] >= 1:
                for f in (s["spread_low"], s["spread_high"]):
                    plan(prio - 0.5, near(med * f), 1)
        # the SKUs the market keeps buying, by themselves (the market says some products sell much more than others)
        for sku, sc in sorted(sku_score.items(), key=lambda kv: -kv[1]):
            c = catalog.get(sku)
            if sc < 2 or not c or (c["kind"] == "goods" and c["list_price"] > s["max_list"] * 2):
                continue
            if c["kind"] == "food" and (c.get("shelf_hours") or 0) < 48:
                continue
            plan(1.5 * sc, dict(c, sku=sku), min(20, round(s["sku_depth"] * scale), math.ceil(sc * scale / 2)))
        # a supply window lasts 3 minutes and the kit buys about one line in 10 s, so the order of the lines decides
        # what gets bought: dear goods first (11/4 13:04: three mattresses bought one each sold within minutes, the
        # top shop made 57M from furniture at 459,240 a sale, while pillows, kimchi and water took the early lines)
        dear = lambda c: s.get("dear_first", 1.0) * min(3.0, c["list_price"] / 150_000) if c.get("kind") == "goods" else 0
        ranked = sorted(plans.values(), key=lambda p: (-(p[0] + dear(p[1])), -p[1]["list_price"]))
        goods_room = s["goods_frac"] * s["stock_value"] - sum(u["cost"] for u in live if u.get("kind") == "goods")
        for prio, c, qty in ranked:
            if len(buy) >= 10:
                break
            cost = c["list_price"] * EST_COST * surge.get(c["sku"], 1.0) * qty
            if cost > spend or (c["kind"] == "goods" and cost > goods_room):
                continue
            if c["kind"] == "goods":
                goods_room -= cost
            buy.append({"sku": c["sku"], "qty": int(qty)})
            spend -= cost
        why = (f"{len(ranked)} SKUs short, buying {len(buy)} lines" + (f" (runs {gap:.0f} s apart: depth x{scale:.1f})" if scale > 1 else "")
               + (f"; {len(surged)} SKUs left out for the market's surge (over {s.get('surge_max', 1.15)}x)" if surged else "")
               + (f"; forum asks for {', '.join(k.split('>')[-1] for k in list(wanted)[:5])}" if wanted else ""))
    (md / "restock_state.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    try:
        import prices_r3                         # going prices from the ledger, forum claims checked (prices_r3.py)
        prices_r3.write(md)
    except Exception as e:                       # the price file is advice; never stop a restock for it
        print(f"[prices] not written: {type(e).__name__}", file=sys.stderr)
    print(json.dumps({"buy": buy, "why": why}, ensure_ascii=False))


if __name__ == "__main__":
    main()
