"""Tests for the A/B test's end (a tie after MAX_N or MAX_HOURS) and for a whole playbook as arm B. Temp folders only."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="ab-r3-"))
(TMP / "logs").mkdir()
os.environ["AB_DIR"] = str(TMP)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ab_r3        # noqa: E402
import meta_r3      # noqa: E402

RESULTS = []


def case(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))


def main():
    ab_r3.EXPERIMENT, ab_r3.LOG = TMP / "experiment_r3.json", TMP / "logs" / "ab_r3.jsonl"
    meta_r3.ab_r3 = ab_r3
    e = {"on": True, "id": "t1", "param": "ask_frac", "kind": "goods", "arms": {"A": 0.9, "B": 0.89}, "min_n": 30,
         "p_win": 0.95, "started": time.time()}
    ab_r3.EXPERIMENT.write_text(json.dumps(e))
    for i in range(ab_r3.MAX_N):                 # two arms that earn the same: no winner by evidence
        for arm in "AB":
            ab_r3.record(id="t1", arm=arm, task=f"{arm}{i}", event="open")
            ab_r3.record(id="t1", arm=arm, task=f"{arm}{i}", event="deal" if i % 2 else "walk",
                         reward=0.1 if i % 2 else 0.0)
    case("equal arms with MAX_N negotiations each end as a tie", ab_r3.winner() == "tie", str(ab_r3.summary()))
    e2 = dict(e, id="t2", started=time.time() - (ab_r3.MAX_HOURS + 1) * 3600)
    ab_r3.EXPERIMENT.write_text(json.dumps(e2))
    case("a test with too few negotiations waits for min_n", ab_r3.winner() is None)

    s = dict(meta_r3.DEFAULTS) if hasattr(meta_r3, "DEFAULTS") else {}
    s.update({k: v[0] for k, v in meta_r3.BOUNDS.items() if k not in s})
    s.update(ask_frac=0.95, floor_frac=0.78, step=0.4, max_turns=6, min_margin=0.1)
    got = meta_r3.start_ab({"playbook": "ikea", "kind": "goods"}, s)
    case("a playbook A/B puts the playbook's per-talk numbers in arm B and the strategy's in arm A",
         got and got["arms"]["B"].get("ask_frac") == 0.85 and got["arms"]["A"].get("ask_frac") == 0.95
         and "goods_frac" not in got["arms"]["B"], json.dumps(got))
    case("a started playbook A/B is a valid experiment the seller draws from",
         ab_r3.experiment() is not None and ab_r3.choose("goods")[1] in ("A", "B"), str(ab_r3.experiment()))
    case("an unknown playbook starts nothing", meta_r3.start_ab({"playbook": "nope", "kind": "goods"}, s) is None)

    # a buyer number on trial: half the orders (code_ab_r3.arm) run B; after the trial the halves decide
    meta_r3.BUYER_TRIAL, meta_r3.BUYER_PLAN = TMP / "buyer_ab_r3.json", TMP / "buyer_plan_r3.json"
    meta_r3.CODE_CHANGES = TMP / "logs" / "code_changes_r3.jsonl"
    meta_r3.BUYER_PLAN.write_text(json.dumps({"CAP": 0.85}))
    meta_r3.BUYER_TRIAL.write_text(json.dumps({"key": "CAP-t", "param": "CAP", "A": 0.85, "B": 0.8,
                                               "started": time.time() - 4000}))
    real_window = meta_r3.metrics_r3.window
    def fake_window(t0, t1, base=None, keep=None):       # arm B (CAP 0.80) closes fewer orders, same surplus
        b = keep("o-b") if keep else False
        return {"buyer_surplus_order": 15000, "buyer_close_rate": 0.45 if b else 0.65, "orders": 200}
    meta_r3.metrics_r3.window = fake_window
    import code_ab_r3
    real_arm, code_ab_r3.arm = code_ab_r3.arm, lambda key, o: "B" if o == "o-b" else "A"
    got = meta_r3.buyer_trial_verdict()
    code_ab_r3.arm, meta_r3.metrics_r3.window = real_arm, real_window
    case("a buyer number that gains no surplus and costs closes is not taken", got == {"CAP": (0.85, 0.85)}
         and json.loads(meta_r3.BUYER_PLAN.read_text())["CAP"] == 0.85 and json.loads(meta_r3.BUYER_TRIAL.read_text()) == {}
         and "inner loop (buyer A/B)" in meta_r3.CODE_CHANGES.read_text(), str(got))

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")


if __name__ == "__main__":
    main()
