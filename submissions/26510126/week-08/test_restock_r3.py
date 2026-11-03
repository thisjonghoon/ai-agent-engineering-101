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
print(f"\n{sum(ok)}/{len(ok)} passed")
