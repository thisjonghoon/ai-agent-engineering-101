"""Tests for meta_r3's number rules (11/9): one shop number per area a cycle, and the 2 h verdict judged on our share
of the market's paid sales. No model is called; the ledger cache and the logs live in a temp folder."""
import json
import tempfile
import time
from pathlib import Path

import meta_r3 as mr
import metrics_r3

RESULTS = []


def case(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))


def ledger(base, rows):
    (base / ".market").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(exist_ok=True)
    url = "https://ours.example"
    entries = [{"kind": "join", "ts": 0, "data": {"name": metrics_r3.ME, "role": "shop", "url": url}}]
    for i, (ts, shop, amount) in enumerate(rows):
        entries.append({"kind": "settle", "ts": ts, "data": {"shop": url if shop == "us" else "https://other.example",
                                                            "amount": amount, "unit": f"u-{i}"}})
    (base / ".market" / "ledger-recent.json").write_text(json.dumps(entries))


def main():
    cur = {"ask_frac": 0.9, "floor_frac": 0.8, "min_margin": 0.1, "max_list": 600_000, "sku_depth": 3,
           "dear_first": 0.5, "stock_value": 50_000_000}

    # 1. one number per area: the manager's first in each area stays, the rest go back
    s = dict(cur, max_list=900_000, sku_depth=5, dear_first=1.0, min_margin=0.06, ask_frac=0.95)
    out, held = mr.one_per_area(dict(s), cur, ["sku_depth", "max_list", "min_margin", "dear_first", "ask_frac"])
    case("the first merchandising number in the manager's order stays", out["sku_depth"] == 5)
    case("the other merchandising numbers go back", out["max_list"] == 600_000 and out["dear_first"] == 0.5,
         str(out))
    case("one sales number stays beside it", out["min_margin"] == 0.06 and out["ask_frac"] == 0.9, str(out))
    case("the held-back numbers are reported", set(held) == {"max_list", "dear_first", "ask_frac"}, str(held))
    out, held = mr.one_per_area(dict(cur, sku_depth=4), cur, [])
    case("a single change is untouched", out["sku_depth"] == 4 and not held)
    # a held-back ask must not leave the floor above it (guard's floor <= ask rule)
    s = dict(cur, ask_frac=0.85, floor_frac=0.85)
    out, held = mr.one_per_area(dict(s, ask_frac=0.95, floor_frac=0.93), dict(cur, ask_frac=0.9),
                                ["floor_frac", "ask_frac"])
    case("the floor never ends above a held-back ask", out["floor_frac"] <= out["ask_frac"], str(out))

    # 2. market share from the ledger cache: count and value, ours over the market's
    tmp = Path(tempfile.mkdtemp(prefix="meta-r3-"))
    t = time.time() - 3 * 3600
    ledger(tmp, [(t - 3000, "us", 100), (t - 2000, "x", 900), (t - 1000, "x", 1000),
                 (t + 1000, "us", 300), (t + 2000, "x", 300), (t + 9000, "us", 50)])
    ms = metrics_r3.market_share(t - 7200, t, tmp)
    case("share by count", ms["ours"] == 1 and ms["market"] == 3 and abs(ms["share_n"] - 1 / 3) < 1e-3, str(ms))
    case("share by value", abs(ms["share_value"] - 100 / 2000) < 1e-3, str(ms))
    case("no market sales gives no share", metrics_r3.market_share(0, 1, tmp)["share_value"] is None)

    # 3. the 2 h verdict leads with the share, so the hour of day cancels out: we sold 3x more after (the morning
    # rush) but so did the market, so the share is flat even though raw counts tripled
    rows = [(t - 6000, "us", 100), (t - 5000, "x", 900)] + \
           [(t + 100 * i, "us", 100) for i in range(1, 4)] + [(t + 100 * i + 50, "x", 900) for i in range(1, 4)]
    ledger(tmp, rows)
    real_window, real_share = metrics_r3.window, metrics_r3.market_share
    metrics_r3.window = lambda a, b, *x, **k: {"shop_margin_h": 1 if b <= t else 3, "shop_deals_h": 1 if b <= t else 3,
                                                "board_pts_h": None, "outage_min": 0}
    metrics_r3.market_share = lambda a, b, base=tmp: real_share(a, b, tmp)
    mr.NUMBER_TRIALS, mr.CODE_CHANGES = tmp / "logs" / "trials.json", tmp / "logs" / "changes.jsonl"
    mr.NUMBER_TRIALS.write_text(json.dumps([{"t": t, "changes": {"sku_depth": [3, 5]}, "reason": "test"}]))
    try:
        out = mr.number_verdicts(now=t + mr.NUMBER_CHECK + 1)
    finally:
        metrics_r3.window, metrics_r3.market_share = real_window, real_share
    row = json.loads(mr.CODE_CHANGES.read_text().splitlines()[-1])
    case("the verdict leads with the share of the market", str(out[0]).startswith("sku_depth 3 -> 5: share of the "
                                                                             "market's paid value"), str(out))
    case("a rush hour that lifted the whole market reads as a flat share", "(+0%)" in row["verdict"].split(";")[0],
         row["verdict"])
    case("raw margin/h stays as context", "margin/h 1 -> 3 (+200%)" in row["verdict"], row["verdict"])
    case("the ledger row names the share as its metric", row["metric"] == "share_value" and row["share"] == 0.0)
    case("the judged change leaves the queue", json.loads(mr.NUMBER_TRIALS.read_text()) == [])

    print(f"{sum(RESULTS)}/{len(RESULTS)} passed")
    return all(RESULTS)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
