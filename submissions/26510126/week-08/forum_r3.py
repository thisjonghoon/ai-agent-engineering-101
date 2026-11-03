"""Forum notes from our buyer: only facts from our own settled deals, with the ledger entries to check them.

Votes on posts written as a buyer are 30% of a buyer's Round 3 score. What other buyers can use is which shops
ship what they claim, what a fair price is against the list price, and which goods broke. So a note is posted
only when there is new settled evidence since the last one, at most once per 5 minutes (the market's limit),
and it says nothing our ledger refs do not show. The kit sends lines of .market/outbox.jsonl.

From 11/3 20:29 the buyer score also counts how many posts the buyer wrote (ALL = 0.5 surplus + 0.3 votes + 0.1 deals
+ 0.1 posts; hidden posts do not count). So when no deal of ours is new for DIGEST_EVERY seconds, the buyer posts a
check of grade claims from the public ledger instead: which shops' settled claims were true and which were not, with
the ledger refs. It helps other buyers (who to trust) without giving away what sells, and is posted only when the
ledger shows at least MIN_CLAIMS settled claims, so a post always carries something checkable.
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
DIGEST_EVERY = 3600  # a ledger claim check when our own deals give nothing new for an hour
MIN_CLAIMS = 10
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
        if m["kind"] == "broken" and m.get("shop") and not m.get("ambiguous"):   # never blame a shop we cannot tell
            parts.append(f"{m['name'][:40]} from {m['shop']} broke after the sale"
                         + (" (warranty covered it)" if m.get("covered") else " (no warranty)"))
    if not parts:                                       # nothing we can state with a shop and a ref
        return None, []
    text = "Buyer notes from our own settled deals (check the refs): " + " | ".join(parts)
    return text[:900], refs[-MAX_REFS:]


def claim_check(entries, names=None):
    """(text, refs) on grade claims in the ledger's recent settles: per shop, true claims out of all, the false ones
    with their refs. Public facts anyone can check; nothing about what sells."""
    names = names or {}
    by = defaultdict(list)
    for e in entries:
        d = e.get("data") or {}
        if e.get("kind") == "settle" and d.get("claim_honest") in (True, False):
            shop = str(d.get("shop") or d.get("payee") or "").rstrip("/")
            by[names.get(shop) or shop.rsplit("/shop/", 1)[-1] or "?"].append((e.get("seq"), d["claim_honest"]))
    total = sum(len(v) for v in by.values())
    if total < MIN_CLAIMS:
        return None, []
    false = sorted(((k, v) for k, v in by.items() if any(h is False for _, h in v)), key=lambda kv: -sum(h is False for _, h in kv[1]))
    clean = sorted((k for k, v in by.items() if len(v) >= 5 and all(h for _, h in v)), key=lambda k: -len(by[k]))
    lie_refs = lambda v: ", ".join(f"#{q}" for q, h in v if h is False)
    parts = [f"{k}: {sum(h is False for _, h in v)} of {len(v)} claims false ({lie_refs(v[-20:])})" for k, v in false[:5]]
    if clean:
        parts.append("all claims true (5+ settles): " + ", ".join(f"{k} {len(by[k])}" for k in clean[:6]))
    refs = [q for k, v in false[:5] for q, h in v if h is False][:MAX_REFS]
    text = f"Grade-claim check from the public ledger, last {total} settled claims (check the refs): " + " | ".join(parts)
    return text[:900], refs


def maybe_post(memory):
    """Queue one forum note when there is something new and the last one is at least EVERY seconds old; with nothing
    new from our own deals for DIGEST_EVERY, a claim check from the ledger."""
    posts = [m for m in memory if m.get("kind") == "forum"]
    if posts and time.time() - posts[-1].get("t", 0) < EVERY:
        return None
    text, refs = note(memory)
    if not text and (not posts or time.time() - posts[-1].get("t", 0) >= DIGEST_EVERY):
        try:
            import market_intel
            entries = market_intel.load_recent(timeout=5.0)
            names = {e["data"]["url"].rstrip("/"): e["data"]["name"] for e in entries
                     if e.get("kind") == "join" and (e.get("data") or {}).get("url") and (e.get("data") or {}).get("name")}
            text, refs = claim_check(entries, names)
        except Exception:
            text, refs = None, []
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
