#!/usr/bin/env python3
"""A read-only dashboard of the Round 4 shop for a phone: the wallet and its trend, the board rank, the watch's alerts
and reconciliation, the relay, the tools the agent forged, its latest moves, what it said first in the app, Claude's
nudges and the time left in the early 72 hours. It reads only logs/ and the market's public board; no secret goes
on the page, and every value is escaped.

    python dashboard_r4.py               # port 8810 (DASH_PORT), from this folder

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

# webtoon-review-board's design system (paper, ink, one accent, red for errors only), with Hermes orange as the accent and D2Coding for numbers
CSS = """
:root{--paper:#f4f5f6;--sheet:#fff;--ink:#111214;--muted:#6b7178;--rule:#e3e5e8;--chip:#eef0f2;
--accent:#f37021;--on-accent:#0a0a0a;--accent-ink:#b4490c;--accent-soft:#fdeee4;--danger:#e5342f;--danger-soft:#fdecec;
--display:"Nanum Gothic","Apple SD Gothic Neo",sans-serif;--body:"Nanum Gothic","Apple SD Gothic Neo",sans-serif;
--mono:"D2 coding","D2Coding","Nanum Gothic Coding",ui-monospace,Menlo,monospace;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#0e0f10;--sheet:#18191b;--ink:#f1f2f3;--muted:#9a9fa6;
--rule:#2a2c30;--chip:#24262a;--accent:#f37021;--on-accent:#0a0a0a;--accent-ink:#ff9a57;--accent-soft:#3a2112;
--danger:#ff5a52;--danger-soft:#3a1a19;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#0e0f10;--sheet:#18191b;--ink:#f1f2f3;--muted:#9a9fa6;--rule:#2a2c30;--chip:#24262a;
--accent:#f37021;--on-accent:#0a0a0a;--accent-ink:#ff9a57;--accent-soft:#3a2112;--danger:#ff5a52;--danger-soft:#3a1a19;color-scheme:dark}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);font-size:15px;line-height:1.6}
.wrap{max-width:860px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left));padding-right:max(16px,env(safe-area-inset-right))}
.top{padding-top:max(20px,env(safe-area-inset-top));padding-bottom:6px;border-bottom:3px solid var(--accent)}
.top-row{display:flex;justify-content:space-between;align-items:flex-end;gap:6px 12px;flex-wrap:wrap;padding-bottom:10px}.top-row>*{min-width:0}
.eyebrow{font-size:12px;letter-spacing:.08em;color:var(--muted)}
h1{font-family:var(--display);font-size:30px;line-height:1.2;margin:2px 0 0;font-weight:800}
h2{font-family:var(--display);font-size:17px;margin:0 0 10px}
.role{font-size:12px;border:1px solid var(--rule);border-radius:999px;padding:1px 9px;color:var(--muted);font-family:var(--mono)}
.main>*{min-width:0;max-width:100%}.main{display:flex;flex-direction:column;gap:14px;padding-block:16px 80px}
section{background:var(--sheet);border:1px solid var(--rule);border-radius:8px;padding:16px;min-width:0}
.hero{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;box-shadow:inset 4px 0 0 var(--accent)}
.hero>div{flex:1 1 150px;min-width:0}.right{text-align:right}
.big{font-family:var(--mono);font-size:28px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.25}
.big small{font-family:var(--body);font-size:13px;color:var(--muted);font-weight:400}
.dim{color:var(--muted);font-size:13px}.up{color:var(--accent-ink);font-weight:700}.down{color:var(--danger);font-weight:700}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;background:none;border:0;padding:0}
@media (max-width:420px){.grid{grid-template-columns:1fr}}
.card{background:var(--sheet);border:1px solid var(--rule);border-radius:8px;padding:12px 14px;min-width:0}
.card>div:nth-child(2){font-family:var(--mono);font-variant-numeric:tabular-nums}
.item{padding:9px 0;border-top:1px solid var(--rule);overflow-wrap:anywhere}.item:first-of-type{border-top:0;padding-top:0}
.tag{font-size:12px;border-radius:999px;padding:1px 9px;background:var(--chip);color:var(--muted)}
.tag.stop{background:var(--danger-soft);color:var(--danger)}.tag.alert{background:var(--accent-soft);color:var(--accent-ink)}
.tag.ok{background:var(--accent-soft);color:var(--accent-ink)}
.spark{width:100%;height:64px;color:var(--accent);display:block}.row{display:flex;justify-content:space-between;font-family:var(--mono)}
b{font-weight:700}
"""


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
        return '<p class="dim">기록이 더 쌓이면 그래프가 나옵니다</p>'
    t0, t1 = points[0][0], points[-1][0]
    lo, hi = min(v for _, v in points), max(v for _, v in points)
    span, tspan = (hi - lo) or 1, (t1 - t0) or 1
    xy = " ".join(f"{(t - t0) / tspan * w:.1f},{h - 4 - (v - lo) / span * (h - 8):.1f}" for t, v in points)
    return (f'<svg viewBox="0 0 {w} {h}" class="spark" role="img" aria-label="지갑 추이">'
            f'<polyline points="{xy}" fill="none" stroke="currentColor" stroke-width="2"/></svg>'
            f'<div class="row dim"><span>{hm(t0)}</span><span>{lo:,.1f} ~ {hi:,.1f}</span><span>{hm(t1)}</span></div>')


def page():
    now = time.time()
    wallet = [e for e in jsonl("wallet.jsonl") if e.get("wallet") == "shop"]
    bal = wallet[-1]["tokrw"] if wallet else None
    pts = [(e["ts"], e["tokrw"]) for e in wallet if now - e["ts"] <= 48 * 3600]
    while pts and pts[0][1] == 0:                        # before the start capital came in
        pts.pop(0)
    if len(pts) > 300:
        pts = pts[:: len(pts) // 300 + 1] + [pts[-1]]
    b = board()
    students = [s for s in b.get("shops", []) if s.get("student")]
    me = next((s for s in b.get("shops", []) if s.get("name") == NAME), {})
    ranked = sum(1 for s in students if s.get("rank"))
    try:
        st = json.loads((KIT / "watch-state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    recon = st.get("recon") or {}
    watch_age = now - st.get("last_pass", 0)

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
    left = EARLY_END - now

    h = []
    h.append('<section class="hero">')
    h.append(f'<div><div class="dim">가게 지갑</div><div class="big">{E(f"{bal:,.1f}") if bal is not None else "-"}'
             f' <small>tOKRW</small></div>')
    if bal is not None:
        d = bal - START_TOKRW
        h.append(f'<div class="{"up" if d >= 0 else "down"}">시작 대비 {d:+,.1f} ({d / START_TOKRW:+.1%})</div>')
    h.append('</div><div class="right">')
    h.append(f'<div class="dim">보드 순위</div><div class="big">{E(str(me.get("rank") or "-"))}'
             f' <small>위</small></div><div class="dim">순위 있는 {ranked}곳 · 학생 가게 {len(students)}곳 · '
             f'{"살아 있음" if me.get("alive") else "응답 없음"}</div></div></section>')
    h.append(f'<section><h2>지갑 추이 (48시간)</h2>{spark(pts)}</section>')

    h.append('<section class="grid">')
    h.append(f'<div class="card"><div class="dim">감시</div><div>{"정상" if watch_age < 180 else "멈춤?"}'
             f' <small class="dim">{int(watch_age)}초 전</small></div></div>')
    diff = recon.get("diff")
    h.append(f'<div class="card"><div class="dim">잔고 대조</div><div class="{"" if diff is None or abs(diff) <= 2 else "down"}">'
             f'{"-" if diff is None else f"{diff:+,.2f}"} <small class="dim">tOKRW</small></div></div>')
    h.append(f'<div class="card"><div class="dim">초반 돕기 남은 시간</div><div>'
             f'{f"{int(left // 3600)}시간 {int(left % 3600 // 60)}분" if left > 0 else "끝남"}</div></div>')
    med = statistics.median([e.get("secs", 0) for e in ok]) if ok else 0
    h.append(f'<div class="card"><div class="dim">중계 (1시간)</div><div>{len(ok)}/{len(relay)} 응답 · 중앙 {med:.1f}초</div>'
             f'<div class="dim">{E(" · ".join(f"{k} {v}" for k, v in sorted(by.items())))}'
             f'{f" · 안전장치 {flagged}" if flagged else ""}</div></div>')
    h.append('</section>')

    h.append('<section><h2>감시 경보</h2>')
    if not alerts:
        h.append('<p class="dim">경보 없음</p>')
    for a in alerts:
        h.append(f'<div class="item"><span class="tag {E(a.get("level", "").lower())}">{E(a.get("level", ""))}</span> '
                 f'<span class="dim">{E(hm(a.get("ts")))}</span><div>{E(clip(a.get("text"), 220))}</div></div>')
    h.append('</section>')

    h.append(f'<section><h2>만든 도구 ({len(forge)})</h2>')
    for name, e in sorted(forge.items(), key=lambda kv: -float(kv[1].get("ts", 0))):
        h.append(f'<div class="item"><b>{E(str(name))}</b> v{E(str(e.get("version")))} '
                 f'<span class="tag {"ok" if e.get("passed") else "stop"}">{"통과" if e.get("passed") else "실패"}</span> '
                 f'<span class="dim">{E(hm(e.get("ts")))}</span></div>')
    h.append('</section>')

    h.append('<section><h2>최근 행동</h2>')
    for e in react:
        h.append(f'<div class="item"><span class="dim">{E(hm(e.get("ts")))}</span> <b>{E(str(e.get("action")))}</b>'
                 f'<div>{E(clip(e.get("thought"), 200))}</div></div>')
    h.append('</section>')

    h.append('<section><h2>에이전트가 먼저 한 말 (앱)</h2>')
    h.append('<p class="dim">아직 없음</p>' if not says else "")
    for e in says:
        h.append(f'<div class="item"><span class="dim">{E(hm(e.get("ts")))}</span><div>{E(clip(e.get("said_first"), 240))}</div></div>')
    h.append('</section><section><h2>Claude의 질문 (nudge)</h2>')
    h.append('<p class="dim">아직 없음</p>' if not nudges else "")
    for e in nudges:
        h.append(f'<div class="item"><span class="dim">{E(hm(e.get("ts")))} · {E(str(e.get("why", "")))}</span>'
                 f'<div>{E(clip(e.get("text"), 240))}</div></div>')
    h.append('</section>')

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta http-equiv="refresh" content="30"><meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="R4 가게"><meta name="theme-color" content="#f37021"><title>R4 가게</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700;800&display=swap">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/joungkyun/font-d2coding@1.3.2/d2coding.css">
<style>{CSS}</style></head><body>
<header class="wrap top"><div class="eyebrow">AGENT MARKET · ROUND 4</div>
<div class="top-row"><h1>{E(NAME)}</h1><span class="role">{E(time.strftime("%m/%d %H:%M:%S"))} · 30초마다 새로고침</span></div></header>
<main class="wrap main">{"".join(h)}</main></body></html>"""


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


def main():
    key = code()
    hosts = ["127.0.0.1"] + [ip for ip in [tailscale_ip()] if ip]
    servers = [ThreadingHTTPServer((h, PORT), Handler) for h in hosts]
    links = [f"http://{h}:{PORT}/?k={key}" for h in hosts]
    (KIT / "dashboard.url").write_text("\n".join(links) + "\n", encoding="utf-8")
    (KIT / "dashboard.url").chmod(0o600)
    print(f"[dash] listening on {', '.join(f'{h}:{PORT}' for h in hosts)}; links with the code in .kit/dashboard.url",
          flush=True)
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    servers[0].serve_forever()


if __name__ == "__main__":
    main()
