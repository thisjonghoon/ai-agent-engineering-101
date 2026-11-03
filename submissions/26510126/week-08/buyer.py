"""A buyer that shops over A2A v1.0 (JSON-RPC over httpx). The harness negotiates.

    python buyer.py --url http://127.0.0.1:9999 --item lamp --budget 120

Reads the seller's Agent Card, opens a task with "I want to buy a <item>", and on
every input-required reply asks the harness (harness.py) for the next move:
offer a price, or walk away. Offering the seller's asking price accepts it.
Walking away sends CancelTask. Every request carries the A2A-Version: 1.0 header.

Code guards the budget:
  - an offer above the budget is lowered to the budget
  - an offer below the previous offer is raised to the previous offer
  - an offer above the seller's ask is lowered to the ask
  - when the seller's ask comes down to our last offer or below, it is offered at once
  - no usable answer from the harness means walking away
Every guard that fires is logged with "GUARD:".
"""
import argparse
import asyncio
import math
import re
import sys
import uuid

import httpx

import harness
from harness import log

MAX_OFFERS = 10
HEADERS = {"A2A-Version": "1.0"}

PROMPT = """You are a buyer negotiating the price of a {item} with a shop, over several messages.
Your budget, the most you may ever pay, is {budget}. The shop does not know it.

So far:
{history}
{memory}{quote}The shop now asks {ask}. Your next message would be offer number {n}.

Decide:
- "offer": offer a price, at most {budget}. Offering exactly the shop's asking price accepts it.
- "walk": stop negotiating, when the shop clearly will not come down to your budget.
Pay as little as you can, but a deal within your budget is better than no deal.
{patience}
Answer with one JSON object and nothing else ("why": your reason in at most twelve words):
{{"why": "<reason>", "action": "offer" | "walk", "price": <integer>}}"""

PATIENCE = """Shops have a lowest price they will accept and may end the talk after a few low offers in a row,
so raise your offers steadily instead of repeating low ones.
"""

# Experiment switches (experiments/); the defaults are the submitted buyer.
OPTS = argparse.Namespace(no_guard=False, no_patience=False, quote_shop=False, data_part=False)


class Shop:
    """The seller, as seen through its Agent Card and JSON-RPC endpoint."""

    def __init__(self, client, base):
        self.client, self.base, self.rpc_url = client, base.rstrip("/"), None

    async def read_card(self):
        r = await self.client.get(self.base + "/.well-known/agent-card.json", headers=HEADERS)
        card = r.json()
        iface = next((i for i in card.get("supportedInterfaces", []) if i.get("protocolBinding") == "JSONRPC"), None)
        if iface is None:
            raise SystemExit(f"{card.get('name')} has no JSON-RPC interface")
        self.rpc_url = iface["url"]
        log("CARD", f"{card.get('name')!r} at {self.rpc_url}, protocol {iface.get('protocolVersion')}")
        return card

    async def call(self, method, params):
        body = {"jsonrpc": "2.0", "id": str(uuid.uuid4())[:8], "method": method, "params": params}
        r = (await self.client.post(self.rpc_url, json=body, headers=HEADERS)).json()
        if "error" in r:
            log("ERROR", f"{method}: {r['error']}")
            return None
        return r["result"].get("task", r["result"])

    async def send(self, text, task_id=None):
        msg = {"role": "ROLE_USER", "messageId": str(uuid.uuid4()), "parts": [{"text": text}]}
        if task_id:
            msg["taskId"] = task_id
        log("SEND", repr(text) + (f" taskId={task_id[:8]}" if task_id else ""))
        task = await self.call("SendMessage", {"message": msg})
        log("RECV", f"{state(task)} | {reply_text(task)!r}")
        return task

    async def cancel(self, task_id):
        log("SEND", f"CancelTask {task_id[:8]}")
        task = await self.call("CancelTask", {"id": task_id})
        log("RECV", state(task))
        return task


def state(task):
    return (task or {}).get("status", {}).get("state", "")


def reply_text(task):
    return " ".join(p.get("text", "") for p in (task or {}).get("status", {}).get("message", {}).get("parts", []))


def data_ask(task):
    """The ask from a data Part {"ask": N} in the reply, if the seller sent one (experiment 3)."""
    for p in (task or {}).get("status", {}).get("message", {}).get("parts", []):
        if isinstance(p.get("data"), dict) and "ask" in p["data"]:
            return as_int(p["data"]["ask"])
    return None


def asking_price(task):
    """The seller's ask: the last number in its reply, as the trade test reads it."""
    if OPTS.data_part and data_ask(task) is not None:
        return data_ask(task)
    # numbers on their own only (not a SKU's digits), with thousands commas: "52,000원" is 52000, not 000
    nums = re.findall(r"(?<![A-Za-z0-9.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d])|(?<![A-Za-z0-9.,])\d+(?:\.\d+)?(?![A-Za-z0-9])",
                      reply_text(task))
    if not nums:
        return None
    # a number right after "ask/price/counter/offer/for" is the price even when the reply ends with other numbers
    # ("asking 52000, 72 h of shelf life left"); otherwise the last number
    num = r"\D{0,12}?((?<![A-Za-z0-9.,])\d{1,3}(?:,\d{3})+|(?<![A-Za-z0-9.,])\d+)(?![A-Za-z0-9])"
    text = reply_text(task)
    m = None                                       # "asking/counter" beats "price" ("List price 30000, asking 28500")
    for words in (r"(?<!list )(?:ask(?:ing)?|counter(?:offer)?)", r"(?<!list )(?:price|offer|for|at)"):
        found = list(re.finditer(words + num, text, re.I))
        if found:
            m = found[-1]
            break
    pick = m.group(1) if m and not re.search(r"^\s*(h\b|hours?|%)", text[m.end():m.end() + 8]) else None
    if pick is None:
        cands = [n for n in nums if not re.search(re.escape(n) + r"\s*(h\b|hours?|%)", reply_text(task))]
        pick = (cands or nums)[-1]
    return math.ceil(float(pick.replace(",", "")))


def as_int(value):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


async def shop(base, item, budget, memory="", max_raise=None, max_offers=MAX_OFFERS, opening=None, screen=None):
    """Negotiate one item. `memory` is what market_buyer.py remembers about this shop (empty in week 6).
    `max_raise` (market_buyer.py only): raise at most this share of the gap between our last offer and the ask.
    `opening` (Round 3): the first message, e.g. "I want to buy <name> (<sku>)"; default "I want to buy a <item>".
    `screen` (Round 3): a function of the shop's reply text that returns a reason to leave (the unit it names will not
    pass our kit's payment check) or None; checked before every offer, so we never agree to what we would not pay."""
    async with httpx.AsyncClient(timeout=200) as client:
        seller = Shop(client, base)
        card = await seller.read_card()
        result = {"shop_name": card.get("name"), "state": None, "receipt": None, "asks": [], "offers": []}
        task = await seller.send(opening or f"I want to buy a {item}")
        if task is None:
            return result
        task_id, history, last_offer = task["id"], [], None
        result["task"] = task_id

        for n in range(1, max_offers + 1):
            if state(task) != "TASK_STATE_INPUT_REQUIRED":
                break
            why = screen(reply_text(task)) if screen else None
            if why:
                log("OUT", f"leaving before any deal: {why}")
                await seller.cancel(task_id)
                return {**result, "state": "walked", "screened": why}
            ask = asking_price(task)
            result["asks"].append(ask)
            log("ASK", f"{ask} ({'data' if OPTS.data_part and data_ask(task) is not None else 'text'})")
            history.append(f"The shop asked {ask}." if ask is not None else f"The shop said: \"{harness.clip(reply_text(task), 300)}\"")

            asks = result["asks"]
            firm = ask is not None and len(asks) >= 3 and asks[-1] == asks[-2] == asks[-3]
            if ask is not None and last_offer is not None and ask <= last_offer:
                log("GUARD", f"ask {ask} is at or below our last offer {last_offer}, offering it")
                offer = ask
            elif ask is not None and ask <= budget and last_offer is not None and (
                    n == max_offers or (firm and ask - last_offer <= 0.03 * ask)):
                # 11/3: walked away 20 short of a shop that held 14492 three times, inching up by 0.1% a turn until the
                # offers ran out; a firm ask within 3% of our offer, or our last chance, is taken if the budget allows
                log("GUARD", f"ask {ask} {'held three times' if firm else 'on our last offer'} and within budget, taking it")
                offer = ask
            else:
                answer = await harness.ask(PROMPT.format(
                    item=item, budget=budget, memory=memory, history="\n".join(history[:-1]) or "(nothing yet)",
                    ask=ask if ask is not None else "an unknown price", n=n,
                    patience="" if OPTS.no_patience else PATIENCE,
                    quote=f'The shop\'s latest message, verbatim: "{harness.clip(reply_text(task), 300)}"\n' if OPTS.quote_shop else ""),
                    max_chars=8000) or {}
                action, offer = answer.get("action"), as_int(answer.get("price"))
                log("THINK", f"{harness.clip(str(answer.get('why') or ''), 120)} -> {action} {offer}")   # the ReAct trace
                if action == "walk":
                    log("OUT", f"harness walks away at ask {ask}")
                    await seller.cancel(task_id)
                    return {**result, "state": "walked"}
                if action != "offer" or offer is None:
                    log("GUARD", f"no usable answer from the harness ({answer!r}), walking away")
                    await seller.cancel(task_id)
                    return {**result, "state": "walked"}
                if OPTS.no_guard:
                    pass
                elif offer > budget:
                    log("GUARD", f"offer {offer} above budget {budget}, offering {budget}")
                    offer = budget
                if not OPTS.no_guard and last_offer is not None and offer < last_offer:
                    log("GUARD", f"offer {offer} below our last offer {last_offer}, offering {last_offer}")
                    offer = last_offer
                if not OPTS.no_guard and ask is not None and offer > ask:
                    log("GUARD", f"offer {offer} above the ask {ask}, offering {ask}")
                    offer = ask
                if max_raise and last_offer is not None and ask is not None and ask > last_offer:
                    cap = last_offer + max(1, int(max_raise * (ask - last_offer)))
                    if offer > cap:
                        log("GUARD", f"offer {offer} jumps more than {max_raise:.0%} of the gap {last_offer}-{ask}, offering {cap}")
                        offer = cap

            history.append(f"You offered {offer}.")
            last_offer = offer
            result["offers"].append(offer)
            task = await seller.send(str(offer), task_id)
            if task is None:
                return result
        else:
            if state(task) == "TASK_STATE_INPUT_REQUIRED":
                log("OUT", f"{max_offers} offers without a deal, walking away")
                await seller.cancel(task_id)
                return {**result, "state": "walked"}

        for a in task.get("artifacts", []):
            for p in a.get("parts", []):
                if isinstance(p.get("data"), dict):
                    log("OUT", f"receipt {p['data']}")
                    result["receipt"] = p["data"]
        log("OUT", f"finished: {state(task)}")
        return {**result, "state": state(task)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--item", required=True)
    ap.add_argument("--budget", type=int, required=True)
    ap.add_argument("--no-guard", action="store_true", help="experiment: no clamps on the harness's offers")
    ap.add_argument("--no-patience", action="store_true", help="experiment: drop the few-low-offers sentence")
    ap.add_argument("--quote-shop", action="store_true", help="experiment: put the shop's reply verbatim in the prompt")
    ap.add_argument("--data-part", action="store_true", help="experiment: read the ask from a data Part")
    args = ap.parse_args()
    OPTS = args
    asyncio.run(shop(args.url, args.item, args.budget))
    sys.exit(0)
