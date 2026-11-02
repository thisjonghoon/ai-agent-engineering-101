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
  - Stop buying `stop_hours` before the round ends: unsold stock at the end is a loss.
The state between runs (last units seen, ledger position, scores) is in .market/restock_state.json.
"""
import argparse
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
MARKET = "https://market.ourolabs.ai"
DEFAULTS = {"reserve_cash": 1_500_000, "stock_value": 2_000_000, "max_list": 150_000, "min_shelf_hours": 96,
            "depth": 3, "half_life_hours": 12, "stop_hours": 36, "round_end": 1794927540}    # 2026-11-17 23:59 KST
EST_COST = 0.6          # expected cost as a share of list price before the grade is drawn (A 55-75, B 40-60, C 25-45)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def strategy():
    s = dict(DEFAULTS)
    s.update({k: v for k, v in read_json(HERE / "strategy_r3.json", {}).items() if k in DEFAULTS and isinstance(v, (int, float))})
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
    if inv.get("round", 0) < 3 or not catalog or not demand:
        print(json.dumps({"buy": [], "why": "no Round 3 stock or catalog yet"}))
        return

    # scores decay with a half-life, then gain the market's new settles and our own sales
    decay = 0.5 ** ((now - st.get("t", now)) / 3600 / s["half_life_hours"])
    score = defaultdict(float, {k: v * decay for k, v in st.get("score", {}).items()})
    settles, st["after"] = ledger_settles(st.get("after", 0))
    for e in settles:
        cat = (catalog.get(e["data"].get("item")) or {}).get("category")
        if cat:
            score[cat] += 1
    units = inv.get("units", [])
    have = {u["unit"]: u for u in units}
    sold = [u for u in st.get("seen", []) if u["unit"] not in have and u.get("grade") != "expired"
            and (u.get("expires_at") or now + 1) > now]
    for u in sold:                                          # our own sale counts double: it is our buyers
        score[u["category"]] += 2
    st.update(score=dict(score), seen=[{k: u.get(k) for k in ("unit", "category", "grade", "expires_at")} for u in units],
              t=now)

    stock = sum(u["cost"] for u in units)
    spend = min(inv.get("balance", 0) - s["reserve_cash"], s["stock_value"] - stock)
    stopping = s["round_end"] and now > s["round_end"] - s["stop_hours"] * 3600
    buy, why = [], ""
    if stopping:
        why = "round ends soon: no new stock"
    elif spend <= 0:
        why = f"spend limit reached (balance {inv.get('balance')}, stock at cost {stock})"
    else:
        count = Counter(u["category"] for u in units if u.get("grade") != "expired")
        by_cat = defaultdict(list)
        for sku, c in catalog.items():
            by_cat[c["category"]].append(dict(c, sku=sku))
        plans = []
        for d in demand:
            cat, med = d["category"], d["median_price"]
            if d["kind"] == "goods" and med > s["max_list"]:
                continue
            if d["kind"] == "food" and (d.get("shelf_hours") or 0) < s["min_shelf_hours"] and score[cat] < 3:
                continue                                     # short-lived food only where it clearly sells
            want = 1 + (min(s["depth"] - 1, math.ceil(score[cat] / 2)) if score[cat] >= 1 else 0)
            if d["kind"] == "food":
                want = min(want, 2)
            if count[cat] >= want:
                continue
            skus = [c for c in by_cat.get(cat, []) if c["list_price"] <= max(s["max_list"], med)]
            if not skus:
                continue
            pick = min(skus, key=lambda c: abs(c["list_price"] - med))
            plans.append((-(score[cat] + (1 if count[cat] == 0 else 0)), cat, pick, want - count[cat]))
        plans.sort(key=lambda p: (p[0], p[2]["list_price"]))
        for _, cat, pick, qty in plans:
            if len(buy) >= 10:
                break
            cost = pick["list_price"] * EST_COST * qty
            if cost > spend:
                continue
            buy.append({"sku": pick["sku"], "qty": int(qty)})
            spend -= cost
        why = f"{len(plans)} categories short, buying {len(buy)} lines"
    (md / "restock_state.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"buy": buy, "why": why}, ensure_ascii=False))


if __name__ == "__main__":
    main()
