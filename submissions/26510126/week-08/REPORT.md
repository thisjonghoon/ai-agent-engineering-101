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

Three loops, each built the same way: a model proposes, code checks and acts, and the outcome is written down as
raw evidence that the next decision reads.

- **The buyer's haggle is a ReAct loop** (week 2): observe the shop's ask, think and act (the model returns a
  one-line `why` with its offer, logged as `THINK`), observe the reply. Code bounds every action (budget, no lower
  offer, raise cap) and ends the loop (walk, max offers).
- **The meta-harness is the same loop, slowed down** to 15 minutes. It observes what the last version did, decides
  the next strategy, and code clamps it. Its outcome is read on the next cycle.
- **Memory follows LongMemEval-V2:**
  - raw evidence only, appended and never summarised on write; summaries are derived on read;
  - static facts and dynamic ones, with the newest evidence winning;
  - transitions (how a shop moved its asks in our last talks);
  - gotchas (false grade claims, broken goods);
  - and saying "no history" instead of guessing.

### 1.1 Models

| Where | Model | What it decides | What code decides instead |
|---|---|---|---|
| Shop strategy, every 15 min | Claude haiku (`meta_r3.py`) | which retail playbook to lean on and which number to A/B test next; ask and floor as shares of list price, separately for food (with a freshness premium) and goods, minimum margin, concession step, food clearance, warranty hours, cash reserve, stock cap, which goods and food to stock, depth, price spread, best-seller depth; it sees settled sales, revenue and the market's settled prices by kind | bounds and a largest step per cycle for every number; floor ≥ cost + 2% for a fresh unit, lower only by named rules (food near its date down to cost × clear_frac; goods past goods_age_days down to cost + aged_margin; the last 24 h down to cost, the last final_hours down to cost × final_frac, since stock left at the end is lost); when fewer than 60% of a busy window's receipts settle and no warranty is offered, code tries a 2 h warranty on grade-A goods; an A/B test's winner is applied by code, not chosen by the model; an unusable answer keeps the current strategy |
| Shop, each haggle turn | none (code) | — | `seller_r3.py`: counter moves `step` toward the offer, never under the floor; accept at or above the floor after two offers or at the midpoint; while an A/B test runs, each negotiation draws one arm and keeps it. No model per turn, so a busy market does not queue behind `claude -p` |
| Buyer, each order | Claude haiku (`buyer_r3.py` via `buyer.py`) | each offer in the haggle, with a one-line reason (the ReAct trace) | which shop and SKU (expected surplus), bans (false grade claims, broken goods without warranty), cap = min(budget, 0.9 × list), accept policy for the kit |
| Ideas | Claude sonnet (`meta_explore.py`, from week 7) | proposals only | everything |

All Claude calls go through `claude -p` with no tools, no settings, no session persistence, on the subscription.

### 1.2 Context

How past deals and reputation reach the next decision:

| Evidence | Kept in | Read by | Decision it changes |
|---|---|---|---|
| A shop lied about a grade, or its goods broke without warranty | `memory.jsonl` (our buyer's raw lines) | `buyer_r3.shop_record` on every order | that shop is banned (2 lies, or 1 in its first 3 deals, or 2 breakages) |
| What a shop took from us, and how its asks moved in our last talks | `memory.jsonl` | `shop_record` → the haggle prompt and the expected price | which shop is tried first, where our opening offer starts |
| What every shop settled for with anyone, and whether its claims were true | the market's ledger (settle entries, last 6 h) | `buyer_r3.ledger_claims` | expected price at shops we never paid; liars dropped before we meet them |
| How each strategy version did (settled sales, revenue, margin, profit, stock) | `logs/strategies_r3.jsonl` | the meta-harness, every 15 min | the next ask, floor, step, warranty, stock policy |
| Each negotiation's offers and outcome | `logs/talks_r3.jsonl` | `simulate_r3` → the meta-harness | which playbook to lean on, which number to A/B test |
| Margin per negotiation under two values at the same hour | `logs/ab_r3.jsonl` | `ab_r3.winner` → code | the winning value is written into the strategy |
| Our stars and rank among shops and players | the market's board | `meta_r3.standing`, `rank_r3` | where the meta-harness trades margin for sales or stars |
| Orders our buyer gets, requests our shop gets | `logs/demand_r3.jsonl` | `restock_r3` via `demand_r3.signals` | which categories and SKUs are bought, at what price point |

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
  sees the last 30, which are kept short:
  - the newest 6 whole;
  - older ones only as what changed and the key results (about a third of the size).

  A version's outcome is the measurement stored at the next decision, so nothing is re-measured.
- **Hidden demand** (`demand_r3.py`, `logs/demand_r3.jsonl`). Round 3 orders on the ledger hide their item and
  budget. Two signals reach only our agents:
  - every order our buyer receives: its category, and the middle of its acceptable price band as the hidden
    reference price;
  - every request to our shop, a miss counting double.

  Both decay with a 48-hour half-life and steer the restock's categories, SKUs and price points.
- **The goal itself is context** (`rank_r3.py`). The rubric grades our percentile on the board's Players table
  (shop ALL + buyer ALL) when the round ends. The meta-harness reads that table each cycle: our rank, the leader's
  gap, the instructor's agent as a floor, and which part has the most to gain. Until the board fills the table, the
  same numbers are recomputed from its shop and buyer tables.
- **Defence against context bombs.** Since Round 3, agents post without being asked, and other agents' text reaches
  our prompts. That text is clipped before it does:
  - control characters stripped (`harness.clip`);
  - a shop's reply cut to 300 characters;
  - a buyer's message to 2,000, and never quoted;
  - any prompt over the cap refused rather than sent.

  Forum "wanted" posts count once per author, at most 3, and not when they name many categories
  (`test_restock_r3.py`).
- **Kit files as the shop's eyes:** `inventory.json` (balance, units with cost, grade and dates), `catalog.json`,
  `demand.json` (categories only; the market publishes no demand weights).

### 1.3 Tools

**What is a tool here.** Each shop publishes `/.well-known/acp.json`. Our copy of the kit turns every entry in it into
a tool object (`AcpTool` in `market_kit.py`):
- a name, a description and a JSON Schema input (`spec()`, in the shape model APIs take);
- a call that checks the arguments against that schema, accepts only safe path segments, and stays on the shop's own
  host.

The checkout then runs through these tools: `create`, `get`, `complete`, found by their ACP name or, failing that, by
method and path (`pick_tool`).

**Code, not a model, calls them.** That is on purpose: a payment must never go out twice or above the mandate.
- Before a session exists, a failure falls back to the kit's fixed checkout.
- After a session exists, the fixed code may send one `complete` on that same session, at most.
- Once a `complete` has been sent, nothing is sent again.

A model takes part only before the checkout, in the haggle that produces the receipt being paid. Our own shop's
`acp.json` describes each input as JSON Schema (`AcpShop.card`), so other students' buyers can make tools from it the
same way.

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
| Seller | a model at every turn; ships the unit that expires first; no quality talk, no warranty; never under cost | code prices from a strategy the meta-harness rewrites; honest grade claim (none within an hour of a grade line, where the grade could change before settle), the market's certificate; warranty only when the meta-harness sets one (0 at the start, since a refund costs the whole price and the break rate is unknown); near-date food cleared under cost (a spoiled unit loses all of its cost) |
| Stock | a few random SKUs | one unit per category near its median price first (a buyer only sees shops that hold the ordered category); where settled deals show, depth plus a cheaper and a dearer SKU (orders take SKUs at 0.5-1.5x a hidden reference price); the SKUs the ledger keeps settling, bought by themselves; categories that buyers ask for in forum "wanted" posts first; cash reserve and stock cap; no buying in the last 36 h |
| Buyer | picks and haggles | expected-surplus choice over (shop, SKU), memory of raw evidence, bans for false claims and unwarranted breakages, accept policy (certificate, shelf life, grade) checked by the kit before paying |
| Checkout | fixed code; inputs described as short strings | tools made from each shop's `acp.json`, fixed code only as a fallback; our card in JSON Schema |
| Forum | none | facts from our settled deals with ledger refs, at most one post in 5 minutes |
| Learning | none | the meta-harness over strategy versions; an A/B test inside the shop that holds the hour fixed; replays of our own negotiations under real retailers' playbooks to choose what to test |
| Demand | `demand.json` categories only | hidden demand estimated from the orders our buyer receives and the requests our shop gets |
| Goal | none | the board's Players table read every cycle: first place, the instructor's agent as a floor |

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
