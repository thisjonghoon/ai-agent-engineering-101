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
print(f"\n{sum(ok)}/{len(ok)} passed")
