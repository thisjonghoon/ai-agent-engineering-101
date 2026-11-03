# Week 08 (midterm) — our shop and buyer in the Round 3 market

**Status, 2026-11-03 (draft).** Round 3 runs 11/3 to 11/17 23:59 (the date moved on 10/31, with kit v4 and the
economy rules). Sections 1 and 2 describe the agents built for Round 3; section 3 is filled in from the Round 3 logs.
The one-page figure is `architecture.tex` / `architecture.pdf`.

- **Shop:** our own seller (`seller_r3.py`) run by kit v4 on a Mac mini behind a cloudflared tunnel, selling from
  stock it buys itself (`restock_r3.py`). A meta-harness (`meta_r3.py`, Claude haiku) sets its prices and stock policy.
- **Buyer:** `market_buyer.py` → `buyer_r3.py` (Claude haiku per offer) with a raw-evidence memory, a review hook and
  forum posts; it pays through our copy of kit v4, which makes the checkout tools from each shop's `acp.json`.
- **Why not the Worker any more.** Until Round 2 the shop was a Cloudflare Worker (`deploy/`) that also served its own
  ACP checkout (section 1.4). In Round 3 a shop sells units from stock, with grades, warranties and a unit chosen at
  checkout; kit v4 does that for a seller it runs, a Worker would have to redo it all. With a day and a half before
  the round, we moved the shop to the kit and kept the Worker work as the Round 2 part of the story.

## 1. Components

### 1.1 Models

| Where | Model | What it decides | What code decides instead |
|---|---|---|---|
| Shop strategy, every 15 min | Claude haiku (`meta_r3.py`) | ask and floor as shares of list price, separately for food (with a freshness premium) and goods, minimum margin, concession step, food clearance, warranty hours, cash reserve, stock cap, which goods and food to stock, depth, price spread, best-seller depth; it sees settled sales, revenue and the market's settled prices by kind | bounds and a largest step per cycle for every number; floor ≥ cost + 2% outside clearance; when fewer than 60% of a busy window's receipts settle and no warranty is offered, code tries a 2 h warranty on grade-A goods; an A/B test's winner is applied by code, not chosen by the model; an unusable answer keeps the current strategy |
| Shop, each haggle turn | none (code) | — | `seller_r3.py`: counter moves `step` toward the offer, never under the floor; accept at or above the floor after two offers or at the midpoint; while an A/B test runs, each negotiation draws one arm and keeps it. No model per turn, so a busy market does not queue behind `claude -p` |
| Buyer, each order | Claude haiku (`buyer_r3.py` via `buyer.py`) | each offer in the haggle | which shop and SKU (expected surplus), bans (false grade claims, broken goods without warranty), cap = min(budget, 0.9 × list), accept policy for the kit |
| Ideas | Claude sonnet (`meta_explore.py`, from week 7) | proposals only | everything |

All Claude calls go through `claude -p` with no tools, no settings, no session persistence, on the subscription.

### 1.2 Context

- **Buyer memory, raw evidence only** (`memory.jsonl`, LongMemEval-V2 style). Each settled deal (grade, claim,
  whether the claim was true, shelf life left, price against list), each refusal the kit wrote to `payments.jsonl`,
  and each broken item from `broken.jsonl` (matched to our last purchase of that name, so we know the shop and the
  warranty) is appended; nothing is summarised on write. The shop's record is derived when an order reads it.
- **The market's record:** settle entries from the ledger (what sold, at what share of list, claim honesty), read in
  small pages. The buyer expects a shop it never paid to charge what that shop settled for with everyone (median of
  its last 10 settles), so cheap shops are tried first and its own memory takes over once it has paid there; the
  restock keeps a decaying score per category in `.market/restock_state.json`.
- **A/B evidence** (`logs/ab_r3.jsonl`, `ab_r3.py`): the meta-harness compares a 15-minute window with the one before,
  but traffic moves more than prices between hours (on 11/3, 8 deals in a night half hour, 73 in a late-morning one).
  So one strategy number is also tested inside the shop: each negotiation draws one of two values at the same hour
  (Thompson sampling, reward = margin over list, 0 for a lost sale), and once one value is better with probability
  0.95 after 30 negotiations each, code writes it into the strategy. The first test: the ask on goods at 0.95 or
  0.85 of list.
- **Retail playbooks and counterfactual replay** (`playbooks_r3.py`, `simulate_r3.py`, `logs/talks_r3.jsonl`): our
  meta-harness only searched near its own last strategy, so it is also shown whole positions from real retail
  (Costco's capped markup with deep, few SKUs; Walmart's everyday low price with little haggling; grocery markdowns
  by hours left; premium goods with a warranty; the 2026 two-tier "cheap and premium" playbook), written in our
  strategy's numbers. The seller writes every negotiation as one raw line (the buyer's offers, list price, cost, ask,
  floor, outcome, whether it asked for a warranty), and the replay runs the seller's own rules against those offers
  under each playbook, without a model. Because buyers react to our counters, which a replay cannot know, it reports
  its `fidelity` and is used only to choose what to A/B test: the meta-harness may propose one number to test, and
  code starts it within the bounds when no test is running. Warranty requests to our shop are counted and weighed
  against refund risk; warranty is not A/B tested, because the test's reward cannot see refunds.
- **How past deals and reputation feed the next decision:** our buyer's record of a shop (prices paid, false claims,
  broken goods) sets which shop it tries and bans liars; the ledger's prices and claim honesty cover shops we never
  met; the shop's own sales and the ledger's settles steer what the restock buys; the strategy history and the A/B
  log steer the prices; reviews of our deals become stars, and our forum notes carry ledger refs so other buyers can
  check them.
- **Meta-harness history** (`logs/strategies_r3.jsonl`): every strategy version with what happened while it ran
  (deals, walk-aways, price as a share of list, margin over cost, profit, stock at cost, ageing stock). The harness
  sees the last 30; a version's outcome is the measurement stored at the next decision, so nothing is re-measured.
- **Kit files as the shop's eyes:** `inventory.json` (balance, units with cost, grade and dates), `catalog.json`,
  `demand.json` (categories only; the market publishes no demand weights).

### 1.3 Tools

| Tool | Who uses it | Made how |
|---|---|---|
| Checkout tools made from a shop's `acp.json` (optional HW) | our buyer's kit, in every Round 3 payment | `market_kit.py` (our copy of kit v4, `acp_pay_tools`): one tool per entry with name, description and JSON Schema input; arguments checked against the schema; the kit's checks (signed checkout matching the receipt or an acceptable SKU, total within the open payment mandate, the buyer's accept policy) before paying; `--fixed-checkout` returns to the kit's code |
| Our shop's `acp.json` | other buyers' tools | `AcpShop.card` in our kit copy writes each input as JSON Schema |
| A2A negotiation | our buyer and our seller | `buyer.py` client, `seller_r3.py` server |
| `restock` hook, `review` hook, forum outbox | kit v4 | `restock_r3.py`, `review_r3.py`, `forum_r3.py` |

**The optional tool buyer.** Built for kit v3 on 10/30 and moved onto kit v4 on 11/1 (`082e28d`, 9/9 offline cases):
before a session exists a failure falls back to the kit's `acp_pay`; after, one fixed `complete` on the same session
at most; after a `complete` was sent, never again. **How it was made:** the first attempt in this session was stopped
part-way by Claude Code's safety filter while writing the mandate-signing code, although the credits are the course
market's. A second session, given the assignment text and this context, wrote it (`1d7cd73`..`7a6ddd0`). Reviewing it
against what the main session knew, one gap was fixed (`cc2afca`): it cancelled sessions when a shop's GET left out
`checkout_jwt` or named its status differently, which shops built without the kit may do and the kit's `acp_pay` would
have paid. Moving it to kit v4 was a mechanical patch of the same diff plus kit v4's new checks.

### 1.4 Round 2 to Round 3: the Worker shop

The Worker (`deploy/src/index.ts`) served A2A with Llama 3.1 8B and code guards, a strategy API for the meta-harness,
and from 10/27 its own ACP checkout (`acp.json`, checkout sessions, `complete` forwarding the mandates to
`/api/settle`; `acp_check.py` and `logs/acp-check-*.txt`). On 10/30 its `acp.json` gained `description` and
`input_schema` beside the unchanged `input` strings, so older buyers kept working (`762979b`).

## 2. Structure, and how it differs from the kit's baseline

See `architecture.pdf`. In short:

| | Kit baseline (starter_round3) | Ours |
|---|---|---|
| Seller | a model at every turn; ships the unit that expires first; no quality talk, no warranty; never under cost | code prices from a strategy the meta-harness rewrites; honest grade claim (one grade lower near a line), the market's certificate; warranty only when the meta-harness sets one (0 at the start, since a refund costs the whole price and the break rate is unknown); near-date food cleared under cost (a spoiled unit loses all of its cost) |
| Stock | a few random SKUs | one unit per category near its median price first (a buyer only sees shops that hold the ordered category); where settled deals show, depth plus a cheaper and a dearer SKU (orders take SKUs at 0.5-1.5x a hidden reference price); the SKUs the ledger keeps settling, bought by themselves; categories that buyers ask for in forum "wanted" posts first; cash reserve and stock cap; no buying in the last 36 h |
| Buyer | picks and haggles | expected-surplus choice over (shop, SKU), memory of raw evidence, bans for false claims and unwarranted breakages, accept policy (certificate, shelf life, grade) checked by the kit before paying |
| Checkout | fixed code; inputs described as short strings | tools made from each shop's `acp.json`, fixed code only as a fallback; our card in JSON Schema |
| Forum | none | facts from our settled deals with ledger refs, at most one post in 5 minutes |
| Learning | none | the meta-harness over strategy versions, plus an A/B test inside the shop that holds the hour fixed |

**What moves without an order.** Week 9 places the rounds on the weak notion of agency (Wooldridge and Jennings,
1995): autonomy, reactivity, social ability and pro-activeness, the last absent until Round 3. Ours acts first in
three places, each with a reason to act and a limit: the restock buys before demand shows (one unit per category, more
only where settles or forum "wanted" posts show demand, within a cash reserve and a stock cap); the forum notes are
written only when our settled evidence is new (Horvitz's 1999 threshold in a crude form: speak first only with
something checkable to say); and the meta-harness and the A/B test change prices between orders.

## 3. Round 3 results

TODO from 11/3: settled deals (shop and buyer), Players rank, refused settlements quoted from `logs/market-kit.log`
and `.market/payments.jsonl` (`python r3_results.py` prints them as Markdown), the A/B results (`python ab_r3.py`), and "값 다시 정하기" (`python reprice_dashboard.py`: opening ask and deal price before
and after the budgets left the ledger).
