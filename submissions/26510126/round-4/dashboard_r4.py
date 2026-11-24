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
    return (f'<svg viewBox="0 0 {w} {h}" class="spark" role="img" aria-label="지갑 추이">'
            f'<polyline points="{xy}" fill="none" stroke="currentColor" stroke-width="2"/></svg>'
            f'<div class="axis"><span>{hm(t0)}</span><span>{lo:,.1f} ~ {hi:,.1f}</span><span>{hm(t1)}</span></div>')


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
           if in_app else '<span class="btn">현황</span>')
    head = (f'<header><div class="avatar">{E(NAME[:1].upper())}</div><div class="who"><b>{E(NAME)}</b>'
            f'<div class="status {"on" if alive else "off"}"><span class="dot"></span><span>'
            f'{"감시 정상" if alive else "감시 멈춤?"} · {E(time.strftime("%H:%M:%S"))}</span></div></div>'
            f'<a class="btn" href="#activity">활동</a>{seg}</header>')
    h = []
    d = (bal - START_TOKRW) if bal is not None else None
    h.append('<section class="panel accent"><div class="split"><div><div class="label">가게 지갑</div>'
             f'<div class="big">{E(f"{bal:,.1f}") if bal is not None else "-"} <small>tOKRW</small></div>'
             + (f'<div class="sub {"up" if d >= 0 else "down"}">시작 대비 {d:+,.1f} ({d / START_TOKRW:+.1%})</div>' if d is not None else "")
             + f'</div><div class="right"><div class="label">보드 순위</div><div class="big">{E(str(me.get("rank") or "-"))}'
             f' <small>/ {ranked}곳</small></div><div class="sub">학생 중 {s_rank or "-"}위 / {len(s_ranks)}곳</div></div></div></section>')
    h.append(f'<section class="panel"><h2>지갑 추이 · 48시간</h2>{spark(pts)}</section>')

    diff = recon.get("diff")
    med = statistics.median([e.get("secs", 0) for e in ok]) if ok else 0
    cards = [
        ("잔고 대조", f'<span class="{"" if diff is None or abs(diff) <= 2 else "down"}">{"-" if diff is None else f"{diff:+,.2f}"}</span>', "기록과 지갑의 차이 · tOKRW"),
        ("판매 정산", f"{len(sales)}건", f'{sum(e["data"].get("amount", 0) for e in sales):,} 크레딧'),
        ("초반 돕기", f"{int(left // 3600)}시간 {int(left % 3600 // 60)}분" if left > 0 else "끝남", "11/27 19:00까지"),
        ("중계 · 1시간", f"{len(ok)}/{len(relay)}", f'중앙 {med:.1f}초 · ' + " · ".join(f"{k} {v}" for k, v in sorted(by.items()))
         + (f" · 안전장치 {flagged}" if flagged else "") if relay else "데스크 사용 중 · 호출 없음"),
    ]
    h.append('<div class="stats">' + "".join(f'<section class="panel"><div class="label">{E(a)}</div><div class="value">{v}</div>'
                                            f'<div class="sub">{E(c)}</div></section>' for a, v, c in cards) + "</div>")

    claude1h = [e for e in ok if str(e.get("backend", "")).startswith("claude")]
    snaps = []
    try:
        snaps = [json.loads(l) for l in (KIT / "usage.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        pass
    if snaps:
        last = snaps[-1]
        proj = f'주간 {last["pct"]}% ({hm(last["ts"])} 기준) · 리셋까지 {max(0.0, (last.get("resets", 0) - now) / 3600):.0f}시간'
        if len(snaps) >= 2 and snaps[-1]["ts"] > snaps[-2]["ts"]:
            rate = (snaps[-1]["pct"] - snaps[-2]["pct"]) / ((snaps[-1]["ts"] - snaps[-2]["ts"]) / 3600)
            end = last["pct"] + rate * max(0.0, (last.get("resets", 0) - last["ts"]) / 3600)
            proj += f" · {rate:.2f}%/시간 → 리셋 때 {end:.0f}%"
        h.append(f'<section class="panel"><h2>Claude 사용</h2><div class="value">중계 {len(claude1h)}회 · 1시간</div>'
                 f'<div class="sub">{E(proj)}</div></section>')

    h.append('<section class="panel"><h2>감시 경보</h2>' + lst(
        [(f'<span class="tag {E(a.get("level", "").lower())}">{E(a.get("level", ""))}</span> <span class="time">{E(hm(a.get("ts")))}</span>',
          E(clip(a.get("text"), 200))) for a in alerts], "경보 없음") + "</section>")
    h.append('<section class="panel" id="activity"><h2>최근 행동</h2>' + lst(
        [(f'<span class="time">{E(hm(e.get("ts")))}</span> <b>{E(str(e.get("action")))}</b>', E(clip(e.get("thought"), 180)))
         for e in react]) + "</section>")
    h.append(f'<section class="panel"><h2>만든 도구 · {len(forge)}</h2>' + lst(
        [(f'<b>{E(str(n))}</b> <span class="time">v{E(str(e.get("version")))}</span> '
          f'<span class="tag {"ok" if e.get("passed") else "stop"}">{"통과" if e.get("passed") else "실패"}</span>',
          f'<span class="time">{E(hm(e.get("ts")))}</span>')
         for n, e in sorted(forge.items(), key=lambda kv: -float(kv[1].get("ts", 0)))]) + "</section>")
    h.append('<section class="panel"><h2>에이전트가 먼저 한 말</h2>' + lst(
        [(f'<span class="time">{E(hm(e.get("ts")))}</span>', E(clip(e.get("said_first"), 220))) for e in says]) + "</section>")
    h.append('<section class="panel"><h2>Claude의 질문</h2>' + lst(
        [(f'<span class="time">{E(hm(e.get("ts")))}</span> <span class="tag">{E(str(e.get("why", "")))}</span>',
          E(clip(e.get("text"), 160)) + (f'<br>→ {E(clip(e.get("reply"), 160))}' if e.get("reply") else ""))
         for e in nudges]) + "</section>")

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta http-equiv="refresh" content="30"><meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="R4 가게"><title>현황 · {E(NAME)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700;800&family=Nanum+Gothic+Coding:wght@400;700&display=swap">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/joungkyun/font-d2coding@1.3.2/d2coding.css">
<style>{ui_css()}</style></head><body class="screen">{head}<main class="page">{"".join(h)}</main></body></html>"""


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
