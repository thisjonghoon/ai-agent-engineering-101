#!/usr/bin/env python3
"""Claude's words to the agent through the mini app's chat, each one on the record (decision 5 plus the early phase).

11/23 the user decided: for the first 72 hours of Round 4 (to 11/27 19:00 KST) Claude may write to the agent directly,
with questions and observations, not orders; after that only on an alert or when the user cannot answer. Every message
says it is from "claude" and goes to logs/nudges.jsonl with its reason and the agent's answer, so the record can later
be laid beside logs/forge.jsonl to see whether a nudge helped or the agent would have got there anyway.

    python nudge.py --why early "오늘 손님 세 명이 사려다 못 샀어. 왜 그랬을지 생각해 볼래?"
    --why: early (until 11/27 19:00 KST) | alert (an alert in logs/watch-r4.jsonl) | offhours (the user is away)
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
    ap.add_argument("--port", type=int, default=8800)
    a = ap.parse_args()
    now = datetime.now(KST)
    if a.why == "early" and now >= EARLY_END:
        raise SystemExit(f"[nudge] the early phase ended {EARLY_END:%m/%d %H:%M}; use --why alert or offhours")
    try:
        out = send(a.text, a.port)
        reply, err = out.get("reply"), out.get("error")
    except Exception as e:
        reply, err = None, f"{type(e).__name__}: {str(e)[:160]}"
    entry = {"ts": int(time.time()), "time": now.strftime("%m/%d %H:%M:%S"), "why": a.why, "text": a.text,
             "reply": reply, "error": err if err else (None if reply else "busy: the agent did not answer in time")}
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
