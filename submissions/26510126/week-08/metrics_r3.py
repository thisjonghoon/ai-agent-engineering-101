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
  shop_deals_h          deals our shop closed per hour
  shop_margin_h         (price - cost) of those deals per hour
"""
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOARD = HERE / "logs" / "board" / "board-round3.json"
SHOP_TERMS = {"profit": 0.5, "revenue": 0.3, "stars": 0.2}
BUYER_TERMS = {"surplus": 0.5, "forum": 0.3, "deals": 0.1, "posts": 0.1}
METRICS = ("buyer_close_rate", "buyer_surplus_order", "buyer_paid_h", "shelf_refused_h", "shop_deals_h",
           "shop_margin_h")
LOWER_IS_BETTER = {"shelf_refused_h"}
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
            p = pct([r.get(term) for r in rows], mine.get(term))
            if p is not None:
                out.append((side, term, w, mine.get(term), p, round(w * (1 - p), 3)))
    return sorted(out, key=lambda x: -x[5])


def gap_text(board=None):
    rows = score_gap(board)
    if not rows:
        return "(no board snapshot)"
    return "\n".join(f"- {s} {t} (weight {w}): ours {v}, percentile {p:.2f}, points lost {lost}"
                     for s, t, w, v, p, lost in rows)


def _ts(text):
    try:
        return time.mktime(time.strptime(text, "%Y-%m-%d %H:%M:%S"))
    except (TypeError, ValueError):
        return None


def window(t0, t1, base=HERE, keep=None):
    """`keep` (an order id -> bool, the code A/B's arm): the buyer's metrics over those orders only; per hour they
    count the arm's half, so compare an arm with the other arm, not with a whole hour."""
    base = Path(base)
    hours = max((t1 - t0) / 3600, 0.25)
    orders = {d["order"] for d in jl(base / "logs" / "demand_r3.jsonl")
              if d.get("event") == "order" and t0 <= d.get("t", 0) < t1 and d.get("order")
              and (keep is None or keep(d["order"]))}
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
    surplus = sum((lists.get(m.get("order")) or 0) - (m.get("price") or 0) for m in paid if lists.get(m.get("order")))
    sold = [x for x in jl(base / "logs" / "talks_r3.jsonl") if x.get("price") and t0 <= x.get("t", 0) < t1]
    return {
        "buyer_close_rate": round(len(paid) / len(orders), 3) if orders else None,
        "buyer_surplus_order": round(surplus / len(orders)) if orders else None,
        "buyer_paid_h": round(len(paid) / hours, 1),
        "shelf_refused_h": round(refused / hours, 1),
        "shop_deals_h": round(len(sold) / hours, 1),
        "shop_margin_h": round(sum(x["price"] - (x.get("cost") or 0) for x in sold) / hours),
        "orders": len(orders),
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
