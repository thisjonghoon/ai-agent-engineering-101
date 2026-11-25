# The shop's screens: one look

Every screen of the shop (the chat, 현황, the Tailscale dashboard, and any screen added later) uses `app/ui.css`.
The look is webtoon-review-board's design system with Hermes orange as its one accent; the frame is the mini app's.

## Rules
- **One accent.** Hermes orange `#F37021` with black text on it (white on orange is 2.9:1). Orange text on white is
  the darker `--accent-ink`. In the chat (11/24, the owner's choices): the owner's bubble is the soft orange with ink text,
  Claude's is `--bubble-strong` `#B4490C` with white text (5.39:1) and signs "by Claude" inside, the agent's is grey on
  the left; no name labels above bubbles; a reply's quote (`>` or an old `↪`) sits in a small tinted box
  above the owner's words; the kit's English notices show as centred Korean system lines ("2분 안에 답하지 않았어요." and "메시지는 그대로 있으니…", one sentence a line); owner and agent bubbles carry a 1 px `--line-strong` edge; a change of
  speaker adds 12 px. A reply quote starts with `>`, not `↪`, which
  iOS draws as an emoji. Red (`--danger`) is for errors, losses and STOP only.
- **Times and dates in the chat** (11/25, the owner's Telegram as the model). Every bubble carries its 24-hour time at
  the bottom right (`.stamp.time`, D2Coding 12 px, the bubble's own ink at .72; in Claude's bubble at full ink after
  "by Claude", now also full ink, 5.39:1). The time sits in the corner and a hidden 48 px gap at the end of the words keeps
  it on the last line when there is room, as Telegram does. A date pill (`.day`: 오늘, 어제, 11월 24일 (화); the year when it is not this year) marks each
  new day, and while the person scrolls the date of the topmost message floats at the top (`#daytip`, a zero-height sticky
  strip so nothing moves, a tinted pill with `--line-strong` edge that stands apart from bubbles in dark; it stays while
  the finger is down or the list still moves and fades 3 s after both stop (owner, 11/25), not on the redraw's own jump to the end, `aria-hidden`). Copy and reply leave the time out.
- **Type.** Pretendard (variable, dynamic subset, swap) for every text role since 11/24: chosen over Wanted Sans, SUIT,
  Noto Sans KR, IBM Plex Sans KR, Gmarket Sans and Nanum Gothic by a specimen review (Hangul and Latin even in colour,
  bold holds in dark mode) and measurement (215 KB / 8 files like Nanum's 207 KB / 19; narrowest Hangul; Gmarket
  1.24 MB and SUIT 626 KB without swap were out). Sizes: name 15/700, panel titles 16/700, switch 13/700 (600
  idle), labels and system lines 12/400 at 1.45, chat 15/400 at 1.6, quotes 12/400 at 1.5, rank line 15/700 + 13/500. Every number (money, counts, times, ids) is D2Coding: `.num`, `.value`, `.big`,
  `.time`, `.mono`. D2Coding is a 12 KB subset served from `app/` (digits, Latin, punctuation; `font-display:swap`;
  licence `app/D2Coding-OFL.txt`); Hangul in a number cell falls back to Pretendard.
- **Frame.** A thin `header`: `.avatar` (the shop's initial), `.who` with the name and a `.status` dot, then the screen
  switch `.seg` (the current screen's link has `aria-current="page"`). No activity sheet since 11/24: 현황
  carries the moves, the forged tools and the tools this app gives (`app_say`, each `miniapp.offer`), and the kit's credit. The orange 3 px line
  under the header is the only decoration.
- **Body.** A screen other than the chat is `body.screen` with `main.page`: panels (`.panel`, `.panel.accent` for the
  one number that matters most), a two-column `.stats` grid that stays two columns on a phone, lists (`.list`), and
  key-value tables (`.kv`). Section titles are `.panel h2`; small labels are `.label` and `.sub`.
- **States.** A live connection is an orange status dot (`--ok`; the owner found grey odd for 시장에서 거래 중). An alert
  is a solid orange chip (`.tag.alert`), so the two stay apart by shape; a stop a
  solid red one (`.tag.stop`), neutral `.tag`/`.tag.ok` grey; `.up`/`.down` for gains and losses. A stale or failed
  refresh turns the dot red and says so (`body.stale`). Alerts read in Korean with what to do.
- **Charts.** One 2px line in `--chart` (the accent's step that passes dataviz's lightness and 3:1 checks: light
  `#D9601A`, dark `#E8682A`), a 10% wash, a dashed reference at the start capital, the range labelled at the left, an
  8px end dot and a touch/hover readout. No hero stripe on the left of a panel: the hero has a full orange outline.
- **Phone first.** 390 px wide with no sideways scroll (`overflow-x:clip`), light and dark from the same tokens, motion
  off under `prefers-reduced-motion`. When the keyboard opens, the chat follows the visible area's height and its offset
  (`--app-h`, `--app-y` from `visualViewport`), so the header stays on top and the message box sits on the keyboard
  (11/25, the owner's iPad: the offset alone had pushed the header off and left a gap).
- **Wide screens** (iPad landscape, PC; 11/24 after the owner's iPad photos). Every header is `header.wide`, so it sits at
  the same place on chat and 현황 and switching does not jump. The chat's talk (`#log`, 728 px) and input share one
  centred column with no side rules. 현황 below the top row (the owner's layout, 11/24): 감시 경보 | 만든 도구, then 최근 행동
  tall on the left (6 moves; 3 on a phone, `.wide-only`/`.narrow-only`, one 더보기 pinned to the panel's bottom) beside
  스스로 보낸 메시지 over Claude의 질문 (`.lower` grid areas); below 900 px one column in DOM order.
- **전체 보기** (11/24, owner). A long list shows its first rows and `전체 보기 · N` (N = all). The script opens
  `dialog#full`: the whole screen on phones and tablets (landscape keeps the chat's 760 px column), a centred 760 px
  sheet over `--scrim` on the web (≥1280 px with a mouse); its head sits exactly where the page header is (same edges, padding, 65 px, ✕ where the switch is, with the switch's edge); ✕ 44 px, Esc, or a click outside the web sheet closes it
  and focus returns to the summary; every row shows unfolded there; it is rebuilt on each 30 s refresh.
- **Rows unfold on a tap** (11/24, owner): 감시 경보, 최근 행동, 스스로 보낸 메시지 and Claude의 질문 rows are all
  `details.move`: a two-line muted preview (`aria-hidden`, the whole text follows), a tap shows the whole text in the
  brighter `--text-soft` (a question in `--text` over its answer, an alert's English original as a small `.orig` line).
  A chevron marks only rows with more to show (`.can`, set by the script); the row's top padding is part of the
  tap area (≥ 52 px). Without the script the
  `<details>` unfold. 만든 도구 shows three rows of chips (90 px) and its 전체 보기 only when they overflow.
- **Fixed header** (11/24, owner). On 현황 the body is a 100dvh column and only `#pane` scrolls (overscroll contained),
  so a pull past either end bounces the content, never the header. Targets: `.btn` 40 px, `.seg a` 36 px, send 40 px.
- **Reviewed 11/24** with impeccable (critique and audit), hallmark (audit) and dataviz; findings kept as false
  positives: the avatar initial read as an eyebrow, the typing dots (a real state), no Hallmark stamp (not a
  Hallmark build).

## Every design change
Run the three checks each time (the owner's rule, 11/24), then look at 390 px in light and dark:
- impeccable: critique (two isolated assessments: design review, and the detector with measurements) and audit
- hallmark: `audit` (sloplint `--scope app`)
- dataviz: whenever a chart or stat tile changes, validate its colours with `validate_palette.js`
Report what was fixed and which findings were left as false positives, with the reason.

## A new screen
1. Write it as `app/<name>.html` (or a page the dashboard writes there), link `/ui.css`, and use the parts above.
2. Add its link to the `.seg` of every screen.
3. Check it at 390 px in light and dark with the stub `miniapp.js` before it goes live (the kit serves `app/` straight
   from disk, so a change is live at once).
4. Keep `<script src="/miniapp.js"></script>` in `index.html` (ROUND4.md: the one line the kit needs).
