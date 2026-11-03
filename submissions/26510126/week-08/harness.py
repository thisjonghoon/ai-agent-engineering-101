"""Calls the harness (Claude Code, haiku) with a prompt on stdin and returns its JSON answer.

Shared by seller.py and buyer.py. The harness runs in an empty directory so it
does not pick up any project's CLAUDE.md or settings.
"""
import asyncio
import json
import os
import re
import sys
import tempfile
import time

HARNESS = ["claude", "-p", "--model", "haiku", "--tools", "", "--setting-sources", "", "--no-session-persistence"]
EMPTY_DIR = tempfile.mkdtemp(prefix="week06-harness-")
TIMEOUT = 90  # seconds for one harness call
MAX_PROMPT = 60_000  # characters: a prompt longer than this was stuffed by someone else's text, do not send it
# Without ANTHROPIC_API_KEY, claude -p uses the logged-in subscription instead of billing the API key.
ENV = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}


def log(tag, text):
    print(f"[{time.strftime('%H:%M:%S')}] {tag}: {text}", file=sys.stderr, flush=True)


def clip(text, n):
    """Text from another agent (a shop's reply, a product or shop name, a forum post) made safe to quote: control
    characters dropped, whitespace collapsed, at most n characters. Round 3 lets agents write first (the forum,
    unasked replies), so their text must not be able to fill our model's context or our logs."""
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def parse_json(text):
    """The first {...} object in the answer, or None."""
    start = text.find("{")
    if start >= 0:
        # a whole object, nested ones included (meta_shop.py asks for {"open": {...}, ...})
        try:
            data, _ = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*?\}", text, re.S)
    if m is None:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


async def ask(prompt, tries=2, model=None, timeout=TIMEOUT, max_chars=MAX_PROMPT):
    """Run the harness once (retry once on failure). Returns a dict, or None if every try failed.
    `model` swaps haiku for another model (meta_explore.py uses sonnet). A prompt over `max_chars` is not sent
    (None, as if the harness failed): the caller's own guards then decide, and a context bomb costs nothing."""
    if len(prompt) > max_chars:
        log("HARNESS", f"prompt of {len(prompt)} characters is over {max_chars}: not sent")
        return None
    cmd = HARNESS if model is None else [model if a == "haiku" else a for a in HARNESS]
    for attempt in range(1, tries + 1):
        started = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=EMPTY_DIR, env=ENV,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            log("HARNESS", f"try {attempt}: timeout after {timeout} s")
            continue
        answer = out.decode().strip()
        log("HARNESS", f"try {attempt}: {time.time() - started:.1f} s, exit {proc.returncode}, answer {answer!r}")
        if proc.returncode != 0:
            log("HARNESS", f"stderr {err.decode().strip()[:300]!r}")
            continue
        data = parse_json(answer)
        if data is not None:
            return data
    return None
