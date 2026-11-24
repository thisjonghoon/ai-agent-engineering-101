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
TAIL = ("결정은 당신 몫이에요. 받아들일지 말지와 그 이유를 짧게 답해 주세요. 쓸 만하면 메모에 남겨서 다음 run에서도 "
        "기억해 주세요.")


def compose(why, text, facts, now):
    parts = [HEAD[why].format(now=now.strftime("%m/%d %H:%M"))]
    if facts:
        parts.append("근거:\n" + "\n".join(f"- {f}" for f in facts))
    parts += ["질문: " + text, TAIL]
    return "\n\n".join(parts)


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
    a = ap.parse_args()
    now = datetime.now(KST)
    if a.why == "early" and now >= EARLY_END:
        raise SystemExit(f"[nudge] the early phase ended {EARLY_END:%m/%d %H:%M}; use --why alert or offhours")
    message = compose(a.why, a.text, a.fact, now)
    if a.dry_run:
        print(message)
        return
    try:
        out = send(message, a.port)
        reply, err = out.get("reply"), out.get("error")
    except Exception as e:
        reply, err = None, f"{type(e).__name__}: {str(e)[:160]}"
    entry = {"ts": int(time.time()), "time": now.strftime("%m/%d %H:%M:%S"), "why": a.why, "text": a.text,
             "facts": a.fact, "sent": message,
             "reply": reply, "error": err if err else (None if reply else "busy: the agent did not answer in time")}
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
