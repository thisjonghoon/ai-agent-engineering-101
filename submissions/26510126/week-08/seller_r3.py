"""Round 3 seller: sells units from the stock the kit keeps in $MARKET_DIR/inventory.json, behind A2A v1.0.

    python seller_r3.py --port 9301

Started from the course's starter_round3/seller.py (A2A side, unit lookup, receipt signing). What is ours:
  - Prices are set by code from strategy_r3.json, which the meta-harness (meta_r3.py, Claude haiku) rewrites; no
    model call per turn, so a busy market does not queue behind `claude -p`.
      ask   = list price x ask_frac
      floor = max(cost x (1 + min_margin), list price x floor_frac), never above the ask
    Food close to its date (less than clear_hours left, or grade C) is cleared down to cost x clear_frac: a unit
    thrown away loses its whole cost, a cheap sale loses less.
  - Concession: the counter moves `step` of the way from the last ask to the buyer's offer, never below the floor; an
    offer at or above the floor is accepted once the buyer has made two offers or meets the midpoint.
  - Honest terms in the receipt: the grade claim is the unit's grade now, one grade lower when food is within 3% of a
    grade line (a claim is judged at checkout or at settle); the market's certificate is always shown; goods carry
    warranty_hours from the strategy.
  - Units promised in an open negotiation or sold in the last 60 s are not offered again (inventory.json can be
    10 s old, and the kit refuses a checkout for a unit already gone).
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

HERE = Path(__file__).resolve().parent
NAME = "thisjonghoon"
RESERVE = {"lamp": 100, "chair": 180, "bookshelf": 260}     # Rounds 0-2 have no stock: the week-07 items
MARKET_DIR = Path(os.environ.get("MARKET_DIR", HERE / ".market"))
STRATEGY = HERE / "strategy_r3.json"
DEFAULTS = {"ask_frac": 0.95, "floor_frac": 0.78, "min_margin": 0.10, "step": 0.4,
            "clear_hours": 6, "clear_frac": 0.6, "warranty_hours": 6, "max_turns": 6}
FOOD_CUTS = (0.80, 0.45)                                     # shelf life left: A at or above 80%, B at or above 45%
RECENT_SOLD = 60


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


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
    near = any(0 <= left - c < 0.03 for c in FOOD_CUTS)      # about to cross a line: claim the grade below
    claim = {"A": "B", "B": "C"}.get(grade, grade) if near else grade
    return grade, hours, claim


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
    fit = named or [u for u in units if (u.get("name") or "").lower() in want
                    or (u.get("category") or "").split(">")[-1].lower() in want]
    return min(fit, key=lambda u: (u["expires_at"] or float("inf"), u["supplied_at"]), default=None)


def prices(u, s):
    """(ask, floor) for a unit under strategy s."""
    lp, cost = u["list_price"], u["cost"]
    if u.get("unit") is None:                                  # before Round 3: the old reserve, ask a little above
        return int(lp), int(cost)
    grade, hours, _ = grade_now(u)
    floor = max(cost * (1 + s["min_margin"]), lp * s["floor_frac"])
    if u.get("kind") == "food" and (grade == "C" or (hours is not None and hours < s["clear_hours"])):
        floor = cost * s["clear_frac"]
    ask = max(lp * s["ask_frac"], floor)
    return int(round(ask)), int(round(min(floor, ask)))


def terms(u, s):
    """Receipt terms beyond shop/item/price/task, and how to say them."""
    if u.get("unit") is None:
        return {}, ""
    grade, hours, claim = grade_now(u)
    t = {"unit": u["unit"], "claim": claim}
    words = [f"grade {claim}", "market certificate attached"]
    if u.get("kind") == "food" and hours is not None:
        words.append(f"{hours:.0f} h of shelf life left")
    if u.get("kind") == "goods" and s["warranty_hours"] > 0:
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
        return {d["unit"]["unit"] for d in self.open.values() if d["unit"].get("unit")} | set(self.sold)

    async def execute(self, context, event_queue):
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        up = TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id)
        say = lambda text: up.new_agent_message(parts=[new_text_part(text)])
        text = get_message_text(context.message) or ""
        s = strategy()
        deal = self.open.get(task.id)

        if deal is None:
            u = find_unit(text, self.taken())
            if u is None:
                await up.reject(say("Sorry, we have none of that in stock."))
                return
            ask, floor = prices(u, s)
            deal = self.open[task.id] = {"unit": u, "ask": ask, "floor": floor, "offers": [], "turns": 0}
            t, words = terms(u, s)
            log(f"OPEN {task.id[:8]} {u['sku']} {u['name'][:30]} list {u['list_price']} cost {u['cost']} ask {ask} floor {floor}")
            await up.requires_input(say(f"{u['name']} ({u['sku']}){': ' + words if words else ''}. "
                                        f"List price {u['list_price']}, asking {ask}. Send your offer as a number."))
            return

        deal["turns"] += 1
        m = re.search(r"\d[\d,]*", text)
        offer = int(m.group().replace(",", "")) if m else None
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
            log(f"DEAL {task.id[:8]} {u['sku']} at {price} (cost {u['cost']}, list {u['list_price']}, turns {deal['turns']})")
            del self.open[task.id]
            return
        if deal["turns"] >= s["max_turns"]:
            await up.reject(say(f"Sorry, {floor} is as low as we go. No deal."))
            log(f"WALK {task.id[:8]} {u['sku']} offers {deal['offers']} floor {floor}")
            del self.open[task.id]
            return
        if offer is not None and offer < ask:
            ask = max(floor, int(round(ask - s["step"] * (ask - offer))))
        deal["ask"] = ask
        await up.requires_input(say(f"Counteroffer: {ask}."))

    async def cancel(self, context, event_queue):
        task = context.current_task
        self.open.pop(task.id, None)
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
