"""Round 3 path of the market buyer (kit v4): real products, stock, quality, and surplus.

    python market_buyer.py --shops .market/shops.json --item 김치 --budget 30000 --order .market/order.json

What counts for a buyer in Round 3 is surplus (the SKU's list price minus what we paid, zero value if the food
did not last `use_within_hours` or the goods broke), forum votes on our posts, and the number of settled deals.

1. Learn. New lines of the kit's payments.jsonl (why it did not pay) and broken.jsonl (goods that broke) become
   memory evidence first, so this order already avoids last order's trap.
2. Pick. Every (shop, SKU) the kit lists for the order is a candidate. Code ranks them by expected surplus:
   list price minus the price we expect to pay (what this shop took from us before, as a share of list price; with a
   shop we never paid, what it settled for with everyone in the market's ledger),
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
import re
import statistics
import time
from pathlib import Path

import asyncio

import httpx

import buyer
import demand_r3
import forum_r3
import prices_r3
import team_r3
import market_intel
import harness
from harness import log

HERE = Path(__file__).resolve().parent
MD = Path(os.environ.get("MARKET_DIR") or HERE / ".market")
CAP = 0.9            # never pay more than this share of the SKU's list price
PRICE_GUESS = 0.75   # expected price as a share of list price with a shop we never paid (cost is 25-75% of list)
FOOD_MARGIN = 1.1    # food must have use_within_hours x this left at checkout (the kit's clock and the shop's differ)
GOOD_GRADES = ["A", "B"]  # C is refurbished: the most likely to break after the sale
# Grade C goods (11/4, the ledger's last 24 h: A broke 1.4%, B 5.2%, C 17.9% of settled units). A settled deal is
# worth the list price, 0 if the goods break, and a warranty refunds the price, so C is worth buying with a warranty
# covering the 6 h in which goods can break, or at C_CAP of list or less (0.82 - 0.65 = +0.17 of list expected).
# Asking for A or B only made shops holding C answer "none in stock" (458 quick rejects 06:00-09:40).
C_CAP = 0.65
C_WARRANTY = 6
B_SHARE = 0.45       # grade B food has at least 45% of its shelf life left (agent.md)
MAX_OFFERS = 8
MAX_TRIES = 3        # shops tried per order when a negotiation ends without a deal
RETRY_UNTIL = 150    # seconds into the order after which no new shop is tried (the kit stops the buyer at 300 s)
MAX_RAISE = 0.4      # each offer moves at most this share of the gap to the shop's ask
SCOUTS = 3           # buyer team: shops asked for a first quote at once before one negotiation starts
SCOUT_WAIT = 6       # seconds the scouts wait for quotes; a slower shop is left out of this order
# The meta-harness tunes these numbers from how our buyer did (meta_r3.py BUYER_BOUNDS, the user on 11/4: the
# harness should make such fixes, not a person); each run reads its plan, the defaults above when it has none.
# shop/SKU pairs that just failed us (the meta-harness's code idea, 11/4: 422 of ~680 orders without a deal ended in
# "none in stock", the same shops dropping the same SKU again and again, and 15 of 100 payments were refused for a
# unit with too little shelf life). A pair that dropped us waits until the next supply window; one that shipped too
# short a unit waits an hour for orders asking more hours than it shipped. Waiting pairs move to the back, not out.
AVOID = MD / "avoid_r3.json"
AVOID_SECS = 900
SHORT_SECS = 3600
SHELF_LEFT = re.compile(r"([\d.]+) h of shelf life left")
PLAN = Path(os.environ.get("BUYER_PLAN") or Path(__file__).resolve().parent / "buyer_plan_r3.json")
PLAN_KEYS = ("CAP", "FOOD_MARGIN", "C_CAP", "C_WARRANTY", "MAX_TRIES", "MAX_RAISE", "FIRM_GAP", "SCOUTS", "CLOSE_GAP")


def load_plan():
    try:
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    for k, v in (plan if isinstance(plan, dict) else {}).items():
        if k in PLAN_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool):
            if k in ("FIRM_GAP", "CLOSE_GAP"):
                setattr(buyer, k, v)
            else:
                globals()[k] = int(v) if k in ("MAX_TRIES", "C_WARRANTY", "SCOUTS") else v
    return plan


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def avoid_load():
    now = time.time()
    a = load(AVOID, {})
    return {k: v for k, v in (a if isinstance(a, dict) else {}).items()
            if isinstance(v, dict) and v.get("until", 0) > now}


def avoid_add(shop, sku, why, secs, hours=None):
    a = avoid_load()
    a[f"{shop}|{sku}"] = {"until": time.time() + secs, "why": why, **({"hours": hours} if hours is not None else {})}
    try:
        tmp = AVOID.with_name(f"{AVOID.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(a), encoding="utf-8")
        os.replace(tmp, AVOID)
    except OSError:
        pass


def avoided(avoid, shop, sku, order):
    """Why this pair waits for this order, or None."""
    v = avoid.get(f"{shop}|{sku}")
    if not v:
        return None
    if "hours" in v:
        need = accept_policy(order).get("min_hours_left")
        return f"shipped a unit with {v['hours']:.0f} h left lately" if need and need > v["hours"] else None
    return f"dropped us lately ({v.get('why')})"


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
        h = SHELF_LEFT.search(p.get("reason") or "")
        if h and not p.get("paid") and shop and p.get("item"):
            avoid_add(shop, p["item"], "short shelf life", SHORT_SECS, hours=float(h.group(1)))
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
        notes.append(f"the kit refused to pay {len(refused)} times, latest: {harness.clip(refused[-1].get('reason'), 120)}")
    # transitions (LongMemEval-V2): how this shop moved in our last talks, as shares of list price, newest last, so
    # the next opening offer starts near where it actually gave in rather than where it opened
    talks = [m for m in mine if m.get("kind") == "trade" and m.get("list_price") and m.get("asks")][-5:]
    moves = []
    for m in talks:
        asks = [a for a in m["asks"] if isinstance(a, (int, float))]
        if asks:
            end = f"paid {m['price'] / m['list_price']:.0%}" if m.get("price") else "no deal"
            moves.append(f"{asks[0] / m['list_price']:.0%}->{min(asks) / m['list_price']:.0%} {end}")
    if moves:
        notes.append("its asks in our last talks (first->lowest, of list): " + ", ".join(moves))
    banned = len(lies) >= 2 or (len(lies) >= 1 and len(settled) <= 3) or len(broke) >= 2
    return "; ".join(notes), banned, statistics.median(shares[-5:]) if shares else None


def ledger_claims(cat=None):
    """Per shop name: (settles, dishonest claims, median price as a share of list or None) from the market's ledger,
    the last six hours. The share is what the shop settled for with any buyer: a shop that sells cheap to others is
    worth trying first even before we have paid it ourselves."""
    try:
        entries = market_intel.load_recent(timeout=5.0)
    except Exception:
        return {}
    names = {e["data"]["url"].rstrip("/"): e["data"]["name"] for e in entries
             if e["kind"] == "join" and e["data"].get("role") == "shop" and e["data"].get("url")}
    out, shares = {}, {}
    for e in entries:
        if e["kind"] != "settle":
            continue
        d = e["data"]
        shop = str(d.get("shop") or d.get("payee") or "").rstrip("/")
        name = names.get(shop, shop.rsplit("/shop/", 1)[-1])
        n, bad = out.get(name, (0, 0))
        out[name] = (n + 1, bad + (d.get("claim_honest") is False))
        lp = ((cat or {}).get(d.get("item")) or {}).get("list_price")
        if lp and isinstance(d.get("amount"), (int, float)):
            shares.setdefault(name, []).append(d["amount"] / lp)
    return {k: (n, bad, statistics.median(shares[k][-10:]) if len(shares.get(k, [])) >= 3 else None)
            for k, (n, bad) in out.items()}


def candidates(order, shops, cat, memory, claims):
    """(expected surplus, shop, offer, list price, note) for every listed offer that fits the order."""
    acceptable = set(order.get("acceptable") or [])
    need = order.get("use_within_hours")
    out, skipped = [], []
    avoid = avoid_load()
    for s in shops:
        note, banned, share = shop_record(s["name"], memory)
        n, bad, market_share = (tuple(claims.get(s["name"], ())) + (0, 0, None))[:3]
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
            expect = lp * (share or market_share or PRICE_GUESS)
            limit = min(order["budget"], int(lp * CAP))
            p_deal = 1.0 if limit >= expect else (limit / expect) ** 4
            surplus = (lp - min(expect, limit)) * p_deal
            short = order.get("kind") == "food" and need and info.get("shelf_hours") and \
                info["shelf_hours"] * B_SHARE < need * FOOD_MARGIN
            if short:
                surplus *= 0.3                          # even a grade-B unit may not last: a last resort
            wait = avoided(avoid, s["name"], sku, order)
            if wait and "shipped" in wait:
                # the same pair shipped too short a unit again and again within the hour (11/4 15:47-16:18:
                # 25620027 G476cc094 three times, 355-431 h against 594 asked): the kit would refuse it again
                skipped.append(s["name"])
                continue
            if wait:
                surplus *= 0.05                         # tried after every other pair, not dropped
            out.append((surplus, s, off, lp, note + ("; short shelf life for this order" if short else "")
                        + (f"; {wait}" if wait else "")))
    if skipped:
        log("GUARD", f"not offering shops caught lying about grades, selling goods that broke or shipping too short a unit lately: {sorted(set(skipped))}")
    return sorted(out, key=lambda c: -c[0])


def accept_policy(order, receipt=None, lp=None):
    """What the kit checks before paying (agent.md: cert, min_hours_left, grades, warranty_hours). Goods: A or B, and
    C when the receipt carries a warranty of C_WARRANTY hours or its price is at most C_CAP of list."""
    if order.get("kind") == "food":
        return {"cert": True, "min_hours_left": round((order.get("use_within_hours") or 0) * FOOD_MARGIN, 1)}
    r = receipt if isinstance(receipt, dict) else {}
    price = buyer.as_int(r.get("price"))
    if (r.get("warranty_hours") or 0) >= C_WARRANTY or (lp and price is not None and price <= C_CAP * lp):
        return {"cert": True, "grades": GOOD_GRADES + ["C"]}
    return {"cert": True, "grades": GOOD_GRADES}


GRADE_SAID = re.compile(r"\bgrade\s*:?\s*([ABC])\b|등급\s*:?\s*([ABC])\b", re.I)
WARRANTY_SAID = re.compile(r"(\d+(?:\.\d+)?)\s*(?:h|hours?|시간)\s*(?:of\s+)?(?:warranty|보증)", re.I)
HOURS_SAID = re.compile(r"(\d+(?:\.\d+)?)\s*(?:h|hours?|시간)\s*(?:of\s+)?(?:shelf[ -]life|left|남)", re.I)


def screen_for(order, lp=None):
    """A check of the shop's own words against our payment policy (accept_policy): a grade or shelf life the shop
    states that the kit would refuse to pay for ends the talk before a deal. On 11/3 six receipts went unpaid this way
    (shelf life 138-338 h against 198-594 h asked, one grade C against A/B), each a result with no settle."""
    pol = accept_policy(order)

    def screen(text):
        g = GRADE_SAID.search(text or "")
        grade = (g.group(1) or g.group(2)).upper() if g else None
        if grade == "C" and pol.get("grades") and lp:
            w = WARRANTY_SAID.search(text or "")
            if w and float(w.group(1)) >= C_WARRANTY:
                return None
            return {"cap": int(C_CAP * lp), "why": f"the shop says grade C with no {C_WARRANTY} h warranty"}
        if grade and pol.get("grades") and grade not in pol["grades"]:
            return f"the shop says grade {grade}, we pay only for {'/'.join(pol['grades'])}"
        h = HOURS_SAID.search(text or "")
        if h and pol.get("min_hours_left") and float(h.group(1)) < pol["min_hours_left"]:
            return f"the shop says {float(h.group(1)):.0f} h of shelf life left, we need {pol['min_hours_left']:.0f}"
        return None
    return screen


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
    load_plan()
    order = load(args.order, {})
    cat = catalog()
    demand_r3.record_order(order, cat, shops)            # a sample of the hidden demand (demand_r3.py)
    sync_kit_files(memory, remember)
    # an order we already paid for can come back when the kit's result post timed out (11/4 11:47: paid, the post
    # timed out, the same order came again, a second shop agreed, the market refused the second payment): no new talk
    try:
        paid = any(json.loads(l).get("order") == order.get("order") and json.loads(l).get("paid")
                   for l in (MD / "payments.jsonl").read_text(encoding="utf-8").splitlines()[-500:])
    except (OSError, ValueError):
        paid = False
    if paid:
        log("PICK", f"order {order.get('order')} is already paid: no new talk")
        print(json.dumps({"shop": "", "receipt": None, "stars": None, "review": None}), flush=True)
        return
    cands = candidates(order, shops, cat, memory, ledger_claims(cat))
    if not cands:
        log("PICK", f"no listed shop has a SKU of {order.get('item')} we can buy")
        print(json.dumps({"shop": "", "receipt": None, "stars": None, "review": None}), flush=True)
        return
    for c in cands[:5]:
        log("CAND", f"{c[1]['name']} {c[2]['sku']} {c[2].get('name', '')[:30]} list {c[3]} surplus~{c[0]:.0f}: {c[4]}")
    cands = await team(order, cat, cands)
    # try the best candidate, then up to two more at other shops while the kit's 300 s per order allows
    # a shop that answers "none in stock" or a broken reply at once costs no time and does not use up a try
    # (11/3 21:06-21:33: 30 of 69 talks ended that way, while three tries ended many orders)
    started, tried, talks, out = time.time(), set(), 0, None
    skus, quick_shops = {}, set()
    for surplus, s, off, lp, note in cands:
        # a shop that said "none in stock" for one SKU may still have another the order accepts: up to two SKUs a
        # shop, the second only after a quick reject (the meta-harness's code idea, 11/4: 714 of ~1,000 talks ended so)
        if (s["name"], off["sku"]) in tried or skus.get(s["name"], 0) >= (2 if s["name"] in quick_shops else 1) \
                or talks >= MAX_TRIES or (tried and time.time() - started > RETRY_UNTIL):
            continue
        tried.add((s["name"], off["sku"]))
        skus[s["name"]] = skus.get(s["name"], 0) + 1
        out = await attempt(order, cat, s, off, lp, note, remember)
        quick = out.pop("_quick", False)
        if out["receipt"]:
            break
        talks += not quick
        if quick:
            quick_shops.add(s["name"])
            avoid_add(s["name"], off["sku"], "quick reject", AVOID_SECS)
    forum_r3.maybe_post(memory)
    print(json.dumps(out, ensure_ascii=False), flush=True)


def opening_for(order, name, sku):
    opening = f"I want to buy {name} ({sku})"
    if order.get("kind") == "food" and order.get("use_within_hours"):
        return opening + (f". I need it to last {order['use_within_hours']} hours: please ship a unit with at least "
                          f"{accept_policy(order)['min_hours_left']} hours of shelf life left, with the market's certificate.")
    return opening + (". Please ship a grade A or B unit with the market's certificate; a grade C unit only with a "
                      f"{C_WARRANTY} h warranty or at a refurbished price. A warranty is welcome.")


async def scout(order, cat, s, off, lp):
    """One scout of the buyer team: ask one shop for this SKU, read its first answer (no model), cancel the talk.
    {"state", "ask", "text"}; "error" when the shop cannot be reached."""
    name = harness.clip((cat.get(off["sku"]) or {}).get("name") or off.get("name") or off["sku"], 80)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            shop = buyer.Shop(client, s["url"])
            await shop.read_card()
            t = await shop.send(opening_for(order, name, off["sku"]))
            if t is None:
                return {"state": "error"}
            st, ask, text = buyer.state(t), buyer.asking_price(t), buyer.reply_text(t)
            if st == "TASK_STATE_INPUT_REQUIRED":
                await shop.cancel(t["id"])               # no unit held for us while the team decides
            return {"state": st, "ask": ask, "text": text}
    except Exception as e:
        return {"state": "error", "error": type(e).__name__}


async def team(order, cat, cands):
    """The buyer team (after dragonash's team-run agents, 11/4): SCOUTS scouts ask the best candidate shops for a quote
    at the same time, then the lead negotiates where the quote leaves the most surplus. Shops that answer "none in
    stock", fail to answer, or state a grade or shelf life our kit would not pay for are dropped before any talk; one
    negotiation at a time follows, so we never agree with two shops for one order."""
    if SCOUTS < 2 or len(cands) < 2:
        return cands
    # a second wave of scouts at other shops when every shop of the first wave dropped out (11/4: most orders without
    # a deal ended with the first shops out of stock while shops further down the list were never asked)
    picked, dropped, quoted = [], set(), []
    for wave in range(2):
        batch, seen = [], {c[1]["name"] for c in picked}
        for c in cands:
            if c[1]["name"] not in seen:
                batch.append(c)
                seen.add(c[1]["name"])
            if len(batch) >= SCOUTS:
                break
        if not batch:
            break
        if wave:
            log("SCOUT", f"no quote from the first wave: asking {len(batch)} more shops")
        picked += batch
        await scout_wave(order, cat, batch, dropped, quoted)
        if quoted:
            break
    lead = [c for _, c in sorted(quoted, key=lambda x: -x[0])]
    rest = [c for c in cands if c not in picked and (c[1]["name"], c[2]["sku"]) not in dropped]
    return lead + rest


async def scout_wave(order, cat, picked, dropped, quoted):
    # wait at most SCOUT_WAIT seconds: the slowest shop set the pace (9.5 s median, one took 27 s)
    tasks = [asyncio.create_task(scout(order, cat, c[1], c[2], c[3])) for c in picked]
    done, _ = await asyncio.wait(tasks, timeout=SCOUT_WAIT)
    quotes = [t.result() if t in done else {"state": "slow"} for t in tasks]
    for t in tasks:
        if t not in done:
            t.cancel()
    for c, q in zip(picked, quotes):
        why = screen_for(order, c[3])(q.get("text") or "") if q["state"] == "TASK_STATE_INPUT_REQUIRED" else None
        if q["state"] != "TASK_STATE_INPUT_REQUIRED" or isinstance(why, str):
            dropped.add((c[1]["name"], c[2]["sku"]))
            log("SCOUT", f"{c[1]['name']} {c[2]['sku']}: dropped ({why or q['state']})")
            if q["state"] != "slow":
                avoid_add(c[1]["name"], c[2]["sku"], why or q["state"], AVOID_SECS)
            continue
        cap = why["cap"] if isinstance(why, dict) else min(order["budget"], int(c[3] * CAP))
        ask = q.get("ask")
        # what is left at the ask, weighed by the chance of getting there when the ask is above what we pay
        value = (c[3] - min(ask, cap)) * min(1.0, cap / ask) ** 4 if isinstance(ask, (int, float)) and ask > 0 else c[0]
        quoted.append((value, c))
        log("SCOUT", f"{c[1]['name']} {c[2]['sku']}: asks {ask} of list {c[3]} (surplus at the ask ~{value:.0f})")


async def attempt(order, cat, s, off, lp, note, remember):
    """One negotiation with one shop over one SKU; returns the result line for the kit."""
    # the catalog's name first: the name in a shop's offer is the shop's own text and goes into our prompt
    name, sku = harness.clip((cat.get(off["sku"]) or {}).get("name") or off.get("name") or off["sku"], 80), off["sku"]
    limit = min(order["budget"], int(lp * CAP))
    log("CHOOSE", f"{s['name']} {s['url']}: {name} ({sku}), list {lp}, paying at most {limit}")
    opening = opening_for(order, name, sku)
    try:                                                  # the buying team member this talk goes to (team_r3.py)
        member, style = team_r3.choose("buyer")
    except (OSError, ValueError, KeyError, TypeError):
        member, style = "", {}
    opening_style = {
        "low": "Open at about half of list or lower and raise slowly; losing a few talks for a better price is fine.",
        "median": "Open a little under what the market paid lately (its median, below) and close fast.",
    }.get(style.get("OPEN"), "Open below what the market paid lately (its lower quartile, below, is a fair opening; far "
                             "under it, shops walk away) and raise slowly.")
    firm_gap, buyer.FIRM_GAP = buyer.FIRM_GAP, style.get("FIRM_GAP", buyer.FIRM_GAP)
    hint = (f"The list price is {lp}. Shops buy stock at 25-75% of list price. {opening_style} "
            f"Our record with this shop: {note}.\n"
            f"What the market paid lately (public ledger): "
            f"{prices_r3.line(MD, sku, (cat.get(sku) or {}).get('category'))}.\n")
    t0 = time.time()
    try:
        log("TEAM", f"{member or 'no team'} haggles this one {json.dumps(style)}")
        result = await buyer.shop(s["url"], name, limit, memory=hint, max_raise=style.get("MAX_RAISE", MAX_RAISE),
                                  max_offers=MAX_OFFERS, plan=bool(style.get("PLAN")),
                                  opening=opening, screen=screen_for(order, lp))
    except Exception as e:
        log("ERROR", f"trade with {s['name']} failed: {e!r}")
        result = {"state": "error", "asks": [], "offers": [], "error": type(e).__name__}

    buyer.FIRM_GAP = firm_gap
    secs = round(time.time() - t0, 1)
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
              "receipt": receipt, "problem": problem, "stars": stars, "screened": result.get("screened"),
              "member": member, "secs": secs})
    return {"shop": s["url"], "receipt": receipt if deal and not problem else None, "stars": stars,
            "review": text, "accept": accept_policy(order, receipt, lp),
            "_quick": not result.get("asks") and result.get("state") in ("TASK_STATE_REJECTED", "error")}
