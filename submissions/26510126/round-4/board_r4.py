"""The mini app's 보드 (11/27, the owner's design): the work between the watchers, Hermes, the market agent and the owner.

Every change is one line in logs/board.jsonl (kept like the other logs); app/board.json is rebuilt from it after each
change so the app's 보드 tab can show it. Hermes runs the board; the owner steps in only for the cards in 내 차례.

Columns (status):
  backlog  a watcher or adviser found something                       who moves it on: Hermes
  doing    Hermes is passing it to the market (nudges, mediation)      the market answers -> Hermes moves it to review
  owner    내 차례: only when the owner is needed                      the owner (see below)
  review   the market says it is done; Hermes judges it                Hermes: done, or reject (back to doing)
  done

Kinds:
  task     ordinary work; never needs the owner unless rejected 3 times
  approve  a permission only the owner may give (the app shows 허용/거절; see "approve" below)
  order    the owner's own words are needed: Hermes writes a draft in the owner's voice ("~하게", "~네"), the owner
           copies it or presses 보내기 in the app, and it goes into the market's chat as the owner's message

Rules this script keeps:
  - Nobody but a person sends the owner's words. This script never posts to the chat; `sync` only notices that the
    owner sent a draft (the same text from the owner in .kit/chat.jsonl after the card went to 내 차례) and moves the
    card to review.
  - A card leaves 내 차례 only by the owner: `move` out of owner needs --by owner, except an order the owner sent (sync).
  - A third rejection sends the card up to 내 차례 (it bounced too often for nudges); attach a draft with `draft`.

Usage (Hermes):
  python board_r4.py add "title" --body "what and why" --source watch|advice|hermes|owner [--kind task|approve|order]
                         [--status backlog|doing|owner] [--draft "owner's words"] [--arg key=value ...]
  python board_r4.py move ID doing|review|done|backlog|owner [--note "why"] [--by hermes|market|owner]
  python board_r4.py reject ID --why "what is still wrong"
  python board_r4.py draft ID "owner's words"        # makes it an order card in 내 차례
  python board_r4.py note ID "text" [--by ...]
  python board_r4.py sync                             # orders the owner sent -> review
  python board_r4.py ls [--all]
  python board_r4.py show ID
"""
import argparse
import fcntl
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "logs" / "board.jsonl"
SNAP = HERE / "app" / "board.json"
CHAT = HERE / ".kit" / "chat.jsonl"
OWNER = "jonghoon"
STATUSES = ["backlog", "doing", "owner", "review", "done"]
KINDS = ["task", "approve", "order"]
SOURCES = ["watch", "advice", "hermes", "owner", "market"]
NAMES = {"backlog": "백로그", "doing": "진행", "owner": "내 차례", "review": "반영·검증", "done": "완료"}
BOUNCE_UP = 3


def events():
    try:
        lines = LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def replay(evs):
    cards = {}
    for e in evs:
        cid, op = e.get("id"), e.get("op")
        if op == "add":
            cards[cid] = {"id": cid, "title": e["title"], "body": e.get("body", ""), "kind": e.get("kind", "task"),
                          "source": e.get("source", "hermes"), "status": e.get("status", "backlog"),
                          "draft": e.get("draft"), "args": e.get("args") or {}, "bounces": 0,
                          "created": e["ts"], "updated": e["ts"], "at": e["ts"], "history": []}
        c = cards.get(cid)
        if not c:
            continue
        c["updated"] = e["ts"]
        h = {"ts": e["ts"], "by": e.get("by", "hermes"), "op": op}
        if op in ("move", "reject", "add"):
            new = e.get("to") or e.get("status") or c["status"]
            if new != c["status"] or op == "add":
                c["at"] = e["ts"]                      # when it came into its column (the app checks sends after this)
            c["status"] = new
            h["to"] = new
        if op == "reject":
            c["bounces"] += 1
        if op == "draft":
            c["kind"], c["draft"] = "order", e["draft"]
            if c["status"] != "owner":
                c["status"], c["at"] = "owner", e["ts"]
            h["to"] = "owner"
        if e.get("note"):
            h["note"] = e["note"]
        c["history"].append(h)
    return cards


def write(e):
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")


def snapshot(cards):
    SNAP.parent.mkdir(exist_ok=True)
    tmp = SNAP.with_suffix(".tmp")
    tmp.write_text(json.dumps({"at": int(time.time()), "names": NAMES, "cards": list(cards.values())}, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(SNAP)                                # whole or nothing: the app never reads half a board


class Lock:
    def __enter__(self):
        LOG.parent.mkdir(exist_ok=True)
        self.f = open(LOG.with_suffix(".lock"), "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def owner_sends(since):
    try:
        lines = CHAT.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get("who") == OWNER and m.get("ts", 0) >= since - 5:
            out.append(m)
    return out


def hm(ts):
    return time.strftime("%m/%d %H:%M", time.localtime(ts))


def main(argv=None):
    os.environ.setdefault("TZ", "Asia/Seoul")
    time.tzset()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("title")
    a.add_argument("--body", default="")
    a.add_argument("--source", choices=SOURCES, default="hermes")
    a.add_argument("--kind", choices=KINDS, default="task")
    a.add_argument("--status", choices=["backlog", "doing", "owner"], default=None)
    a.add_argument("--draft")
    a.add_argument("--arg", action="append", default=[], help="key=value shown on an approve card")
    a.add_argument("--by", default="hermes")
    m = sub.add_parser("move")
    m.add_argument("id", type=int)
    m.add_argument("to", choices=STATUSES)
    m.add_argument("--note")
    m.add_argument("--by", default="hermes")
    r = sub.add_parser("reject")
    r.add_argument("id", type=int)
    r.add_argument("--why", required=True)
    r.add_argument("--by", default="hermes")
    d = sub.add_parser("draft")
    d.add_argument("id", type=int)
    d.add_argument("text")
    d.add_argument("--by", default="hermes")
    n = sub.add_parser("note")
    n.add_argument("id", type=int)
    n.add_argument("text")
    n.add_argument("--by", default="hermes")
    sub.add_parser("sync")
    ls = sub.add_parser("ls")
    ls.add_argument("--all", action="store_true")
    sh = sub.add_parser("show")
    sh.add_argument("id", type=int)
    a = ap.parse_args(argv)
    now = int(time.time())

    with Lock():
        cards = replay(events())

        def need(cid):
            if cid not in cards:
                sys.exit(f"no card #{cid}")
            return cards[cid]

        if a.cmd == "add":
            if a.kind == "order" and not a.draft:
                sys.exit("an order card needs --draft (the owner's words)")
            status = a.status or ("owner" if a.kind in ("approve", "order") else "backlog")
            if a.kind in ("approve", "order") and status != "owner":
                sys.exit(f"an {a.kind} card goes straight to 내 차례 (owner)")
            args = dict(kv.split("=", 1) for kv in a.arg if "=" in kv)
            cid = max(cards, default=0) + 1
            write({"ts": now, "op": "add", "id": cid, "title": a.title, "body": a.body, "kind": a.kind, "source": a.source,
                   "status": status, "draft": a.draft, "args": args, "by": a.by})
            print(f"#{cid} {NAMES[status]}: {a.title}")
        elif a.cmd == "move":
            c = need(a.id)
            if c["status"] == "owner" and a.to != "owner" and a.by != "owner":
                sys.exit(f"#{a.id} is in 내 차례: only the owner moves it out (--by owner), or `sync` once the owner sent it")
            if a.to == "owner" and c["kind"] == "task" and not a.note:
                sys.exit("say why the owner is needed (--note), or use `draft` for an order")
            write({"ts": now, "op": "move", "id": a.id, "to": a.to, "note": a.note, "by": a.by})
            print(f"#{a.id} -> {NAMES[a.to]}")
        elif a.cmd == "reject":
            c = need(a.id)
            if c["status"] != "review":
                sys.exit(f"#{a.id} is in {NAMES[c['status']]}, not 반영·검증")
            up = c["bounces"] + 1 >= BOUNCE_UP
            to = "owner" if up else "doing"
            write({"ts": now, "op": "reject", "id": a.id, "to": to, "note": a.why, "by": a.by})
            print(f"#{a.id} rejected ({c['bounces'] + 1}) -> {NAMES[to]}")
            if up:
                print(f"  rejected {BOUNCE_UP} times: it is in 내 차례 now. Attach the owner's words: board_r4.py draft {a.id} \"...\"")
        elif a.cmd == "draft":
            need(a.id)
            write({"ts": now, "op": "draft", "id": a.id, "draft": a.text, "by": a.by})
            print(f"#{a.id} order in 내 차례")
        elif a.cmd == "note":
            need(a.id)
            write({"ts": now, "op": "note", "id": a.id, "note": a.text, "by": a.by})
            print(f"#{a.id} noted")
        elif a.cmd == "sync":
            moved = 0
            for c in cards.values():
                if c["status"] != "owner" or c["kind"] != "order" or not c.get("draft"):
                    continue
                hit = next((m for m in owner_sends(c["at"]) if m.get("text", "").strip() == c["draft"].strip()), None)
                if hit:
                    write({"ts": now, "op": "move", "id": c["id"], "to": "review",
                           "note": f"주인이 보냄 {hm(hit['ts'])}", "by": "owner", "sent": hit["ts"]})
                    print(f"#{c['id']} sent by the owner at {hm(hit['ts'])} -> 반영·검증")
                    moved += 1
            if not moved:
                print("nothing sent")
        elif a.cmd == "ls":
            for st in STATUSES:
                rows = [c for c in cards.values() if c["status"] == st]
                if st == "done" and not a.all:
                    rows = rows[-5:]
                print(f"{NAMES[st]} ({len(rows)})")
                for c in rows:
                    extra = f" · 반려 {c['bounces']}" if c["bounces"] else ""
                    print(f"  #{c['id']} [{c['kind']}/{c['source']}] {c['title']}{extra}")
        elif a.cmd == "show":
            print(json.dumps(need(a.id), ensure_ascii=False, indent=2))
        if a.cmd not in ("ls", "show"):
            snapshot(replay(events()))


if __name__ == "__main__":
    main()
