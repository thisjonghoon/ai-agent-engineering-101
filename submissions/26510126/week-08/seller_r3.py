"""Round 3 seller: sells units from the stock the kit keeps in $MARKET_DIR/inventory.json, behind A2A v1.0.

    python seller_r3.py --port 9301

Started from the course's starter_round3/seller.py (A2A side, unit lookup, receipt signing). What is ours:
  - Prices are set by code from strategy_r3.json, which the meta-harness (meta_r3.py, Claude haiku) rewrites.
  - Haggling: in a share of negotiations (model_share, drawn once per negotiation) Claude haiku makes each turn's
    call, ReAct style: it reads the unit (grade, shelf life left, list and cost), our ask and floor, every offer so
    far, the turns left, our stock of that SKU, how often buyers ask for it and what the market paid for it and its
    category lately (prices_r3.py: the ledger, with the forum's price posts checked against it), and answers with a one-line reason
    and accept or a counter. Code keeps it honest and safe: it accepts only at or above the floor, counters only
    between the buyer's offer and our last ask (never raising it), and when the model is busy (MODEL_SLOTS calls at
    once), slow (MODEL_TIMEOUT s) or answers nonsense, the rules below decide that turn, so a busy market never
    queues behind `claude -p`. The other negotiations run on the rules alone; logs/talks_r3.jsonl marks which was
    which, and the meta-harness compares the two and moves model_share (a controlled comparison, same hours).
      ask   = list price x ask_frac (food: ask_frac_food, up to fresh_premium more for a full shelf life)
      floor = max(cost x (1 + min_margin), list price x floor_frac (food: floor_frac_food)), never above the ask
    Food close to its date (less than clear_hours left, or grade C) is cleared down to cost x clear_frac: a unit
    thrown away loses its whole cost, a cheap sale loses less.
  - Concession: the counter moves `step` of the way from the last ask to the buyer's offer, never below the floor; an
    offer at or above the floor is accepted once the buyer has made two offers or meets the midpoint.
  - Honest terms in the receipt: the grade claim is the unit's grade now, one grade lower when food is within 3% of a
    grade line (a claim is judged at checkout or at settle); the market's certificate is always shown; goods carry
    warranty_hours from the strategy (0 at the start: a refund costs the whole price and the break rate
    is not published; the meta-harness may raise it if buyers refuse checkouts for want of one).
  - Units promised in an open negotiation or sold in the last 60 s are not offered again (inventory.json can be
    10 s old, and the kit refuses a checkout for a unit already gone).
A/B test (ab_r3.py, experiment_r3.json): when an experiment is on, a new negotiation for a unit of its kind draws
one of two values of one strategy number and keeps it to the end; the outcome goes to logs/ab_r3.jsonl.
Goods older than `goods_age_days` (storage is 1% of cost a day) may go down to cost x (1 + aged_margin).
In the last `endgame_hours` of the round the floor drops to cost (endgame_frac), and in the last `final_hours`
under it (final_frac): stock left at the end has cost money and earns nothing.
Rounds 0-2 have no stock: the week-07 items are sold at the old reserves so the shop keeps working before Round 3.
"""
import argparse
import asyncio
import base64
import json
import os
import random
import re
import time
from pathlib import Path

import uvicorn
from cryptography.hazmat.primitives import serialization
from starlette.applications import Starlette

from a2a.helpers import get_message_text, new_data_part, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

import ab_r3
import demand_r3
import harness
import prices_r3
import team_r3

HERE = Path(__file__).resolve().parent
NAME = "thisjonghoon"
RESERVE = {"lamp": 100, "chair": 180, "bookshelf": 260}     # Rounds 0-2 have no stock: the week-07 items
MARKET_DIR = Path(os.environ.get("MARKET_DIR", HERE / ".market"))
STRATEGY = Path(os.environ.get("STRATEGY_FILE") or HERE / "strategy_r3.json")   # tests: the defaults, not the live file
DEFAULTS = {"ask_frac": 0.95, "floor_frac": 0.78, "min_margin": 0.10, "step": 0.4,
            "clear_hours": 6, "clear_frac": 0.6, "warranty_hours": 0, "max_turns": 6,
            "endgame_hours": 24, "endgame_frac": 1.0, "final_hours": 6, "final_frac": 0.6,
            "ask_frac_food": 0.95, "floor_frac_food": 0.78, "fresh_premium": 0.10,
            "goods_age_days": 5, "aged_margin": 0.03, "model_share": 0.5, "market_ask": 1.0,
            "stuck_hours": 6, "stuck_frac": 0.95}
ROUND_END = 1794927540                                       # 2026-11-17 23:59 KST: stock left then is a loss
OFFER = re.compile(r"(?<![A-Za-z0-9])\d[\d,]*(?![A-Za-z0-9])")   # a number on its own, not the digits of a SKU
FOOD_CUTS = (0.80, 0.45)                                     # shelf life left: A at or above 80%, B at or above 45%
RECENT_SOLD = 600   # seconds a unit we signed a receipt for is not offered again (60 until 11/4)
# The kit's checkout holds a unit while a session is open and never lets an abandoned session go, so one unit was
# refused at checkout 16 times (11/4 13:09-13:52) while we kept choosing it. A unit we agreed on twice that is still
# in stock is taken as held and not offered for STUCK_SECS (the kit's code, kit v4, is not ours to change). Until 11/5
# 01:20 it stayed out until a restart: 51 units were set aside in two hours against 3 refusals at checkout, mostly
# grade-C food that buyers agree on and their kits then refuse to pay for, a sellable unit left to spoil.
STUCK_AFTER = 2
STUCK_SECS = 1800
# the kit's checkout logs "checkout refused: unit u-... is not in stock" for a unit an abandoned session still holds; the
# seller cannot see refusals, only its own agreements, so a unit refused 33-44 min apart was offered and refused 4 times
# (u-e8b84402c1ee, 11/8 12:27-14:19). A unit named in such a line is left out for REFUSED_SECS (sold units leave anyway)
KIT_LOG = HERE / "logs" / "market-kit.log"
REFUSED = re.compile(r"checkout refused: unit (u-[0-9a-f]+) is not in stock")
REFUSED_SECS = 7200
# a unit refused again after its REFUSED_SECS is held for good (until a restart, which also frees the kit's sessions):
# u-8766bea1baa3 (11/9 02:25, 05:23) and u-9eec9af868a3 (06:12, 09:33) came back after 2 h and were refused again.
# Refusals closer than REFUSED_APART are one checkout retried, not a second refusal
REFUSED_APART = 600
# the grades that carry a warranty and the share of their price we expect to refund (11/9 15:1x: with every grade
# warranted from 13:41, 5 refunds came in 90 min, 4.78M, four of them grade C (3.23M on 8.8M of C sold); the market's
# goods break, counted over the full 6 h after the sale, about A 3%, B 9-18%, C 29-40%). C is sold without one
WARRANTY_Q = {"A": 0.03, "B": 0.13}
OPEN_HOLD = 120     # seconds a negotiation keeps its unit before another buyer may be offered it
MODEL_SLOTS = asyncio.Semaphore(3)    # model calls at once; a turn that finds them all busy is decided by the rules
MODEL_TIMEOUT = 8                     # seconds (haiku answered in 3.7 s at the median, 5.3 s at p90, over 160k calls)
SELL_PROMPT = """You haggle for an online shop in a market of AI buyers. The goal is the most profit over the round
(price minus cost) without losing sales a fair price would win: goods that wait pay storage, food is thrown away at its
date, and a buyer who walks away buys elsewhere.
Unit: {name} ({kind}), grade {grade}, {life}. List price {lp}, our cost {cost}.
Our floor is {floor} (never below it); our last ask was {ask}. The buyer's offers so far, oldest first: {offers}.
Turns left before we must walk away: {left}. Our stock of this SKU: {stock}. Demand for it lately: {demand}.
What the market paid lately (public ledger): {market}.
Our shop's fixed rule would {rule_move} here. {record} Treat the floor as a hard limit, not a target: beat the rule,
do not undercut it. Counter at or above the rule's counter unless the buyer has shown it will not move and few turns
are left; accept when the offer is at least what the rule would take.
Either accept the last offer ({offer}) or counter with a whole number from {lo} to {hi}. A counter far above the offer
may lose the buyer; accepting too early leaves money on the table.
Answer with JSON only: {{"why": "<at most twelve words>", "action": "accept" or "counter", "price": <your counter>}}"""
DEMAND = {"t": 0, "sku": {}}
RECORD = {"t": 0, "text": ""}


def record_line():
    """How the rule's talks and the model's talks did in the last 24 h (talks_r3.jsonl, cached 10 min): the share
    that sold and the median price over the floor. On 11/4 the model sold 36% at 1.03x the floor against the rule's
    43% at 1.11x: it gave margin away early without saving sales, so the model now sees both numbers each turn."""
    if time.time() - RECORD["t"] < 600:
        return RECORD["text"]
    out = {}
    try:
        cut = time.time() - 24 * 3600
        for line in TALKS.read_text(encoding="utf-8").splitlines()[-20000:]:
            t = json.loads(line)
            if t.get("t", 0) >= cut and t.get("event") in ("deal", "walk") and t.get("floor"):
                o = out.setdefault("model" if t.get("model_on") else "rule", [0, []])
                o[0] += 1
                if t["event"] == "deal" and t.get("price"):
                    o[1].append(t["price"] / t["floor"])
    except (OSError, ValueError, KeyError, TypeError):
        out = {}
    part = lambda k: (f"{k} talks that got an offer sold {len(out[k][1]) / out[k][0]:.0%} at "
                      f"{sorted(out[k][1])[len(out[k][1]) // 2]:.2f}x the floor (median)") if out.get(k) and out[k][1] else None
    parts = [x for x in (part("rule"), part("model")) if x]
    RECORD.update(t=time.time(), text=("Last 24 h: " + "; ".join(parts) + ".") if parts else "")
    return RECORD["text"]


def demand_of(sku):
    """How often buyers asked for or were sent for this SKU lately, relative to the average SKU (cached 5 min)."""
    if time.time() - DEMAND["t"] > 300:
        try:
            _, w, _ = demand_r3.signals()
            mean = sum(w.values()) / len(w) if w else 0
            DEMAND.update(t=time.time(), sku={k: v / mean for k, v in w.items()} if mean else {})
        except Exception:                             # demand is a hint for the model; never stop a sale for it
            DEMAND.update(t=time.time(), sku={})
    v = DEMAND["sku"].get(sku)
    return "none seen" if v is None else f"{v:.1f}x the average SKU"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


TALKS = Path(os.environ.get("TALKS_LOG") or HERE / "logs" / "talks_r3.jsonl")
WARRANTY_WORDS = re.compile(r"warrant|guarantee|보증|보장|AS\b", re.I)


def ab_end(task_id, deal, event, reward=0.0, price=None):
    """Record how a negotiation ended: one raw line in logs/talks_r3.jsonl (the buyer's offers, the unit's list price
    and cost, our ask and floor, the outcome) for simulate_r3.py to replay under other strategies, and the A/B
    outcome when it ran in an experiment. A failure here never stops a sale."""
    if deal and deal["unit"].get("unit"):
        u = deal["unit"]
        try:
            TALKS.parent.mkdir(exist_ok=True)
            with TALKS.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"t": round(time.time(), 1), "task": task_id[:8], "sku": u["sku"], "kind": u.get("kind"),
                                    "list_price": u["list_price"], "cost": u["cost"], "ask0": deal.get("ask0"),
                                    "floor": deal["floor"], "clear": deal.get("clear"), "offers": deal["offers"],
                                    "turns": deal["turns"], "event": event, "price": price,
                                    "warranty_ask": deal.get("warranty_ask"), "model_on": deal.get("model_on", False),
                                    "model_calls": deal.get("model_calls", 0), "ab": deal.get("ab"),
                                    "member": deal.get("member", "")}) + "\n")
        except (OSError, KeyError, TypeError):
            pass
    if deal and deal.get("ab"):
        try:
            ab_r3.record(id=deal["ab"][0], arm=deal["ab"][1], task=task_id, event=event, reward=round(reward, 4))
        except OSError:
            pass


def canon(d):
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sign(receipt):
    key = serialization.load_pem_private_key((HERE / "shop_key.pem").read_bytes(), password=None)
    body = {k: receipt[k] for k in ("shop", "item", "price", "task")}
    return dict(receipt, sig_seller=base64.b64encode(key.sign(canon(body))).decode())


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def strategy():
    s = dict(DEFAULTS)
    s.update({k: v for k, v in read_json(STRATEGY, {}).items() if k in DEFAULTS and isinstance(v, (int, float))})
    if os.environ.get("SELLER_MODEL_SHARE"):         # tests run the rules alone (0) or the model on every talk (1)
        s["model_share"] = float(os.environ["SELLER_MODEL_SHARE"])
    return s


SHELF = {}
CATALOG = {}


def catalog():
    if not CATALOG:
        cat = read_json(MARKET_DIR / "catalog.json", {})
        CATALOG.update(cat if isinstance(cat, dict) else {})
    return CATALOG


def shelf_hours(sku):
    if not SHELF:
        cat = read_json(MARKET_DIR / "catalog.json", {})
        SHELF.update({k: v.get("shelf_hours") for k, v in (cat.items() if isinstance(cat, dict) else [])})
    return SHELF.get(sku)


def grade_now(u):
    """(grade, hours left, claim) for a unit: food by shelf life left now, goods by the grade it arrived with."""
    if u.get("kind") != "food" or not u.get("expires_at"):
        return u.get("grade"), None, u.get("grade")
    hours = (u["expires_at"] - time.time()) / 3600
    shelf = shelf_hours(u["sku"])
    if not shelf:
        return u.get("grade"), hours, u.get("grade")
    left = hours / shelf
    grade = "A" if left >= FOOD_CUTS[0] else "B" if left >= FOOD_CUTS[1] else "C"
    # a claim is true if it matches the grade at checkout or at settle, seconds apart; within an hour of a line
    # the grade might change in between, so say nothing and let the market's certificate speak (review, 11/2:
    # claiming the grade below would be false while the unit is still above the line)
    near = any(0 <= (left - c) * shelf < 1 for c in FOOD_CUTS)
    return grade, hours, None if near else grade


HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:h\b|hours?|시간)", re.I)


def needed_hours(text):
    """The shelf life the buyer asked for ("at least 594 hours", "540 h", "180시간"), or 0."""
    hs = [float(h) for h in HOURS.findall(text or "") if 0 < float(h) <= 5000]
    return max(hs, default=0)


def pick(units, need):
    """Among fitting units, the one to clear first (food that expires first, goods that arrived first), but for
    food only among those with the shelf life the buyer asked for; if none has it, the freshest: two 2-star reviews
    on 11/3 were for food that expired before the buyer's stated need while a fresher unit sat on our shelf."""
    left = lambda u: (u["expires_at"] - time.time()) / 3600 if u.get("expires_at") else float("inf")
    if need and units and any(u.get("kind") == "food" for u in units):
        ok = [u for u in units if left(u) >= need]
        if not ok:
            return max(units, key=left)
        units = ok
    return min(units, key=lambda u: (u["expires_at"] or float("inf"), u["supplied_at"]))


def find_unit(text, taken=()):
    """The in-stock unit that fits what the buyer asked for (SKU first, then name or category). Among fitting units
    the one to clear first that still lasts as long as the buyer asked (pick)."""
    want = text.lower()
    need = needed_hours(text)
    inv = read_json(MARKET_DIR / "inventory.json", {})
    if inv.get("round", 0) < 3:
        item = next((k for k in RESERVE if k in want), None)
        return item and {"sku": item, "name": item, "list_price": int(RESERVE[item] * 1.3), "cost": RESERVE[item],
                         "unit": None, "expires_at": None, "supplied_at": 0, "kind": "goods", "grade": None}
    # the kit marks a unit "expired" only on its next refresh, so a unit that ran out since was still offered and its
    # settle refused ("not_expired", 11/7 00:21); a minute's margin covers the talk and the payment
    soon = time.time() + 60
    units = [u for u in inv.get("units", []) if u["grade"] != "expired" and u["unit"] not in taken
             and not (u.get("expires_at") and u["expires_at"] <= soon)]
    named = [u for u in units if u["sku"].lower() in want]
    if named:
        return pick(named, need)
    fit = [u for u in units if (u.get("name") or "").lower() in want
           or (u.get("category") or "").split(">")[-1].lower() in want]
    # asked by category only: the order takes SKUs at 0.5-1.5x a reference price we cannot see, so offer the unit
    # whose list price is nearest the category's median first, then the one to clear first
    med = {d["category"]: d["median_price"] for d in read_json(MARKET_DIR / "demand.json", [])}
    off = lambda u: abs(u["list_price"] / med[u["category"]] - 1) if med.get(u.get("category")) else 0
    if need and fit:
        best = min(round(off(u), 1) for u in fit)
        return pick([u for u in fit if round(off(u), 1) == best], need)
    return min(fit, key=lambda u: (round(off(u), 1), u["expires_at"] or float("inf"), u["supplied_at"]), default=None)


def storage_rate():
    """Storage as a share of cost per day, from inventory.json (the market may change it; 1% at the start)."""
    r = read_json(MARKET_DIR / "inventory.json", {}).get("storage_per_day")
    return r if isinstance(r, (int, float)) and 0 < r < 1 else 0.01


def market_cap(u, s):
    """The highest opening ask the market bears for this unit: list x the 75th percentile of what this SKU settled for
    lately (5 settles or more), else its category's (10 or more), times market_ask; None without enough data or with
    market_ask 0. On 11/4 (6 h, 1,455 talks with market data) 92% of our food talks opened above that line and closed
    37% of the time, those at or under it 65% (goods 56% against 60%); a forum post listed us as asking 33% above the
    going price. The cost floor below still holds: the market line never takes a unit under cost + min_margin."""
    k = s.get("market_ask", 1.0)
    if not k:
        return None
    d = prices_r3.read(MARKET_DIR)
    st = (d.get("skus") or {}).get(u.get("sku"))
    if not st or st.get("n", 0) < 5:
        c = (d.get("categories") or {}).get(prices_r3.leaf(u.get("category")))
        st = (c.get("h6") or c.get("h24")) if c else None
        if not st or st.get("n", 0) < 10:
            return None
    return u["list_price"] * st["p75"] * k


def prices(u, s):
    """(ask, floor) for a unit under strategy s."""
    lp, cost = u["list_price"], u["cost"]
    if u.get("unit") is None:                                  # before Round 3: the old reserve, ask a little above
        return int(lp), int(cost)
    grade, hours, _ = grade_now(u)
    food = u.get("kind") == "food"
    ask_frac = s["ask_frac_food"] if food else s["ask_frac"]
    floor_frac = s["floor_frac_food"] if food else s["floor_frac"]
    if food and hours is not None and shelf_hours(u["sku"]):
        # fresher food is worth more to a buyer who must eat it within some hours: up to fresh_premium more for a
        # full shelf life, as much less near the date (before the clearance rule below takes over)
        left = min(1.0, hours / shelf_hours(u["sku"]))
        ask_frac *= 1 + s["fresh_premium"] * (2 * left - 1)
    floor = max(cost * (1 + s["min_margin"]), lp * min(floor_frac, ask_frac))
    cap = market_cap(u, s)
    if cap:                                     # follow the market down, never under cost + min_margin
        floor = max(cost * (1 + s["min_margin"]), min(floor, cap))
    # clear food by the hours it has left, not by grade: a grade-C unit can still have days (review, 11/2)
    if u.get("kind") == "food" and hours is not None and (hours < s["clear_hours"] or (grade == "C" and hours < 24)):
        floor = cost * s["clear_frac"]
    # goods pay 1% of cost a day while they wait: past goods_age_days the floor drops to cost plus aged_margin, so a
    # slow unit goes before it eats its margin in storage
    # (goods_age_days is set for 1% a day; at another storage rate the same storage paid comes sooner or later)
    if u.get("kind") != "food" and u.get("supplied_at") and \
            (time.time() - u["supplied_at"]) / 86400 > s["goods_age_days"] * 0.01 / storage_rate():
        floor = min(floor, cost * (1 + s["aged_margin"]))
    left = (ROUND_END - time.time()) / 3600                  # the end of the round: unsold stock earns nothing
    if left < s["final_hours"]:
        floor = min(floor, cost * s["final_frac"])
    elif left < s["endgame_hours"]:
        floor = min(floor, cost * s["endgame_frac"])
    # a warranted unit never goes under its cost plus margin after the refunds we expect, whatever drop came above
    if u.get("kind") == "goods" and s["warranty_hours"] > 0 and grade in WARRANTY_Q:
        floor = max(floor, cost * (1 + s["min_margin"]) / (1 - WARRANTY_Q[grade]))
    # stuck goods (11/9 16:0x): 50 grade-A 450k+ units (41.7M of 125M stock) sat on floors above the market's p75 and
    # opened at the floor in 413 of 543 talks, closing 17% against 42% where the market line was above it. The market
    # allows a sale under cost (it costs the shop); the user: only bankruptcy and the rules are limits. Goods held
    # stuck_hours whose market line is under their floor follow it down to stuck_frac of cost, warranty or not:
    # ~6% of cost lost once frees the capital for faster lines
    if u.get("kind") != "food" and cap and cap < floor and u.get("supplied_at") and \
            (time.time() - u["supplied_at"]) / 3600 > s.get("stuck_hours", 6):
        floor = max(cost * s.get("stuck_frac", 0.95), cap)
    ask = max(min(lp * min(ask_frac, 1.0), cap or lp), floor)
    return int(round(ask)), int(round(min(floor, ask)))


def terms(u, s):
    """Receipt terms beyond shop/item/price/task, and how to say them."""
    if u.get("unit") is None:
        return {}, ""
    grade, hours, claim = grade_now(u)
    t = {"unit": u["unit"]}
    if claim:
        t["claim"] = claim
    words = ([f"grade {claim}"] if claim else []) + ["market certificate attached"]
    if u.get("kind") == "food" and hours is not None:
        words.append(f"{hours:.0f} h of shelf life left")
    # every grade of goods (11/9 review): goods break only within 6 h of the sale (agent.md), so any warranty costs the
    # same, and buyers that ask for one closed 4% of our 300k+ talks against 41% without (6 h, 367 vs 119 talks) while
    # the market sells 85% of B and 64% of C with a warranty (72 h most often). Expected refunds (B ~5%, C ~18% of the
    # price) stay under the margin at our asks; stars stay on a refunded deal
    if u.get("kind") == "goods" and s["warranty_hours"] > 0 and grade in WARRANTY_Q:
        t["warranty_hours"] = int(s["warranty_hours"])
        words.append(f"{int(s['warranty_hours'])} h warranty")
    return t, ", ".join(words)


class Seller(AgentExecutor):
    def __init__(self):
        self.open = {}      # task id -> {"unit", "ask", "floor", "offers", "turns"}
        self.sold = {}      # unit -> time a receipt was signed
        self.dealt = {}     # unit -> times receipts were signed for it (two within STUCK_SECS: held by the kit)
        # a unit set aside once that gets stuck again is held for good: 11/5 03:16-04:19 one unit came back after each
        # 30 minutes and was refused at checkout again each time
        self.held, self.stuck_once = set(), set()
        self.refused, self.log_pos, self.log_read = {}, None, 0.0
        self.refusals = {}  # unit -> times of its refusals at checkout, REFUSED_APART apart (two: held for good)

    def agreed(self, unit, now=None):
        """Record a receipt signed for `unit`; returns a STUCK log line when the unit is set aside. A unit set aside
        once is held for good on its next agreement: its refusals came 40-80 min apart, so two within STUCK_SECS never
        added up again and it was refused 4 more times (u-3f62d60535ba, 11/6 18:36-21:22); if that agreement does
        settle, the unit leaves the stock and holding it costs nothing."""
        now = now or time.time()
        self.sold[unit] = now
        self.dealt.setdefault(unit, []).append(now)
        if unit in self.stuck_once and unit not in self.held:
            self.held.add(unit)
            return f"STUCK {unit} stuck again: left out until a restart"
        if len(self.dealt[unit]) == STUCK_AFTER and unit not in self.stuck_once:
            self.stuck_once.add(unit)
            return f"STUCK {unit} agreed {STUCK_AFTER} times and still offered: left out for {STUCK_SECS // 60} min"
        return None

    def read_refusals(self, now, path=None):
        """Units the kit's checkout refused since the last read (at most once a minute; starts at the log's end)."""
        path = path or KIT_LOG
        if now - self.log_read < 60:
            return
        self.log_read = now
        try:
            size = path.stat().st_size
            if self.log_pos is None or size < self.log_pos:
                self.log_pos = size if self.log_pos is None else 0
            with path.open("rb") as f:
                f.seek(self.log_pos)
                text = f.read().decode("utf-8", "ignore")
                self.log_pos = f.tell()
        except OSError:
            return
        for u in set(REFUSED.findall(text)):
            self.refused[u] = now
            seen = self.refusals.setdefault(u, [])
            if not seen or now - seen[-1] >= REFUSED_APART:
                seen.append(now)
            if len(seen) >= 2 and u not in self.held:
                self.held.add(u)
                log(f"STUCK {u} refused at checkout {len(seen)} times, {(seen[-1] - seen[0]) / 60:.0f} min apart: "
                    f"left out until a restart")

    def taken(self):
        now = time.time()
        self.read_refusals(now)
        self.refused = {k: t for k, t in self.refused.items() if now - t < REFUSED_SECS}
        self.sold = {k: t for k, t in self.sold.items() if now - t < RECENT_SOLD}
        self.dealt = {k: [x for x in ts if now - x < STUCK_SECS] for k, ts in self.dealt.items()}
        self.dealt = {k: ts for k, ts in self.dealt.items() if ts}
        stuck = {k for k, ts in self.dealt.items() if len(ts) >= STUCK_AFTER} | self.held | set(self.refused)
        # a buyer that leaves without cancelling must not hold the unit forever (review, 11/2)
        for k in [k for k, d in self.open.items() if now - d.get("t", now) > OPEN_HOLD]:
            ab_end(k, self.open.pop(k, None), "gone")
        return {d["unit"]["unit"] for d in self.open.values() if d["unit"].get("unit")} | set(self.sold) | stuck

    async def execute(self, context, event_queue):
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        up = TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id)
        say = lambda text: up.new_agent_message(parts=[new_text_part(text)])
        text = (get_message_text(context.message) or "")[:2000]   # a buyer's text is matched, never quoted; cap the work
        deal = self.open.get(task.id)
        s = deal["s"] if deal and deal.get("s") else strategy()      # an A/B arm keeps its value to the end

        if deal is None:
            u = find_unit(text, self.taken())
            if u is None or u.get("unit"):
                demand_r3.record_ask(text, catalog(), have=u is not None,       # what buyers came for (demand_r3.py)
                                     warranty=bool(WARRANTY_WORDS.search(text)))
            if u is None:
                await up.reject(say("Sorry, we have none of that in stock."))
                return
            ab, member = None, ""
            if u.get("unit"):
                try:                                      # the sales team member this talk goes to (team_r3.py)
                    member, style = team_r3.choose("seller")
                    s = team_r3.apply_seller(s, style)
                except (OSError, ValueError, KeyError, TypeError):
                    member = ""
                try:
                    e, arm = ab_r3.choose(u.get("kind"))
                except (OSError, ValueError, KeyError):
                    e, arm = None, None
                if arm:
                    v = e["arms"][arm]               # one number, or a whole retail playbook's numbers
                    s, ab = dict(s, **(v if isinstance(v, dict) else {e["param"]: v})), (e["id"], arm)
            ask, floor = prices(u, s)
            normal = max(u["cost"] * (1 + s["min_margin"]), u["list_price"] * min(
                s["floor_frac_food"] if u.get("kind") == "food" else s["floor_frac"], 1.0))
            deal = self.open[task.id] = {"unit": u, "ask": ask, "floor": floor, "offers": [], "turns": 0,
                                         "t": time.time(), "s": s if (ab or member) else None, "ab": ab, "ask0": ask,
                                         "member": member,
                                         "clear": floor < 0.99 * normal,     # clearance, aged or endgame floor
                                         "warranty_ask": bool(WARRANTY_WORDS.search(text)),
                                         "model_on": bool(u.get("unit")) and random.random() < s["model_share"],
                                         "model_calls": 0}
            if ab:
                try:
                    ab_r3.record(id=ab[0], arm=ab[1], task=task.id, event="open", sku=u["sku"], kind=u.get("kind"),
                                 list_price=u["list_price"], cost=u["cost"], ask=ask, floor=floor)
                except OSError:
                    pass
            t, words = terms(u, s)
            log(f"OPEN {task.id[:8]} {u['sku']} {u['name'][:30]} list {u['list_price']} cost {u['cost']} ask {ask} floor {floor}"
                + (f" ab {ab[0]}:{ab[1]}" if ab else "") + (" model" if deal["model_on"] else ""))
            await up.requires_input(say(f"{u['name']} ({u['sku']}){': ' + words if words else ''}. "
                                        f"List price {u['list_price']}, asking {ask}. Send your offer as a number."))
            return

        deal["turns"] += 1
        deal["t"] = time.time()                           # still talking: keep the unit
        nums = OFFER.findall(text)
        offer = int(nums[-1].replace(",", "")) if nums else None     # the last number on its own is the offer
        if offer is not None:
            deal["offers"].append(offer)
        ask, floor, u = deal["ask"], deal["floor"], deal["unit"]
        mid = (ask + floor) / 2
        accept = offer is not None and offer >= floor and (offer >= ask or len(deal["offers"]) >= 2 or offer >= mid)
        think = None
        if deal.get("model_on") and offer is not None and offer < ask and deal["turns"] < s["max_turns"]:
            think = await self.think(task.id, deal, offer, s)
            if think:
                accept = think["action"] == "accept"
        if accept:
            price = min(offer, ask)
            t, words = terms(u, s)
            receipt = sign(dict({"shop": NAME, "item": u["sku"], "price": price, "task": task.id}, **t))
            await up.add_artifact(parts=[new_data_part(receipt)], name="receipt")
            await up.complete(say(f"Deal: {u['name']} at {price}."))
            if u.get("unit"):
                note = self.agreed(u["unit"])
                if note:
                    log(note)
            ab_end(task.id, deal, "deal", (price - u["cost"]) / u["list_price"] if u.get("list_price") else 0.0, price)
            log(f"DEAL {task.id[:8]} {u['sku']} at {price} (cost {u['cost']}, list {u['list_price']}, turns {deal['turns']})")
            del self.open[task.id]
            return
        if deal["turns"] >= s["max_turns"]:
            await up.reject(say(f"Sorry, {floor} is as low as we go. No deal."))
            ab_end(task.id, deal, "walk")
            log(f"WALK {task.id[:8]} {u['sku']} offers {deal['offers']} floor {floor}")
            del self.open[task.id]
            return
        if think:
            ask = think["price"]
        elif offer is not None and offer < ask:
            ask = max(floor, int(round(ask - s["step"] * (ask - offer))))
        deal["ask"] = ask
        await up.requires_input(say(f"Counteroffer: {ask}."))

    async def think(self, task_id, deal, offer, s):
        """The model's call on this turn: {"action": "accept"|"counter", "price", "why"} inside the code's limits, or
        None when every slot is busy, it is slow, or the answer does not parse (the rules then decide)."""
        lo, hi = max(deal["floor"], offer + 1), deal["ask"]      # a counter sits above the offer, never above our ask
        if MODEL_SLOTS.locked():
            log(f"THINK {task_id[:8]} model busy: rules decide")
            return None
        u = deal["unit"]
        grade, hours, _ = grade_now(u)
        life = f"{hours:.0f} h of shelf life left" if u.get("kind") == "food" and hours is not None else \
            f"in stock {(time.time() - (u.get('supplied_at') or time.time())) / 3600:.0f} h"
        stock = sum(x.get("sku") == u["sku"] for x in read_json(MARKET_DIR / "inventory.json", {}).get("units", []))
        mid = (hi + deal["floor"]) / 2
        if offer >= deal["floor"] and (len(deal["offers"]) >= 2 or offer >= mid):
            rule_move = f"accept the offer {offer}"
        else:
            rule_move = f"counter at {max(deal['floor'], int(round(hi - s['step'] * (hi - offer))))}"
        prompt = SELL_PROMPT.format(
            name=harness.clip(u.get("name"), 60), kind=u.get("kind"), grade=grade, life=life, lp=u["list_price"],
            cost=u["cost"], floor=deal["floor"], ask=hi, offers=deal["offers"][-6:], offer=offer,
            left=s["max_turns"] - deal["turns"], stock=stock, demand=demand_of(u["sku"]), lo=lo, hi=max(lo, hi),
            market=prices_r3.line(MARKET_DIR, u["sku"], u.get("category")), rule_move=rule_move, record=record_line())
        deal["model_calls"] += 1
        async with MODEL_SLOTS:
            ans = await harness.ask(prompt, tries=1, timeout=MODEL_TIMEOUT, max_chars=4000)
        if not isinstance(ans, dict) or ans.get("action") not in ("accept", "counter"):
            log(f"THINK {task_id[:8]} no usable answer: rules decide")
            return None
        why = harness.clip(str(ans.get("why") or ""), 120)
        if ans["action"] == "accept":
            if offer < deal["floor"]:
                log(f"THINK {task_id[:8]} {why} -> accept {offer} under the floor {deal['floor']}: rules decide")
                return None
            log(f"THINK {task_id[:8]} {why} -> accept {offer}")
            return {"action": "accept", "price": offer, "why": why}
        p = ans.get("price")
        if lo > hi or not isinstance(p, (int, float)) or isinstance(p, bool):
            log(f"THINK {task_id[:8]} {why} -> counter {p!r} not usable: rules decide")
            return None
        price = int(min(max(round(p), lo), hi))
        log(f"THINK {task_id[:8]} {why} -> counter {price}" + (f" (asked {p})" if price != p else ""))
        return {"action": "counter", "price": price, "why": why}

    async def cancel(self, context, event_queue):
        task = context.current_task
        ab_end(task.id, self.open.pop(task.id, None), "gone")
        await TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id).cancel()


def build(port):
    url = f"http://127.0.0.1:{port}/"
    card = AgentCard(
        name=NAME,
        description="An online shop selling from real stock: groceries, furniture, bedding, appliances. Ask for an item "
                    "by name or SKU; every answer states the grade, the shelf life left for food and the warranty for goods, "
                    "and the market's certificate comes with the unit.",
        version="3.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["application/json", "text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=url, protocol_version="1.0")],
        skills=[AgentSkill(id="negotiate", name="Negotiate a purchase",
                           description="Ask for an item, then send a price. The shop answers with a counteroffer or a signed receipt.",
                           tags=["shopping", "negotiation"], examples=["I want to buy 종가 알뜰맘 포기김치 10kg (G00001)", "52000"])],
    )
    handler = DefaultRequestHandler(agent_executor=Seller(), task_store=InMemoryTaskStore(), agent_card=card)
    return Starlette(routes=create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9301)
    port = ap.parse_args().port
    uvicorn.run(build(port), host="127.0.0.1", port=port, log_level="warning")
