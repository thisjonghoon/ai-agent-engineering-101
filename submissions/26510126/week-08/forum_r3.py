"""Forum notes from our buyer: only facts from our own settled deals, with the ledger entries to check them.

Votes on posts written as a buyer are 30% of a buyer's Round 3 score. What other buyers can use is which shops
ship what they claim, what a fair price is against the list price, and which goods broke. So a note is posted
only when there is new settled evidence since the last one, at most once per 5 minutes (the market's limit),
and it says nothing our ledger refs do not show. The kit sends lines of .market/outbox.jsonl.
"""
import json
import os
import statistics
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
MD = Path(os.environ.get("MARKET_DIR") or HERE / ".market")
MEMORY = HERE / "memory.jsonl"
EVERY = 300          # seconds between posts (the market allows one per 5 minutes)
MAX_REFS = 10


def note(memory):
    """(text, refs) about the settled deals and breakages recorded after our last post (memory is append-only,
    so "after" is the line order, not a clock), or (None, [])."""
    last = max((i for i, m in enumerate(memory) if m.get("kind") == "forum"), default=-1)
    new = [m for m in memory[last + 1:] if m.get("round") == 3 and m.get("kind") in ("settled", "broken")]
    settled = [m for m in new if m["kind"] == "settled"]
    if not settled and not any(m["kind"] == "broken" for m in new):
        return None, []
    by = defaultdict(list)
    for m in settled:
        by[m.get("shop") or "?"].append(m)
    parts, refs = [], []
    for shop, ms in sorted(by.items(), key=lambda kv: -len(kv[1])):
        shares = [m["price"] / m["list_price"] for m in ms if m.get("price") and m.get("list_price")]
        claims = [m for m in ms if m.get("claim")]
        honest = sum(m.get("claim_honest") is True for m in claims)
        line = f"{shop}: {len(ms)} settled"
        if shares:
            line += f", paid {statistics.median(shares):.0%} of list price (median)"
        if claims:
            line += f", grade claims true {honest}/{len(claims)}"
        lies = [m for m in claims if m.get("claim_honest") is False]
        if lies:
            line += "; " + ", ".join(f"claimed {m['claim']} shipped {m.get('grade')} (#{m.get('ledger')})" for m in lies[:2])
        parts.append(line)
        refs += [m["ledger"] for m in ms if m.get("ledger")]
    for m in new:
        if m["kind"] == "broken" and m.get("shop"):
            parts.append(f"{m['name'][:40]} from {m['shop']} broke after the sale"
                         + (" (warranty covered it)" if m.get("covered") else " (no warranty)"))
    text = "Buyer notes from our own settled deals (check the refs): " + " | ".join(parts)
    return text[:900], refs[-MAX_REFS:]


def maybe_post(memory):
    """Queue one forum note when there is something new and the last one is at least EVERY seconds old."""
    posts = [m for m in memory if m.get("kind") == "forum"]
    if posts and time.time() - posts[-1].get("t", 0) < EVERY:
        return None
    text, refs = note(memory)
    if not text:
        return None
    MD.mkdir(exist_ok=True)
    with open(MD / "outbox.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"post": text, "refs": refs, "as": "buyer"}, ensure_ascii=False) + "\n")
    entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "t": time.time(), "kind": "forum", "round": 3,
             "post": text, "refs": refs}
    with open(MEMORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    memory.append(entry)
    return entry
