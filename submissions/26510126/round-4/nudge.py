#!/usr/bin/env python3
"""Hermes's binding directives to the Round 4 agent through the mini app's chat (v2, gen2 cutover 11/28, TK-41/42 8절).

v1 (nudge.py) sent "observations and questions" that the agent could set aside. In gen2 the goal ranks the supervisor
above the agent's own judgment: each message is one action with a deadline, the cited facts, a check, and the reply
format "S-xx done: <log line>" / "S-xx not done: <record against it>". Every message goes to logs/nudges.jsonl (as v1)
and to ~/.hermes/state/round4_directives.jsonl, where round4_sentinel.py judges the deadline and the check.

    python nudge_v2.py "a2a 핸들러에 handles [a2a]를 넣어 같은 이름으로 다시 forge하게" \
        --fact "forge.jsonl 21:52 shop_reply v3 passed, permission.handles 없음" \
        --fact "talk.jsonl 21:55, 21:58 손님 2명 busy" \
        --deadline +15m --check 'forge:passed.: true.*handles.: \\[.a2a' --why alert --urgent --dry-run
    python nudge_v2.py --remind S-07            # the one reminder round4_sentinel.py asked for ('독촉 필요')

Kept from v1: positional text (now the action), --why early|alert|offhours, --fact, --port, --dry-run, --no-wait,
--urgent, user=claude, logs/nudges.jsonl, answered_elsewhere().
New: --id (default: next S-NN), --deadline (HH:MM, +30m, or minutes; default 30 min, urgent 15), --check (shown as
확인; "src[,src]:REGEX" or "file:PATH:REGEX" is also a machine rule), --check-text, --role supervisor|owner,
--owner-approved, --remind ID, --wait (seconds to wait for a safe moment).
Send guards: the agent asleep (its last "[mind] sleeps N s" not yet over), no customer message in 90 s, not from 10 min
before a restock window (last 429 opens_at; 2 min if --urgent) to closes_at+30 s, not inside a QUIET window. If no safe
moment comes before --wait runs out, the message is held, not forced (exit 2). A busy answer gets one resend with the
same id at the agent's next sleep, marked "(재전송: 받았으면 무시)".
Owner name: Hermes always speaks as [HERMES-SUPERVISOR] (user=claude). --role owner sends as user=jonghoon only with
--owner-approved (종훈 님 approved this exact text) or when OWNER_AUTOSEND is switched on at his request.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(os.environ.get("ROUND4_SHOP") or Path(__file__).resolve().parent)
if not (HERE / "agent.json").exists():          # run from scratch: point at the shop folder
    HERE = Path.home() / "Developer/ai-agent-engineering-101-round4/submissions/26510126/round-4"
LOG = HERE / "logs" / "nudges.jsonl"
DIRECTIVES = Path(os.environ.get("ROUND4_DIRECTIVES") or Path.home() / ".hermes/state/round4_directives.jsonl")
QUIET_FILE = Path(os.environ.get("ROUND4_QUIET") or Path.home() / ".hermes/state/round4_quiet.json")
KST = timezone(timedelta(hours=9))

# Owner-name switch (종훈 님 결정 11/28): off. Turn on only when 종훈 님 asks, if the agent stops following SUPERVISOR
# directives; then --role owner may send as jonghoon without --owner-approved. Env R4_OWNER_AUTOSEND=1 does the same.
OWNER_AUTOSEND = False

# QUIET windows: only --why alert (a customer's money, lost notes or stock) goes out inside one.
# Static list here; the cutover script adds the gen2 window (T0 .. first handler pass, at most 60 min) in QUIET_FILE.
QUIET = [
    (datetime(2026, 11, 28, 3, 0, tzinfo=KST), datetime(2026, 11, 28, 9, 0, tzinfo=KST), "11/28 무넛지 대조 실험"),
]

SRCS = ("talk", "forge", "react", "ledger", "chat", "notes")
BUSY_TEXT = "the agent did not answer in time"


# ---------- composing ----------
def compose(did, role, action, facts, deadline, check_text, now, urgent=False, resend=False, remind=False):
    tag = "[OWNER]" if role == "owner" else "[HERMES-SUPERVISOR]"
    lines = [f"{tag} {did}"]
    if resend:
        lines.append("(재전송: 받았으면 무시)")
    if remind:
        lines.append("(독촉: 기한이 지났네. 아래 둘 중 하나로 지금 답하게)")
    lines.append(f"지금: {now:%m/%d %H:%M} KST" + (" · 중요: 손님 돈이나 판매 통로가 걸린 일" if urgent else ""))
    lines.append(f"행동: {action}")
    lines.append(f"기한: {deadline:%H:%M} KST")
    if facts:
        lines.append("근거:\n" + "\n".join(f"- {f}" for f in facts))
    lines.append(f"확인: {check_text or '답에 적은 로그 줄로 확인'}")
    lines.append(f'답: "{did} done: <로그 줄>" 또는 "{did} not done: <반대 근거>" 한 줄을 기한 안에. '
                 f"'사례가 더 쌓이면'은 이유가 아니네. 기다리는 손님과 진행 중 결제가 먼저일세.")
    return "\n".join(lines)


def parse_deadline(s, now, urgent):
    if not s:
        return now + timedelta(minutes=15 if urgent else 30)
    s = s.strip()
    m = re.fullmatch(r"\+?(\d+)\s*m?", s)
    if m:
        return now + timedelta(minutes=int(m.group(1)))
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        d = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        return d if d > now else d + timedelta(days=1)
    raise SystemExit(f"[nudge] bad --deadline {s!r}: use HH:MM, +30m or 30")


def parse_check(s):
    """A machine rule from --check, or None: 'forge:REGEX', 'forge,talk:REGEX', 'file:notes.md:REGEX'."""
    if not s:
        return None
    m = re.fullmatch(r"file:([^:]+):(.+)", s, re.S)
    if m:
        return {"file": m.group(1), "regex": m.group(2)}
    m = re.fullmatch(r"((?:%s)(?:,(?:%s))*):(.+)" % ("|".join(SRCS), "|".join(SRCS)), s, re.S)
    if m:
        return {"sources": m.group(1).split(","), "regex": m.group(2)}
    return None


def check_label(s, rule):
    if not rule:
        return s
    where = rule.get("file") or ", ".join(f"{x}.jsonl" if x != "notes" else "notes.md" for x in rule["sources"])
    return f"{where}에서 /{rule['regex']}/ 가 보이면 이행"


# ---------- directives ----------
def load_directives():
    cur = {}
    try:
        for line in DIRECTIVES.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("id"):
                cur[e["id"]] = {**cur.get(e["id"], {}), **e}
    except OSError:
        pass
    return cur


def next_id(role):
    prefix = "O-" if role == "owner" else "S-"
    n = [int(k[2:]) for k in load_directives() if k.startswith(prefix) and k[2:].isdigit()]
    return f"{prefix}{(max(n) + 1) if n else 1:02d}"


def record(d):
    DIRECTIVES.parent.mkdir(parents=True, exist_ok=True)
    with open(DIRECTIVES, "a", encoding="utf-8") as f:
        f.write(json.dumps({**d, "ts": int(time.time())}, ensure_ascii=False) + "\n")


# ---------- guards ----------
def quiet_now(now):
    wins = [(a, b, label) for a, b, label in QUIET]
    try:
        for w in json.loads(QUIET_FILE.read_text()).get("windows", []):
            wins.append((datetime.fromtimestamp(w[0], KST), datetime.fromtimestamp(w[1], KST), w[2] if len(w) > 2 else "quiet"))
    except (OSError, ValueError, TypeError, IndexError):
        pass
    for a, b, label in wins:
        if a <= now < b:
            return f"{label} {a:%m/%d %H:%M}-{b:%H:%M}"
    return None


def asleep():
    """The agent's last [mind] line is 'sleeps N s' and that sleep has not run out."""
    try:
        with open(HERE / "logs" / "agent-kit.log", "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 60000))
            lines = [l for l in f.read().decode("utf-8", "replace").splitlines() if "[mind]" in l]
    except OSError:
        return False
    if not lines:
        return False
    m = re.match(r"(\d\d):(\d\d):(\d\d) \[mind\] sleeps (\d+) s", lines[-1])
    if not m:
        return False
    now = datetime.now(KST)
    start = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=int(m.group(3)), microsecond=0)
    if start > now + timedelta(minutes=1):
        start -= timedelta(days=1)
    return now < start + timedelta(seconds=int(m.group(4))) - timedelta(seconds=5)


def last_customer_ts():
    try:
        with open(HERE / "logs" / "talk.jsonl", "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 20000))
            rows = f.read().decode("utf-8", "replace").splitlines()[1:]
        return max((float(json.loads(r).get("ts", 0)) for r in rows if r.strip()), default=0.0)
    except (OSError, ValueError):
        return 0.0


def last_window():
    try:
        with open(HERE / "logs" / "react.jsonl", "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 3_000_000))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    w = re.findall(r'opens_at\\?"?\s*:\s*(\d+(?:\.\d+)?)\s*,\s*\\?"?closes_at\\?"?\s*:\s*(\d+(?:\.\d+)?)', tail)
    return tuple(map(float, w[-1])) if w else None


def blocked(urgent):
    """Why now is not a safe moment, or None."""
    t = time.time()
    if t - last_customer_ts() < 90:
        return "손님 대화 90초 안"
    w = last_window()
    if w and w[0] - (120 if urgent else 600) <= t <= w[1] + 30:
        return f"매입 창구 {datetime.fromtimestamp(w[0], KST):%H:%M}~{datetime.fromtimestamp(w[1], KST):%H:%M}"
    if not asleep():
        return "에이전트가 실행 중(잠들지 않음)"
    return None


def wait_safe(limit, urgent):
    """Seconds waited until a safe moment, or None if the limit ran out (then the message is held, not forced)."""
    start = time.time()
    while True:
        why = blocked(urgent)
        if not why:
            return int(time.time() - start), None
        if time.time() - start >= limit:
            return None, why
        time.sleep(3)


# ---------- sending (as v1) ----------
def answered_elsewhere(since, did=None):
    """The agent's reply that the kit refused (11/24 20:48: it wrote to "claude" and not the message id)."""
    try:
        for line in (HERE / "logs" / "react.jsonl").read_text(encoding="utf-8").splitlines()[::-1][:40]:
            e = json.loads(line)
            if float(e.get("ts", 0)) < since:
                break
            a = e.get("args") or {}
            if e.get("action") in ("reply", "app_say") and (str(a.get("to")) == "claude" or (did and did in str(a.get("text")))):
                return a.get("text"), str(e.get("observation"))[:200]
    except (OSError, ValueError):
        pass
    return None, None


def send(text, port, user):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/chat", method="POST",
                                 data=json.dumps({"text": text, "user": user}).encode(),
                                 headers={"content-type": "application/json"})
    key = HERE / ".kit" / "app.key"                    # read only to authenticate; never printed or logged
    if key.exists():
        req.add_header("cookie", "miniapp_access=" + key.read_text(encoding="utf-8").strip())
    with urllib.request.urlopen(req, timeout=130) as r:   # the app waits up to 120 s for the agent's reply
        return json.load(r)


def try_send(message, port, user, did):
    sent_at = time.time()
    try:
        out = send(message, port, user)
        reply, err = out.get("reply"), out.get("error")
    except Exception as e:
        reply, err = None, f"{type(e).__name__}: {str(e)[:160]}"
    if not reply and not err:
        text, why = answered_elsewhere(sent_at, did)
        if text:
            reply, err = text, f"answered, but the kit refused the reply: {why}"
    return reply, err, sent_at


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", help="the one action asked (v1: the question)")
    ap.add_argument("--why", default="alert", choices=["early", "alert", "offhours"])
    ap.add_argument("--fact", action="append", default=[], help="a fact read from the records (근거), one per flag")
    ap.add_argument("--id")
    ap.add_argument("--deadline")
    ap.add_argument("--check", help="확인; 'src[,src]:REGEX' or 'file:PATH:REGEX' also becomes a machine rule")
    ap.add_argument("--check-text", help="the 확인 line shown, when --check is a rule")
    ap.add_argument("--role", default="supervisor", choices=["supervisor", "owner"])
    ap.add_argument("--owner-approved", action="store_true", help="종훈 님 approved this exact text for his name")
    ap.add_argument("--remind", metavar="ID", help="send the one reminder for an overdue directive")
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-wait", action="store_true", help="skip the safe-moment guards (v1 compatible; use for money only)")
    ap.add_argument("--wait", type=int, help="seconds to wait for a safe moment (default 900, urgent 120)")
    ap.add_argument("--urgent", action="store_true", help="a customer's money, a broken sale path, lost notes or stock")
    a = ap.parse_args()
    now = datetime.now(KST)

    remind = None
    if a.remind:
        remind = load_directives().get(a.remind) or sys.exit(f"[nudge] no directive {a.remind}")
        a.role = remind.get("role", "supervisor")
        a.text, a.fact, did = remind.get("action"), remind.get("facts") or [], a.remind
        rule = remind.get("check")
        check_text = remind.get("check_text") or check_label("", rule)
        deadline = datetime.fromtimestamp(float(remind.get("deadline_ts") or (now + timedelta(minutes=30)).timestamp()), KST)
        if deadline <= now:
            deadline = now + timedelta(minutes=30)
    else:
        if not a.text:
            ap.error("text (the action) is required unless --remind")
        did = a.id or next_id(a.role)
        rule = parse_check(a.check)
        check_text = a.check_text or check_label(a.check, rule)
        deadline = parse_deadline(a.deadline, now, a.urgent)

    user = "claude"
    if a.role == "owner":
        if not (a.owner_approved or OWNER_AUTOSEND or os.environ.get("R4_OWNER_AUTOSEND") == "1"):
            raise SystemExit("[nudge] --role owner needs --owner-approved (종훈 님이 이 문장을 승인) — "
                             "the owner-name autosend switch is off. Send as supervisor instead.")
        user = "jonghoon"

    q = quiet_now(now)
    if q and a.why != "alert":
        raise SystemExit(f"[nudge] quiet window {q}: only --why alert goes out")

    message = compose(did, a.role, a.text, a.fact, deadline, check_text, now, a.urgent, remind=bool(remind))
    if a.dry_run:
        print(message)
        if rule:
            print(f"\n(rule: {json.dumps(rule, ensure_ascii=False)})")
        return

    base = {"id": did, "role": a.role, "sender": user, "action": a.text, "facts": a.fact, "check": rule,
            "check_text": check_text, "deadline_ts": int(deadline.timestamp()), "urgent": a.urgent, "why": a.why}
    if remind:
        base = {**remind, **base, "reminders": int(remind.get("reminders", 1)), "remind_needed": False}
    else:
        base.update(reminders=0, misses=0)

    limit = a.wait if a.wait is not None else (120 if a.urgent else 900)
    waited, why = (0, None) if a.no_wait else wait_safe(limit, a.urgent)
    if waited is None:
        record({**base, "status": "held", "held_reason": why})
        print(f"[nudge] held {did}: no safe moment in {limit} s ({why}); not forced. Run again later.")
        sys.exit(2)

    reply, err, sent_at = try_send(message, a.port, user, did)
    resent = False
    if not reply and not err:                          # busy: one resend with the same id at the next sleep
        w2, why2 = wait_safe(max(limit, 600), a.urgent)
        if w2 is not None:
            resent = True
            reply, err, _ = try_send(compose(did, a.role, a.text, a.fact, deadline, check_text, datetime.now(KST),
                                             a.urgent, resend=True, remind=bool(remind)), a.port, user, did)
        else:
            err = f"busy, resend held ({why2})"

    status = "open" if reply else ("unacked" if not err or err.startswith("busy") else "send_failed")
    if remind:
        status = "reminded" if reply else status
    record({**base, "status": status, "sent_ts": int(sent_at) if not remind else int(remind.get("sent_ts") or sent_at),
            "last_sent_ts": int(time.time()), "reply": (reply or "")[:300], "error": err, "resent": resent})
    entry = {"ts": int(time.time()), "time": now.strftime("%m/%d %H:%M:%S"), "why": a.why, "id": did, "role": a.role,
             "text": a.text, "facts": a.fact, "deadline": deadline.strftime("%m/%d %H:%M"), "check": rule,
             "urgent": a.urgent, "sent": message, "waited_s": waited, "resent": resent, "reply": reply,
             "error": err if err else (None if reply else f"busy: {BUSY_TEXT}")}
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
