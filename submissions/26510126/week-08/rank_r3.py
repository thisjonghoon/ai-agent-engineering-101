"""Where we stand on the midterm's rank (week 9 FIG. 07, agent.md 11/3 20:29), and against the instructor's agents.

    python rank_r3.py        # our shop ALL, buyer ALL, Players rank, and the gap to q00 (the instructor's shop+buyer)

The goal set on 11/3: a high Players rank, above the instructor's own agent (q00), while staying honest (no false
grade claims, no hidden certificates, no votes against others, no self-dealing). The meta-harness and the watchers
read this, so every decision sees the same target.
  shop ALL  = 0.5 profit + 0.3 revenue + 0.2 stars             (percentiles among shops with a deal or a purchase)
  buyer ALL = 0.5 surplus + 0.3 votes + 0.1 deals + 0.1 posts  (percentiles among buyers with a deal)
  Players   = shop ALL + buyer ALL per GitHub owner
The board's own Players table, when it has one, is the truth; this recomputes it from the shop and buyer tables so
it also works before the market fills that table, and names which part to push.
"""
import json

US, TEACHER = "thisjonghoon", "q00"
SHOP_W = {"profit": 0.5, "revenue": 0.3, "stars": 0.2}
BUYER_W = {"surplus": 0.5, "votes": 0.3, "deals": 0.1, "posts": 0.1}
ALIASES = {"surplus": ("surplus", "saved"), "votes": ("votes", "forum", "score"), "posts": ("posts",)}


def value(row, key):
    for k in ALIASES.get(key, (key,)):
        if isinstance(row.get(k), (int, float)) and not isinstance(row.get(k), bool):
            return row[k]
    return None


def pct(x, xs):
    xs = [v for v in xs if v is not None]
    return sum(v <= x for v in xs) / len(xs) if xs and x is not None else None


def table_all(rows, weights, active):
    """name -> (ALL, parts) for every row, parts as percentiles; a part the table lacks is left out and the weights
    of the rest are scaled up (so Round 2's tables, without votes or posts, still give a comparable number)."""
    rows = [r for r in rows if active(r)]
    have = [k for k in weights if any(value(r, k) is not None for r in rows)]
    total = sum(weights[k] for k in have) or 1
    out = {}
    for r in rows:
        parts = {k: pct(value(r, k), [value(x, k) for x in rows]) for k in have}
        out[r.get("name")] = (sum(weights[k] * (parts[k] or 0) for k in have) / total, parts)
    return out


def owner(r):
    return ((r.get("owner") or {}).get("login") or r.get("name") or "").lower()


def standing(board):
    shops = table_all(board.get("shops") or [], SHOP_W, lambda r: (r.get("deals") or 0) > 0 or (r.get("purchases") or 0) > 0)
    buyers = table_all(board.get("buyers") or [], BUYER_W, lambda r: (r.get("deals") or 0) > 0)
    players = {}
    for kind, t in (("shop", shops), ("buyer", buyers)):
        rows = {r.get("name"): r for r in board.get(kind + "s") or []}
        for name, (score, _) in t.items():
            r = rows.get(name) or {}
            if r.get("house"):
                continue
            players.setdefault(owner(r), {"shop": 0.0, "buyer": 0.0})[kind] = score
    ranked = sorted(players.items(), key=lambda kv: -(kv[1]["shop"] + kv[1]["buyer"]))
    rank = {o: i + 1 for i, (o, _) in enumerate(ranked)}
    us, teacher = players.get(US, {}), players.get(TEACHER, {})
    weakest = None
    for kind, t, w in (("shop", shops, SHOP_W), ("buyer", buyers, BUYER_W)):
        parts = (t.get(US) or (None, {}))[1]
        for k, p in parts.items():
            if p is not None:
                gain = w[k] * (1 - p)             # what moving this part to the top would add
                if weakest is None or gain > weakest[2]:
                    weakest = (kind, k, round(gain, 3))
    return {"players": len(players), "our_rank": rank.get(US), "teacher_rank": rank.get(TEACHER),
            "our_all": round(us.get("shop", 0) + us.get("buyer", 0), 3),
            "teacher_all": round(teacher.get("shop", 0) + teacher.get("buyer", 0), 3),
            "our_shop": {k: round(v, 3) for k, v in ((shops.get(US) or (0, {}))[1]).items() if v is not None},
            "our_buyer": {k: round(v, 3) for k, v in ((buyers.get(US) or (0, {}))[1]).items() if v is not None},
            "biggest_gain": weakest}


def line(s):
    if not s:
        return "rank unavailable"
    ahead = s["our_all"] - s["teacher_all"]
    return (f"Players #{s['our_rank']}/{s['players']} (ALL {s['our_all']}), q00 #{s['teacher_rank']} ({s['teacher_all']}): "
            f"{'ahead' if ahead >= 0 else 'behind'} by {abs(ahead):.3f}; most to gain: {s['biggest_gain']}")


def fetch():
    import httpx
    return standing(httpx.get("https://market.ourolabs.ai/api/board", timeout=15).json())


if __name__ == "__main__":
    s = fetch()
    print(line(s))
    print(json.dumps(s, ensure_ascii=False))
