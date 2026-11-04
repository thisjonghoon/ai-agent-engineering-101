"""Tests for meta_code_r3: the gate between the coding agent's copy and the live folder, which idea is next, and the
build budget. No model is called and nothing is deployed: HERE, the logs and the work folder point at temp folders."""
import json
import shutil
import tempfile
import time
from pathlib import Path

import meta_code_r3 as mc

RESULTS = []


def case(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="meta-code-"))
    live, work = tmp / "live", tmp / "work"
    live.mkdir()
    work.mkdir()
    for d in (live, work):
        (d / "buyer_r3.py").write_text("A = 1\n")
        (d / "seller_r3.py").write_text("B = 1\n")
    mc.HERE, mc.TESTS = live, []
    mc.LOGS = live
    mc.ATTEMPTS, mc.STRATEGIES = live / "attempts.jsonl", live / "strategies.jsonl"

    # 1. the gate: nothing changed, an allowed change, a file outside the set, a forbidden line, too many lines
    case("no change is not deployed", mc.gate(work) == ([], "no change"))
    (work / "buyer_r3.py").write_text("A = 1\nB = 2  # open lower where shops sold cheap\n")
    case("an allowed file with plain lines passes", mc.gate(work) == (["buyer_r3.py"], None), str(mc.gate(work)))
    (work / "seller_r3.py").write_text("B = 2\n")
    case("the seller is outside the allowed set", "outside the allowed set" in str(mc.gate(work)[1]))
    (work / "seller_r3.py").write_text("B = 1\n")
    (work / "buyer_r3.py").write_text("A = 1\nimport subprocess\n")
    case("a line starting a process is refused", "forbidden" in str(mc.gate(work)[1]))
    (work / "buyer_r3.py").write_text("A = 1\nx = o['mandates']['payment']\n")
    case("a line touching the payment mandate is refused", "forbidden" in str(mc.gate(work)[1]))
    (work / "buyer_r3.py").write_text("A = 1\n" + "".join(f"v{i} = {i}\n" for i in range(mc.MAX_LINES + 1)))
    case("more than MAX_LINES added lines is refused", "added lines" in str(mc.gate(work)[1]))

    # 2. the next idea: the newest strategy's ideas first, an idea already tried is skipped
    mc.STRATEGIES.write_text(json.dumps({"code_ideas": ["Route scouts to shops with stock of dear SKUs first",
                                                        "Remember shops that ship short food for an hour"]}) + "\n")
    idea, key, _ = mc.next_idea()
    case("the first untried idea is picked", idea.startswith("Route scouts"))
    mc.append(mc.ATTEMPTS, {"t": time.time() - 99999, "key": key})
    idea2, _, _ = mc.next_idea()
    case("a tried idea is not tried again", idea2.startswith("Remember shops"), str(idea2))

    # 3. the build budget: one build every BUILD_EVERY
    mc.append(mc.ATTEMPTS, {"t": time.time() - 60, "key": "x"})
    mc.WORK = tmp / "auto"
    mc.build()
    case("no build within BUILD_EVERY of the last one", not mc.WORK.exists())

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
