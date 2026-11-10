"""The shop's first move (week-10 LAB): answer "[구합니다]" (wanted) forum posts with what we actually hold.

Why: buyers post what they could not buy (11im, 11/10 20:3x: sofas 7 of 14 orders unmet, processed meat 51 of 85),
and our shop's forum slot (one post per 5 minutes for the shop, separate from the buyer's) was never used. A reply in
the wanted post's thread names the matching SKUs we hold, by grade, with the certificate and the warranty: facts from
inventory.json only, no prices (they move with every talk), no claims about other shops.

Goal guessed: the poster wants certified A/B units of that category now. Chance right: high (stated by the poster).
Cost if wrong: one reply in an otherwise unused slot. Number to watch: our settles in the replied categories, and the
replies' likes/dislikes (baseline written to logs/wanted_r3_baseline.json when the module first runs).

Called from buyer_r3 once per order (cheap: reads forum.json and inventory.json, writes at most one outbox line).
"""
import json
import os
import re
import time
from pathlib import Path

MD = Path(os.environ.get("MARKET_DIR") or Path(__file__).resolve().parent / ".market")   # as forum_r3
US = "thisjonghoon"
STATE = "wanted_r3.json"
WANTED = re.compile(r"\[구합니다\]|구합니다|\bWTB\b|\bwanted\b", re.I)
LEAF = re.compile(r"\]\s*([^:：\n]{2,40})[:：]")
MAX_AGE = 3 * 3600          # answer only fresh wanted posts
GAP = 330                   # the shop may post once per 5 minutes; a margin over 300 s
WARRANTY_H = 72


def read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def leaf(category):
    return (category or "").split(">")[-1].strip()


def matches(units, want):
    """Our A/B goods (C carries no warranty and most kits do not pay for it) and certified food in that category."""
    out = {}
    for u in units:
        if leaf(u.get("category")) != want or u.get("grade") in (None, "expired", "C"):
            continue
        if u.get("kind") == "food" and not u.get("cert"):
            continue
        k = u["sku"]
        row = out.setdefault(k, {"name": u.get("name") or k, "kind": u.get("kind"), "A": 0, "B": 0})
        row[u["grade"]] = row.get(u["grade"], 0) + 1
    return sorted(out.items(), key=lambda kv: -(kv[1]["A"] + kv[1]["B"]))


def reply_text(post, want, rows):
    parts = []
    for sku, r in rows[:3]:
        g = " · ".join(f"{g} {r[g]}개" for g in ("A", "B") if r.get(g))
        parts.append(f"{r['name'][:30]} ({sku}) {g}")
    goods = any(r["kind"] == "goods" for _, r in rows[:3])
    terms = "모든 유닛에 시장 인증서" + (f", A/B 상품은 {WARRANTY_H}시간 보증" if goods else ", 남은 유통시간은 첫 답변에 적어 드립니다")
    return (f"[재고 있습니다] {want}: 지금 {US} 가게에 " + "; ".join(parts) + f". {terms}. "
            f"SKU로 물어보시면 바로 호가를 드립니다.")


def maybe_reply(now=None, md=None):
    """Write at most one outbox reply; returns the line written or None."""
    md = Path(md) if md else MD
    now = now or time.time()
    st = read(md / STATE, {"answered": [], "last": 0})
    if now - st.get("last", 0) < GAP:
        return None
    forum = read(md / "forum.json", [])
    posts = forum if isinstance(forum, list) else forum.get("posts") or []
    units = (read(md / "inventory.json", {}) or {}).get("units") or []
    for p in sorted(posts, key=lambda p: -p.get("ts", 0)):
        if (p.get("author") == US or p.get("thread") or p.get("id") in st["answered"]
                or now - p.get("ts", 0) > MAX_AGE or not WANTED.search(p.get("text") or "")):
            continue
        m = LEAF.search(p.get("text") or "")
        if not m:
            continue
        want = m.group(1).strip()
        rows = matches(units, want)
        st["answered"] = (st["answered"] + [p["id"]])[-200:]
        if not rows:
            continue                                   # nothing of ours fits: say nothing
        line = {"post": reply_text(p, want, rows), "refs": [], "thread": p["id"], "as": "shop"}
        with open(md / "outbox.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        st["last"] = now
        st.setdefault("sent", []).append({"t": now, "thread": p["id"], "author": p.get("author"), "want": want,
                                          "skus": [k for k, _ in rows[:3]]})
        tmp = md / f".{STATE}.tmp"
        tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, md / STATE)
        return line
    tmp = md / f".{STATE}.tmp"
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, md / STATE)
    return None
