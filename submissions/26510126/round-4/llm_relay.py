#!/usr/bin/env python3
"""An OpenAI-compatible endpoint on this computer that answers with the user's subscriptions, for the Round 4 kit.

The kit calls one model through POST <base>/chat/completions. This relay takes that call and answers it with, in order:
  1. Claude Code (`claude -p`, the logged-in subscription; ANTHROPIC_API_KEY is removed so no API key is billed),
  2. GPT through the Codex CLI (the logged-in ChatGPT plan), when Claude fails (a usage limit, an outage),
  3. a free OpenRouter model, when both fail (OPENROUTER_API_KEY; costs nothing).
Every call and every fallback is written to logs/llm-relay.jsonl (backend, ok, seconds, sizes; never the prompt), so a
fallback is never silent (Round 3, 11/9: a reviewer failed silently for 2.5 h).

    export RELAY_KEY=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    python llm_relay.py                        # listens on 127.0.0.1:8790
    agent.json: "llm": {"base": "http://127.0.0.1:8790/v1", "model": "claude-sonnet", "key_env": "RELAY_KEY"}

The relay listens on 127.0.0.1 only and answers only a request that carries RELAY_KEY. The kit runs forged tools with
an environment that holds no keys, so a tool cannot use the relay to call a model on its own.

Settings (environment): RELAY_PORT (8790), RELAY_ORDER (claude,codex,openrouter), RELAY_CLAUDE_MODEL (from the
request's model "claude-<alias>", else sonnet), RELAY_GPT_MODEL (gpt-6.1-sol), RELAY_FREE_MODEL
(nvidia/nemotron-3.5-super-vl:free), RELAY_DEADLINE (170 s, under the kit's 180 s cap).
"""
import json
import os
import signal
import subprocess
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "logs" / "llm-relay.jsonl"
EMPTY = tempfile.mkdtemp(prefix="round4-relay-")      # no project CLAUDE.md, AGENTS.md or settings are picked up
PORT = int(os.environ.get("RELAY_PORT", "8790"))
ORDER = [b.strip() for b in os.environ.get("RELAY_ORDER", "claude,codex,openrouter").split(",") if b.strip()]
GPT_MODEL = os.environ.get("RELAY_GPT_MODEL", "gpt-6.1-sol")
FREE_MODEL = os.environ.get("RELAY_FREE_MODEL", "nvidia/nemotron-3.5-super-vl:free")
DEADLINE = float(os.environ.get("RELAY_DEADLINE", "170"))
ONE_AT_A_TIME = threading.Lock()                         # the kit's mind calls one at a time; keep it that way
ENV = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "RELAY_KEY")}


def log(entry):
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(entry, ts=int(time.time())), ensure_ascii=False) + "\n")


def transcript(messages):
    """The chat as one prompt for a CLI that takes a single text: the system part first, then each turn labelled."""
    system = "\n\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
    turns = [f"[{m.get('role')}]\n{m.get('content') or ''}" for m in messages if m.get("role") != "system"]
    return (f"{system}\n\n--- the conversation so far ---\n\n" + "\n\n".join(turns)
            + "\n\n--- your turn ---\nWrite only the assistant's next message.")


def run(cmd, timeout, stdin_text=None):
    """stdout of one CLI call, or raise with the reason."""
    # its own process group, so a timeout ends the CLI's children too (11/23 test: a timed-out codex left its child
    # running after the wrapper was killed)
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=EMPTY, env=ENV,
                         start_new_session=True)
    try:
        out, err = p.communicate(stdin_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.communicate()
        # the exception's text holds the whole command, prompt included; the log keeps no prompt (11/23 test)
        raise RuntimeError(f"{cmd[0]} did not answer within {timeout:.0f} s") from None
    out = (out or "").strip()
    if p.returncode != 0 or not out:
        raise RuntimeError(f"exit {p.returncode}: {(err or out).strip()[:300]}")
    return out


def claude(messages, model, timeout):
    """The kit's system message goes in Claude's system slot and only the conversation in the user turn (11/24: with
    the system part pasted into the user turn, the safeguards flagged 8 of 25 calls in the first hour, the more often
    the longer the run; it read like instructions smuggled into a user message)."""
    alias = model.split("claude-", 1)[1] if model.startswith("claude-") else os.environ.get("RELAY_CLAUDE_MODEL", "sonnet")
    system = "\n\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
    turns = [m for m in messages if m.get("role") != "system"]
    cmd = ["claude", "-p", "--model", alias, "--tools", "", "--setting-sources", "", "--no-session-persistence"]
    if system:
        cmd += ["--system-prompt", system]
    return run(cmd, timeout, transcript(turns))


def codex(messages, model, timeout):
    cmd = ["codex", "exec", "-m", GPT_MODEL, "--skip-git-repo-check", "-s", "read-only", "--ephemeral",
           "--ignore-user-config", "-c", "project_doc_max_bytes=0", transcript(messages)]
    return run(cmd, timeout)


def openrouter(messages, model, timeout):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("no OPENROUTER_API_KEY")
    body = json.dumps({"model": FREE_MODEL, "messages": messages, "max_tokens": 4000}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body,
                                 headers={"authorization": "Bearer " + key, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = (json.load(r)["choices"][0]["message"].get("content") or "").strip()
    if not out:
        raise RuntimeError("empty answer")
    return out


BACKENDS = {"claude": claude, "codex": codex, "openrouter": openrouter}


def answer(messages, model):
    """The first backend that answers within the deadline: (text, backend), or (None, None)."""
    order = ORDER if not model.startswith("gpt") else ["codex"] + [b for b in ORDER if b != "codex"]
    start, size = time.time(), sum(len(str(m.get("content") or "")) for m in messages)
    for i, name in enumerate(order):
        left = DEADLINE - (time.time() - start)
        if left < 10:
            log({"backend": name, "ok": False, "why": "no time left", "chars_in": size})
            break
        t = time.time()
        try:
            text = BACKENDS[name](messages, model, left)
            log({"backend": name, "ok": True, "secs": round(time.time() - t, 1), "chars_in": size,
                 "chars_out": len(text), "fallback": i > 0})
            if i > 0:
                print(f"[relay] answered by {name} after {i} failed backend(s)", flush=True)
            return text, name
        except Exception as e:                              # the next backend tries; the reason is kept
            log({"backend": name, "ok": False, "secs": round(time.time() - t, 1), "chars_in": size,
                 "why": f"{type(e).__name__}: {str(e)[:300]}"})
            print(f"[relay] {name} failed: {type(e).__name__}: {str(e)[:160]}", flush=True)
    return None, None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):                              # the jsonl log is the record; keep stderr quiet
        pass

    def send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        key = os.environ.get("RELAY_KEY", "")
        if not key or self.headers.get("authorization", "") != "Bearer " + key:
            return self.send(401, {"error": "a RELAY_KEY bearer token is required"})
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self.send(404, {"error": "only /v1/chat/completions"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        except ValueError:
            return self.send(400, {"error": "the body is not JSON"})
        messages, model = body.get("messages") or [], str(body.get("model") or "claude-sonnet")
        # The kit's socket gives up after 60 s without a byte (agent_kit.Model.complete), and a CLI can take longer
        # (11/23 test: codex did not answer within 60 s). So the headers go out at once and a space every 10 s keeps
        # the line alive; JSON allows the leading whitespace. A failure then arrives as a body without "choices",
        # which the kit logs as a failed model call and retries.
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("connection", "close")
        self.end_headers()
        self.close_connection = True
        result = {}

        def work():
            with ONE_AT_A_TIME:
                result["text"], result["used"] = answer(messages, model)
        t = threading.Thread(target=work, daemon=True)
        t.start()
        try:
            while t.is_alive():
                t.join(10)
                if t.is_alive():
                    self.wfile.write(b" ")
                    self.wfile.flush()
            if result.get("text") is None:
                obj = {"error": "every backend failed; see logs/llm-relay.jsonl"}
            else:
                obj = {"id": f"relay-{int(time.time() * 1000)}", "object": "chat.completion", "model": result["used"],
                       "choices": [{"index": 0, "message": {"role": "assistant", "content": result["text"]},
                                    "finish_reason": "stop"}]}
            self.wfile.write(json.dumps(obj, ensure_ascii=False).encode())
        except (BrokenPipeError, ConnectionResetError):     # the kit gave up first; the answer is logged anyway
            log({"backend": result.get("used"), "ok": False, "why": "the caller hung up before the answer"})


if __name__ == "__main__":
    if not os.environ.get("RELAY_KEY"):
        raise SystemExit("[relay] set RELAY_KEY first (the kit sends it as the bearer token)")
    print(f"[relay] http://127.0.0.1:{PORT}/v1, order {', '.join(ORDER)}, log {LOG}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
