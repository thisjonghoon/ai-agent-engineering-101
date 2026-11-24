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
EARLY_END = 1795777200            # 11/27 19:00 KST: the end of the early 72 hours
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


def spark(points, w=320, h=64):
    if len(points) < 2:
        return '<p class="none">기록이 더 쌓이면 그래프가 나옵니다</p>'
    t0, t1 = points[0][0], points[-1][0]
    lo, hi = min(v for _, v in points), max(v for _, v in points)
    span, tspan = (hi - lo) or 1, (t1 - t0) or 1
    xy = " ".join(f"{(t - t0) / tspan * w:.1f},{h - 4 - (v - lo) / span * (h - 8):.1f}" for t, v in points)
    return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" class="spark" role="img" aria-label="지갑 추이">'
            f'<polyline points="{xy}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>'
            f'<div class="axis"><span>{hm(t0)}</span><span>{lo:,.1f} ~ {hi:,.1f}</span><span>{hm(t1)}</span></div>')


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


def lst(rows, empty="아직 없습니다."):
    """rows: (main html, small html); a .list like the activity sheet's."""
    if not rows:
        return f'<div class="none">{empty}</div>'
    return '<div class="list">' + "".join(f"<div>{a}{f'<small>{b}</small>' if b else ''}</div>" for a, b in rows) + "</div>"


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

    seg = ('<nav class="seg" aria-label="화면"><a href="/">채팅</a><a href="/dashboard.html" aria-current="page">현황</a></nav>'
           if in_app else '')
    head = (f'<header class="wide"><div class="avatar">{E(NAME[:1].upper())}</div><div class="who"><b>{E(NAME)}</b>'
            f'<div class="status {"on" if alive else "off"}"><span class="dot"></span><span>'
            f'{"감시 정상" if alive else "감시 멈춤?"} · <span class="num">{E(time.strftime("%H:%M:%S"))}</span></span></div></div>'
            f'<a class="btn" href="#activity">활동</a>{seg}</header>')

    def more(key, rows, shown, empty="아직 없습니다."):
        """The first `shown` rows, the rest folded under 더보기 (its open state survives the 30 s refresh)."""
        if not rows:
            return f'<div class="none">{empty}</div>'
        out = lst(rows[:shown])
        if len(rows) > shown:
            out += f'<details class="more" id="more-{key}"><summary>더보기 · {len(rows) - shown}</summary>{lst(rows[shown:])}</details>'
        return out

    d = (bal - START_TOKRW) if bal is not None else None
    hero = ('<section class="panel accent"><div class="split"><div><div class="label">가게 지갑</div>'
            f'<div class="big">{E(f"{bal:,.1f}") if bal is not None else "-"} <small>tOKRW</small></div>'
            + (f'<div class="sub {"up" if d >= 0 else "down"}">시작 대비 <span class="num">{d:+,.1f} ({d / START_TOKRW:+.1%})</span></div>' if d is not None else "")
            + f'</div><div class="right"><div class="label">보드 순위</div><div class="big">{E(str(me.get("rank") or "-"))}'
            f' <small>/ {ranked}</small></div></div></div>'
            f'<div class="rankline"><b>학생 <span class="num">{s_rank or "-"}</span>위</b>'
            f'{f"<span>상위 <span class=num>{s_rank / len(s_ranks):.0%}</span></span>" if s_rank and s_ranks else ""}{trend}</div>'
            f'<div class="trend">{spark(pts)}</div></section>')

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
        ("잔고 대조", f'<span class="{"" if diff is None or abs(diff) <= 2 else "down"}">{"-" if diff is None else f"{diff:+,.2f}"}</span>',
         "기록과 지갑의 차이"),
        ("판매 정산", f"{len(sales)}건", f'{sum(e["data"].get("amount", 0) for e in sales):,} 크레딧'),
        ("초반 돕기", f"{int(left // 3600)}시간 {int(left % 3600 // 60)}분" if left > 0 else "끝남", "11/27 19:00까지"),
        ("모델", "데스크" if desk else "우리 중계",
         desk_sub if desk else f'{len(ok)}/{len(relay)} 응답 · 중앙 {statistics.median([e.get("secs", 0) for e in ok]) if ok else 0:.1f}초'
         + (f' · 거절 {flagged}' if flagged else "")),
    ]
    stats = '<div class="stats">' + "".join(
        f'<section class="panel"><div class="label">{E(a)}</div><div class="value">{v}</div><div class="sub clip">{E(c)}</div></section>'
        for a, v, c in cards) + "</div>"

    moves = ('<section class="panel" id="activity"><h2>최근 행동</h2>' + more("moves",
             [(f'<span class="time">{E(hm(e.get("ts"))[6:])}</span> <b>{E(str(e.get("action")))}</b>', E(clip(e.get("thought"), 140)))
              for e in react], 5) + "</section>")
    alert_rows = [(f'<span class="tag {E(a.get("level", "").lower())}">{E(a.get("level", ""))}</span> <span class="time">{E(hm(a.get("ts")))}</span>',
                   E(clip(a.get("text"), 140))) for a in alerts]
    alerts_html = '<section class="panel"><h2>감시 경보</h2>' + more("alerts", alert_rows, 3, "경보 없음") + "</section>"
    tools = (f'<section class="panel"><h2>만든 도구 · {len(forge)}</h2><div class="tchips">' + "".join(
             f'<span class="tchip {"" if e.get("passed") else "bad"}" title="{E(hm(e.get("ts")))}">{E(str(n))} <span class="num">v{E(str(e.get("version")))}</span></span>'
             for n, e in sorted(forge.items(), key=lambda kv: -float(kv[1].get("ts", 0)))) + "</div></section>") if forge else ""
    # app_say: whatever the agent sends to the app outside a reply (the kit logs it as said_first); 11/24 19:45 it was
    # the promised follow-up to the owner's question, so it is not always the agent speaking first
    said = ('<section class="panel"><h2>앱으로 보낸 말</h2><div class="sub" style="margin:-6px 0 10px">답장 밖에서 보낸 메시지: 후속 답, 알림</div>' + more("said",
            [(f'<span class="time">{E(hm(e.get("ts")))}</span>', E(clip(e.get("said_first"), 200))) for e in says], 2) + "</section>")
    asked = ('<section class="panel"><h2>Claude의 질문</h2>' + more("nudges",
             [(f'<span class="time">{E(hm(e.get("ts")))}</span> <span class="tag">{E(str(e.get("why", "")))}</span>',
               E(clip(e.get("text"), 120)) + (f'<br>→ {E(clip(e.get("reply"), 140))}' if e.get("reply") else ""))
              for e in nudges], 3) + "</section>")

    body = (f'<div class="top">{hero}{stats}</div>'
            f'<div class="cols"><div class="col">{moves}</div><div class="col">{alerts_html}{tools}{said}{asked}</div></div>')

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="R4 가게"><title>현황 · {E(NAME)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700;800&family=Nanum+Gothic+Coding:wght@400;700&display=swap">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/joungkyun/font-d2coding@1.3.2/d2coding.css">
<style>{ui_css()}</style></head><body class="screen">{head}<main class="page wide">{body}</main>
<script>
// every 30 s swap in the new numbers without reloading: the scroll position and any open 더보기 stay as they are
setInterval(async () => {{
  try {{
    const r = await fetch(location.pathname, {{cache: 'no-store'}});
    if (!r.ok) return;
    const d = new DOMParser().parseFromString(await r.text(), 'text/html');
    const open = [...document.querySelectorAll('details[open]')].map(x => x.id);
    document.querySelector('main').replaceWith(d.querySelector('main'));
    document.querySelector('header .status').replaceWith(d.querySelector('header .status'));
    open.forEach(id => {{ const e = document.getElementById(id); if (e) e.open = true; }});
  }} catch (e) {{}}
}}, 30000);
</script></body></html>"""


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


def write_app_copy():
    """Every 30 s, the same page into app/ so the mini app's 현황 button opens it (git-ignored; no secret in it)."""
    while True:
        try:
            tmp = APP_COPY.with_suffix(".tmp")
            tmp.write_text(page(in_app=True), encoding="utf-8")
            tmp.replace(APP_COPY)                   # whole or nothing: the app never serves half a page
        except Exception as e:
            print(f"[dash] app copy not written: {type(e).__name__}: {e}", flush=True)
        time.sleep(30)


def main():
    key = code()
    hosts = ["127.0.0.1"] + [ip for ip in [tailscale_ip()] if ip]
    servers = [ThreadingHTTPServer((h, PORT), Handler) for h in hosts]
    links = [f"http://{h}:{PORT}/?k={key}" for h in hosts]
    (KIT / "dashboard.url").write_text("\n".join(links) + "\n", encoding="utf-8")
    (KIT / "dashboard.url").chmod(0o600)
    print(f"[dash] listening on {', '.join(f'{h}:{PORT}' for h in hosts)}; links with the code in .kit/dashboard.url",
          flush=True)
    threading.Thread(target=write_app_copy, daemon=True).start()
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    servers[0].serve_forever()


if __name__ == "__main__":
    main()
