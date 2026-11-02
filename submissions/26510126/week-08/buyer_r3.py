"""Round 3 path of the market buyer (kit v4): real products, stock, quality, and surplus.

    python market_buyer.py --shops .market/shops.json --item 김치 --budget 30000 --order .market/order.json

What counts for a buyer in Round 3 is surplus (the SKU's list price minus what we paid, zero value if the food
did not last `use_within_hours` or the goods broke), forum votes on our posts, and the number of settled deals.

1. Learn. New lines of the kit's payments.jsonl (why it did not pay) and broken.jsonl (goods that broke) become
   memory evidence first, so this order already avoids last order's trap.
2. Pick. Every (shop, SKU) the kit lists for the order is a candidate. Code ranks them by expected surplus:
   list price minus the price we expect to pay (what this shop took from us before, as a share of list price),
   with shops our memory or the ledger caught lying about grades, or whose goods broke on us, left out.
   Food whose shelf life cannot cover `use_within_hours` even at grade B is a last resort.
3. Trade. buyer.shop() haggles over A2A as in weeks 6-7 (harness offers, code guards), opening with
   "I want to buy <name> (<sku>)" and the shelf life or certificate we need. The cap is min(budget, CAP x list):
   above the list price a deal loses surplus, and near it a broken or spoiled unit costs more than it saves.
4. Accept. The last line carries an accept policy the kit checks before paying: the market's certificate,
   enough shelf life for food, and no refurbished (grade C) goods, whose hidden break rate can turn a deal
   into minus the price.
5. Remember and post. Each trade is one raw line in memory.jsonl; at most every 5 minutes, a factual note on
   the forum (what we paid against list price, whether claims were true, with ledger refs).
"""
import json
import os
import statistics
import time
from pathlib import Path

import buyer
import forum_r3
import market_intel
from harness import log

HERE = Path(__file__).resolve().parent
MD = Path(os.environ.get("MARKET_DIR") or HERE / ".market")
CAP = 0.9            # never pay more than this share of the SKU's list price
PRICE_GUESS = 0.75   # expected price as a share of list price with a shop we never paid (cost is 25-75% of list)
FOOD_MARGIN = 1.1    # food must have use_within_hours x this left at checkout (the kit's clock and the shop's differ)
GOOD_GRADES = ["A", "B"]  # C is refurbished: the most likely to break after the sale
B_SHARE = 0.45       # grade B food has at least 45% of its shelf life left (agent.md)
MAX_OFFERS = 8
MAX_TRIES = 3        # shops tried per order when a negotiation ends without a deal
RETRY_UNTIL = 150    # seconds into the order after which no new shop is tried (the kit stops the buyer at 300 s)


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except (OSError, ValueError):
        return []


def catalog():
    """sku -> {name, category, list_price, kind, shelf_hours}; the kit writes a dict, the market API a list."""
    c = load(MD / "catalog.json", {})
    return {x["sku"]: x for x in c} if isinstance(c, list) else c


# ---------------------------------------------------------------- learn from the kit's files

def sync_kit_files(memory, remember):
    """Payment refusals and broken goods the kit reported since we last looked, as raw memory lines.
    A broken item is matched to our latest settled purchase of that name before it broke, so we know
    which shop sold it and whether a warranty covered it."""
    seen_pay = {m.get("order") for m in memory if m.get("kind") == "payment"}
    for p in lines(MD / "payments.jsonl"):
        if p.get("order") in seen_pay:
            continue
        shop = next((m["shop"] for m in reversed(memory) if m.get("order") == p.get("order") and m.get("shop")), p.get("shop"))
        entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "payment", "round": 3, "order": p.get("order"),
                 "shop": shop, "sku": p.get("item"), "price": p.get("price"), "paid": p.get("paid"),
                 "ledger": p.get("ledger"), "reason": p.get("reason")}
        remember(entry)
        memory.append(entry)
    seen_broken = {(m.get("name"), m.get("broke_at")) for m in memory if m.get("kind") == "broken"}
    for b in lines(MD / "broken.jsonl"):
        key = (b.get("name"), b.get("broke_at"))
        if key in seen_broken:
            continue
        bought = [m for m in memory if m.get("kind") == "settled" and m.get("name") == b.get("name")
                  and (m.get("settled_at") or 0) <= (b.get("broke_at") or 0)]
        src = bought[-1] if bought else {}
        # the same name bought from two shops within the 6 h goods can break in: we cannot tell which one broke
        recent = {m.get("shop") for m in bought if (b.get("broke_at") or 0) - (m.get("settled_at") or 0) <= 6 * 3600}
        ambiguous = len(recent) > 1
        hours = ((b.get("broke_at") or 0) - (src.get("settled_at") or 0)) / 3600 if src else None
        entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "broken", "round": 3, "name": b.get("name"),
                 "broke_at": b.get("broke_at"), "shop": src.get("shop"), "order": src.get("order"),
                 "price": src.get("price"), "warranty_hours": src.get("warranty_hours"),
                 "covered": bool(src.get("warranty_hours")) and hours is not None and hours <= src["warranty_hours"],
                 "ambiguous": ambiguous}
        remember(entry)
        memory.append(entry)


# ---------------------------------------------------------------- derived on read

def shop_record(name, memory):
    """What our own Round 3 evidence says about a shop: (note, banned, price share of list or None)."""
    mine = [m for m in memory if m.get("round") == 3 and m.get("shop") == name]
    if not mine:
        return "no Round 3 trades with us", False, None
    settled = [m for m in mine if m.get("kind") == "settled"]
    lies = [m for m in settled if m.get("claim_honest") is False]
    broke = [m for m in mine if m.get("kind") == "broken" and not m.get("covered")]
    refused = [m for m in mine if m.get("kind") == "payment" and not m.get("paid")]
    shares = [m["price"] / m["list_price"] for m in settled if m.get("price") and m.get("list_price")]
    notes = [f"{len(settled)} settled with us"]
    if shares:
        notes.append(f"we paid {statistics.median(shares):.0%} of list (median)")
    if lies:
        notes.append(f"GOTCHA claimed a better grade than it shipped {len(lies)} times (ledger #{lies[-1].get('ledger')})")
    if broke:
        notes.append(f"GOTCHA {len(broke)} goods broke without warranty cover")
    if refused:
        notes.append(f"the kit refused to pay {len(refused)} times, latest: {refused[-1].get('reason')}")
    banned = len(lies) >= 2 or (len(lies) >= 1 and len(settled) <= 3) or len(broke) >= 2
    return "; ".join(notes), banned, statistics.median(shares[-5:]) if shares else None


def ledger_claims():
    """Per shop URL or name: (settles, dishonest claims) from the market's ledger, the last six hours."""
    try:
        entries = market_intel.load_recent(timeout=5.0)
    except Exception:
        return {}
    names = {e["data"]["url"].rstrip("/"): e["data"]["name"] for e in entries
             if e["kind"] == "join" and e["data"].get("role") == "shop" and e["data"].get("url")}
    out = {}
    for e in entries:
        if e["kind"] != "settle":
            continue
        d = e["data"]
        shop = str(d.get("shop") or d.get("payee") or "").rstrip("/")
        name = names.get(shop, shop.rsplit("/shop/", 1)[-1])
        n, bad = out.get(name, (0, 0))
        out[name] = (n + 1, bad + (d.get("claim_honest") is False))
    return out


def candidates(order, shops, cat, memory, claims):
    """(expected surplus, shop, offer, list price, note) for every listed offer that fits the order."""
    acceptable = set(order.get("acceptable") or [])
    need = order.get("use_within_hours")
    out, skipped = [], []
    for s in shops:
        note, banned, share = shop_record(s["name"], memory)
        n, bad = claims.get(s["name"], (0, 0))
        if n >= 5 and bad / n >= 0.3:
            banned = True
            note += f"; market ledger: {bad} of its last {n} settled grade claims were false"
        for off in s.get("offers") or []:
            sku = off.get("sku")
            info = cat.get(sku) or {}
            lp = info.get("list_price")
            if sku not in acceptable or not lp or not off.get("qty"):
                continue
            if banned:
                skipped.append(s["name"])
                continue
            # what we expect to pay there, and whether our limit reaches it: an expensive SKU whose shop floor sits
            # above our limit only looks like a big surplus (review, 11/2), so the chance of a deal weighs it
            expect = lp * (share or PRICE_GUESS)
            limit = min(order["budget"], int(lp * CAP))
            p_deal = 1.0 if limit >= expect else (limit / expect) ** 4
            surplus = (lp - min(expect, limit)) * p_deal
            short = order.get("kind") == "food" and need and info.get("shelf_hours") and \
                info["shelf_hours"] * B_SHARE < need * FOOD_MARGIN
            if short:
                surplus *= 0.3                          # even a grade-B unit may not last: a last resort
            out.append((surplus, s, off, lp, note + ("; short shelf life for this order" if short else "")))
    if skipped:
        log("GUARD", f"not offering shops our memory or the ledger caught lying about grades or selling goods that broke: {sorted(set(skipped))}")
    return sorted(out, key=lambda c: -c[0])


def accept_policy(order):
    """What the kit checks before paying (agent.md: cert, min_hours_left, grades, warranty_hours)."""
    if order.get("kind") == "food":
        return {"cert": True, "min_hours_left": round((order.get("use_within_hours") or 0) * FOOD_MARGIN, 1)}
    return {"cert": True, "grades": GOOD_GRADES}


def check_receipt(receipt, order, agreed, task_id):
    if not isinstance(receipt, dict):
        return "no receipt"
    price = buyer.as_int(receipt.get("price"))
    if receipt.get("item") not in set(order.get("acceptable") or []) | {order.get("item")}:
        return f"receipt names {receipt.get('item')!r}, not a SKU of this order"
    if price is None or (agreed is not None and price > agreed):   # a lower price than our offer is fine
        return f"agreed {agreed}, receipt says {receipt.get('price')}"
    if price > order["budget"]:
        return f"receipt price {price} above budget {order['budget']}"
    if receipt.get("task") != task_id:
        return f"receipt task {receipt.get('task')!r} is not this negotiation"
    return None


def review(result, name, lp, problem):
    """Stars before payment; the review hook replaces them with what actually arrived."""
    asks = [a for a in result.get("asks", []) if a is not None]
    offers = result.get("offers", [])
    if result.get("state") == "TASK_STATE_COMPLETED" and problem:
        return 1, f"Bad receipt: {problem}."
    if result.get("state") == "error":
        return 1, f"No deal: the shop could not be traded with ({result.get('error', 'error')})."
    if result.get("state") == "TASK_STATE_COMPLETED":
        return 4, f"{name}: agreed {offers[-1]} ({offers[-1] / lp:.0%} of list {lp}) after {len(offers)} offers."
    if not asks:
        return 2, f"No deal on {name}: the shop named no price."
    return 3, f"No deal on {name}: lowest ask {min(asks)} ({min(asks) / lp:.0%} of list {lp}), above what we pay."


async def main(args, shops, memory, remember):
    order = load(args.order, {})
    cat = catalog()
    sync_kit_files(memory, remember)
    cands = candidates(order, shops, cat, memory, ledger_claims())
    if not cands:
        log("PICK", f"no listed shop has a SKU of {order.get('item')} we can buy")
        print(json.dumps({"shop": "", "receipt": None, "stars": None, "review": None}), flush=True)
        return
    for c in cands[:5]:
        log("CAND", f"{c[1]['name']} {c[2]['sku']} {c[2].get('name', '')[:30]} list {c[3]} surplus~{c[0]:.0f}: {c[4]}")
    # try the best candidate, then up to two more at other shops while the kit's 300 s per order allows
    started, tried, out = time.time(), set(), None
    for surplus, s, off, lp, note in cands:
        if s["name"] in tried or len(tried) >= MAX_TRIES or (tried and time.time() - started > RETRY_UNTIL):
            continue
        tried.add(s["name"])
        out = await attempt(order, cat, s, off, lp, note, remember)
        if out["receipt"]:
            break
    forum_r3.maybe_post(memory)
    print(json.dumps(out, ensure_ascii=False), flush=True)


async def attempt(order, cat, s, off, lp, note, remember):
    """One negotiation with one shop over one SKU; returns the result line for the kit."""
    name, sku = off.get("name") or (cat.get(off["sku"]) or {}).get("name", off["sku"]), off["sku"]
    limit = min(order["budget"], int(lp * CAP))
    log("CHOOSE", f"{s['name']} {s['url']}: {name} ({sku}), list {lp}, paying at most {limit}")
    opening = f"I want to buy {name} ({sku})"
    if order.get("kind") == "food" and order.get("use_within_hours"):
        opening += (f". I need it to last {order['use_within_hours']} hours: please ship a unit with at least "
                    f"{accept_policy(order)['min_hours_left']} hours of shelf life left, with the market's certificate.")
    else:
        opening += ". Please ship a grade A or B unit with the market's certificate; a warranty is welcome."
    hint = (f"The list price is {lp}. Shops buy stock at 25-75% of list price, so start well below list "
            f"(around half) and raise slowly. Our record with this shop: {note}.\n")
    try:
        result = await buyer.shop(s["url"], name, limit, memory=hint, max_raise=0.4, max_offers=MAX_OFFERS,
                                  opening=opening)
    except Exception as e:
        log("ERROR", f"trade with {s['name']} failed: {e!r}")
        result = {"state": "error", "asks": [], "offers": [], "error": type(e).__name__}

    receipt = result.get("receipt")
    deal = result.get("state") == "TASK_STATE_COMPLETED"
    agreed = result["offers"][-1] if deal and result.get("offers") else None
    problem = check_receipt(receipt, order, agreed, result.get("task")) if deal else None
    if problem:
        log("GUARD", f"receipt problem: {problem}")
    stars, text = review(result, name, lp, problem)
    remember({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "trade", "round": 3, "order": order.get("order"),
              "shop": s["name"], "url": s["url"], "item": order.get("item"), "sku": sku, "name": name,
              "list_price": lp, "budget": order.get("budget"), "food_hours": order.get("use_within_hours"),
              "outcome": "bad_receipt" if problem else "deal" if deal else "no_deal", "end": result.get("state"),
              "price": agreed, "asks": result.get("asks", []), "offers": result.get("offers", []),
              "receipt": receipt, "problem": problem, "stars": stars})
    return {"shop": s["url"], "receipt": receipt if deal and not problem else None, "stars": stars,
            "review": text, "accept": accept_policy(order)}
