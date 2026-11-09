"""Checks the numbers our standing orders and memory state as facts against the market's board, now.

Why (11/9 16:2x): the supervisor wrote "our forum rating leads the market (0.909)" into the standing orders and its
memory from a comparison with a few top players; the board had us #13 of 40 students. The team read it every cycle and
nothing checked it. The memory study (Anthropic, components of agent memory) closes the loop by fixing notes against the
record; the team's lessons already drop rules that cite no fact (lessons_r3.valid). This does the same for the
supervisor's own claims.

  Since 11/9 17:1x the standing orders carry no board numbers: {live:key} is filled from the board as the team
  reads them (board_terms_r3.render), so claims_r3.json is empty and this mostly catches a number typed in again.
  claims_r3.json   one row per claim: {"id", "file", "says" (text that must still be in the file), "metric",
                   "value", "tol", "as_of"}. A claim whose `says` text is gone from its file is retired.
  check(board)     [(claim, now, status)] with status ok / STALE / retired.
  loose(text)      "#N of M" ranks in a file that no claim covers, so a new unchecked fact is caught too.

    python claims_r3.py           # prints every claim; exit 1 when one is STALE or a rank is unregistered
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLAIMS = HERE / "claims_r3.json"
US = "thisjonghoon"
FILES = (HERE / "standing_orders_r3.md",
         Path("~/.claude/projects/-Users-hoon/memory/agent-market-claude-owns-structure.md").expanduser(),
         Path("~/.claude/projects/-Users-hoon/memory/agent-market-ten-principles.md").expanduser())


def _students(board):
    return sorted([r for r in board.get("players") or [] if r.get("student")], key=lambda r: -(r.get("student_total") or 0))


def _forum_students(board):
    names = {(r.get("buyer") or {}).get("name") for r in board.get("players") or [] if r.get("student")}
    rows = [r for r in board.get("buyers") or [] if r.get("name") in names and isinstance(r.get("forum"), (int, float))]
    return sorted(rows, key=lambda r: -r["forum"])


def _rank(rows, key, name):
    return next((i + 1 for i, r in enumerate(rows) if r.get(key) == name), None)


METRICS = {
    "student_rank": lambda b: _rank(_students(b), "player", US),
    "student_total": lambda b: next((r.get("student_total") for r in _students(b) if r.get("player") == US), None),
    "rank10_total": lambda b: (_students(b)[9].get("student_total") if len(_students(b)) >= 10 else None),
    "forum_rating": lambda b: next((r["forum"] for r in _forum_students(b) if r.get("name") == US), None),
    "forum_rank_students": lambda b: _rank(_forum_students(b), "name", US),
    "forum_leader_rating": lambda b: (_forum_students(b)[0]["forum"] if _forum_students(b) else None),
    "buyer_saved": lambda b: next((r.get("saved") for r in b.get("buyers") or [] if r.get("name") == US), None),
}


def load():
    try:
        return json.loads(CLAIMS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def check(board, claims=None):
    out = []
    for c in claims if claims is not None else load():
        path = Path(c["file"]).expanduser()
        path = path if path.is_absolute() else HERE / path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if c.get("says") and c["says"] not in text:
            out.append((c, None, "retired"))
            continue
        f = METRICS.get(c.get("metric"))
        now = f(board) if f else None
        ok = now is not None and abs(now - c["value"]) <= c.get("tol", 0)
        out.append((c, now, "ok" if ok else "STALE"))
    return out


def loose(text, claims):
    """'#N of M' ranks in text that no claim's `says` contains."""
    covered = " ".join(c.get("says", "") for c in claims)
    return [m.group(0) for m in re.finditer(r"#\d+ of \d+", text) if m.group(0) not in covered]


def report(board):
    claims, lines, bad = load(), [], False
    for c, now, status in check(board, claims):
        if status == "retired":
            continue
        bad |= status == "STALE"
        lines.append(f"{status} {c['id']}: says {c['value']} ({c.get('as_of', '?')}), board now {now} "
                     f"[{Path(c['file']).name}: \"{c['says'][:60]}\"]")
    for f in FILES:
        try:
            for r in loose(f.read_text(encoding="utf-8"), claims):
                bad = True
                lines.append(f"UNREGISTERED {f.name}: \"{r}\" is a rank no claim checks")
        except OSError:
            pass
    return lines, bad


if __name__ == "__main__":
    import httpx
    b = httpx.get("https://market.ourolabs.ai/api/board", timeout=20).json()
    out, bad = report(b)
    print("\n".join(out) or "no claims")
    sys.exit(1 if bad else 0)
