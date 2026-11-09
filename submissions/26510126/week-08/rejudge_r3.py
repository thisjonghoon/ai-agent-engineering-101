"""Re-judge the team's past number verdicts on the measure the board pays for, and mark what cannot be re-judged.

11/9: the 2 h verdicts on the team's numbers compared our raw margin/h before and after a change until 11:13 that day,
so each read the hour of day as much as the number. The team kept them as facts: 31 meta decisions held a number
because it had been "judged in both directions". An agent's memory carries a wrong note into every later session
until something re-checks it (Anthropic, "components of agent memory", 2026: a mislabelled map note sent the agent
down the same ledge three times until a review of the transcript fixed the note).

Each verdict row is re-judged once its two hours have run: our share of the market's paid value over the same
hours, and board points/h net of the market's own change (metrics_r3.shop_side: the ledger cache, else the
10-minute buckets). The result is VERIFIED (confirmed, reversed, or flat within NOISE) or UNVERIFIED when no data
reaches back to the row (the cache keeps ~6 h; the buckets start 11/9). Results are cached in logs/rejudged_r3.json;
the verdict ledger itself is never edited. memory_text() is what the team reads each cycle.
"""
import json
import time
from pathlib import Path

import metrics_r3

HERE = Path(__file__).resolve().parent
OUT = Path("logs") / "rejudged_r3.json"
CHANGES = Path("logs") / "code_changes_r3.jsonl"
SPAN = 2 * 3600          # the number verdict's span (meta_r3.NUMBER_CHECK)
NOISE = 0.05             # a move under 5% either way is flat


def key(r):
    return f"{r.get('t', 0):.0f}|{r.get('change')}"


def rows(base=HERE):
    """The number verdict rows (fast guard reverts are not verdicts on a change)."""
    return [x for x in metrics_r3.jl(Path(base) / CHANGES) if x.get("source") == "inner loop (number)"
            and not str(x.get("change", "")).startswith("fast guard")]


def side(t0, t1, base):
    """Board points/h, our value share and the market's paid value over [t0, t1), or None without data."""
    s = metrics_r3.shop_side(t0, t1, base)
    if not s or not s["mkt_value"]:
        return None
    w = metrics_r3.window(t0, t1, base)
    hours = max((t1 - t0 - (w.get("outage_min") or 0) * 60) / 3600, 0.25)
    pts = metrics_r3.board_points_h(s["ours_margin"] / hours, s["ours_value"] / hours, w.get("buyer_paid_h") or 0,
                                    w.get("buyer_saved_deal"))
    return {"pts": pts, "share_value": s["ours_value"] / s["mkt_value"], "mkt_value": s["mkt_value"],
            "ours_n": s["ours_n"], "mkt_n": s["mkt_n"]}


def judge(r, base=HERE):
    """The re-judged result for one verdict row, or None when no data reaches back to it."""
    t = r["t"]
    a, b = side(t - SPAN, t, base), side(t, t + SPAN, base)
    if not a or not b:
        return None
    share = (b["share_value"] - a["share_value"]) / a["share_value"] if a["share_value"] else None
    net = None
    if a["pts"] and b["pts"] is not None:          # board points net of the market's own change in paid value
        net = (b["pts"] / (b["mkt_value"] / a["mkt_value"]) - a["pts"]) / abs(a["pts"])
    aim = net if net is not None else share
    orig = r.get("measured") if isinstance(r.get("measured"), (int, float)) else r.get("share")
    if aim is None:
        return None
    if abs(aim) < NOISE:
        status = "flat"
    elif not isinstance(orig, (int, float)) or abs(orig) < NOISE:
        status = "up" if aim > 0 else "down"
    else:
        status = "confirmed" if (aim > 0) == (orig > 0) else "reversed"
    return {"status": status, "aim": round(aim, 3), "share": round(share, 3) if share is not None else None,
            "net_pts": round(net, 3) if net is not None else None, "orig": orig,
            "sales": f"{a['ours_n']}/{a['mkt_n']} -> {b['ours_n']}/{b['mkt_n']}"}


def earliest(base=HERE):
    """The earliest time any data reaches back to: the first bucket or the cache's first settle."""
    ts = [x.get("t") for x in metrics_r3.jl(Path(base) / metrics_r3.BUCKETS)[:1]]
    ts += [min((e["ts"] for e in metrics_r3._settles(base)), default=None)]
    ts = [x for x in ts if x]
    return min(ts) if ts else None


def update(base=HERE, now=None):
    """Re-judge the rows whose span has run and are not in the cache yet; mark those no data reaches as UNVERIFIED.
    Returns how many rows were added."""
    base, now = Path(base), now or time.time()
    path = base / OUT
    try:
        done = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        done = {}
    first, added = earliest(base), 0
    for r in rows(base):
        k = key(r)
        if k in done or now - r["t"] < SPAN:
            continue
        res = judge(r, base) if first and r["t"] - SPAN >= first else None
        if res is None and first and r["t"] - SPAN >= first:
            continue                                    # covered but not measurable yet (no market sales): retry
        done[k] = res or {"status": "unverified", "orig": r.get("measured")}
        added += 1
    if added:
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    return added


def note(res):
    """One verdict's re-judged words for the prompt."""
    if not res:
        return "not re-judged yet"
    o = res.get("orig")
    raw = f"raw margin {o:+.0%}" if isinstance(o, (int, float)) else "raw verdict"
    if res["status"] == "unverified":
        return f"UNVERIFIED ({raw})"
    return (f"VERIFIED {res['status']}: board points/h net of the market {res['net_pts']:+.0%}, " if res.get("net_pts")
            is not None else f"VERIFIED {res['status']}: ") + \
        (f"value share {res['share']:+.0%} " if res.get("share") is not None else "") + f"({raw}; {res['sales']} sales)"


def memory_text(base=HERE, per_key=3, max_chars=2500):
    """Per number, its last `per_key` judged changes with their re-judged status, newest numbers first."""
    try:
        done = json.loads((Path(base) / OUT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    by = {}
    for r in rows(base):
        for part in str(r.get("change", "")).split(", "):
            if " -> " in part:
                k, _, rest = part.partition(" ")
                by.setdefault(k, []).append((r["t"], f"{time.strftime('%m/%d %H:%M', time.localtime(r['t']))} "
                                                     f"{rest}: {note(done.get(key(r)))}"))
    lines = []
    for k, items in sorted(by.items(), key=lambda kv: -kv[1][-1][0]):
        lines.append(f"- {k}: " + "; ".join(x for _, x in items[-per_key:]))
    head = ("\nYour numbers' past verdicts, re-judged (memory check): VERIFIED rows were judged again on our share of "
            "the market's paid sales over the same hours; UNVERIFIED rows were judged on raw margin/h before 11/9 "
            "11:13 and read the hour of day, so they are weak evidence, not a reason to hold a number "
            "(\"judged in both directions\" on UNVERIFIED rows proves nothing):\n")
    out = head
    for line in lines:
        if len(out) + len(line) + 1 > max_chars:
            break
        out += line + "\n"
    return out if out != head else ""                   # not even one number fits: say nothing rather than half


if __name__ == "__main__":
    print(metrics_r3.record_buckets(HERE), "buckets filed;", update(HERE), "verdicts re-judged")
    print(memory_text(HERE))
