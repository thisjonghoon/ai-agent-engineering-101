"""What the outer loop's engineer reads before it picks an area: one table per area, counted by code, and which area to
look at first.

The engineer reads files but runs nothing, so on 11/5 it could not count what a hypothesis needs: twice it skipped
("no change backed by counts I could verify"), and the one buyer change it made (17:21) came from counts the supervisor
had put in a note. Its prompt also named one area to look at, so it read only the forum for two cycles. Now code counts
each area here, and focus() ranks the areas by the board points they leave on the table, discounted by how often the
loop already tried them in the last day without a gain, so the engineer explores where the data points rather than
where a sentence told it to.

Areas and the files the code loop may change there:
  buyer   buyer_r3.py, buyer.py          buyer surplus (0.5) and deals (0.1)
  forum   forum_r3.py                     buyer forum votes (0.3) and posts (0.1)
  stock   restock_r3.py, demand_r3.py,    shop book (0.5) and revenue (0.3): what and how much the shop stocks
          prices_r3.py
"""
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

import metrics_r3

HERE = Path(__file__).resolve().parent
AREAS = {
    "buyer": {"files": {"buyer_r3.py", "buyer.py"}, "terms": {("buyer", "surplus"), ("buyer", "deals")},
              "words": ("buyer", "order", "haggl", "offer", "walk")},
    "forum": {"files": {"forum_r3.py"}, "terms": {("buyer", "forum"), ("buyer", "posts")}, "words": ("forum", "post")},
    "stock": {"files": {"restock_r3.py", "demand_r3.py", "prices_r3.py"},
              "terms": {("shop", "book"), ("shop", "revenue"), ("shop", "profit")},
              "words": ("restock", "stock", "supply", "price")},
}
BANDS = ((0, 30_000, "<30k"), (30_000, 100_000, "30-100k"), (100_000, 300_000, "100-300k"), (300_000, 10**12, "300k+"))
TAIL = 8_000_000                   # bytes of the kit log read for the buyer's talks, about the last 7 hours


def jl(path):
    try:
        return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def band(price):
    return next(name for lo, hi, name in BANDS if lo <= (price or 0) < hi)


def area_of(row):
    """The area a code attempt or ledger row belongs to: by the files it changed, else by its words."""
    files = set((row.get("spec") or {}).get("files") or row.get("files") or [])
    for name, a in AREAS.items():
        if files & a["files"]:
            return name
    text = f"{row.get('result', '')} {row.get('idea', '')} {row.get('change', '')}".lower()
    hits = {name: sum(w in text for w in a["words"]) for name, a in AREAS.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] else None


def gained(row):
    """Did a judged automatic change move its own metric by more than 3%? (its verdict reads 'measured +12%')"""
    m = re.search(r"measured ([+-]\d+)%", str(row.get("verdict") or ""))
    return bool(m) and int(m.group(1)) > 3


def focus(base=HERE, board=None, now=None):
    """[(area, priority, points lost, tries in 24 h, gains)] with the area to look at first on top."""
    now = now or time.time()
    if board is None:
        try:
            board = json.loads((Path(base) / "logs" / "board" / "board-round3.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            board = {}
    gap = metrics_r3.score_gap(board)
    attempts = [a for a in jl(Path(base) / "logs" / "code_attempts_r3.jsonl") if now - a.get("t", 0) < 86400]
    ledger = [x for x in jl(Path(base) / "logs" / "code_changes_r3.jsonl")
              if now - x.get("t", 0) < 86400 and x.get("source") == "meta (auto)"]
    out = []
    for name, a in AREAS.items():
        lost = round(sum(row[5] for row in gap if (row[0], row[1]) in a["terms"]), 3)
        tries = sum(area_of(x) == name for x in attempts)
        gains = sum(area_of(x) == name and gained(x) for x in ledger)
        # a try that gained counts half: the area still pays, the loop should not leave it for good
        out.append((name, round(lost / (1 + tries - 0.5 * gains), 3), lost, tries, gains))
    return sorted(out, key=lambda x: -x[1])


def buyer_digest(base=HERE, hours=12, now=None):
    now = now or time.time()
    base = Path(base)
    orders = {d["order"]: d for d in jl(base / "logs" / "demand_r3.jsonl")
              if d.get("event") == "order" and now - d.get("t", 0) < hours * 3600 and d.get("order")}
    mem = jl(base / "memory.jsonl")
    settled = {m["order"]: m for m in mem if m.get("kind") == "settled" and m.get("order") in orders}
    lines = [f"Orders, last {hours} h, by reference price: orders, share closed, surplus (list - price) of the closed"]
    total = sum(m["list_price"] - m["price"] for m in settled.values() if m.get("list_price")) or 1
    for lo, hi, name in BANDS:
        os_ = [o for o, d in orders.items() if lo <= (d.get("ref") or 0) < hi]
        got = [settled[o] for o in os_ if o in settled]
        s = sum(m["list_price"] - m["price"] for m in got if m.get("list_price"))
        lines.append(f"  {name}: {len(os_)} orders, closed {len(got) / max(len(os_), 1):.0%}, surplus {s:,} "
                     f"({s / total:.0%} of all)")
    # the talks: market-kit.log, from each CHOOSE (its 'paying at most' is our cap) to the talk's OUT line
    try:
        path = base / "logs" / "market-kit.log"
        with path.open("rb") as f:
            f.seek(max(path.stat().st_size - TAIL, 0))
            text = f.read().decode("utf-8", "ignore")
    except OSError:
        text = ""
    talks, cur = [], None
    for line in text.splitlines():
        if "[buyer]" not in line:
            continue
        if "CHOOSE:" in line:
            m = re.search(r"paying at most (\d+)", line)
            cur = {"cap": int(m.group(1)) if m else None, "asks": [], "calls": 0, "t0": line[:8], "end": None}
            talks.append(cur)
        elif cur is None:
            continue
        elif " ASK: " in line:
            m = re.search(r"ASK: (\d+)", line)
            if m:
                cur["asks"].append(int(m.group(1)))
        elif " HARNESS: try" in line:
            cur["calls"] += 1
        elif " OUT: " in line and cur["end"] is None:
            cur["end"], cur["t1"] = line.split("OUT: ", 1)[1][:40], line[:8]

    def secs(x):
        a, b = (sum(int(p) * k for p, k in zip(t.split(":"), (3600, 60, 1))) for t in (x["t0"], x["t1"]))
        return (b - a) % 86400

    talks = [x for x in talks if x["end"] and x["cap"] and x["asks"]]
    if talks:
        won = lambda x: x["end"].startswith("receipt")
        lines.append(f"Talks in the kit log (about the last {TAIL // 1_000_000} MB): {len(talks)}, closed "
                     f"{sum(map(won, talks))}, model calls {sum(x['calls'] for x in talks)}")
        ends = Counter(re.sub(r"[\d{'].*", "", x["end"]).strip() for x in talks if not won(x))
        lines.append("  how the unclosed ended: " + ", ".join(f"{k or '?'} {n}" for k, n in ends.most_common(5)))
        for label, test in (("first ask over 1.5x our cap", lambda x: x["asks"][0] > 1.5 * x["cap"]),
                            ("first ask 1.1-1.5x our cap", lambda x: 1.1 * x["cap"] < x["asks"][0] <= 1.5 * x["cap"]),
                            ("the shop repeated an ask above our cap", lambda x: len(x["asks"]) >= 2
                             and x["asks"][0] == x["asks"][1] > x["cap"]),
                            ("first ask within our cap", lambda x: x["asks"][0] <= x["cap"])):
            g = [x for x in talks if test(x)]
            if g:
                lines.append(f"  {label}: {len(g)} talks, closed {sum(map(won, g)) / len(g):.0%}, "
                             f"median {statistics.median(map(secs, g)):.0f} s, {sum(map(secs, g)) / 60:.0f} min in all")
    return "\n".join(lines)


def stock_digest(base=HERE, hours=6, now=None):
    now = now or time.time()
    base = Path(base)
    sold = [x for x in jl(base / "logs" / "talks_r3.jsonl") if x.get("price") and now - x.get("t", 0) < hours * 3600]
    lines = [f"Our shop's sales, last {hours} h, by list price: sold an hour, price and cost as a share of list, "
             "margin a unit"]
    for lo, hi, name in BANDS:
        g = [x for x in sold if lo <= (x.get("list_price") or 0) < hi]
        if g:
            lines.append(f"  {name}: {len(g) / hours:.1f}/h, price {statistics.median(x['price'] / x['list_price'] for x in g):.2f}"
                         f", cost {statistics.median(x['cost'] / x['list_price'] for x in g):.2f}, "
                         f"margin {statistics.median(x['price'] - x['cost'] for x in g):,.0f}")
    try:
        inv = json.loads((base / ".market" / "inventory.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        inv = {}
    units = inv.get("units") or []
    if units:
        by = defaultdict(lambda: [0, 0])
        for u in units:
            b = by[band(u.get("list_price"))]
            b[0] += 1
            b[1] += u.get("cost") or 0
        old = [u for u in units if u.get("kind") == "goods" and now - (u.get("supplied_at") or now) > 86400]
        cats = {u.get("category") for u in units}
        lines.append(f"In stock now: {len(units)} units at cost {sum(u.get('cost') or 0 for u in units):,} in "
                     f"{len(cats)} categories; cash {inv.get('balance', 0):,}; " +
                     ", ".join(f"{k} {v[0]} units ({v[1]:,})" for k, v in sorted(by.items())))
        lines.append(f"  goods unsold for over a day: {len(old)} units, cost {sum(u.get('cost') or 0 for u in old):,}")
        surge = inv.get("surge") or []
        if surge:
            lines.append(f"  SKUs under the market's supply surge now: {len(surge)} (top: " + ", ".join(
                f"{x.get('name', '')[:20]} x{x.get('factor')}" for x in surge[:3] if isinstance(x, dict)) + ")")
    return "\n".join(lines)


def forum_digest(base=HERE, hours=24, now=None):
    now = now or time.time()
    base = Path(base)
    ours = [m for m in jl(base / "memory.jsonl") if m.get("kind") == "forum" and now - (m.get("t") or 0) < hours * 3600]
    try:
        posts = json.loads((base / ".market" / "forum.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        posts = []
    posts = posts if isinstance(posts, list) else posts.get("posts", []) if isinstance(posts, dict) else []
    votes = {p.get("text", "")[:40]: (p.get("likes") or 0, p.get("dislikes") or 0) for p in posts
             if isinstance(p, dict) and p.get("author") == metrics_r3.ME}
    by = defaultdict(lambda: [0, 0, 0, 0])
    for m in ours:
        b = by[m.get("format") or "?"]
        b[0] += 1
        v = votes.get((m.get("post") or "")[:40])
        if v:
            b[1], b[2], b[3] = b[1] + 1, b[2] + v[0], b[3] + v[1]
    lines = [f"Our buyer's posts, last {hours} h, by kind: posts, of them still in forum.json (the newest 100 posts), "
             "likes and dislikes on those"]
    lines += [f"  {k}: {n} posts, {seen} visible, +{lk} / -{dk}" for k, (n, seen, lk, dk) in sorted(by.items())]
    others = Counter()
    for p in posts:
        if isinstance(p, dict) and p.get("role") == "buyer" and p.get("author") != metrics_r3.ME:
            others[p.get("author")] += (p.get("likes") or 0) - (p.get("dislikes") or 0)
    if others:
        lines.append("  other buyers' net votes in forum.json, the top 3: " +
                     ", ".join(f"{a} {v:+d}" for a, v in others.most_common(3)))
    return "\n".join(lines)


def for_prompt(base=HERE):
    rows = focus(base)
    head = ["Areas, the one to look at first on top (priority = board points it loses / (1 + tries in the last day, a "
            "try that gained counting half)):"]
    head += [f"  {a}: priority {p}, points lost {lost}, tries {t}, gains {g}" for a, p, lost, t, g in rows]
    parts = {"buyer": buyer_digest, "forum": forum_digest, "stock": stock_digest}
    body = []
    for a, *_ in rows:
        try:
            body.append(f"[{a}]\n" + parts[a](base))
        except Exception as e:                          # one broken table must not cost the cycle
            body.append(f"[{a}] (could not count: {type(e).__name__})")
    return "\n".join(head) + "\n\n" + "\n\n".join(body)


if __name__ == "__main__":
    import sys
    print(for_prompt(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE))
