#!/usr/bin/env python3
"""A read-only dashboard of the Round 4 shop for a phone: the wallet and its trend, the board rank, the watch's alerts
and reconciliation, the relay, the tools the agent forged, its latest moves, what it said first in the app, Claude's
nudges and the time left in the early 72 hours. It reads only logs/ and the market's public board; no secret goes
on the page, and every value is escaped.

    python dashboard_r4.py               # port 8810 (DASH_PORT), from this folder

The same page is also written to app/dashboard.html every 30 s for the mini app's 현황 button (git-ignored).
It listens on 127.0.0.1 and on this computer's Tailscale address (100.64.0.0/10, found at start), never on the LAN
or a tunnel. The page asks for an access code kept in .kit/dashboard.key (git-ignored); the link with the code is
written to .kit/dashboard.url. Open it once on the phone (it sets a cookie), then Safari, Share, Add to Home Screen.
"""
import hmac
import html
import ipaddress
import json
import os
import re
import secrets
import statistics
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
KIT = HERE / ".kit"
PORT = int(os.environ.get("DASH_PORT", "8810"))
MARKET = os.environ.get("MARKET", "https://market.ourolabs.ai")
NAME = os.environ.get("AGENT_NAME", "thisjonghoon")
START_TOKRW = 5000.0
EARLY_END = 1798729140            # advisory team on until the owner says otherwise (was 11/27 19:00; 11/26 owner)
E = html.escape



def code():
    p = KIT / "dashboard.key"
    if not p.exists():
        KIT.mkdir(exist_ok=True)
        p.write_text(secrets.token_urlsafe(16), encoding="utf-8")
        p.chmod(0o600)
    return p.read_text(encoding="utf-8").strip()


def tailscale_ip():
    for cmd in (["/Applications/Tailscale.app/Contents/MacOS/Tailscale", "ip", "-4"], ["tailscale", "ip", "-4"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.split()
            if out:
                return out[0]
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        for ip in re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", subprocess.run(["ifconfig"], capture_output=True,
                                                                           text=True).stdout):
            if ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10"):
                return ip
    except OSError:
        pass
    return None


def jsonl(name, last=None):
    p = LOGS / name
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-last:] if last else lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


_board = {"at": 0, "data": None}


def board():
    if time.time() - _board["at"] > 60:
        try:
            with urllib.request.urlopen(MARKET.rstrip("/") + "/api/board", timeout=10) as r:
                _board["data"] = json.load(r)
        except Exception:
            pass
        _board["at"] = time.time()
    return _board["data"] or {}


def hm(ts):
    return time.strftime("%m/%d %H:%M", time.localtime(float(ts or 0)))


def clip(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def spark(points, w=320, h=72):
    """The wallet over time (dataviz review 11/24): one 2px line in the chart step of the accent, a 10% wash, a dashed
    reference at the start capital, the range labelled on the left, an end dot, and a hover/touch readout."""
    if len(points) < 2:
        return '<p class="none">기록이 더 쌓이면 그래프가 나옵니다</p>'
    t0, t1 = points[0][0], points[-1][0]
    vals = [v for _, v in points] + [START_TOKRW]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    X = lambda t: (t - t0) / ((t1 - t0) or 1) * w
    Y = lambda v: h - (v - lo) / (hi - lo) * h
    xy = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in points)
    area = f"M0,{h} L" + " L".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in points) + f" L{w},{h} Z"
    ref = Y(START_TOKRW)
    data = json.dumps([[int(t), round(v, 1)] for t, v in points], separators=(",", ":"))
    last_x, last_y = X(points[-1][0]) / w * 100, Y(points[-1][1]) / h * 100
    return (f'<div class="chartbox" data-pts=\'{E(data)}\' data-lo="{lo:.3f}" data-hi="{hi:.3f}" aria-label="지갑 추이">'
            f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" class="spark" aria-hidden="true">'
            f'<path class="area" d="{area}"/>'
            f'<line class="ref" x1="0" x2="{w}" y1="{ref:.1f}" y2="{ref:.1f}" vector-effect="non-scaling-stroke"/>'
            f'<polyline points="{xy}" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" '
            f'stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>'
            f'<span class="yl" style="top:-4px">{hi - pad:,.1f}</span><span class="yl" style="bottom:-4px">{lo + pad:,.1f}</span>'
            f'<span class="pt" style="left:{last_x:.2f}%;top:{last_y:.2f}%"></span>'
            f'<span class="hairv" hidden></span><span class="tip" hidden></span></div>'
            f'<div class="axis"><span>{hm(t0)}</span><span>점선: 시작 {START_TOKRW:,.0f}</span><span>{hm(t1)}</span></div>')

RANKS = KIT / "rank.jsonl"                              # the shop's rank over time, for the ▲▼ beside it


def rank_trend(now, rank, s_rank):
    """Append the rank when it changes (at most once a minute) and compare the student rank with an hour ago."""
    try:
        rows = [json.loads(l) for l in RANKS.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        rows = []
    if s_rank and (not rows or rows[-1].get("s_rank") != s_rank or now - rows[-1]["ts"] > 600):
        with open(RANKS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(now), "rank": rank, "s_rank": s_rank}) + "\n")
        rows.append({"ts": now, "rank": rank, "s_rank": s_rank})
    old = [r for r in rows if r["ts"] <= now - 3600]
    if not s_rank or not old:
        return ""
    moved = old[-1]["s_rank"] - s_rank                  # positive: climbed
    if moved == 0:
        return '<span class="num">— (1시간)</span>'
    return (f'<span><span class="{"up" if moved > 0 else "down"} num">{"▲" if moved > 0 else "▼"}{abs(moved)}</span>'
            '<span class="num"> (1시간)</span></span>')


ALERT_KO = [   # (what, a phrase in the text) -> (Korean, what to do); the watch writes English, the owner reads Korean
    ("relay", "answered by", "Claude 대신 다른 모델이 답했습니다", "조치 필요 없음 · 데스크를 쓰는 중이면 지난 일"),
    ("relay", "answered nothing", "모델 중계가 응답하지 않습니다", "Claude가 확인합니다"),
    ("relay", "took over", "모델 응답이 70초를 넘었습니다", "손님이 기다리다 떠날 수 있음"),
    ("mind", "", "에이전트의 모델 호출이 실패하고 있습니다", "Claude가 우리 중계로 되돌립니다"),
    ("wallet", "fell from", "지갑이 크게 줄었습니다", "매입인지 확인 · 멈춤이면 Claude가 원인 보고"),
    ("big", "", "큰 송금이 나갔습니다", "환불·보증인지 확인"),
    ("recon", "", "지갑과 기록이 맞지 않습니다", "결제만 되고 정산 안 된 손님인지 확인"),
    ("secret", "", "비밀값이 기록에 보입니다", "에이전트 멈춤 · 키 교체 필요"),
    ("bearer", "", "토큰 모양의 값이 기록에 보입니다", "Claude가 확인합니다"),
    ("process", "", "프로세스가 멈췄습니다", "Claude가 다시 띄웁니다"),
]


def alert_ko(a):
    what, text = a.get("what", ""), a.get("text", "")
    for w, phrase, ko, act in ALERT_KO:
        if what == w and phrase in text:
            nums = re.findall(r"\d[\d,.]*", text)
            return ko, act, nums[:2]
    return text, "", []


def lst(rows, empty="아직 없습니다."):
    """rows: (main html, small html); a .list like the activity sheet's."""
    if not rows:
        return f'<div class="none">{empty}</div>'
    return '<div class="list">' + "".join(r if isinstance(r, str) and r.startswith("<div") else
                                          f"<div>{r}</div>" if isinstance(r, str) else
                                          f"<div>{r[0]}{f'<small>{r[1]}</small>' if r[1] else ''}</div>" for r in rows) + "</div>"


# 가게 구조 (11/26, owner: "see the structure on our board"): who writes in, what answers in code, what the model decides,
# which forged tools sit behind it by role and what each may touch, and the advisory team outside. Read from tools/ and
# logs only; folded at the bottom of 현황 so the numbers stay first.
ROLES = [("판매·응대", ("a2a", "checkout", "card", "forum", "refund", "channel")),
         ("매입", ("buy_stock",)),
         ("원장·결제 확인", ("ledger", "chain", "payments", "audit", "inventory", "board", "compare")),
         ("시장 정보", ("market", "fetch", "read_market")),
         ("메모·기타", ())]


def structure(now, desk):
    tools = []
    for d in sorted((HERE / "tools").iterdir()) if (HERE / "tools").is_dir() else []:
        perm = d / "permission.yml"
        if d.name.startswith(".") or not perm.is_file():
            continue
        y = perm.read_text(encoding="utf-8", errors="replace")
        get = lambda k: (re.search(rf"^\s*{k}:\s*(.+)$", y, re.M) or [None, ""])[1].strip()
        tools.append({"name": d.name, "desc": get("description"), "ver": get("version") or "1",
                      "handles": "a2a" in get("handles"), "wallet": get("wallet") not in ("", "[]"),
                      "pay": get("pay_limit"), "net": get("network").strip("[]")})
    used = {}
    for e in jsonl("react.jsonl", 20000):
        if now - float(e.get("ts", 0)) <= 86400:
            used[e.get("action")] = used.get(e.get("action"), 0) + 1
    clerk = next((x for x in tools if x["handles"]), None)
    clerk_mode = "없음"
    if clerk:
        src = (HERE / "tools" / clerk["name"] / "logic.py").read_text(encoding="utf-8", errors="replace")
        body = [l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")]
        clerk_mode = "모든 문의를 에이전트에게 넘김" if len(body) <= 3 and "defer" in src else "코드로 바로 답하고, 필요할 때만 넘김"
    flow = ('<ol class="flow-steps">'
            '<li><b>손님·다른 가게</b><small>A2A로 가게에 메시지</small></li>'
            f'<li><b>자동 응대</b> <span class="num">{E(clerk["name"] + " v" + clerk["ver"]) if clerk else "-"}</span><small>{E(clerk_mode)}</small></li>'
            f'<li><b>에이전트</b><small>{"시장 모델 데스크" if desk else "우리 중계"} · 최근 24시간 행동 {sum(used.values())}번</small></li>'
            f'<li><b>만든 도구 {len(tools)}개</b><small>아래 역할별</small></li></ol>')
    def role(x):
        # match the bookkeeping words first, so audit_checkout_logs and checkout_payments are checks, not selling
        for name, keys in sorted(ROLES, key=lambda r: r[0] != "원장·결제 확인"):
            if any(k in x["name"] for k in keys):
                return name
        return ROLES[-1][0]
    groups = ""
    for name, _ in ROLES:
        rows = [x for x in tools if role(x) == name]
        if not rows:
            continue
        chips = "".join(
            f'<span class="tchip{" neutral" if not used.get(x["name"]) else ""}" title="{E(x["desc"])}">{E(x["name"])} '
            f'<span class="num">v{E(x["ver"])}</span>'
            + (' · 응대' if x["handles"] else "") + (' · 지갑' if x["wallet"] else "")
            + (f' · <span class="num">{used[x["name"]]}</span>회' if used.get(x["name"]) else "") + '</span>'
            for x in rows)
        groups += f'<div class="sub" style="margin:12px 0 6px">{E(name)} · {len(rows)}</div><div class="tchips">{chips}</div>'
    team = ('<div class="sub" style="margin:14px 0 6px">바깥에서 돕는 쪽</div><div class="list">'
            '<div><b>주인 jonghoon</b> · 앱 채팅으로 지시 (에이전트는 주인 말을 자기 도구보다 우선)</div>'
            '<div><b>Claude 조언팀</b> · 30분마다 기록 점검, 사실과 질문으로 넛지 (결정은 에이전트가)</div>'
            '<div><b>감시</b> · 지갑·장부 대조와 경보 (watch_r4)</div></div>')
    return ('<section class="panel g-st"><details class="struct" id="structure"><summary><h2 style="display:inline">가게 구조</h2>'
            '<small class="preview"> 손님 문의가 어디로 가서 누가 답하는지, 도구 역할과 권한</small></summary>'
            f'{flow}{groups}<div class="note">회색 칩은 최근 24시간 안 쓴 도구 · "응대"는 손님 메시지를 직접 받는 도구 · "지갑"은 서명·송금 권한</div>'
            f'{team}</details></section>')


def status_data():
    """현황 as data (11/27, owner: the mini app draws every screen itself). app/status.html reads this as
    app/status.json; no HTML here, every value is plain text or a number and the page escapes what it shows."""
    now = time.time()
    wallet = [e for e in jsonl("wallet.jsonl") if e.get("wallet") == "shop"]
    bal = wallet[-1]["tokrw"] if wallet else None
    pts = [(e["ts"], e["tokrw"]) for e in wallet if now - e["ts"] <= 48 * 3600]
    while pts and pts[0][1] == 0:                        # before the start capital came in
        pts.pop(0)
    if len(pts) > 300:
        pts = pts[:: len(pts) // 300 + 1] + [pts[-1]]
    b = board()
    students = [x for x in b.get("shops", []) if x.get("student")]
    me = next((x for x in b.get("shops", []) if x.get("name") == NAME), {})
    ranked = sum(1 for x in b.get("shops", []) if x.get("rank"))
    s_ranks = sorted(x.get("rank") for x in students if x.get("rank"))
    s_rank = s_ranks.index(me["rank"]) + 1 if me.get("rank") in s_ranks else None
    moved = rank_moved(now, me.get("rank"), s_rank)
    try:
        st = json.loads((KIT / "watch-state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    recon, watch_age = st.get("recon") or {}, now - st.get("last_pass", 0)
    alerts = jsonl("watch-r4.jsonl", 12)[::-1]
    relay = [e for e in jsonl("llm-relay.jsonl", 400) if now - e.get("ts", 0) <= 3600]
    ok = [e for e in relay if e.get("ok")]
    flagged = sum(1 for e in relay if "safeguards" in (e.get("why") or ""))
    forge = {}
    for e in jsonl("forge.jsonl"):
        forge[e.get("tool")] = e
    sales = [e for e in jsonl("ledger.jsonl") if e.get("kind") == "settle"]
    left = EARLY_END - now
    alive = watch_age < 180
    diff = recon.get("diff")
    desk = not [e for e in relay if now - e.get("ts", 0) <= 900]
    steps = [float(e.get("ts", 0)) for e in jsonl("react.jsonl", 400) if now - float(e.get("ts", 0)) <= 3600]
    gaps = [y - x for x, y in zip(steps, steps[1:]) if y - x < 120]
    fails = 0
    try:
        cut, end = time.strftime("%H:%M:%S", time.localtime(now - 3600)), time.strftime("%H:%M:%S", time.localtime(now))
        for line in (LOGS / "agent-kit.log").read_text(encoding="utf-8", errors="replace").splitlines()[-3000:]:
            t = line[:8]                                 # the kit stamps HH:MM:SS; the hour before may cross midnight
            if "[mind] model call failed" in line and ((cut <= t <= end) if cut <= end else (t >= cut or t <= end)):
                fails += 1
    except OSError:
        pass
    model_sub = ((f"응답 {statistics.median(gaps):.0f}초 · 실패 {fails}" if gaps else f"실패 {fails}") if desk else
                 f'{len(ok)}/{len(relay)} 응답 · 중앙 {statistics.median([e.get("secs", 0) for e in ok]) if ok else 0:.1f}초'
                 + (f" · 거절 {flagged}" if flagged else ""))
    cards = [
        {"k": "잔고 대조", "v": "-" if diff is None else ("일치" if abs(diff) < 0.005 else f"{diff:+,.2f}"),
         "tone": "down" if diff is not None and abs(diff) > 2 else "", "sub": "장부와 지갑 차이"},
        {"k": "판매 정산", "v": f"{len(sales)}건", "sub": f'판매가 {sum(e["data"].get("amount", 0) for e in sales):,} · 수수료 뺀 입금 '
         f'{sum(e["data"].get("amount", 0) - e["data"].get("shop_fee", 0) for e in sales):,} 크레딧'},
        {"k": "Claude 조언팀", "v": "켜짐" if left > 0 else "끝남", "sub": "주인이 끌 때까지 (11/26 연장)"},
        {"k": "모델", "v": "시장 데스크" if desk else "우리 중계", "sub": model_sub},
    ]
    MENU.clear()                                         # the ⋯ menu's rows (app/menu.json, written with the status)
    MENU.update({"at": time.strftime("%H:%M"), "warn": False, "rows": [
        {"k": "모델", "v": cards[3]["v"], "sub": model_sub},
        {"k": "Claude 조언팀", "v": cards[2]["v"], "sub": cards[2]["sub"]},
        {"k": "감시", "v": "정상" if alive else "멈춤?", "sub": f"마지막 점검 {int(watch_age)}초 전" if watch_age < 1e8 else "기록 없음"}]})
    out_alerts = []
    for a in alerts:
        ko, act, _ = alert_ko(a)
        out_alerts.append({"ts": a.get("ts", 0), "level": a.get("level", ""), "ko": ko, "act": act,
                           "orig": a.get("text", "") if ko != a.get("text") else ""})
    app_tools = [{"name": "app_say", "desc": "앱에 먼저 말하기 (키트)"}]
    try:
        page_src = (HERE / "app" / "index.html").read_text(encoding="utf-8")
        app_tools += [{"name": f"app_{n}", "desc": d} for n, d in re.findall(r"miniapp\.offer\('([a-z_]+)',\s*'([^']*)'", page_src)]
    except OSError:
        pass
    return {
        "at": int(now), "name": NAME, "alive": alive, "start": START_TOKRW,
        "wallet": {"bal": bal, "pts": [[int(t), round(v, 1)] for t, v in pts]},
        "rank": {"rank": me.get("rank"), "ranked": ranked, "s_rank": s_rank, "s_total": len(s_ranks), "moved": moved},
        "cards": cards,
        "alerts": out_alerts, "alerts_hour": sum(1 for a in alerts if now - a.get("ts", 0) <= 3600),
        "moves": [{"ts": float(e.get("ts", 0)), "action": str(e.get("action")),
                   "thought": " ".join(str(e.get("thought") or "").split())[:4000]} for e in jsonl("react.jsonl", 15)[::-1]],
        "forge": [{"name": str(n), "version": str(e.get("version")), "passed": bool(e.get("passed")), "ts": e.get("ts")}
                  for n, e in sorted(forge.items(), key=lambda kv: -float(kv[1].get("ts", 0)))],
        "app_tools": app_tools,
        "said": [{"ts": e.get("ts", 0), "text": str(e.get("said_first") or "").strip()} for e in jsonl("app.jsonl", 5)[::-1]],
        "nudges": [{"ts": e.get("ts", 0), "why": e.get("why", ""), "text": str(e.get("text") or "").strip(),
                    "reply": str(e.get("reply") or "").strip()} for e in jsonl("nudges.jsonl", 5)[::-1]],
        "structure": structure_data(now, desk),
    }


def rank_moved(now, rank, s_rank):
    """Append the rank when it changes (at most once in 10 minutes); how many student places it climbed in an hour."""
    try:
        rows = [json.loads(l) for l in RANKS.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        rows = []
    if s_rank and (not rows or rows[-1].get("s_rank") != s_rank or now - rows[-1]["ts"] > 600):
        with open(RANKS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(now), "rank": rank, "s_rank": s_rank}) + "\n")
        rows.append({"ts": now, "rank": rank, "s_rank": s_rank})
    old = [r for r in rows if r["ts"] <= now - 3600]
    return old[-1]["s_rank"] - s_rank if s_rank and old else None


def structure_data(now, desk):
    """가게 구조 as data: the clerk, the agent, the forged tools by role and their rights (see structure())."""
    tools = []
    for d in sorted((HERE / "tools").iterdir()) if (HERE / "tools").is_dir() else []:
        perm = d / "permission.yml"
        if d.name.startswith(".") or not perm.is_file():
            continue
        y = perm.read_text(encoding="utf-8", errors="replace")
        get = lambda k: (re.search(rf"^\s*{k}:\s*(.+)$", y, re.M) or [None, ""])[1].strip()
        tools.append({"name": d.name, "desc": get("description"), "ver": get("version") or "1",
                      "handles": "a2a" in get("handles"), "wallet": get("wallet") not in ("", "[]")})
    used = {}
    for e in jsonl("react.jsonl", 20000):
        if now - float(e.get("ts", 0)) <= 86400:
            used[e.get("action")] = used.get(e.get("action"), 0) + 1
    clerk = next((x for x in tools if x["handles"]), None)
    mode = "없음"
    if clerk:
        src = (HERE / "tools" / clerk["name"] / "logic.py").read_text(encoding="utf-8", errors="replace")
        body = [l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")]
        mode = "모든 문의를 에이전트에게 넘김" if len(body) <= 3 and "defer" in src else "코드로 바로 답하고, 필요할 때만 넘김"

    def role(x):
        for name, keys in sorted(ROLES, key=lambda r: r[0] != "원장·결제 확인"):
            if any(k in x["name"] for k in keys):
                return name
        return ROLES[-1][0]
    groups = []
    for name, _ in ROLES:
        rows = [dict(x, used=used.get(x["name"], 0)) for x in tools if role(x) == name]
        if rows:
            groups.append({"role": name, "tools": rows})
    return {"clerk": {"name": clerk["name"], "ver": clerk["ver"]} if clerk else None, "clerk_mode": mode, "desk": desk,
            "actions24": sum(used.values()), "count": len(tools), "groups": groups}


def page(in_app=False):
    now = time.time()
    wallet = [e for e in jsonl("wallet.jsonl") if e.get("wallet") == "shop"]
    bal = wallet[-1]["tokrw"] if wallet else None
    pts = [(e["ts"], e["tokrw"]) for e in wallet if now - e["ts"] <= 48 * 3600]
    while pts and pts[0][1] == 0:                        # before the start capital came in
        pts.pop(0)
    if len(pts) > 300:
        pts = pts[:: len(pts) // 300 + 1] + [pts[-1]]
    b = board()
    students = [x for x in b.get("shops", []) if x.get("student")]
    me = next((x for x in b.get("shops", []) if x.get("name") == NAME), {})
    ranked = sum(1 for x in b.get("shops", []) if x.get("rank"))   # the board ranks every shop, the market's own too
    s_ranks = sorted(x.get("rank") for x in students if x.get("rank"))
    s_rank = s_ranks.index(me["rank"]) + 1 if me.get("rank") in s_ranks else None
    trend = rank_trend(now, me.get("rank"), s_rank)
    try:
        st = json.loads((KIT / "watch-state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    recon, watch_age = st.get("recon") or {}, now - st.get("last_pass", 0)
    alerts = jsonl("watch-r4.jsonl", 12)[::-1]
    relay = [e for e in jsonl("llm-relay.jsonl", 400) if now - e.get("ts", 0) <= 3600]
    ok = [e for e in relay if e.get("ok")]
    flagged = sum(1 for e in relay if "safeguards" in (e.get("why") or ""))
    by = {}
    for e in ok:
        by[e.get("backend")] = by.get(e.get("backend"), 0) + 1
    forge = {}
    for e in jsonl("forge.jsonl"):
        forge[e.get("tool")] = e
    react = jsonl("react.jsonl", 15)[::-1]
    says = jsonl("app.jsonl", 5)[::-1]
    nudges = jsonl("nudges.jsonl", 5)[::-1]
    sales = [e for e in jsonl("ledger.jsonl") if e.get("kind") == "settle"]
    left = EARLY_END - now
    alive = watch_age < 180

    who = (f'<div class="avatar"><img src="/icon.svg?v=2" alt=""></div><div class="who"><h1>{E(NAME)}</h1>'
           f'<div class="status {"on" if alive else "off"}"><span class="dot"></span><span>'
           f'<span class="st-text">{"감시 정상" if alive else "감시 멈춤?"}</span> <span class="num">{E(time.strftime("%H:%M:%S"))}</span></span></div></div>')
    # in the mini app (11/27, owner): the shared frame of app/shell.js, tabs 현황 · 채팅 · 보드 and the ⋯ menu
    head = (f'<header class="wide app-head"><div class="ident">{who}</div>'
            '<nav class="tabs" aria-label="화면"><a href="/dashboard.html" aria-current="page">현황</a><a href="/">채팅</a>'
            '<a href="/board.html">보드<span class="badge" id="boardbadge" hidden></span></a></nav>'
            '<button type="button" class="morebtn" id="morebtn" aria-label="더보기" aria-haspopup="dialog" aria-expanded="false" aria-controls="menu">'
            '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="2"/>'
            '<circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg><span class="pip" hidden></span></button></header>'
            if in_app else f'<header class="wide">{who}</header>')

    def item(iid, head, preview, full):
        """A row that unfolds on a tap: two muted lines of preview, then the whole text (the sheet opens them all)."""
        return (f'<details class="move" id="{iid}"><summary>{head}<small class="preview" aria-hidden="true">{preview}</small></summary>'
                f'<p class="fulltext">{full}</p></details>')

    def more(key, rows, shown, empty="아직 없습니다."):
        """The first `shown` rows, the rest folded under 더보기 (its open state survives the 30 s refresh)."""
        if not rows:
            return f'<div class="none">{empty}</div>'
        out = lst(rows[:shown])
        if len(rows) > shown:
            out += f'<details class="more" id="more-{key}"><summary>전체 보기 · {len(rows)}</summary>{lst(rows[shown:])}</details>'
        return out

    d = (bal - START_TOKRW) if bal is not None else None
    hero = ('<section class="panel accent"><div class="split"><div><div class="label">가게 지갑</div>'
            f'<div class="big">{E(f"{bal:,.1f}") if bal is not None else "-"} <small>tOKRW</small></div>'
            + (f'<div class="sub {"up" if d >= 0 else "down"}">시작 대비 <span class="num">{d:+,.1f} ({d / START_TOKRW:+.1%})</span></div>' if d is not None else "")
            + f'</div><div class="right"><div class="label">보드 순위</div><div class="big">{E(str(me.get("rank") or "-"))}'
            f' <small>/ {ranked}</small></div></div></div>'
            f'<div class="rankline"><b>학생 <span class="num">{s_rank or "-"}</span>위</b>'
            f'{f"<span>상위 <span class=num>{s_rank / len(s_ranks):.0%}</span></span>" if s_rank and s_ranks else ""}{trend}</div>'
            f'<div class="trend">{spark(pts)}</div><div class="note">1 tOKRW = 1,000 크레딧</div></section>')

    diff = recon.get("diff")
    relay15 = [e for e in relay if now - e.get("ts", 0) <= 900]
    desk = not relay15
    # the desk: how fast the agent steps and how often a model call failed, in the last hour (from its own logs)
    steps = [float(e.get("ts", 0)) for e in jsonl("react.jsonl", 400) if now - float(e.get("ts", 0)) <= 3600]
    gaps = [b - a for a, b in zip(steps, steps[1:]) if b - a < 120]
    fails = 0
    try:
        cut, end = time.strftime("%H:%M:%S", time.localtime(now - 3600)), time.strftime("%H:%M:%S", time.localtime(now))
        for line in (LOGS / "agent-kit.log").read_text(encoding="utf-8", errors="replace").splitlines()[-3000:]:
            t = line[:8]                                 # the kit stamps HH:MM:SS; the hour before may cross midnight
            if "[mind] model call failed" in line and ((cut <= t <= end) if cut <= end else (t >= cut or t <= end)):
                fails += 1
    except OSError:
        pass
    desk_sub = f'응답 {statistics.median(gaps):.0f}초 · 실패 {fails}' if gaps else f"실패 {fails}"
    cards = [
        ("잔고 대조", "-" if diff is None else ("일치" if abs(diff) < 0.005 else f'<span class="{"" if abs(diff) <= 2 else "down"}">{diff:+,.2f}</span>'),
         "장부와 지갑 차이"),
        ("판매 정산", f"{len(sales)}건", f'판매가 {sum(e["data"].get("amount", 0) for e in sales):,} · 수수료 뺀 입금 '
         f'{sum(e["data"].get("amount", 0) - e["data"].get("shop_fee", 0) for e in sales):,} 크레딧'),
        ("Claude 조언팀", "켜짐" if left > 0 else "끝남", "주인이 끌 때까지 (11/26 연장)"),
        ("모델", "시장 데스크" if desk else "우리 중계",
         desk_sub if desk else f'{len(ok)}/{len(relay)} 응답 · 중앙 {statistics.median([e.get("secs", 0) for e in ok]) if ok else 0:.1f}초'
         + (f' · 거절 {flagged}' if flagged else "")),
    ]
    MENU.clear()                                         # the ⋯ menu's rows (app/menu.json, written with the page)
    MENU.update({"at": time.strftime("%H:%M"), "warn": False, "rows": [
        {"k": "모델", "v": cards[3][1], "sub": numify_plain(cards[3][2])},
        {"k": "Claude 조언팀", "v": cards[2][1], "sub": cards[2][2]},
        {"k": "감시", "v": "정상" if alive else "멈춤?", "sub": f"마지막 점검 {int(watch_age)}초 전" if watch_age < 1e8 else "기록 없음"}]})
    stats = '<div class="stats">' + "".join(
        f'<section class="panel"><div class="label">{E(a)}</div><div class="value">{v}</div><div class="sub clip">{numify(E(c))}</div></section>'
        for a, v, c in cards) + "</div>"

    # each move opens to its full thought on a tap (11/24); its id keeps it open across the 30 s refresh
    def move(e):
        full = " ".join(str(e.get("thought") or "").split())
        return (f'<details class="move" id="mv-{int(float(e.get("ts", 0)))}"><summary><span class="time">{E(hm(e.get("ts"))[6:])}</span> '
                f'<b>{E(str(e.get("action")))}</b><small class="preview" aria-hidden="true">{E(clip(full, 140))}</small></summary>'
                f'<p class="fulltext">{E(full[:4000])}</p></details>')
    mv = [move(e) for e in react]
    # phone: 3 moves; landscape: 6, so the tall left cell beside two stacked panels is filled (owner's layout, 11/24)
    moves = ('<section class="panel g-mv" id="activity"><h2>최근 행동</h2>'
             + (f'<div class="list">{"".join(f"<div>{m}</div>" for m in mv[:3])}'
                f'{"".join(f"<div class=wide-only>{m}</div>" for m in mv[3:6])}</div>' if mv else '<div class="none">아직 없습니다.</div>')
             # one 전체 보기: it also holds moves 4-6 for a phone (the list above shows them in landscape); the modal lists all
             + (f'<details class="more" id="more-moves"><summary>전체 보기 · {len(mv)}</summary><div class="list">'
                + "".join(f"<div class=narrow-only>{m.replace('id="mv-', 'id="mvn-', 1)}</div>" for m in mv[3:6])  # own ids
                + "".join(f"<div>{m}</div>" for m in mv[6:]) + "</div></details>" if len(mv) > 3 else "")
             + "</section>")
    alert_rows = []
    for a in alerts:
        ko, act, _ = alert_ko(a)
        lvl = a.get("level", "")
        alert_rows.append(item(f'al-{int(a.get("ts", 0))}-{len(alert_rows)}',
                               f'<span class="tag {E(lvl.lower())}">{"멈춤" if lvl == "STOP" else "경보"}</span> '
                               f'<span class="time">{E(hm(a.get("ts")))}</span> {E(ko)}', E(act),
                               E(act) + (f'<span class="orig">감시 원문 <span lang="en">{E(a.get("text", ""))}</span></span>' if ko != a.get("text") else "")))
    recent = sum(1 for a in alerts if now - a.get("ts", 0) <= 3600)
    alerts_html = (f'<section class="panel g-al"><h2>감시 경보 · 최근 1시간 {recent}건</h2>' + more("alerts", alert_rows, 3, "경보 없음")
                   + "</section>")
    chips = "".join(
        f'<span class="tchip {"" if e.get("passed") else "bad"}" title="{E(hm(e.get("ts")))}">{E(str(n))} <span class="num">v{E(str(e.get("version")))}</span></span>'
        for n, e in sorted(forge.items(), key=lambda kv: -float(kv[1].get("ts", 0))))
    # three rows of chips at most; when they overflow, the page's script shows 전체 보기 (11/24, owner)
    tools = (f'<section class="panel g-tl"><h2>만든 도구 · {len(forge)}</h2><div class="tchips cap">{chips}</div>'
             f'<details class="more chipsmore" id="more-tools"><summary>전체 보기 · {len(forge)}</summary>'
             f'<div class="tchips">{chips}</div></details></section>') if forge else ""
    # app_say: whatever the agent sends to the app outside a reply (the kit logs it as said_first); 11/24 19:45 it was
    # the promised follow-up to the owner's question, so it is not always the agent speaking first
    # the tools this app gives the agent (the kit logs none of them): app_say from the kit, and each miniapp.offer in
    # app/index.html; they were in the chat's activity sheet, which is gone (11/24)
    app_tools = [("app_say", "앱에 먼저 말하기 (키트)")]
    try:
        page_src = (HERE / "app" / "index.html").read_text(encoding="utf-8")
        app_tools += [(f"app_{n}", d) for n, d in re.findall(r"miniapp\.offer\('([a-z_]+)',\s*'([^']*)'", page_src)]
    except OSError:
        pass
    tools = tools.replace("</section>", '<div class="sub" style="margin:12px 0 6px">이 앱이 준 도구</div><div class="tchips">' + "".join(
        f'<span class="tchip neutral" title="{E(d)}">{E(n)}</span>' for n, d in app_tools) + "</div></section>", 1) if tools else tools
    said = ('<section class="panel g-sd"><h2>스스로 보낸 메시지</h2><div class="sub" style="margin:-6px 0 10px">직접 답장 외에 에이전트가 채팅에 따로 올린 후속 답과 알림</div>' + more("said",
            [item(f'sd-{int(e.get("ts", 0))}-{i}', f'<span class="time">{E(hm(e.get("ts")))}</span>',
                  E(" ".join(str(e.get("said_first") or "").split())), E(str(e.get("said_first") or "").strip()))
             for i, e in enumerate(says)], 2) + "</section>")
    asked = ('<section class="panel g-qs"><h2>Claude의 질문</h2>' + more("nudges",
             [item(f'qs-{int(e.get("ts", 0))}-{i}',
                   f'<span class="time">{E(hm(e.get("ts")))}</span> <span class="tag">{E({"early": "조언팀", "alert": "경보", "offhours": "부재"}.get(e.get("why"), str(e.get("why", ""))))}</span>',
                   E(" ".join(str(e.get("text") or "").split()))
                   + (f'<span class="a">→ {E(" ".join(str(e.get("reply")).split()))}</span>' if e.get("reply") else ""),
                   f'<span class="q">{E(str(e.get("text") or "").strip())}</span>'
                   + (f'<span class="a">→ {E(str(e.get("reply")).strip())}</span>' if e.get("reply") else ""))
              for i, e in enumerate(nudges)], 3) + "</section>")

    # phone: one column in this order; landscape (owner's layout, 11/24): alerts | tools, then moves tall on the left
    # beside the app messages over Claude's questions
    body = (f'<div class="top">{hero}{stats}</div>'
            f'<div class="lower">{alerts_html}{moves}{tools}{said}{asked}</div>{structure(now, desk)}')

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0e0f10" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="R4 가게"><title>현황 · {E(NAME)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<meta name="description" content="thisjonghoon 가게의 지갑, 순위, 감시 경보와 에이전트 활동">
<style>{ui_css()}</style></head><body class="screen">{head}<div id="pane"><main class="page wide" data-ts="{int(now)}">{body}{"" if in_app else CREDIT}</main></div>{MENU_SHEET if in_app else ""}
<dialog id="full" class="full" aria-labelledby="full-h"><div class="full-head"><h2 id="full-h"></h2>
<button type="button" class="full-x" aria-label="닫기">✕</button></div><div class="full-body"></div></dialog>
<script>
// every 30 s swap in the new numbers without reloading: the scroll position and any open 더보기 stay as they are;
// when the style itself changed (a new look), reload the whole page instead. A failed or late refresh shows in the header.
const mark = (text) => {{ document.body.classList.add('stale'); const t = document.querySelector('.st-text'); if (t) t.textContent = text; }};
setInterval(async () => {{
  if (document.hidden) return;
  try {{
    const r = await fetch(location.pathname, {{cache: 'no-store'}});
    if (!r.ok) {{ mark('갱신 실패'); return; }}
    const d = new DOMParser().parseFromString(await r.text(), 'text/html');
    if (d.querySelector('style')?.textContent !== document.querySelector('style')?.textContent) {{ location.reload(); return; }}
    if (document.querySelector('main').contains(document.activeElement)) return;
    const open = [...document.querySelectorAll('details[open]')].map(x => x.id);
    document.querySelector('main').replaceWith(d.querySelector('main'));
    document.querySelector('header .status').replaceWith(d.querySelector('header .status'));
    document.body.classList.remove('stale');
    open.forEach(id => {{ const e = document.getElementById(id); if (e) e.open = true; }});
    chart(); caps(); cans(); if (full.open) fill(full.dataset.key);
  }} catch (e) {{ mark('갱신 실패'); }}
}}, 30000);
setInterval(() => {{
  const ts = +document.querySelector('main')?.dataset.ts || 0, age = Date.now() / 1000 - ts;
  if (age > 90) mark(`업데이트 ${{Math.round(age / 60)}}분 전`);
}}, 5000);
// the wallet chart's readout: a hairline and the value at the nearest point, by pointer or touch
function chart() {{
  const box = document.querySelector('.chartbox'); if (!box) return;
  const pts = JSON.parse(box.dataset.pts), lo = +box.dataset.lo, hi = +box.dataset.hi;
  const line = box.querySelector('.hairv'), tip = box.querySelector('.tip');
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
  const show = (clientX) => {{
    const r = box.getBoundingClientRect(), f = Math.min(1, Math.max(0, (clientX - r.left) / r.width)), t = t0 + f * (t1 - t0);
    let best = pts[0]; for (const p of pts) if (Math.abs(p[0] - t) < Math.abs(best[0] - t)) best = p;
    const x = (best[0] - t0) / ((t1 - t0) || 1) * 100;
    line.hidden = tip.hidden = false; line.style.left = tip.style.left = x + '%';
    const d = new Date(best[0] * 1000);
    tip.textContent = `${{String(d.getHours()).padStart(2, '0')}}:${{String(d.getMinutes()).padStart(2, '0')}} · ${{best[1].toLocaleString('ko-KR', {{minimumFractionDigits: 1}})}}`;
  }};
  box.onpointermove = e => show(e.clientX);
  box.onpointerdown = e => show(e.clientX);
  box.onpointerleave = () => {{ line.hidden = tip.hidden = true; }};
}}
chart();
// 전체 보기: a full-screen list of the whole panel instead of unfolding in place (11/24, owner); without the script the
// <details> still unfold. The list is rebuilt from the page on each 30 s refresh while it is open.
const full = document.getElementById('full');
function fill(key) {{
  const panel = document.querySelector('main .' + key); if (!panel) {{ full.close(); return; }}
  full.dataset.key = key;
  document.getElementById('full-h').textContent = panel.querySelector('h2').textContent;
  const body = full.querySelector('.full-body'); body.replaceChildren();
  const chipsAll = panel.querySelector('details.chipsmore .tchips');
  if (chipsAll) {{ body.append(chipsAll.cloneNode(true)); return; }}
  // a copy: no ids (they belong to the page), every move unfolded so the sheet shows whole texts
  const list = document.createElement('div'); list.className = 'list';
  panel.querySelectorAll('.list>div:not(.wide-only)').forEach(x => {{ const c = x.cloneNode(true); c.classList.remove('narrow-only'); list.append(c); }});
  list.querySelectorAll('[id]').forEach(x => x.removeAttribute('id'));
  list.querySelectorAll('details.move').forEach(x => x.open = true);
  body.append(list);
}}
document.addEventListener('click', e => {{
  const s = e.target.closest('details.more>summary'); if (!s) return;
  e.preventDefault();
  const key = [...s.closest('section.panel').classList].find(c => c.startsWith('g-'));
  fill(key); full.showModal(); full.querySelector('.full-body').scrollTop = 0;
}});
full.querySelector('.full-x').onclick = () => full.close();
// back to the 전체 보기 that opened it (the page may have been refreshed under the sheet meanwhile)
full.addEventListener('close', () => document.querySelector('main .' + full.dataset.key + ' details.more>summary')?.focus());
// a click on the dimmed page around the web's sheet closes it (the sheet fills the screen elsewhere, so no such click)
full.addEventListener('click', e => {{ if (e.target === full) full.close(); }});
// the tools' 전체 보기 shows only when the chips overflow their three rows
// a row whose whole text is longer than its two-line preview gets a chevron (.can), so a tap visibly has more to give
function cans() {{ document.querySelectorAll('main details.move').forEach(d => {{ const p = d.querySelector('.preview'), f = d.querySelector('.fulltext');
  if (!d.open && p) d.classList.toggle('can', p.scrollHeight > p.clientHeight + 1 || (f && f.textContent.trim().length > p.textContent.trim().length + 2)); }}); }}
function caps() {{ document.querySelectorAll('.tchips.cap').forEach(c => c.closest('section').classList.toggle('over', c.scrollHeight > c.clientHeight + 2)); }}
document.documentElement.classList.add('js'); caps(); addEventListener('resize', caps); document.fonts?.ready.then(() => {{ caps(); cans(); }}); cans(); addEventListener('resize', cans);
</script>{'<script src="/shell.js?v=3"></script>' if in_app else ''}</body></html>"""


def numify(text):
    """Digits in a sub line go in the number face (DESIGN.md: every number is D2Coding)."""
    return re.sub(r"(\d[\d,.:%]*)", r'<span class="num">\1</span>', text)



def ui_css():
    """app/ui.css, the one look the chat and this page share (inlined: the Tailscale page has no /ui.css)."""
    try:
        return (HERE / "app" / "ui.css").read_text(encoding="utf-8")
    except OSError:
        return ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        key = code()
        given = parse_qs(u.query).get("k", [""])[0]
        cookie = re.search(r"(?:^|;\s*)r4dash=([^;]+)", self.headers.get("Cookie", ""))
        if given and hmac.compare_digest(given, key):
            self.send_response(303)
            self.send_header("Set-Cookie", f"r4dash={key}; Max-Age=2592000; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Location", "/")
            self.end_headers()
            return
        if not (cookie and hmac.compare_digest(cookie.group(1), key)):
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("접근 코드가 필요합니다 (.kit/dashboard.url의 링크로 한 번 여세요)".encode())
            return
        try:
            body = page().encode()
            self.send_response(200)
        except Exception as e:                          # the page must not die on one bad log line
            body = f"page error: {type(e).__name__}".encode()
            self.send_response(500)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)


APP_COPY = HERE / "app" / "dashboard.html"           # the mini app serves it behind its own access code (11/24)
STATUS_COPY = HERE / "app" / "status.json"           # 11/27: 현황 as data; app/status.html draws it
MENU_COPY = HERE / "app" / "menu.json"               # the ⋯ menu's rows (11/27)
MENU = {}
CREDIT = ('<p class="note credit">미니앱 키트는 <a href="https://github.com/Q00/meshkit" target="_blank" rel="noopener">MeshKit</a>과 '
          '<a href="https://github.com/Q00/ouroboros" target="_blank" rel="noopener">Ouroboros</a>에서 영감을 받았습니다</p>')
MENU_SHEET = ('<div class="shade" id="menu" hidden><div class="sheet menu-sheet" role="dialog" aria-modal="true" aria-labelledby="menu-h" tabindex="-1">'
              '<div class="grip"></div><h2 id="menu-h">가게 정보</h2><div id="menu-body"></div></div></div>')


def numify_plain(text):
    return re.sub(r"<[^>]+>", "", text)


TICKET_LIMITS = os.environ.get("TICKET_LIMITS", "http://127.0.0.1:8830/api/limits")


def usage_rows():
    """Claude and Codex plan usage from the ticket app (hoon-ticket's top-bar meter, local only; 11/27 owner).
    The ticket app caches it for 5 minutes. Copilot and OpenRouter are left out (owner)."""
    try:
        with urllib.request.urlopen(TICKET_LIMITS, timeout=8) as r:
            snap = json.loads(r.read())
    except Exception:
        return [], False
    rows, warn = [], False
    for a in snap.get("agents", []):
        if a.get("agent") not in ("claude", "codex"):
            continue
        ws = {w["label"]: w for w in a.get("windows", [])}
        week, five = ws.get("Week"), ws.get("5 hours")
        if not week:
            continue
        rest = [f'5시간 {five["usedPercent"]:.0f}%'] if five else []
        rest += [f'{k.replace("Week · ", "")} {w["usedPercent"]:.0f}%' for k, w in ws.items() if k.startswith("Week · ")]
        if week.get("resetsAt"):
            rest.append("리셋 " + time.strftime("%m/%d %H:%M", time.localtime(week["resetsAt"] / 1000)))
        pct = week["usedPercent"]
        warn = warn or pct >= 85 or (five or {}).get("usedPercent", 0) >= 90
        rows.append({"k": "Claude" if a["agent"] == "claude" else "Codex", "v": f"주간 {pct:.0f}%", "sub": " · ".join(rest),
                     "pct": pct})
    return rows, warn


def board_sync():
    """Orders the owner sent from the app move to 반영·검증 (board_r4.py sync), on the page's own 30 s beat."""
    if not (LOGS / "board.jsonl").exists():
        return
    import contextlib, io
    import board_r4
    with contextlib.redirect_stdout(io.StringIO()):
        board_r4.main(["sync"])


def write_app_copy():
    """Every 30 s, 현황's data into app/status.json for the mini app's app/status.html (git-ignored; no secret in it).
    Until 11/27 this wrote the whole page (app/dashboard.html); that address now forwards to the new page."""
    APP_COPY.write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=/status.html">'
                        '<a href="/status.html">현황</a>', encoding="utf-8")
    while True:
        try:
            data = status_data()
            tmp = STATUS_COPY.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(STATUS_COPY)                # whole or nothing: the app never reads half a status
            use, warn = usage_rows()
            menu = dict(MENU, rows=use + MENU.get("rows", []), warn=warn)
            tmp = MENU_COPY.with_suffix(".tmp")
            tmp.write_text(json.dumps(menu, ensure_ascii=False), encoding="utf-8")
            tmp.replace(MENU_COPY)
            board_sync()
        except Exception as e:
            print(f"[dash] app copy not written: {type(e).__name__}: {e}", flush=True)
        time.sleep(30)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-serve", action="store_true",
                    help="only write app/status.json for the mini app's 현황 (11/24: the separate Tailscale page is off)")
    a = ap.parse_args()
    if a.no_serve:
        print("[dash] writing app/status.json every 30 s for the mini app (no server of its own)", flush=True)
        write_app_copy()                                 # runs forever
        return
    key = code()
    hosts = ["127.0.0.1"] + [ip for ip in [tailscale_ip()] if ip]
    servers = [ThreadingHTTPServer((h, PORT), Handler) for h in hosts]
    links = [f"http://{h}:{PORT}/?k={key}" for h in hosts]
    (KIT / "dashboard.url").write_text("\n".join(links) + "\n", encoding="utf-8")
    (KIT / "dashboard.url").chmod(0o600)
    print(f"[dash] listening on {', '.join(f'{h}:{PORT}' for h in hosts)}; links with the code in .kit/dashboard.url",
          flush=True)
    threading.Thread(target=write_app_copy, daemon=True).start()
    for srv in servers[1:]:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    servers[0].serve_forever()


if __name__ == "__main__":
    main()
