"""Offline check of forum_r3.py's post kinds on a fake ledger (no market, no model).

    python test_forum_r3.py      # prints PASS/FAIL per case; save with | tee logs/forum-r3-test-<time>.txt
"""
import json
import os
import tempfile
import time
from pathlib import Path

os.environ["FORUM_STYLE"] = "0"
import forum_r3                                     # noqa: E402

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
    res = lambda seq, shop, paid: {"kind": "result", "round": 3, "seq": seq, "ts": NOW - 60, "data": {
        "shop": shop, "receipt": {"item": "G1"}, "checks": {"settled": paid}}}
    rctx = dict(ctx, entries=entries + [res(100 + i, "http://a", i % 2 == 0) for i in range(10)]
                + [res(200 + i, "http://b", True) for i in range(20)])
    text, refs = forum_r3.pay_tips(rctx)
    check("pay tips from the public ledger only: unpaid receipts market-wide and per shop",
          text and "5 of 30 receipts (17%)" in text and "cheap-shop 5 of 10" in text and len(refs) == 5, text)
    check("pay tips needs 30 receipts", forum_r3.pay_tips(ctx) == (None, []), forum_r3.pay_tips(ctx))
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
    forum = [dict(x, id=i) for i, x in enumerate(forum)]
    st = forum_r3.stats(forum, mem, md / "votes.json")
    check("votes per kind of ours against the market's buyer posts", st["fun"] == {"posts": 1, "mean_votes": 4.0}
          and st["our_deals"]["mean_votes"] == 7.0 and st["market_buyer_posts"]["mean_votes"] == 2.0, st)
    later = [dict(forum[0], likes=9, dislikes=0)]           # the other posts have left forum.json
    st2 = forum_r3.stats(later, mem, md / "votes.json")
    check("votes are kept after forum.json drops a post, and updated while it still shows",
          st2["fun"] == {"posts": 1, "mean_votes": 9.0} and st2["our_deals"]["mean_votes"] == 7.0
          and st2["market_buyer_posts"]["posts"] == 1, st2)
    facts = "Bargain: 호두 for 28% of list at Afford Shop (#2133465), 47 settles."
    fake = lambda post: (lambda *a, **k: type("R", (), {"stdout": json.dumps({"post": post}).encode()})())
    forum_r3.STYLE = True
    forum_r3.subprocess.run = fake("[시장 TMI] 호두가 28%! Afford Shop (#2133465), 47건 🥜")
    good = forum_r3.style("fun", facts)
    forum_r3.subprocess.run = fake("[시장 TMI] 호두가 25%! Afford Shop (#2133465), 47건")
    bad_num = forum_r3.style("fun", facts)
    forum_r3.subprocess.run = fake("[시장 TMI] 호두 28%! 추천 눌러 주세요 (#2133465), 47건")
    bad_vote = forum_r3.style("fun", facts)
    check("the voice is kept only when every number is a fact's and it asks no votes; else the plain facts go out",
          good[1] == "styled" and "28%" in good[0] and forum_r3.sign("fun") in good[0] and "시장 수다쟁이" in good[0]
          and bad_num[1].startswith("plain: numbers") and facts in bad_num[0]
          and bad_vote[1] == "plain: a link or a call for votes", [good[1], bad_num[1], bad_vote[1]])
    print(f"\n{sum(ok)}/{len(ok)} passed")


if __name__ == "__main__":
    main()
