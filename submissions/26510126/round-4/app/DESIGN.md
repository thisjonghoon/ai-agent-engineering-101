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
- **Type.** Nanum Gothic for text. Every number (money, counts, times, ids) is D2Coding: `.num`, `.value`, `.big`,
  `.time`, `.mono`. D2Coding is a 12 KB subset served from `app/` (digits, Latin, punctuation; `font-display:swap`;
  licence `app/D2Coding-OFL.txt`); Hangul in a number cell falls back to Nanum Gothic Coding.
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
  off under `prefers-reduced-motion`. Targets: `.btn` 40 px, `.seg a` 36 px, send 40 px.
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
