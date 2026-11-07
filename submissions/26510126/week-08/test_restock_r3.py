"""Offline check of restock_r3.forum_wanted against forum floods and bait (no market).

    python test_restock_r3.py      # prints PASS/FAIL per case

Round 3 lets agents post without being asked. A "wanted" post raises a category in our restock, so a flood of them
could make the shop buy stock that never sells. Cases: one author posting fifty times counts once; many authors count
at most WANT_CAP; a post naming every category, a very long post and our own posts count nothing; old posts expire.
"""
import json
import tempfile
import time
from pathlib import Path

import restock_r3

restock_r3.STRATEGY = Path(tempfile.mkdtemp(prefix="restock-strategy-")) / "none.json"   # the defaults, not the live file

NOW = time.time()
DEMAND = [{"item": "김치", "category": "식품>김치"}, {"item": "의자", "category": "가구>의자"},
          {"item": "침대", "category": "가구>침대"}, {"item": "라면", "category": "식품>라면"},
          {"item": "생수", "category": "식품>생수"}]
CATALOG = {"G0000abcd": {"category": "가구>침대"}}
ok = []


def case(name, cond, detail=""):
    ok.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name}{': ' + str(detail) if detail else ''}", flush=True)


def wanted(posts):
    md = Path(tempfile.mkdtemp(prefix="restock-"))
    (md / "forum.json").write_text(json.dumps(posts, ensure_ascii=False), encoding="utf-8")
    return restock_r3.forum_wanted(md, DEMAND, CATALOG, NOW)


post = lambda who, text, age=60: {"author": who, "text": text, "ts": NOW - age}
w = wanted([post("spammer", "김치 구합니다!") for _ in range(50)])
case("one author posting fifty times counts once", w.get("식품>김치") == 1, dict(w))
w = wanted([post(f"buyer{i}", "의자 구합니다") for i in range(10)])
case(f"ten authors count at most {restock_r3.WANT_CAP}", w.get("가구>의자") == restock_r3.WANT_CAP, dict(w))
w = wanted([post("lister", "구합니다: 김치 의자 침대 라면 생수 전부")])
case("a post naming more than three categories counts nothing", not w, dict(w))
w = wanted([post("long", "김치 구합니다 " + "x" * 5000)])
case("a post over the length cap counts nothing", not w, dict(w))
w = wanted([post(restock_r3.US, "침대 구합니다")])
case("our own post counts nothing", not w, dict(w))
w = wanted([post("old", "라면 구합니다", age=7 * 3600)])
case("a post older than six hours counts nothing", not w, dict(w))
w = wanted([post("sku", "looking for G0000abcd"), "not a dict", {"text": None}])
case("a SKU in a post maps to its category; malformed posts are skipped", w.get("가구>침대") == 1, dict(w))

# food first, and goods held under goods_frac of stock_value (goods pay storage and may break)
md = Path(tempfile.mkdtemp(prefix="restock-main-"))
demand = [{"item": f"g{i}", "category": f"G>{i}", "kind": "goods", "median_price": 50000} for i in range(30)]
demand += [{"item": f"f{i}", "category": f"F>{i}", "kind": "food", "median_price": 10000} for i in range(30)]
catalog = {f"SG{i}": {"category": f"G>{i}", "kind": "goods", "list_price": 50000, "name": f"g{i}"} for i in range(30)}
catalog.update({f"SF{i}": {"category": f"F>{i}", "kind": "food", "list_price": 10000, "shelf_hours": 200, "name": f"f{i}"}
                for i in range(30)})
held = [{"unit": f"u{i}", "sku": f"SG{i}", "category": f"G>{i}", "kind": "goods", "grade": "B", "cost": 30000,
         "supplied_at": NOW, "expires_at": None} for i in range(20)]               # 600,000 of goods already
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 4_000_000, "units": held}), encoding="utf-8")
(md / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
(md / "demand.json").write_text(json.dumps(demand), encoding="utf-8")
restock_r3.ledger_settles = lambda after: ([], after)
import contextlib, io, sys
out = io.StringIO()
sys.argv = ["restock_r3.py", "--state", str(md)]
with contextlib.redirect_stdout(out):
    restock_r3.main()
buy = json.loads(out.getvalue().splitlines()[-1])["buy"]
kinds = [catalog[b["sku"]]["kind"] for b in buy]
case("food first: with 600,000 of goods held (cap 0.35 x 2,000,000 = 700,000), the buy is food plus at most "
     "one 30,000 goods unit", kinds.count("food") >= 9 and kinds.count("goods") <= 1, {"food": kinds.count("food"), "goods": kinds.count("goods")})

# the cash floor holds under any reserve the meta-harness sets: reserve 0 and a huge stock cap still keep 700,000
real = restock_r3.strategy
restock_r3.strategy = lambda: dict(real(), reserve_cash=0, stock_value=10_000_000)
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 800_000, "units": []}), encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
res = json.loads(out.getvalue().splitlines()[-1])
spent = sum(catalog[b["sku"]]["list_price"] * restock_r3.EST_COST * b["qty"] for b in res["buy"])
case("reserve 0 from the meta-harness: code still keeps 700,000 (balance 800,000, so at most 100,000 spent)",
     0 < spent <= 100_000, {"spent (estimated)": spent, "lines": len(res["buy"])})
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 650_000, "units": []}), encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
res = json.loads(out.getvalue().splitlines()[-1])
case("under the cash floor nothing is bought", res["buy"] == [] and "cash floor 700000" in res["why"], res["why"])
restock_r3.strategy = real

# runs 20 minutes apart (the rule may change): depth scales up to 4x where things sell, and the market's own
# bankruptcy line from inventory.json sets the cash floor
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 4_000_000, "units": [], "bankrupt_line": 900_000}),
                                   encoding="utf-8")
(md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 1200,
                                                   "score": {"F>1": 8.0}, "sku_score": {}}), encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
res = json.loads(out.getvalue().splitlines()[-1])
q = {b["sku"]: b["qty"] for b in res["buy"]}
case("runs 20 min apart: depth x4 for a selling food category (4 units, not 2)", q.get("SF1") == 4 and "x4.0" in res["why"],
     {"SF1": q.get("SF1"), "why": res["why"]})
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 1_000_000, "units": [], "bankrupt_line": 900_000}),
                                   encoding="utf-8")
restock_r3.strategy = lambda: dict(real(), reserve_cash=0)        # the default 1,500,000 reserve would hide the line
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
restock_r3.strategy = real
res = json.loads(out.getvalue().splitlines()[-1])
case("a raised bankruptcy line (900,000) raises the cash floor to 1,100,000: nothing bought at 1,000,000",
     res["buy"] == [] and "cash floor 1100000" in res["why"], res["why"])

# supply windows (agent.md 11/3 20:23): closed -> no lines (the kit would wait 90 s per line); open -> deeper
fresh_state = json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {"F>1": 8.0}, "sku_score": {}})
for is_open in (False, True):
    (md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 4_000_000, "units": [],
        "restock": {"open": is_open, "opens_at": time.time() + 600, "closes_at": time.time() + 780}}), encoding="utf-8")
    (md / "restock_state.json").write_text(fresh_state, encoding="utf-8")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        restock_r3.main()
    res = json.loads(out.getvalue().splitlines()[-1])
    if is_open:
        q = {b["sku"]: b["qty"] for b in res["buy"]}
        case("window open: depth x2 for a selling food category (4 units), lines bought", q.get("SF1") == 4 and len(res["buy"]) == restock_r3.DEFAULTS["lines"],
             {"SF1": q.get("SF1"), "lines": len(res["buy"]), "why": res["why"]})
    else:
        st_after = json.loads((md / "restock_state.json").read_text())
        case("window closed: no lines, and the scores still update", res["buy"] == [] and "supply closed until" in res["why"]
             and st_after["t"] > time.time() - 5, res["why"])

# hidden demand (demand_r3.py): orders our buyer saw point at a reference price; restock stocks the SKU nearest it
# and gives the category depth, even with no settle anywhere
import demand_r3
demand_r3.LOG = md / "demand_r3.jsonl"
cat3 = dict(catalog, **{f"SH{i}": {"category": "F>hot", "kind": "food", "list_price": p, "shelf_hours": 200, "name": f"h{i}"}
                        for i, p in enumerate((5000, 10000, 20000))})
(md / "catalog.json").write_text(json.dumps(cat3), encoding="utf-8")
(md / "demand.json").write_text(json.dumps(demand + [{"item": "hot", "category": "F>hot", "kind": "food", "median_price": 10000}]),
                                encoding="utf-8")
for i in range(6):                                       # bands around 20,000: acceptable 10,000 and 20,000 (ref 15,000)
    demand_r3.record_order({"order": f"o{i}", "category": "F>hot", "kind": "food", "acceptable": ["SH1", "SH2"]}, cat3,
                           [{"offers": [{"sku": "SH1", "qty": 1}]}])
demand_r3.record_ask("I want to buy h2 (G0000beef)", cat3, have=False)   # not in the catalog: no SKU, still logged
cw, sw, ref = demand_r3.signals()
case("orders become category weight, a nearest-reference SKU and a reference price",
     round(cw["F>hot"]) == 6 and sw["SH1"] + sw["SH2"] >= 5.9 and round(ref["F>hot"]) == 15000, (dict(cw), dict(sw), ref))
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 4_000_000, "units": []}), encoding="utf-8")
(md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {}, "sku_score": {}}),
                                       encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
res = json.loads(out.getvalue().splitlines()[-1])
q = {b["sku"]: b["qty"] for b in res["buy"]}
st3 = json.loads((md / "restock_state.json").read_text())
case("restock buys the ordered category first, at the reference price (not the 10,000 median alone), with depth",
     res["buy"][0]["sku"] in ("SH1", "SH2") and sum(q.get(k, 0) for k in ("SH1", "SH2")) >= 3,
     {"first": res["buy"][0], "hot": {k: q.get(k) for k in ("SH0", "SH1", "SH2")}})
case("order weights are not written into the decaying scores (no compounding)", "F>hot" not in st3.get("score", {}), st3.get("score"))
# the market's surge (11/4 21:14): a SKU priced over surge_max x its plain cost is left out, the next one taken
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 4_000_000, "units": [],
                                              "surge": [{"sku": "SH1", "units": 300, "factor": 1.47},
                                                        {"sku": "SH2", "units": 60, "factor": 1.02}]}), encoding="utf-8")
(md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {}, "sku_score": {}}),
                                       encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
res = json.loads(out.getvalue().splitlines()[-1])
skus = [b["sku"] for b in res["buy"]]
case("a SKU the market surged to 1.47x is not bought; one at 1.02x still is", "SH1" not in skus and "SH2" in skus
     and "surge" in res["why"], {"buy": skus, "why": res["why"]})
# a dear SKU (list 150,000 or more) is bought dear_depth units deep (11/4: the top shops sold 470-575 such units in 6 h)
assert "dear_depth" in restock_r3.DEFAULTS
case("dear goods get dear_depth units a line", restock_r3.DEFAULTS["dear_depth"] >= 2 and restock_r3.DEFAULTS["lines"] >= 14)
# dear depth only for 300k+ (11/5: 300k+ sold 10.3 an hour, the 150-300k band 1.3): a 200,000 SKU is bought 2 deep, a 400,000 one 4
cat5 = {"SM": {"category": "G>mid", "kind": "goods", "list_price": 200000, "name": "mid"},
        "SX": {"category": "G>top", "kind": "goods", "list_price": 400000, "name": "top"}}
(md / "catalog.json").write_text(json.dumps(cat5), encoding="utf-8")
(md / "demand.json").write_text(json.dumps([{"item": "mid", "category": "G>mid", "kind": "goods", "median_price": 200000},
                                           {"item": "top", "category": "G>top", "kind": "goods", "median_price": 400000}]),
                                encoding="utf-8")
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 40_000_000, "units": []}), encoding="utf-8")
restock_r3.strategy = lambda: dict(real(), reserve_cash=0, stock_value=40_000_000, goods_frac=1.0, max_list=500_000)
(md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {}, "sku_score": {"SX": 2000}}),
                                       encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
res = json.loads(out.getvalue().splitlines()[-1])
q = {b["sku"]: b["qty"] for b in res["buy"]}
case("a 200,000 SKU is held at 2 units, a 400,000 one gets dear_depth", q.get("SM", 0) <= 2 and q.get("SX", 0) >= 3, q)
# 6 h: 300k+ sold 2.2 an hour on 35 held units: a 400,000 SKU with no sales score is held at 2 like the band below
cat5["SC"] = {"category": "G>cold", "kind": "goods", "list_price": 400000, "name": "cold"}
(md / "catalog.json").write_text(json.dumps(cat5), encoding="utf-8")
(md / "demand.json").write_text(json.dumps([{"item": "top", "category": "G>top", "kind": "goods", "median_price": 400000},
                                           {"item": "cold", "category": "G>cold", "kind": "goods", "median_price": 400000}]),
                                encoding="utf-8")
(md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {}, "sku_score": {"SX": 2000, "SC": 53}}),
                                       encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
res = json.loads(out.getvalue().splitlines()[-1])
q = {b["sku"]: b["qty"] for b in res["buy"]}
case("a 400,000 SKU under DEAR_HOT (sku_score 53) is held at 2 units, a best seller (2,000) gets dear_depth", q.get("SC", 0) <= 2 and q.get("SX", 0) >= 3, q)
# stock at its cap (69.5M of 70M) with 53.2M in 300k+ units, 65 of them non-hot: a non-hot 400,000 SKU is held at 1
case("a 400,000 SKU under DEAR_HOT (sku_score 53) is held at 1 unit", q.get("SC", 0) == 1, q)
# 11/6: a best seller (sku_score 1,500) planned 20 units (4.8M at cost) against 2.3M of goods room and was skipped every
# window; now it is bought at its depth, trimmed to what the room affords
restock_r3.strategy = lambda: dict(real(), reserve_cash=0, stock_value=1_000_000, goods_frac=1.0, max_list=500_000, dear_depth=8)
(md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {}, "sku_score": {"SX": 1500}}),
                                       encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
q = {b["sku"]: b["qty"] for b in json.loads(out.getvalue().splitlines()[-1])["buy"]}
case("a best-selling 400,000 SKU too dear for a full line is bought trimmed to the room (1M / 240k = 4), not skipped",
     q.get("SX") == 4, q)
# 6 h: the market sold 334-341 units of each top 300k+ SKU while we held 5-8: depth is dear_depth x sku_score/DEAR_HOT, 1-3x
restock_r3.strategy = lambda: dict(real(), reserve_cash=0, stock_value=50_000_000, goods_frac=1.0, max_list=500_000, dear_depth=4)
qs = {}
for sc in (300, 600):                    # scores decay a little between runs, so the depth is checked as a range
    (md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {}, "sku_score": {"SX": sc}}),
                                           encoding="utf-8")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        restock_r3.main()
    qs[sc] = {b["sku"]: b["qty"] for b in json.loads(out.getvalue().splitlines()[-1])["buy"]}.get("SX", 0)
case("a 400,000 SKU at sku_score 300 is held about 6 deep, one at 600 about 12 (dear_depth 4 x score/DEAR_HOT)",
     5 <= qs[300] <= 6 and 11 <= qs[600] <= 12, qs)
restock_r3.strategy = real
# goods listed 100-150k are held at 2 units like the 150-300k band (6 h: 100-300k sold 1.0 an hour, 46 h of stock)
cat6 = {"SL": {"category": "G>low", "kind": "goods", "list_price": 120000, "name": "low"}}
(md / "catalog.json").write_text(json.dumps(cat6), encoding="utf-8")
(md / "demand.json").write_text(json.dumps([{"item": "low", "category": "G>low", "kind": "goods", "median_price": 120000}]),
                                encoding="utf-8")
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 40_000_000, "units": []}), encoding="utf-8")
restock_r3.strategy = lambda: dict(real(), reserve_cash=0, stock_value=40_000_000, goods_frac=1.0, max_list=500_000)
(md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {}, "sku_score": {}}),
                                       encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
res = json.loads(out.getvalue().splitlines()[-1])
q = {b["sku"]: b["qty"] for b in res["buy"]}
case("a 120,000 SKU is held at 2 units, not sku_cap", q.get("SL", 0) <= 2, q)
restock_r3.strategy = real
# a cheap goods SKU that keeps selling may be held up to 2x sku_cap (goods under 100k: 3 h of stock, 60M of cash idle); a slow one may not
cat7 = {"SH": {"category": "G>hot", "kind": "goods", "list_price": 50000, "name": "hot"},
        "SS": {"category": "G>slow", "kind": "goods", "list_price": 50000, "name": "slow"}}
(md / "catalog.json").write_text(json.dumps(cat7), encoding="utf-8")
(md / "demand.json").write_text(json.dumps([{"item": "hot", "category": "G>hot", "kind": "goods", "median_price": 50000},
                                           {"item": "slow", "category": "G>slow", "kind": "goods", "median_price": 50000}]),
                                encoding="utf-8")
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 40_000_000, "units": []}), encoding="utf-8")
restock_r3.strategy = lambda: dict(real(), reserve_cash=0, stock_value=40_000_000, goods_frac=1.0, max_list=500_000)
(md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {},
                                                   "sku_score": {"SH": 400.0, "SS": 40.0}}), encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
res = json.loads(out.getvalue().splitlines()[-1])
q = {b["sku"]: b["qty"] for b in res["buy"]}
case("a cheap SKU over DEAR_HOT (400) is bought up to 2x sku_cap, one under it (40) only to sku_cap",
     q.get("SH", 0) > q.get("SS", 0) and q.get("SH", 0) <= 2 * restock_r3.DEFAULTS["sku_cap"]
     and q.get("SS", 0) <= restock_r3.DEFAULTS["sku_cap"], q)
restock_r3.strategy = real
# a goods category whose reference is above max_list but within 2x (sofa/chair ~1.4M-2M at max_list 1.4M) is stocked
cat4 = dict(cat3, SD0={"category": "G>dear", "kind": "goods", "list_price": 120000, "name": "dear"})
(md / "catalog.json").write_text(json.dumps(cat4), encoding="utf-8")
(md / "demand.json").write_text(json.dumps(demand + [{"item": "dear", "category": "G>dear", "kind": "goods", "median_price": 120000}]),
                                encoding="utf-8")
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 4_000_000, "units": []}), encoding="utf-8")
(md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {}, "sku_score": {}}),
                                       encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
res = json.loads(out.getvalue().splitlines()[-1])
case("goods at 120,000 (max_list 80,000, under 2x) are stocked by the category loop", "SD0" in [b["sku"] for b in res["buy"]],
     [b["sku"] for b in res["buy"]])
# breadth first: a category we hold none of gets one of the first lines even against deeper, dearer lines
case("breadth_lines and sku_cap are in the defaults", restock_r3.DEFAULTS["breadth_lines"] >= 1 and restock_r3.DEFAULTS["sku_cap"] >= 3)
# 11/6 13:44: breadth lines bought 2 gaming PCs ahead of the best seller; now a best-selling 300k+ SKU goes first and
# a breadth line takes no slow 150k+ goods
cat6 = {"SB": {"category": "G>bed", "kind": "goods", "list_price": 400000, "name": "best"},
        "SP": {"category": "G>pc", "kind": "goods", "list_price": 1200000, "name": "pc"}}
(md / "catalog.json").write_text(json.dumps(cat6), encoding="utf-8")
(md / "demand.json").write_text(json.dumps([{"item": "pc", "category": "G>pc", "kind": "goods", "median_price": 1200000},
                                           {"item": "bed", "category": "G>bed", "kind": "goods", "median_price": 400000}]),
                                encoding="utf-8")
bed = [{"unit": f"b{i}", "sku": "SB", "category": "G>bed", "kind": "goods", "grade": "A", "cost": 240000,
        "supplied_at": NOW, "expires_at": None} for i in range(2)]
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 40_000_000, "units": bed}), encoding="utf-8")
(md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {}, "sku_score": {"SB": 1500, "SP": 10}}),
                                       encoding="utf-8")
restock_r3.strategy = lambda: dict(real(), reserve_cash=0, stock_value=2_500_000, goods_frac=1.0, max_list=1_500_000, dear_depth=8)
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
q = {b["sku"]: b["qty"] for b in json.loads(out.getvalue().splitlines()[-1])["buy"]}
case("the best-selling 300k+ SKU comes before an empty category's slow 1.2M goods (room 2.5M - 0.48M held)",
     q.get("SB") == 8 and "SP" not in q, q)    # depth 8 x 3 at score 1,500: the room (2.02M / 240k) binds
restock_r3.strategy = real
# 66.6M of stock against the 70M cap, 51.3M of it in 97 slow 300k+ units: slow 300k+ units (sku_score under DEAR_HOT) do
# not count against the cap or the goods room, so the best seller still gets its room
cat8 = {"SB": cat6["SB"], "SC": {"category": "G>cold", "kind": "goods", "list_price": 400000, "name": "cold"}}
(md / "catalog.json").write_text(json.dumps(cat8), encoding="utf-8")
(md / "demand.json").write_text(json.dumps([{"item": "bed", "category": "G>bed", "kind": "goods", "median_price": 400000},
                                           {"item": "cold", "category": "G>cold", "kind": "goods", "median_price": 400000}]),
                                encoding="utf-8")
cold = [{"unit": f"c{i}", "sku": "SC", "category": "G>cold", "kind": "goods", "grade": "B", "cost": 240000,
         "supplied_at": NOW, "expires_at": None} for i in range(10)]               # 2.4M of slow 300k+ goods held
(md / "inventory.json").write_text(json.dumps({"round": 3, "balance": 40_000_000, "units": cold}), encoding="utf-8")
(md / "restock_state.json").write_text(json.dumps({"after": 1, "seen": [], "t": time.time() - 30, "score": {}, "sku_score": {"SB": 1500, "SC": 10}}),
                                       encoding="utf-8")
restock_r3.strategy = lambda: dict(real(), reserve_cash=0, stock_value=2_500_000, goods_frac=1.0, max_list=1_500_000, dear_depth=8)
out = io.StringIO()
with contextlib.redirect_stdout(out):
    restock_r3.main()
q = {b["sku"]: b["qty"] for b in json.loads(out.getvalue().splitlines()[-1])["buy"]}
case("10 slow 400,000 units (2.4M) held against a 2.5M cap do not block the best seller: bought 10 (2.5M / 240k)",
     q.get("SB") == 10 and "SC" not in q, q)
restock_r3.strategy = real
print(f"\n{sum(ok)}/{len(ok)} passed")
