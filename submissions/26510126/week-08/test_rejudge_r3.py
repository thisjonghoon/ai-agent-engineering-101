"""Tests for rejudge_r3: past number verdicts re-judged on the market share, or marked UNVERIFIED when no data
reaches back. The ledger cache, the verdict ledger and the output live in a temp folder; no model is called."""
import json
import tempfile
import time
from pathlib import Path

import metrics_r3
import rejudge_r3

RESULTS = []


def case(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))


def main():
    base = Path(tempfile.mkdtemp(prefix="rejudge-"))
    (base / ".market").mkdir()
    (base / "logs").mkdir()
    now = time.time()
    t = now - 3 * 3600                                   # a change 3 h ago: its 2 h after have run
    url = "https://ours.example"
    sale = lambda ts, shop, amount, u: {"kind": "settle", "ts": ts, "data": {"shop": shop, "amount": amount, "unit": u}}
    entries = [{"kind": "join", "ts": 0, "data": {"name": metrics_r3.ME, "role": "shop", "url": url}},
               sale(now - 6 * 3600, "https://x.example", 1, "u-0"),            # the cache reaches back 6 h
               sale(t - 3000, url, 100, "u-1"), sale(t - 2000, "https://x.example", 900, "u-2"),
               sale(t + 1000, url, 300, "u-3"), sale(t + 2000, "https://x.example", 700, "u-4")]
    (base / ".market" / "ledger-recent.json").write_text(json.dumps(entries))
    rows = [{"t": now - 30 * 3600, "source": "inner loop (number)", "change": "dear_depth 4 -> 5", "measured": 0.12},
            {"t": t, "source": "inner loop (number)", "change": "dear_depth 5 -> 4, max_list 900000 -> 600000",
             "measured": -0.1},
            {"t": now - 600, "source": "inner loop (number)", "change": "ask_frac 0.7 -> 0.75"},
            {"t": t, "source": "inner loop (number)", "change": "fast guard revert: x 1 -> 0"}]
    (base / "logs" / "code_changes_r3.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    added = rejudge_r3.update(base, now)
    done = json.loads((base / rejudge_r3.OUT).read_text())
    old, new = done.get(rejudge_r3.key(rows[0])), done.get(rejudge_r3.key(rows[1]))
    case("a verdict no data reaches back to is UNVERIFIED", old and old["status"] == "unverified", old)
    case("a raw -10% that the market share says rose is reversed", new and new["status"] == "reversed"
         and new["share"] == 2.0, new)
    case("a change whose 2 h have not run waits, a fast guard revert is no verdict", added == 2, added)
    case("a second pass adds nothing", rejudge_r3.update(base, now) == 0)
    text = rejudge_r3.memory_text(base)
    case("the memory names each number with its status, newest numbers first",
         "- dear_depth:" in text and "UNVERIFIED (raw margin +12%" in text and "VERIFIED reversed" in text
         and text.index("- dear_depth") < text.index("- max_list") if "- max_list" in text else False, text)
    case("the memory tells the team UNVERIFIED rows are weak evidence", "weak evidence" in text)
    case("the memory stays under its cap", len(rejudge_r3.memory_text(base, max_chars=300)) <= 300)
    print(f"{sum(RESULTS)}/{len(RESULTS)} passed")
    return all(RESULTS)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
