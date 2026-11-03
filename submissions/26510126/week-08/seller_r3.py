"""Round 3 seller: sells units from the stock the kit keeps in $MARKET_DIR/inventory.json, behind A2A v1.0.

    python seller_r3.py --port 9301

Started from the course's starter_round3/seller.py (A2A side, unit lookup, receipt signing). What is ours:
  - Prices are set by code from strategy_r3.json, which the meta-harness (meta_r3.py, Claude haiku) rewrites; no
    model call per turn, so a busy market does not queue behind `claude -p`.
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
import base64
import json
import os
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

HERE = Path(__file__).resolve().parent
NAME = "thisjonghoon"
RESERVE = {"lamp": 100, "chair": 180, "bookshelf": 260}     # Rounds 0-2 have no stock: the week-07 items
MARKET_DIR = Path(os.environ.get("MARKET_DIR", HERE / ".market"))
STRATEGY = HERE / "strategy_r3.json"
DEFAULTS = {"ask_frac": 0.95, "floor_frac": 0.78, "min_margin": 0.10, "step": 0.4,
            "clear_hours": 6, "clear_frac": 0.6, "warranty_hours": 0, "max_turns": 6,
            "endgame_hours": 24, "endgame_frac": 1.0, "final_hours": 6, "final_frac": 0.6,
            "ask_frac_food": 0.95, "floor_frac_food": 0.78, "fresh_premium": 0.10,
            "goods_age_days": 5, "aged_margin": 0.03}
ROUND_END = 1794927540                                       # 2026-11-17 23:59 KST: stock left then is a loss
OFFER = re.compile(r"(?<![A-Za-z0-9])\d[\d,]*(?![A-Za-z0-9])")   # a number on its own, not the digits of a SKU
FOOD_CUTS = (0.80, 0.45)                                     # shelf life left: A at or above 80%, B at or above 45%
RECENT_SOLD = 60
OPEN_HOLD = 120     # seconds a negotiation keeps its unit before another buyer may be offered it


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ab_end(task_id, deal, event, reward=0.0):
    """Record how a negotiation in an A/B experiment ended; a failure here never stops a sale."""
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
    return s


SHELF = {}


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


def find_unit(text, taken=()):
    """The in-stock unit that fits what the buyer asked for (SKU first, then name or category). Among fitting units
    the one to clear first: food that expires first, goods that arrived first."""
    want = text.lower()
    inv = read_json(MARKET_DIR / "inventory.json", {})
    if inv.get("round", 0) < 3:
        item = next((k for k in RESERVE if k in want), None)
        return item and {"sku": item, "name": item, "list_price": int(RESERVE[item] * 1.3), "cost": RESERVE[item],
                         "unit": None, "expires_at": None, "supplied_at": 0, "kind": "goods", "grade": None}
    units = [u for u in inv.get("units", []) if u["grade"] != "expired" and u["unit"] not in taken]
    named = [u for u in units if u["sku"].lower() in want]
    if named:
        return min(named, key=lambda u: (u["expires_at"] or float("inf"), u["supplied_at"]))
    fit = [u for u in units if (u.get("name") or "").lower() in want
           or (u.get("category") or "").split(">")[-1].lower() in want]
    # asked by category only: the order takes SKUs at 0.5-1.5x a reference price we cannot see, so offer the unit
    # whose list price is nearest the category's median first, then the one to clear first
    med = {d["category"]: d["median_price"] for d in read_json(MARKET_DIR / "demand.json", [])}
    off = lambda u: abs(u["list_price"] / med[u["category"]] - 1) if med.get(u.get("category")) else 0
    return min(fit, key=lambda u: (round(off(u), 1), u["expires_at"] or float("inf"), u["supplied_at"]), default=None)


def storage_rate():
    """Storage as a share of cost per day, from inventory.json (the market may change it; 1% at the start)."""
    r = read_json(MARKET_DIR / "inventory.json", {}).get("storage_per_day")
    return r if isinstance(r, (int, float)) and 0 < r < 1 else 0.01


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
    ask = max(lp * min(ask_frac, 1.0), floor)
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
    if u.get("kind") == "goods" and s["warranty_hours"] > 0 and grade == "A":   # B and C break more, we guess
        t["warranty_hours"] = int(s["warranty_hours"])
        words.append(f"{int(s['warranty_hours'])} h warranty")
    return t, ", ".join(words)


class Seller(AgentExecutor):
    def __init__(self):
        self.open = {}      # task id -> {"unit", "ask", "floor", "offers", "turns"}
        self.sold = {}      # unit -> time a receipt was signed

    def taken(self):
        now = time.time()
        self.sold = {k: t for k, t in self.sold.items() if now - t < RECENT_SOLD}
        # a buyer that leaves without cancelling must not hold the unit forever (review, 11/2)
        for k in [k for k, d in self.open.items() if now - d.get("t", now) > OPEN_HOLD]:
            ab_end(k, self.open.pop(k, None), "gone")
        return {d["unit"]["unit"] for d in self.open.values() if d["unit"].get("unit")} | set(self.sold)

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
            if u is None:
                await up.reject(say("Sorry, we have none of that in stock."))
                return
            ab = None
            if u.get("unit"):
                try:
                    e, arm = ab_r3.choose(u.get("kind"))
                except (OSError, ValueError, KeyError):
                    e, arm = None, None
                if arm:
                    s, ab = dict(s, **{e["param"]: e["arms"][arm]}), (e["id"], arm)
            ask, floor = prices(u, s)
            deal = self.open[task.id] = {"unit": u, "ask": ask, "floor": floor, "offers": [], "turns": 0,
                                         "t": time.time(), "s": s if ab else None, "ab": ab}
            if ab:
                try:
                    ab_r3.record(id=ab[0], arm=ab[1], task=task.id, event="open", sku=u["sku"], kind=u.get("kind"),
                                 list_price=u["list_price"], cost=u["cost"], ask=ask, floor=floor)
                except OSError:
                    pass
            t, words = terms(u, s)
            log(f"OPEN {task.id[:8]} {u['sku']} {u['name'][:30]} list {u['list_price']} cost {u['cost']} ask {ask} floor {floor}"
                + (f" ab {ab[0]}:{ab[1]}" if ab else ""))
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
        if offer is not None and offer >= floor and (offer >= ask or len(deal["offers"]) >= 2 or offer >= mid):
            price = min(offer, ask)
            t, words = terms(u, s)
            receipt = sign(dict({"shop": NAME, "item": u["sku"], "price": price, "task": task.id}, **t))
            await up.add_artifact(parts=[new_data_part(receipt)], name="receipt")
            await up.complete(say(f"Deal: {u['name']} at {price}."))
            if u.get("unit"):
                self.sold[u["unit"]] = time.time()
            ab_end(task.id, deal, "deal", (price - u["cost"]) / u["list_price"] if u.get("list_price") else 0.0)
            log(f"DEAL {task.id[:8]} {u['sku']} at {price} (cost {u['cost']}, list {u['list_price']}, turns {deal['turns']})")
            del self.open[task.id]
            return
        if deal["turns"] >= s["max_turns"]:
            await up.reject(say(f"Sorry, {floor} is as low as we go. No deal."))
            ab_end(task.id, deal, "walk")
            log(f"WALK {task.id[:8]} {u['sku']} offers {deal['offers']} floor {floor}")
            del self.open[task.id]
            return
        if offer is not None and offer < ask:
            ask = max(floor, int(round(ask - s["step"] * (ask - offer))))
        deal["ask"] = ask
        await up.requires_input(say(f"Counteroffer: {ask}."))

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
