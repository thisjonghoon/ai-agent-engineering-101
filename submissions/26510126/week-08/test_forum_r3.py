"""Offline check of forum_r3.py's post kinds on a fake ledger (no market, no model).

    python test_forum_r3.py      # prints PASS/FAIL per case; save with | tee logs/forum-r3-test-<time>.txt
"""
import json
import tempfile
import time
from pathlib import Path

import forum_r3

NOW = time.time()
CAT = {f"G{i}": {"list_price": 10000, "category": f"식품>김치>{'김치' if i < 5 else '과자'}", "name": f"item {i}"} for i in range(10)}
SHOPS = {"http://a": "cheap-shop", "http://b": "dear-shop", "http://c": "fresh-shop"}


def settle(seq, shop, item, amount, hours_left=None, honest=True, ago=600):
    return {"kind": "settle", "seq": seq, "ts": NOW - ago, "data": {"shop": shop, "item": item, "sku": item, "amount": amount,
            "name": CAT[item]["name"], "claim_honest": honest,
            "expires_at": NOW - ago + hours_left * 3600 if hours_left else None}}


def main():
    ok = []

    def check(name, cond, detail):
        ok.append(bool(cond))
        print(f"{'PASS' if cond else 'FAIL'}  {name}: {detail}", flush=True)

    md = Path(tempfile.mkdtemp(prefix="forum-"))
    forum_r3.MD, forum_r3.PLAN = md, md / "forum_plan_r3.json"
    entries = [settle(1, "http://a", "G1", 5000, 100), settle(2, "http://a", "G2", 5200, 120),
               settle(3, "http://b", "G3", 9000, 600), settle(4, "http://b", "G4", 9100, 620),
               settle(5, "http://c", "G6", 7000, 500), settle(6, "http://c", "G7", 7100, 520),
               settle(7, "http://a", "G6", 4000, 90), settle(8, "http://a", "G7", 4100, 95, honest=False),
               settle(9, "http://b", "G1", 9900, 300, ago=8 * 3600)]
    ctx = {"entries": entries, "names": SHOPS, "cat": CAT, "now": NOW}
    text, refs = forum_r3.best_value(ctx)
    check("best value: cheapest shop per busy category, a shop with a false claim left out, settles over 6 h ignored",
          text and "김치: cheap-shop 51% of list over 2 settles" in text and "과자: fresh-shop 70%" in text, text)
    text, refs = forum_r3.freshness(ctx)
    check("freshness: shelf life left at sale per shop, longest first, with refs", text
          and text.index("dear-shop") < text.index("fresh-shop") < text.index("cheap-shop") and refs, text)
    (md / "payments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in
                                       [{"order": f"o{i}", "paid": True} for i in range(8)]
                                       + [{"order": "x1", "paid": False, "reason": "not paying: 138 h of shelf life left"},
                                          {"order": "x2", "paid": False, "reason": "not paying: 100 h of shelf life left"},
                                          {"order": "x3", "paid": False, "reason": "not paying: grade C, the policy accepts"}]))
    text, _ = forum_r3.pay_tips(ctx)
    check("pay tips: our unpaid receipts counted by reason", text and "3 of our last 11" in text and "shelf life 2" in text, text)
    check("fun needs 20 settles, so a quiet market gets no trivia", forum_r3.fun(ctx) == (None, []), forum_r3.fun(ctx))
    forum_r3.PLAN.write_text(json.dumps({"weights": {"best_value": 0, "freshness": 0, "pay_tips": 0, "fun": 3, "claims": 0}}))
    check("the meta-harness's weights pick the kind; a kind with nothing to say yields no post",
          forum_r3.drawn(ctx) == (None, None, []) and forum_r3.plan()["fun"] == 3.0, forum_r3.plan())
    forum_r3.PLAN.write_text(json.dumps({"weights": {"best_value": 3, "freshness": 0, "pay_tips": 0, "fun": 0, "claims": 0}}))
    check("a drawn kind with something to say is posted", forum_r3.drawn(ctx)[0] == "best_value", forum_r3.drawn(ctx)[0])
    mem = [{"kind": "forum", "post": "P1", "format": "fun"}, {"kind": "forum", "post": "P2"}]
    forum = [{"round": 3, "role": "buyer", "owner": "thisjonghoon", "text": "P1", "likes": 5, "dislikes": 1},
             {"round": 3, "role": "buyer", "owner": "thisjonghoon", "text": "P2", "likes": 7},
             {"round": 3, "role": "buyer", "owner": "other", "text": "Q", "likes": 2}]
    st = forum_r3.stats(forum, mem)
    check("votes per kind of ours against the market's buyer posts", st["fun"] == {"posts": 1, "mean_votes": 4.0}
          and st["our_deals"]["mean_votes"] == 7.0 and st["market_buyer_posts"]["mean_votes"] == 2.0, st)
    print(f"\n{sum(ok)}/{len(ok)} passed")


if __name__ == "__main__":
    main()
