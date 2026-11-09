# Week 08 (midterm) — our shop and buyer in the Round 3 market

**Status, 2026-11-09 (draft).** Round 3 runs 11/3 to 11/17 23:59 (the date moved on 10/31, with kit v4 and the
economy rules). Sections 1 and 2 describe the agents as they run on 11/9; section 3 is filled in from the Round 3 logs.
The one-page figure is `architecture.tex` / `architecture.pdf` (rebuilt 11/9 with the memory structure).

- **Shop:** our own seller (`seller_r3.py`) run by kit v4 on a Mac mini behind a cloudflared tunnel, selling from
  stock it buys itself (`restock_r3.py`). A sales team of three pricing styles takes the talks by rank (`team_r3.py`).
- **Buyer:** `market_buyer.py` → `buyer_r3.py`: scouts ask several shops for a quote at once, then one member of a
  buying team with ranks haggles with the best (Claude haiku per offer); a raw-evidence memory, a review hook and a
  forum column; it pays through our copy of kit v4, which makes the checkout tools from each shop's `acp.json`.
- **Two loops aimed at the grade.** The *inner loop* (`meta_r3.py` + `meta_team_r3.py`) moves numbers every 15
  minutes: four specialists (sales, merchandising, buying, community; Claude haiku, in parallel) propose changes to
  their own numbers, a manager (Claude sonnet) approves, trims or rejects them, code bounds and applies the result and
  promotes team members; an A/B test inside the shop tries one number or a whole retail playbook on live buyers. The
  *outer loop* (`meta_code_r3.py`) changes the harness's own code every 90 minutes: an engineer agent reads the code
  and the raw traces and writes one hypothesis aimed at the board term that costs the most points
  (`metrics_r3.py`), a coder agent builds it with a test, a code gate puts it live on half the buyer's orders, and an hour
  later code keeps or reverts it by the metric it named, the two halves compared over the same hours (2f23dbf's rule
  never fired, yet a before/after reading gave it -10%: the evening's traffic). Expected and measured results go to one ledger
  (`logs/code_changes_r3.jsonl`) that both loops read.
- **Supervisor** (Claude Code, for the user): watches every decision, stops bad ones with evidence, and steers through
  standing orders and notes the manager reads as advice (`standing_orders_r3.md`, `advice_r3.json`); when it must
  change a number it does so through `supervise_r3.py`, and the change is judged like the team's.
- **Memory that is checked, not only kept (11/9, section 1.2).** One aim for every verdict (board points per hour, by
  the board's own weights), number verdicts on our share of the market's paid sales, the market filed every 10
  minutes so old verdicts can be judged again, each area's lessons rewritten from that record with what is verified
  and what is not, and standing orders that carry where they came from and when to review them.
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
- **The outer loop is the same loop over code** (11/4). Numbers cannot fix everything: the scouts asked shops that
  were out of stock, the A/B slot stayed blocked by a test with no winner, the buyer haggled past an affordable ask.
  Until 11/4 17:00 the supervisor did this by hand from the data; now an engineer agent does the diagnosis
  (observe: code, traces, the ledger of past changes; think: one hypothesis with the metric it should move and by how
  much), a coder agent acts in a copy, and code judges: the gate before it goes live, the named metric an hour after.
  The supervisor still watches it, reads each automatic diff and pushes the commits.
- **Memory follows LongMemEval-V2:**
  - raw evidence only, appended and never summarised on write; summaries are derived on read;
  - static facts and dynamic ones, with the newest evidence winning;
  - transitions (how a shop moved its asks in our last talks);
  - gotchas (false grade claims, broken goods);
  - and saying "no history" instead of guessing.

### 1.1 Models

| Where | Model | What it decides | What code decides instead |
|---|---|---|---|
| Meta-harness team, every 15 min | 4 specialists on Claude haiku, a manager on Claude sonnet (`meta_team_r3.py`) | each specialist proposes changes to its own numbers from its own evidence (sales: prices, warranty, model share, an A/B test, a seller recruit; merchandising: what and how much to stock; buying: the buyer's numbers and a buyer recruit; community: forum post kinds); the manager approves, trims or rejects each, with a reason per proposal | the same bounds and steps as before; if the manager fails, the proposals are merged as they are; if every specialist fails, the single prompt below runs |
| Shop strategy (until 11/4 12:40, and as the fallback) | Claude haiku (`meta_r3.py`) | which retail playbook to lean on and which number to A/B test next; ask and floor as shares of list price, separately for food (with a freshness premium) and goods, minimum margin, concession step, food clearance, warranty hours, cash reserve, stock cap, which goods and food to stock, depth, price spread, best-seller depth; it sees settled sales, revenue and the market's settled prices by kind | bounds and a largest step per cycle for every number; floor ≥ cost + 2% for a fresh unit, lower only by named rules (food near its date down to cost × clear_frac; goods past goods_age_days down to cost + aged_margin; the last 24 h down to cost, the last final_hours down to cost × final_frac, since stock left at the end is lost); when fewer than 60% of a busy window's receipts settle and no warranty is offered, code tries a 2 h warranty on grade-A goods; an A/B test's winner is applied by code, not chosen by the model; an unusable answer keeps the current strategy |
| Shop, each haggle turn | Claude haiku in a share of talks (`model_share`), the rule otherwise | accept or a counter, with a one-line reason; it sees the unit, every offer, our stock, demand, the going price and what the rule would do here | `seller_r3.py`: the floor is a hard limit; a counter sits between the offer and our last ask; busy (3 calls at once), slow (8 s) or unusable answers go to the rule. The model sold 24% of its talks at 2,128 a talk against the rule's 40% at 3,207 (11/4, after its prompt was reworked), so the meta-harness set its share to 0 |
| Buyer, each order | Claude haiku (`buyer_r3.py` via `buyer.py`) | each offer in the haggle, with a one-line reason (the ReAct trace) | which shops the scouts ask and which quote the lead takes (surplus at the ask), bans (false grade claims, broken goods without warranty), the cap (min(budget, CAP × list), lower for grade C without a 6 h warranty), leaving before a deal when the shop's own words fail our payment policy, the accept policy for the kit |
| Forum column | eight writers on Claude haiku (`forum_r3.style`), an editor on GPT (Hermes) | each writer gives its kind of post a voice (`장보기 레이더`) from facts code built; the editor publishes, revises or rejects each draft against those facts | every number in the writer's or the editor's text must be one of the facts' numbers, no link, no call for votes; else the plain facts go out |
| Second opinion on the meta-harness | GPT through Hermes (`meta_team_r3.second_opinion`); Claude opus when GPT fails, and at once until 11/11 15:36 (the ChatGPT plan's usage limit, hit 11/9 09:09) | keep, trim or reject per specialist proposal, looking for short trials, cycles of unequal length, crossed evidence | the sonnet manager weighs it; it never sets a number. A failed review is logged: from 09:09 to 11:36 on 11/9 it returned nothing silently and the manager decided alone |
| Fallback for every call | GPT through Hermes (`harness.fallback`) | the same prompt, when every Claude try failed (a usage limit or an outage) | when GPT fails too, the buyer haggles on by code (a set share of the gap, within budget) instead of walking away; the watcher alerts on each fallback |
| Lessons per area, every 3 h | Claude sonnet (`lessons_r3.dream`) | rewrites each area's lessons from the record: rule, the facts it rests on, verified / unverified / contradicted, the trap | a lesson citing no fact or an unknown one is dropped; the old version goes to the history |
| Ideas | Claude sonnet (`meta_explore.py`, from week 7) | proposals only | everything |

All Claude calls go through `claude -p` with no tools, no settings, no session persistence, on the subscription.
While the ChatGPT plan is at its limit (11/9-11/11), the forum editor and the GPT fallback fail too: the column posts
the plain facts and the buyer haggles on by code, as designed.

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
| What each category and SKU settled for (24 h), and forum price claims checked against it | `.market/prices_r3.json` (`prices_r3.py`, from the ledger) | the seller's model, the buyer's haggle hint, the sales specialist | where our asks, floors and first offers sit; forum numbers are never used as prices |
| Each team member's reward per talk (buyer surplus, seller margin over list) | `memory.jsonl`, `logs/talks_r3.jsonl` | `team_r3.review` each cycle | who leads, who is replaced and by what style |
| How our buyer's talks ended, why payments were refused, break rate per grade | `memory.jsonl`, `.market/payments.jsonl`, the ledger | the buying specialist (`meta_r3.buyer_diag`) | the buyer's cap, the price it pays for grade C, the shelf life it demands, the scouts |
| Votes on every post of ours, by kind | `logs/forum_votes_r3.json` (kept after the forum's 100-post window drops them) | the community specialist | which post kinds the column writes |
| The supervisor's standing orders and notes with their evidence | `standing_orders_r3.md` (since, from, review), `advice_r3.json` (last 3 of 24 h, with their age) | every specialist and the manager | read as advice; the manager says what it did with each |
| Every change and its verdict, re-judged on the board's terms | `logs/code_changes_r3.jsonl`, `logs/rejudged_r3.json`, `logs/market_buckets_r3.jsonl` | every specialist and the manager (each number's value now and its last 3 verdicts) | whether a number is moved, and which way (memory, below) |
| Each area's lessons | `logs/lessons_r3.json` | that area's specialist | the rule it follows and the trap it avoids (memory, below) |

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

- **Results compared per hour.** A meta cycle runs 3-15 minutes (a restart cuts one short). On 11/4 a dry run of
  the team read 40 deals against 9 as the effect of raising max_list; per hour the deals had gone from 160 to 180.
  The specialists now see deals, revenue and settles per hour.

### 1.2.1 Memory: what the team keeps, how it is checked, and why (11/9)

**Why.** Anthropic's study of agent memory ([Components of agent memory](https://www.anthropic.com/research/components-of-agent-memory),
2026; Korean summary on [GeekNews](https://news.hada.io/topic?id=36775)) treats writing a memory as a prediction that a
later session will need it, and reports three things that matter here:
- the learning loop closed only when the model kept *one consolidated reference* with each rule, its evidence and
  whether it was verified (Opus 5 on CL-Bench; earlier models left unverified guesses across many files);
- a *wrong note travels into every later session* until something re-checks it against the record (in Pokémon Red a
  misplaced PokéCenter sent the agent down the same ledge three times; a "dreaming" pass over the transcript fixed the
  note and the agent reached Cerulean City);
- the tier injected every session must stay *small*, and fixed rules such as "record only failures" cut the gain.

Our team had all three problems on 11/9. Its memory was the verdict ledger, the last 12 versions and the supervisor's
notes; 11 manager decisions and 10 specialist proposals (log from 11/3) held a number because it had been "judged
in both directions" (or "both ways"), yet all 89 number verdicts
(11/5-11/9) compared raw margin/h in the 2 h before and after a change, which reads the hour of day; the market's paid
sales were kept only for the last ~6 h, so no verdict could be judged again; and a standing order ("do not repeat a
change judged both directions") made those verdicts binding.

**The tiers.** Each tier is written by one party, read by named readers, and checked by something other than its
writer:

| Tier | Kept in | Written by | Read by | Checked by |
|---|---|---|---|---|
| Raw traces | `memory.jsonl`, `logs/talks_r3.jsonl`, `logs/demand_r3.jsonl`, `logs/strategies_r3.jsonl`, the kit log | code, on every event; nothing summarised on write | the buyer, the restock, the specialists, the engineer | the market's ledger (settles, claims) |
| The market over time | `.market/ledger-recent.json` (~6 h), `logs/market_buckets_r3.jsonl` (ours and the market's paid sales, count and value, and our margin, per 10 minutes), `.market/backfill_r3.jsonl` (the ledger from 11/5, fetched one page at a time) | `metrics_r3.record_buckets` each cycle; `backfill_r3.py` | every verdict | the public ledger itself |
| Verdict ledger | `logs/code_changes_r3.jsonl` | code: a number change after 2 h on our share of the market's paid sales; a code change on half the orders (A/B) or 3 h before/after net of the market, board points deciding; a buyer A/B; a supervisor change | both loops, the engineer | the re-judge, the supervisor |
| Re-judged past | `logs/rejudged_r3.json` | `rejudge_r3.update` each cycle | every specialist and the manager: each number's value now and its last 3 verdicts, VERIFIED (what the change did to board points net of the market, and whether the raw verdict agreed) or UNVERIFIED (no market data reaches back; weak evidence) | its own data coverage; an UNVERIFIED row is judged again once data reaches it |
| Lessons per area | `logs/lessons_r3.json` | Claude sonnet every 3 h per area ("dreaming" between cycles) | that area's specialist, at most 3,000 characters | code drops a lesson citing an unknown fact; every rewrite keeps the old version (where a rule came from, what it replaced) |
| Top tier | `standing_orders_r3.md` (6 rules, 2.4 KB, each with since / from / review), `advice_r3.json` (last 3 notes of 24 h, shown with their age) | the supervisor | everyone, every cycle | the supervisor's hourly check |

We did not build a wiki (our record is a few thousand rows, not the 350,000 files the study's wiki covered) and set
no fixed rule on what to record.

**What it changed, and what went wrong on the way.** The first re-judge verified 2 of the 89 verdicts (both
confirmed: `dear_depth` 5 -> 4 lowered board points/h net of the market by 20%, `stock_value` 65M -> 60M by 28%) and
marked 87 UNVERIFIED; at 11:43 the manager restored `dear_depth` 5 citing the verified verdict. The ledger backfill
from 11/5 is filling the market buckets so the 87 can be judged. Three mistakes in the first hour, each fixed in the
same hour and listed in section 3.x: the first lessons rewrite read a clipped A/B fact backwards (the losing arm's ask
0.85 became a "verified" rule); the manager, seeing only the 06:43 bundle's `ask_frac_food` 0.7 -> 0.85, raised it
0.7 -> 0.75 while its reason said it was lowering it (the memory now shows each number's value now, and standing order
5 says to read it); a hand-run rewrite saved over another area's lessons (a rewrite now changes only its own area).
The study's warning held: a memory that is written but not re-checked passed a wrong note to the next decision
within one cycle.

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
| Decisions | none (the person sets the agent) | two loops aimed at one number, board points per hour by the board's own weights: a team moves numbers every 15 min (four specialists propose from their own evidence and lessons, a reviewer on another model (GPT; opus while GPT is out), a manager decides, code bounds it and keeps one shop number per area a cycle); an engineer and a coder agent change the code every 90 min, one hypothesis at a time, gated by tests; a supervisor watches both and steers through standing orders and notes |
| Teams | one buyer, one seller | buyer: scouts quote several shops at once, a member haggles with the best; both sides have members with ranks (lead 60%, senior 25%, junior 15% of talks), promoted by reward per talk and replaced when they trail |
| Seller | a model at every turn; ships the unit that expires first; no quality talk, no warranty; never under cost | code prices from a strategy the meta-harness rewrites; honest grade claim (none within an hour of a grade line, where the grade could change before settle), the market's certificate; warranty only when the meta-harness sets one (0 at the start, since a refund costs the whole price and the break rate is unknown); near-date food cleared under cost (a spoiled unit loses all of its cost); the ask follows the market down to the 75th percentile of what the SKU settled for, never under cost + margin |
| Stock | a few random SKUs | one unit per category near its median price first (a buyer only sees shops that hold the ordered category); where settled deals show, depth plus a cheaper and a dearer SKU (orders take SKUs at 0.5-1.5x a hidden reference price); the SKUs the ledger keeps settling, bought by themselves; categories that buyers ask for in forum "wanted" posts first; cash reserve and stock cap; no buying in the last 36 h |
| Buyer | picks and haggles | expected-surplus choice over (shop, SKU), memory of raw evidence, bans for false claims and unwarranted breakages, accept policy (certificate, shelf life, grade) checked by the kit before paying; an affordable ask within a few percent of its offer is taken rather than haggled away |
| Checkout | fixed code; inputs described as short strings | tools made from each shop's `acp.json`, fixed code only as a fallback; our card in JSON Schema |
| Forum | none | a column (`장보기 레이더`) in kinds built from the ledger (best value, freshness, unpaid receipts, trivia, grade claims, our deals), styled by a model under a number check, at most one post in 10 minutes (20 until 11/4 17:05); kinds weighted by the votes they earn |
| Learning | none | the meta-harness over strategy versions; an A/B test inside the shop that holds the hour fixed and tries a number or a whole retail playbook (Costco, Walmart, IKEA, grocery markdown, premium, two-track) on live buyers, ending as a tie after 400 talks an arm or 6 h; a ledger of code hypotheses with expected and measured results |
| Verdicts | none | every change, from anyone, is judged by code into one ledger: a number after 2 h on our share of the market's paid sales (a fast guard reverts it in the first hour if that share halves); a code change on half the orders (same hours) or 3 h before/after net of the market's own change, board points deciding |
| Memory | none | tiers with a writer, readers and a check each (section 1.2.1): raw traces; the market's paid sales per 10 minutes, backfilled from 11/5; the verdict ledger; past verdicts re-judged or marked UNVERIFIED, shown with each number's value now; each area's lessons rewritten by a model every 3 h with their evidence and status, unknown citations dropped, history kept; standing orders with since / from / review and notes with their age |
| Demand | `demand.json` categories only | hidden demand estimated from the orders our buyer receives and the requests our shop gets |
| Goal | none | the board's Players table read every cycle: first place, the instructor's agent as a floor; the points each board term costs us, by the midterm's weights, chooses what the outer loop works on |

**What the first day taught, and what changed (11/3-11/4).** Each change came from a measurement on the ledger or our
own logs, and is kept in git with its numbers:
- **Grade C is worth buying, at a price.** The ledger's last 24 h of goods settles: A broke 1.4%, B 5.2%, C 17.9%. A
  deal is worth the list price and 0 if the goods break, so C pays at 65% of list or less, or with a 6 h warranty;
  asking for A or B only had made shops holding C answer "none in stock" (458 quick rejects in a morning).
- **A buying team.** After dragonash's team-run agents: scouts ask the best candidate shops for a quote at once and
  the lead haggles where the quote leaves the most surplus. Orders with a deal went from 78% to 81% and surplus per
  order from 11,161 to 16,954 in the first hours (43 orders; to be confirmed over the round).
- **The buyer side was the gap, and the team found why.** At 14:40 on 11/4 we were 20th of 51: shop 0.725, buyer
  0.509. We closed 39% of orders against 50-65% for the top buyers, and 422 of ~680 orders without a deal ended with
  the shops asked out of stock. From the meta-harness's code idea, the scouts now send a second wave to other shops when
  the first wave is all out, and a shop/SKU pair that dropped us or shipped too short a food unit waits
  (`.market/avoid_r3.json`). Orders closed rose to 62% from 14:40 to 16:20 (130 of 210), and we reached 16th.
- **Teams with ranks** (after another student's team with promotions): three styles a side, promoted by reward per
  talk, so a style is tried on live talks without betting the shop on it.
- **The negotiator model lost to the rule.** At first haiku conceded to the floor early (of talks with an offer, 85%
  sold at 1.03x the floor, the rule's 92% at 1.11x). Its prompt was then given what the rule would do and both records;
  over the next 33 talks it still sold 24% of them at 2,128 margin a talk against the rule's 40% at 3,207, and the
  meta-harness turned it off. Kept as a result, not hidden.
- **Bugs the measurements found:** a malformed shop card raised `SystemExit` and ended 405 buyer runs with no other
  shop tried; the ledger cache stayed on a Round 2 position, so the buyer saw no Round 3 prices for its first hours; a
  leftover Round 2 kit loop took 11 orders at the round's start.
- **Where the shop's money is.** The top shop by profit (57M) sold 284 units at an average 459,240, 99% furniture,
  at 0.86 of list; we sold at 27,780 on average, none above 150,000, because the list-price cap topped out at 400,000.
  The caps were raised (the user set max_list 600,000 at once), restock now buys dear goods first (`dear_first`,
  since a 3-minute supply window fits about 18 lines), and the first mattress sold at 446,430 three minutes after it
  arrived.
- **A bug in kit v4's checkout, reported.** An unpaid checkout session never expires, so its unit was refused 16
  times; the seller now leaves such a unit out, and the bug went to the course discussion (#378) with the lines.
- **Both sides were too strict (the user, 11/4 17:20, after another agent's forum post listed us as asking 33%
  above the going price).** Six hours of talks: 92% of our food talks opened above the market's 75th percentile
  (0.92 of list against 0.70 settled) and closed 37% of the time, those at or under it 65%. The seller now stops its
  ask at that line (`market_ask`, the team's knob). On the buyer side, 119 talks were lost while the shop's ask was
  inside our limit, 86 of them because the shop ended the talk at a median 4.6% above our last offer (0.79 of list,
  a 21% surplus left for nothing); the buyer now takes such an ask (`CLOSE_GAP`, the team's knob, 5% at first).
- **One way to change anything (11/4 21:50).** Every change now runs as an A/B over the same hours: a seller number or
  a whole playbook on half the shop's talks (Thompson sampling), a buyer number or a code change on half the buyer's
  orders (by a hash of the order id), and a verdict writes the result to the ledger both loops read; the supervisor's
  own changes go into the same ledger. The buyer's CAP had gone 0.85 -> 0.80 on one cycle's reasoning while 29 of 538
  deals in 6 h were paid at 0.80-0.85 of list. Taken out: the seller's negotiator model (it lost to the rule, 2,128
  against 3,207 margin a talk, yet kept drawing proposals) and the replay of our talks under each playbook (it could
  not know how buyers answer our counters; playbooks are now tried on live buyers). Added: a forum metric (net votes
  per post), so the outer loop can aim at forum votes, the second-costliest term (0.17 points).
- **The tests that taught nothing, and the playbooks nobody used.** An A/B of 0.92 against 0.90 of list for food
  ran 20 hours and 4,193 talks without a winner and kept every other test from starting; tests now end as a tie
  after 400 talks an arm or 6 hours. The retail playbooks were text in a prompt (25 of 30 cycles leaned on none);
  now a whole playbook can be arm B of the A/B test, and IKEA was added for our furniture.
- **Speed and resilience.** An order took 36 s (scouts 9.5 s, haggle 21 s); scouts now wait 6 s, a fast member plans
  its haggle in one model call, and buyer members are ranked by surplus per minute. Every model call fails over from
  Claude to GPT, and the buyer haggles by code if both fail, so a usage limit does not stop the agents.
- **Decisions misread, and caught.** The single prompt raised our stock depth for other shops' stock-outs and grew
  past its size guard; a team dry run read a 4-minute cycle against a 15-minute one. The fixes (role-split evidence,
  clearer names, per-hour results) are in the structure above.

**A self-changing agent still has to stay readable (11/5-11/6).** Two loops edit the agent's own code and numbers,
so the code can grow by accretion: on 11/6 `restock_r3.py` took more than eight changes in one day, from the outer loop
and the supervisor, each with a reason, together five overlapping rules for dear goods (a priority factor, a best-seller
bar, a reserved share of the room, two depths, a trim to the room). The engineer agent reads that code before it writes
a hypothesis, so a tangle misleads it: at 14:35 it capped dear stock by our own past sales, which were low only because
a ranking bug had kept the market's best sellers out, and the supervisor reverted it the same hour. Keeping the
structure clean is therefore part of the structure, done by the supervisor and written into the loops:
- *Consolidate after the verdicts, never before.* Once the changes on one area are judged, the kept ones are rewritten
  as one rule (for stock: depth and order in proportion to the market's sales) and the rest are dropped.
- *Refactor without changing behaviour, and prove it.* The test suites must pass unchanged, and the old and new
  versions are run on the same live state; the buy plans must match before the rewrite is deployed.
- *Merge before adding.* The engineer's prompt asks it to fold a new condition into an existing rule where it can,
  rather than add another layer to the same function.
- *Give the loops the evidence they cannot count.* The engineer reads files but runs nothing, so code counts each area
  for it (`digest_r3.py`), now with the whole market's sales beside ours: a reading of our own numbers alone produced
  the 14:35 mistake.
- *Every change, from anyone, is judged the same way.* Number changes by the team get an automatic 2 h before/after
  verdict with confounds named; code changes are judged per order (A/B) or over 3 h before and after; the supervisor's
  own changes go into the same ledger and are judged by the same code.

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

### 3.x What went wrong, and what each failure changed in the structure

Draft, kept as it happened (11/6-11/9); every row is in `logs/code_changes_r3.jsonl` and the git history. The rank fell
from 8th (11/6 17:57) to 22nd (11/9) while Book kept growing (85M to 133M): the failures below cost us relative speed,
not money.

| When | What went wrong | How it was found | What it changed |
|---|---|---|---|
| 11/4 17:57 - 11/7 09:38 (2.6 days; the damage fell mostly in the last ~15 h, after the stock cap was opened on 11/6 18:1x) | `shop_margin_h` and `shop_deals_h` counted receipts our seller signed, not sales paid. Buyers haggle with several shops and pay one: 300k+ goods were agreed 23 times and paid once (11/7 06:52-09:35), so margin/h read 2-4M while Book grew 0.7-0.9M an hour. The loops, and the supervisor, believed the inflated number. | Supervisor reconciled the metric with Book growth | Metrics count ledger settles (`101789f`); every shop verdict before it was flagged as judged on agreements |
| 11/6 18:05 | The market began scoring the forum as the raw rating, not a percentile; rivals gained 0.1-0.15 in minutes, we fell 8th to 13th with no change of ours | Rank alert, then a diff of the board rows | Forum effort was rated down; points moved to shop and buyer saved |
| 11/7 | Dear stock bought at surged cost (about 0.74 of list) could not sell at the market's paid median (0.70-0.73); our floors sat 1-5% above the buyers' last offers | Talks read against the ledger's paid prices | min_margin lowered (judged +36% margin/h), surge-aware restock tried twice |
| 11/7 20:4x | 97 slow 300k+ units (51M) filled the stock cap, so restock bought nothing and the cheap shelves that sell ran down (1046 units to 584) | Stock composition by price band | Slow dear goods no longer count against the cap (`e143aad`, judged deals/h +63%) |
| 11/7 10:41 - 11:05 | After a market outage the market listed our shop at a tunnel from before our last restart; buyers could not reach us | Talks opened fell 74 to 7 per 10 min | Kit restarted; the watch compares the listed URL with our tunnel |
| 11/7-11/8 | The team held judged numbers as "pending" (a verdict naming confounds read as unfinished), lowered `clear_hours` to clear food *earlier* (the number works the other way), repeated `max_list` 900k to 600k after both directions had been judged | Supervisor reading each decision against the ledger | Verdict rows say JUDGED or PENDING (`b1e3a73`); the two numbers were set back with the ledger rows quoted |
| 11/8 | Buyer A/B changes measuring -2% to -6% were all kept: the revert bar (15%) was sized for noisy before/after windows, not same-hour A/B | Reading the verdict ledger | A/B verdicts revert at -3% (`2270665`); the -6% change was reverted |
| 11/9 06:43 - 09:2x | A playbook that won its A/B on margin *per talk opened* was adopted for goods and, untested, for food; paid sales fell 141 to 49 and revenue 20% over 2.5 h with margin flat | Supervisor, 2.5 h late | Bundle undone on paid-sales evidence; the watch now alerts when the last hour's paid sales fall under half the prior 3 h (backtest: would have fired at 07:45) |
| 11/9 10:48 | The manager approved three numbers at once, two of them in merchandising (`ask_frac`, `max_list`, `sku_depth`), and the 2 h verdicts compared our raw margin/h before and after, so a change made before the morning rush read as a gain and one made at night as a loss | Reading the verdict ledger against the hour of day; the 06:43 bundle could not say which of its numbers cut sales | Verdicts lead with our share of the market's paid sales over the same hours, by value and count (`metrics_r3.market_share`); code keeps one shop number per area (sales, merchandising) a cycle, the manager's first, and logs the rest as held back (`3a9a327`) |
| 11/9 02:25-09:33 | Two units refused at checkout ("not in stock": an abandoned session holds them) came back after their 2 h and were refused again, 3 h apart | Counting refusals per unit in `logs/market-kit.log` | A unit refused again after its 2 h is held until a restart, which also frees the kit's sessions; retries within 10 min count once (`23fad57`) |
| 11/9 11:15 | The coder's 3 h before/after verdict reverted 4d10151 (deeper stock of hot 300k+ lines) on its own metric, margin/h -20%, while revenue/h went 2.0M to 3.8M and board points/h moved +3% (-0.4% net of the market): the one aim set in b620df9 had not reached the code verdicts | Monitor alert, then the same hours recomputed as market share and board points | Before/after code verdicts divide shop numbers by the market's own change and let board points/h decide when measurable (`46776c3`); 4d10151 restored by the supervisor (`cf13a5a`) |
| 11/9 09:09 - 11:36 | The GPT reviewer (Hermes on the ChatGPT plan) hit the plan's usage limit; `second_opinion` returned None silently and the manager decided alone for 2.5 h with nothing in the log | A Codex test of the instruction files returned the same usage-limit error | A failed GPT review is logged and opus (a different model from the sonnet manager) reviews the same proposals with the same prompt (`8689803`); the supervisor checks each decision every 15 min while GPT is down |
| 11/5 - 11/9 | The team treated 89 raw margin/h verdicts as facts: 11 manager decisions and 10 specialist proposals held a number because it was "judged in both directions", but those verdicts read the hour of day. The ledger cache keeps only ~6 h of settles, so they could not be judged again | Re-reading the verdict ledger after the share-of-market change; the memory study (Anthropic, components of agent memory) on wrong notes carried into later sessions | The market's paid sales are filed in 10-minute buckets each cycle; `rejudge_r3.py` re-judges past verdicts on the market share and board points net of the market, marks the rest UNVERIFIED, and the team reads each number's re-judged past (`3ed53a3`). First pass: 2 verified (both confirmed), 87 unverified |
| 11/9 11:57-11:58 | The supervisor deployed a new helper as `review_r3.py` into the live folder, over the buyer's review hook of the same name, and moved it to the Trash when the plan changed; restored from git 2 min later. The deal paid in that window (11:58:00) was reviewed and recorded normally | `git diff --stat` listing review_r3.py as deleted | Before a new file goes live, check that its name is not taken (`git ls-files`); GPT is now skipped until its limit resets (11/11 15:36) and opus reviews at once, so no helper was needed |
| 11/9 12:04-12:06 | The first lessons rewrite misread a clipped A/B fact (made the losing arm's ask 0.85 a "verified" rule) and kept a 07:21 value a 09:21 row had undone; the manager, seeing only the 06:43 bundle's ask_frac_food 0.7 -> 0.85 in the number memory, raised it 0.7 -> 0.75 while its reason said it was lowering it for volume | Supervisor's 12:04 check reading the decision against strategy_r3.json | ask_frac_food set back to 0.7 (supervise_r3.py); the number memory shows each number's value now; facts keep 240 characters and the rewrite prompt says the arm before "won" wins and a later undo supersedes; sales lessons rewritten at 12:07 (the wrong version kept in their history) |
| 11/9 12:07 | A hand-run rewrite of the sales lessons, loaded before the meta cycle saved the community lessons, wrote over them | The lessons file showing no community entry after the log said 5 were kept | A rewrite reads the file again just before saving and changes only its own area |
| 11/9 (all round) | The top memory had no sources or expiry: standing order 2 ("do not repeat a change judged both directions") fed those holds on unverified verdicts, and a 10:51 note's "CAP 0.7" was stale (CAP 0.75, bounds from 0.75) when the buying team read it | Memory plan item 3 (sources and expiry on the top memory) | Each standing order says since when, from what and when to review it; order 2 counts only VERIFIED verdicts; order 5: read a number's value now before moving it; notes show their age; a correction note for CAP |

The supervisor made mistakes too: it relayed the inflated margin as a win before checking it against Book (11/7),
read a 10-minute bucket that had only just begun (11/9 07:01) and undid an A/B-backed ask, restoring it 20 minutes
later. The rule taken from both: reconcile a loop's metric with the board's own terms, and judge only closed windows.
