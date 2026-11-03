"""Offline check of seller_r3.py against a fake Round 3 inventory (no market, no model).

    python test_seller_r3.py      # prints PASS/FAIL per case; save with | tee logs/seller-r3-test-<time>.txt

Starts the seller on a free port with MARKET_DIR pointing at a temporary folder holding inventory.json and
catalog.json, then negotiates over A2A with buyer.py's Shop client and checks the receipt: price never under the
floor, honest claim, warranty on goods, cleared food sold under cost, no unit promised twice; and the A/B test
(ab_r3.py): off without an experiment file, both arms drawn first, its arm kept and logged, a clear winner found.
"""
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from buyer import Shop

HERE = Path(__file__).resolve().parent
NOW = time.time()
UNITS = [
    {"unit": "u-goods", "sku": "G1", "name": "Test Lamp", "category": "가구/침구>조명>스탠드", "list_price": 100000,
     "kind": "goods", "cost": 60000, "grade": "A", "supplied_at": NOW - 100, "expires_at": None, "cert": {}},
    {"unit": "u-goods2", "sku": "G2", "name": "Test Chair", "category": "가구/침구>가구>의자", "list_price": 100000,
     "kind": "goods", "cost": 60000, "grade": "B", "supplied_at": NOW - 50, "expires_at": None, "cert": {}},
    {"unit": "u-food", "sku": "F1", "name": "Test Kimchi", "category": "식품>김치/반찬/즉석요리>김치", "list_price": 30000,
     "kind": "food", "cost": 18000, "grade": "A", "supplied_at": NOW - 3600, "expires_at": NOW + 150 * 3600, "cert": {}},
    {"unit": "u-old", "sku": "F2", "name": "Old Kimchi", "category": "식품>김치/반찬/즉석요리>김치", "list_price": 30000,
     "kind": "food", "cost": 18000, "grade": "C", "supplied_at": NOW - 160 * 3600, "expires_at": NOW + 3 * 3600, "cert": {}},
    {"unit": "u-goods3", "sku": "G3", "name": "Test Desk", "category": "가구/침구>가구>책상", "list_price": 100000,
     "kind": "goods", "cost": 50000, "grade": "B", "supplied_at": NOW - 10, "expires_at": None, "cert": {}},
]
CATALOG = {"G1": {"shelf_hours": None}, "G2": {"shelf_hours": None}, "G3": {"shelf_hours": None}, "F1": {"shelf_hours": 168}, "F2": {"shelf_hours": 168}}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def receipt(task):
    for a in (task or {}).get("artifacts") or []:
        for p in a.get("parts") or []:
            if "data" in p:
                return p["data"]
    return None


async def haggle(base, ask_for, offers):
    async with httpx.AsyncClient(timeout=30) as c:
        shop = Shop(c, base)
        await shop.read_card()
        t = await shop.send(f"I want to buy {ask_for}")
        for o in offers:
            if t is None or t.get("status", {}).get("state") != "TASK_STATE_INPUT_REQUIRED":
                break
            t = await shop.send(str(o), t["id"])
        return t


async def main():
    md = Path(tempfile.mkdtemp(prefix="r3md-"))
    (md / "inventory.json").write_text(json.dumps({"round": 3, "units": UNITS}), encoding="utf-8")
    (md / "catalog.json").write_text(json.dumps(CATALOG), encoding="utf-8")
    port = free_port()
    p = subprocess.Popen([sys.executable, str(HERE / "seller_r3.py"), "--port", str(port)], cwd=HERE,
                         env=dict(os.environ, MARKET_DIR=str(md), AB_DIR=str(md)))
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(base + "/.well-known/agent-card.json", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    ok = []

    def check(name, cond, detail):
        ok.append(bool(cond))
        print(f"{'PASS' if cond else 'FAIL'}  {name}: {detail}", flush=True)

    try:
        t = await haggle(base, "Test Lamp (G1)", [50000, 70000, 76000, 79000, 80000])
        r = receipt(t)
        check("goods floor, no warranty by default", r and r["price"] >= 78000 and "warranty_hours" not in r and r["claim"] == "A",
              r)
        t = await haggle(base, "Test Kimchi (F1)", [29000])
        r = receipt(t)
        check("fresh food: the ask carries the freshness premium, so 29000 is accepted; honest claim", r and r["price"] == 29000 and r["claim"] == "A" and "warranty_hours" not in r,
              r)   # 150 of 168 h left = 89%: grade A, not near a grade line
        t = await haggle(base, "Old Kimchi (F2)", [9000, 11000, 11000])
        r = receipt(t)
        check("near-date food cleared under cost", r and 10800 <= r["price"] < 18000, r)
        t = await haggle(base, "Test Chair (G2)", ["For G2 I offer 79,000", "OK, 79,000 for G2 then"])
        r = receipt(t)
        check("offer read past the SKU's digits", r and r["price"] == 79000, r)
        t = await haggle(base, "Test Lamp (G1)", [100000])
        check("a sold unit is not offered again within 60 s", receipt(t) is None, (t or {}).get("status", {}).get("state"))
        import seller_r3                                # in-process: a buyer that left without cancelling
        sel = seller_r3.Seller()
        sel.open["gone"] = {"unit": {"unit": "u-x"}, "t": time.time() - seller_r3.OPEN_HOLD - 1}
        sel.open["live"] = {"unit": {"unit": "u-y"}, "t": time.time()}
        held = sel.taken()
        check("an abandoned negotiation frees its unit", "u-x" not in held and "u-y" in held, sorted(held))
        os.environ["MARKET_DIR"] = str(md)
        seller_r3.MARKET_DIR = md
        near = dict(UNITS[2], expires_at=time.time() + (0.80 * 168 + 0.5) * 3600)   # half an hour above the A line
        check("no grade claim within an hour of a line", seller_r3.grade_now(near)[2] is None, seller_r3.grade_now(near))

        aged = dict(UNITS[0], supplied_at=time.time() - 6 * 86400)    # goods 6 days in stock (storage 1% a day)
        fresh = dict(UNITS[0], supplied_at=time.time() - 3600)
        s0 = seller_r3.strategy()
        check("goods past goods_age_days may go down to cost + 3%", seller_r3.prices(aged, s0)[1] == 61800
              and seller_r3.prices(fresh, s0)[1] == 78000, (seller_r3.prices(aged, s0), seller_r3.prices(fresh, s0)))

        import ab_r3                                     # A/B: same folder as the seller subprocess
        ab_r3.EXPERIMENT, ab_r3.LOG = md / "experiment_r3.json", md / "logs" / "ab_r3.jsonl"
        check("no experiment file: the seller logs no A/B events", not ab_r3.LOG.exists(), ab_r3.LOG)
        ab_r3.EXPERIMENT.write_text(json.dumps({"on": True, "id": "t1", "param": "ask_frac", "kind": "goods",
                                                "arms": {"A": 0.95, "B": 0.70}, "min_n": 30, "p_win": 0.95}))
        check("an experiment on goods leaves food alone", ab_r3.choose("food") == (None, None), ab_r3.choose("food"))
        t = await haggle(base, "Test Desk (G3)", [80000, 80000])   # at or over both arms' floors
        r = receipt(t)
        ev = [json.loads(l) for l in ab_r3.LOG.read_text().splitlines()]
        opened = [e for e in ev if e["event"] == "open"]
        ended = [e for e in ev if e["event"] == "deal"]
        arm_ask = {"A": 95000, "B": 70000}
        check("a negotiation draws an arm, asks with it and logs open and deal with the margin",
              r and len(opened) == 1 and opened[0]["ask"] == arm_ask[opened[0]["arm"]] and len(ended) == 1
              and ended[0]["reward"] == round((r["price"] - 50000) / 100000, 4) and r["price"] >= 55000,
              {"receipt": r and r["price"], "events": ev})
        seen = [ab_r3.choose("goods")[1] for _ in range(1)]
        check("the arm with fewer negotiations is drawn first", seen == ["B" if opened[0]["arm"] == "A" else "A"], seen)
        with ab_r3.LOG.open("a") as f:                   # 40 negotiations each: B earns more
            for i in range(40):
                for arm, rew in (("A", 0.05 if i % 2 else 0.0), ("B", 0.15 if i % 3 else 0.0)):
                    f.write(json.dumps({"id": "t1", "arm": arm, "task": f"{arm}{i}", "event": "open"}) + "\n")
                    f.write(json.dumps({"id": "t1", "arm": arm, "task": f"{arm}{i}", "event": "deal" if rew else "walk",
                                        "reward": rew}) + "\n")
        picks = [ab_r3.choose("goods")[1] for _ in range(200)]
        check("the bandit leans to the arm that earns more, and a winner is called", picks.count("B") > 150
              and ab_r3.winner() == "B", {"B share": picks.count("B") / 200, "summary": ab_r3.summary()})
    finally:
        p.terminate()
    print(f"\n{sum(ok)}/{len(ok)} passed")


if __name__ == "__main__":
    asyncio.run(main())
