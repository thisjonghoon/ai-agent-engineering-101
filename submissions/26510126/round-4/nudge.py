#!/usr/bin/env python3
"""Claude's words to the agent through the mini app's chat, each one on the record (decision 5 plus the early phase).

11/23 the user decided: for the first 72 hours of Round 4 (to 11/27 19:00 KST) Claude may write to the agent directly,
with questions and observations, not orders; after that only on an alert or when the user cannot answer. Every message
says it is from "claude" and goes to logs/nudges.jsonl with its reason and the agent's answer, so the record can later
be laid beside logs/forge.jsonl to see whether a nudge helped or the agent would have got there anyway.

    python nudge.py --why early "다음 공급 창에서는 무엇을 얼마나 들일지 어떻게 정하나요?" \
        --fact "19:20~19:50 손님 5명이 우유·계란·김치·콩나물을 물었고 재고가 없어 돌려보냄" --dry-run
    --why: early (until 11/27 19:00 KST) | alert (an alert in logs/watch-r4.jsonl) | offhours (the user is away)
    --fact: a fact read from the records, one per flag, sent as evidence under the question
    --dry-run: print the message, send nothing, log nothing
    --no-wait: send at once (by default it waits up to 15 minutes for the agent to sleep between runs, since a message
               that finds the agent mid-run and is not answered in the app's 120 s is dropped by the kit: 20:36, 11/24)

11/24 the user asked that the agent can follow these better: each message now opens with what this is (the owner gave
claude the early watch; the current time in KST, since the agent's notes ran about 50 minutes ahead), carries its
evidence as facts, and asks for a short answer (taken or not, and why) and a note if it is worth keeping. The decision
stays the agent's: the goal reads claude's words as questions and observations to weigh.
"""
import argparse
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "logs" / "nudges.jsonl"
KST = timezone(timedelta(hours=9))
EARLY_END = datetime(2026, 11, 27, 19, 0, tzinfo=KST)    # Round 4 opens 11/24 19:00; 72 hours from then


HEAD = {
    "early": "[초반 집중 모니터링 · 11/27 19:00까지 · 지금 {now} KST]\n주인 jonghoon이 초반 72시간 동안 claude에게 30분마다 "
             "가게 기록을 읽고 관찰을 전하도록 맡겼어요. 아래는 기록에서 확인한 사실과 질문입니다.",
    "alert": "[감시 경보 · 지금 {now} KST]\n주인 jonghoon이 맡긴 감시에서 경보가 났어요. 아래는 기록에서 확인한 사실과 질문입니다.",
    "offhours": "[주인 부재 중 · 지금 {now} KST]\n주인 jonghoon이 자리를 비운 동안 claude가 기록을 보고 있어요. 아래는 기록에서 "
                "확인한 사실과 질문입니다.",
}
# the tail matches the goal (11/25 17:40, owner): check the cited records with your own tools and act on what holds
TAIL = ("근거는 기록으로 확인할 수 있습니다. 당신의 도구로 직접 확인하고, 맞으면 지금 반영해 주세요. 반영하지 않는다면 "
        "무엇이 확인되면 바꿀지 적어 주세요. 반영한 것은 메모 끝에 남겨 다음 run에서도 기억해 주세요.")
# --urgent (owner, 11/25): a customer's money, a long sales stall, or lost notes or stock
URGENT_HEAD = "[중요] 손님 돈이나 가게 기록이 걸린 일입니다."
URGENT_TAIL = ("지금 바로 당신의 도구로 확인하고, 맞으면 다음 행동부터 바꿔 주세요. 확인한 결과와 바꾼 행동을 답해 주세요. "
               "바꾸지 않는다면 무엇이 확인되면 바꿀지 적어 주세요.")


def compose(why, text, facts, now, urgent=False):
    parts = ([URGENT_HEAD] if urgent else []) + [HEAD[why].format(now=now.strftime("%m/%d %H:%M"))]
    if facts:
        parts.append("근거:\n" + "\n".join(f"- {f}" for f in facts))
    parts += ["질문: " + text, URGENT_TAIL if urgent else TAIL]
    return "\n\n".join(parts)


def wait_for_sleep(limit=900):
    """Until the kit's last log line is the agent going to sleep, or `limit` seconds; returns the seconds waited."""
    log, start = HERE / "logs" / "agent-kit.log", time.time()
    while time.time() - start < limit:
        try:
            last = log.read_text(encoding="utf-8", errors="replace").rstrip().splitlines()[-1]
        except (OSError, IndexError):
            break
        if "[mind] sleeps" in last:
            break
        time.sleep(3)
    return int(time.time() - start)


def answered_elsewhere(since):
    """The agent's reply to claude that the kit refused (11/24 20:48: it wrote to "claude" and not the message id)."""
    try:
        for line in (HERE / "logs" / "react.jsonl").read_text(encoding="utf-8").splitlines()[::-1][:40]:
            e = json.loads(line)
            if float(e.get("ts", 0)) < since:
                break
            if e.get("action") == "reply" and str((e.get("args") or {}).get("to")) == "claude":
                return (e.get("args") or {}).get("text"), str(e.get("observation"))[:200]
    except (OSError, ValueError):
        pass
    return None, None


def send(text, port):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/chat", method="POST",
                                 data=json.dumps({"text": text, "user": "claude"}).encode(),
                                 headers={"content-type": "application/json"})
    key = HERE / ".kit" / "app.key"                    # the app asks for its access code once it is reachable outside
    if key.exists():
        req.add_header("cookie", "miniapp_access=" + key.read_text(encoding="utf-8").strip())
    with urllib.request.urlopen(req, timeout=130) as r:   # the app waits up to 120 s for the agent's reply
        return json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--why", required=True, choices=["early", "alert", "offhours"])
    ap.add_argument("--fact", action="append", default=[])
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--urgent", action="store_true", help="a customer's money, a long sales stall, lost notes or stock")
    a = ap.parse_args()
    now = datetime.now(KST)
    if a.why == "early" and now >= EARLY_END:
        raise SystemExit(f"[nudge] the early phase ended {EARLY_END:%m/%d %H:%M}; use --why alert or offhours")
    message = compose(a.why, a.text, a.fact, now, a.urgent)
    if a.dry_run:
        print(message)
        return
    waited = 0 if a.no_wait else wait_for_sleep(120 if a.urgent else 900)
    sent_at = time.time()
    try:
        out = send(message, a.port)
        reply, err = out.get("reply"), out.get("error")
    except Exception as e:
        reply, err = None, f"{type(e).__name__}: {str(e)[:160]}"
    if not reply and not err:
        text, why = answered_elsewhere(sent_at)
        if text:
            reply, err = text, f"answered, but the kit refused the reply: {why}"
    entry = {"ts": int(time.time()), "time": now.strftime("%m/%d %H:%M:%S"), "why": a.why, "text": a.text,
             "facts": a.fact, "urgent": a.urgent, "sent": message, "waited_s": waited,
             "reply": reply, "error": err if err else (None if reply else "busy: the agent did not answer in time")}
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
