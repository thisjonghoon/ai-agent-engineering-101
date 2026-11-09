"""What the midterm grades, and the numbers a change is judged by.

score_gap(): the board's Players rank is shop ALL + buyer ALL, each a weighted sum of percentiles (agent.md: shops by
profit 0.5, revenue 0.3, stars 0.2; buyers by surplus 0.5, forum votes 0.3, deals 0.1, posts 0.1). For each term it
gives our percentile and the points it leaves on the table (weight x (1 - percentile)), so the harness works on the
term that costs most, not on the one it happens to see.

window(t0, t1): the fixed metrics a hypothesis may name, from our own logs (code computes them, no model):
  buyer_close_rate      paid orders / orders
  buyer_surplus_order   (list - price) of paid deals / orders
  buyer_paid_h          paid deals per hour
  shelf_refused_h       payments the kit refused for too little shelf life, per hour
  shop_deals_h          our sales paid on the ledger per hour (not receipts signed: buyers pay one of several shops)
  shop_margin_h         (price - cost) of those deals per hour
  forum_votes_post      net votes per post our buyer wrote in the window (forum.json keeps the newest 100 posts, so
                        only the last hours can be read; forum votes are 0.3 of the buyer's ALL)
  buyer_saved_deal      mean of (list - price) / list over the paid deals: the board's saved term per deal (11/6 06:02
                        rules), so a cheap order counts as much as a dear one; goods that break later count -1 on the
                        board, which this window cannot see yet
  buyer_dear_close      paid orders / orders among orders whose reference price is DEAR or more. 11/3 21:00-11/5 11:00:
                        the 216 orders of 300k or more (5%) gave 55% of our surplus, closing 61%; one more of them
                        closed is worth about ten cheap deals
  buyer_secs_order      median seconds from an order to our buyer's answer (lower is better). The market sends the
                        next order no sooner than 20 s after the last, so time past 20 s is orders lost: 31% of orders
                        took longer, no-deal ones 23 s at the median and 66 s at p90, and we got 139 orders an hour
                        where 20 s each would give about 170
  outage_min            minutes of the window the market listed no shops (the kit logs 'no shops in the market yet'
                        about every 30 s; 11/5 16:12-16:45 and 17:16-17:23). The per-hour metrics count only the
                        minutes the market was up, so an outage does not read as a price or stock effect
"""
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOARD = HERE / "logs" / "board" / "board-round3.json"
# the rules of 11/5 03:49: the shop's first term is book (cash + what unsold units cost), no longer cash ("profit")
SHOP_TERMS = {"book": 0.5, "revenue": 0.3, "stars": 0.2}
# the rules of 11/6 06:02: the buyer's first term is saved, the sum over deals of surplus / list price (-1 for a deal that
# served nothing, 0 if refunded) divided by deals + 100, so a snack and a sofa at 30% off score the same
BUYER_TERMS = {"saved": 0.5, "forum": 0.3, "deals": 0.1, "posts": 0.1}
METRICS = ("board_pts_h", "shop_revenue_h", "buyer_close_rate", "buyer_surplus_order", "buyer_paid_h", "shelf_refused_h", "shop_deals_h",
           "shop_margin_h", "forum_votes_post", "buyer_dear_close", "buyer_secs_order", "buyer_saved_deal")
LOWER_IS_BETTER = {"shelf_refused_h", "buyer_secs_order"}
DEAR = 100000
KIT_LOG = "logs/market-kit.log"
OUTAGE_LINE = "no shops in the market yet"
TAIL = 16_000_000                  # the kit log grows about 1 MB an hour; 16 MB covers more than the windows judged
ME = "thisjonghoon"


def jl(path):
    try:
        return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def pct(values, mine):
    """Share of the others we beat or tie, the board's kind of percentile."""
    others = [v for v in values if v is not None]
    if mine is None or not others:
        return None
    return round(sum(v <= mine for v in others) / len(others), 3)


def score_gap(board=None):
    """[(side, term, weight, our value, percentile, points lost)], the costliest first."""
    if board is None:
        try:
            board = json.loads(BOARD.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    out = []
    for side, rows, terms, alive in (("shop", board.get("shops") or [], SHOP_TERMS, lambda r: r.get("deals")),
                                     ("buyer", board.get("buyers") or [], BUYER_TERMS, lambda r: r.get("deals"))):
        rows = [r for r in rows if alive(r)]
        mine = next((r for r in rows if r.get("name") == ME), None)
        if not mine:
            continue
        for term, w in terms.items():
            # patch 3.5 (11/6 15:53): the forum rating counts as itself in the buyer's ALL, not as a percentile
            p = mine.get(term) if (side, term) == ("buyer", "forum") and isinstance(mine.get(term), (int, float)) \
                else pct([r.get(term) for r in rows], mine.get(term))
            if p is not None:
                out.append((side, term, w, mine.get(term), p, round(w * (1 - p), 3)))
    return sorted(out, key=lambda x: -x[5])


def gap_text(board=None):
    rows = score_gap(board)
    if not rows:
        return "(no board snapshot)"
    return "\n".join(f"- {s} {t} (weight {w}): ours {v}, {'rating' if (s, t) == ('buyer', 'forum') else 'percentile'} {p:.2f}, points lost {lost}"
                     for s, t, w, v, p, lost in rows)


def _ts(text):
    try:
        return time.mktime(time.strptime(text, "%Y-%m-%d %H:%M:%S"))
    except (TypeError, ValueError):
        return None


def outage_secs(t0, t1, base=HERE):
    """Seconds of [t0, t1) the market listed no shops: each 'no shops' line of the kit log stands for the 30 s the kit
    waits before it asks again. The log's lines carry only a clock time, read on the day of t1."""
    path = Path(base) / KIT_LOG
    try:
        with path.open("rb") as f:
            f.seek(max(path.stat().st_size - TAIL, 0))
            text = f.read().decode("utf-8", "ignore")
    except OSError:
        return 0
    day = time.strftime("%Y-%m-%d ", time.localtime(t1))
    seen = set()
    for line in text.splitlines():
        if OUTAGE_LINE not in line:
            continue
        t = _ts(day + line[:8])
        if t is not None and t > t1 + 60:
            t -= 86400                                # a line from the day before
        if t is not None and t0 <= t < t1:
            seen.add(t)
    return min(len(seen) * 30, t1 - t0)


def settled_sales(t0, t1, base=HERE):
    """Our shop's paid sales in [t0, t1): {"t", "price", "cost"} per settle on the market's ledger (the small cache
    market_intel keeps, .market/ledger-recent.json, the last 6 h). Until 11/7 these metrics counted every receipt the
    seller signed (talks_r3.jsonl), but a buyer haggles with several shops and pays one: from 06:52 to 09:35 on 11/7,
    17 of our 300k+ agreements (18M) were paid once, so margin/h read 2-4M against Book growing 0.7-0.9M an hour.
    A unit's cost is its supply entry's total / qty; one not found there is matched to the talk agreed at that price."""
    base = Path(base)
    try:
        entries = json.loads((base / ".market" / "ledger-recent.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    urls = {(e["data"].get("url") or "").rstrip("/") for e in entries
            if e.get("kind") == "join" and e["data"].get("name") == ME and e["data"].get("role") == "shop"}
    cost = {}
    for e in entries:
        d = e.get("data") or {}
        if e.get("kind") == "supply" and d.get("shop") == ME and d.get("units"):
            for u in d["units"]:
                cost[u] = (d.get("total") or 0) / len(d["units"])
    talks = [x for x in jl(base / "logs" / "talks_r3.jsonl") if x.get("price") and t0 - 900 <= x.get("t", 0) < t1]
    out = []
    for e in entries:
        d = e.get("data") or {}
        if e.get("kind") != "settle" or not t0 <= e.get("ts", 0) < t1 or str(d.get("shop") or "").rstrip("/") not in urls:
            continue
        c = cost.get(d.get("unit"))
        if c is None:
            c = next((x.get("cost") for x in reversed(talks) if x["price"] == d.get("amount") and x["t"] <= e["ts"]), 0)
        out.append({"t": e["ts"], "price": d.get("amount") or 0, "cost": c or 0})
    return out


def paid_share(t0, t1, base=HERE):
    """(our paid sales, the whole market's paid sales) in [t0, t1) from the ledger cache: the fast guard compares our
    share before and after a change, so the market's own rhythm (night, outages) cancels out."""
    base = Path(base)
    try:
        entries = json.loads((base / ".market" / "ledger-recent.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0, 0
    market = sum(1 for e in entries if e.get("kind") == "settle" and t0 <= e.get("ts", 0) < t1)
    return len(settled_sales(t0, t1, base)), market


def market_share(t0, t1, base=HERE):
    """Our part of the market's paid sales in [t0, t1): by count and by value (settled amounts), from the ledger cache.
    11/9: the 2 h number verdicts compared our raw margin/h before and after a change, so a change made at 06:00
    looked good for the morning rush and one made at 22:00 bad for the night; the market's own sales over the same
    hours divide that clock out. {"ours", "market", "share_n", "share_value"}, shares None with no market sales."""
    base = Path(base)
    try:
        entries = json.loads((base / ".market" / "ledger-recent.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        entries = []
    settles = [e for e in entries if e.get("kind") == "settle" and t0 <= e.get("ts", 0) < t1]
    mkt_value = sum((e.get("data") or {}).get("amount") or 0 for e in settles)
    ours = settled_sales(t0, t1, base)
    return {"ours": len(ours), "market": len(settles), "market_value": mkt_value,
            "share_n": round(len(ours) / len(settles), 4) if settles else None,
            "share_value": round(sum(x["price"] for x in ours) / mkt_value, 4) if mkt_value else None}


def lever_prices(board=None, k=3):
    """ALL points per unit of Book, revenue and buyer saved where we stand now: the weight times the percentile step of
    passing the next k rivals, over the distance to the k-th. One price list for every verdict, so a change is judged
    on what the board pays for it (11/9: the loops judged margin/h, margin per talk or deals/h, each a different aim,
    and a playbook that won on margin per talk cut revenue and sales)."""
    if board is None:
        try:
            board = json.loads(BOARD.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    out = {}
    for side, term, key in (("shops", "book", "book"), ("shops", "revenue", "revenue"), ("buyers", "saved", "saved")):
        rows = [r for r in board.get(side) or [] if r.get("deals")]
        mine = next((r for r in rows if r.get("name") == ME), None)
        if not mine or not isinstance(mine.get(term), (int, float)):
            continue
        above = sorted(v for r in rows if r is not mine and isinstance(v := r.get(term), (int, float)) and v > mine[term])
        if not above:
            continue
        kk = min(k, len(above))
        w = (SHOP_TERMS if side == "shops" else BUYER_TERMS)[term]
        out[key] = w * kk / (len(rows) - 1) / max(above[kk - 1] - mine[term], 1e-9)
        if side == "buyers":
            out["deals_total"] = mine.get("deals") or 0
            out["saved_now"] = mine[term]
    return out


def board_points_h(margin_h, revenue_h, paid_h, saved_deal, prices=None):
    """Estimated ALL points an hour at this pace: Book grows by the margin of paid sales, revenue by their price, and
    saved moves by each paid buyer deal's distance from our running mean, over deals + 100 (the board's formula)."""
    p = prices if prices is not None else lever_prices()
    if not p:
        return None
    pts = margin_h * p.get("book", 0) + revenue_h * p.get("revenue", 0)
    if saved_deal is not None and "saved" in p:
        pts += paid_h * (saved_deal - p["saved_now"]) / (p["deals_total"] + 100) * p["saved"]
    return round(pts, 5)


def window(t0, t1, base=HERE, keep=None):
    """`keep` (an order id -> bool, the code A/B's arm): the buyer's metrics over those orders only; per hour they
    count the arm's half, so compare an arm with the other arm, not with a whole hour."""
    base = Path(base)
    down = outage_secs(t0, t1, base)
    hours = max((t1 - t0 - down) / 3600, 0.25)
    orders = {d["order"]: d for d in jl(base / "logs" / "demand_r3.jsonl")
              if d.get("event") == "order" and t0 <= d.get("t", 0) < t1 and d.get("order")
              and (keep is None or keep(d["order"]))}
    dear = {o for o, d in orders.items() if (d.get("ref") or 0) >= DEAR}
    mem = jl(base / "memory.jsonl")
    lists = {m.get("order"): m.get("list_price") for m in mem if m.get("kind") == "trade" and m.get("list_price")}
    paid, refused = [], 0
    for m in mem:
        if m.get("kind") != "payment":
            continue
        t = _ts(m.get("time"))
        if t is None or not t0 <= t < t1 or (keep is not None and not keep(m.get("order"))):
            continue
        if m.get("paid"):
            paid.append(m)
        elif "shelf life" in (m.get("reason") or ""):
            refused += 1
    secs = sorted(_ts(m.get("time")) - orders[m["order"]]["t"] for m in mem
                  if m.get("kind") == "trade" and m.get("order") in orders and _ts(m.get("time")))
    secs = [x for x in secs if 0 <= x < 600]
    dear_paid = sum(1 for m in paid if m.get("order") in dear)
    rates = [(lists[m["order"]] - m["price"]) / lists[m["order"]] for m in paid
             if lists.get(m.get("order")) and m.get("price") is not None]
    surplus = sum((lists.get(m.get("order")) or 0) - (m.get("price") or 0) for m in paid if lists.get(m.get("order")))
    sold = settled_sales(t0, t1, base)
    try:
        posts = json.loads((base / ".market" / "forum.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        posts = []
    posts = posts if isinstance(posts, list) else posts.get("posts", []) if isinstance(posts, dict) else []
    ours = [p for p in posts if isinstance(p, dict) and p.get("author") == ME and p.get("role", "buyer") == "buyer"
            and t0 <= (p.get("ts") or 0) < t1]
    margin_h = sum(x["price"] - (x.get("cost") or 0) for x in sold) / hours
    revenue_h = sum(x["price"] for x in sold) / hours
    saved_deal = sum(rates) / len(rates) if rates else None
    return {
        "board_pts_h": board_points_h(margin_h, revenue_h, len(paid) / hours, saved_deal),
        "shop_revenue_h": round(revenue_h),
        "buyer_close_rate": round(len(paid) / len(orders), 3) if orders else None,
        "buyer_surplus_order": round(surplus / len(orders)) if orders else None,
        "buyer_paid_h": round(len(paid) / hours, 1),
        "shelf_refused_h": round(refused / hours, 1),
        "shop_deals_h": round(len(sold) / hours, 1),
        "shop_margin_h": round(margin_h),
        "forum_votes_post": round(sum((p.get("likes") or 0) - (p.get("dislikes") or 0) for p in ours) / len(ours), 2)
        if ours else None,
        "buyer_saved_deal": round(saved_deal, 4) if saved_deal is not None else None,
        "buyer_dear_close": round(dear_paid / len(dear), 3) if len(dear) >= 5 else None,
        "buyer_secs_order": round(secs[len(secs) // 2], 1) if secs else None,
        "orders": len(orders),
        "outage_min": round(down / 60),
    }


def change(metric, before, after):
    """Relative change of a metric, signed so that positive is better; None when it cannot be told."""
    b, a = (before or {}).get(metric), (after or {}).get(metric)
    if b is None or a is None or b == 0:
        return None
    r = (a - b) / abs(b)
    return round(-r if metric in LOWER_IS_BETTER else r, 3)


if __name__ == "__main__":
    now = time.time()
    print(gap_text())
    print(json.dumps(window(now - 3600, now), ensure_ascii=False))
