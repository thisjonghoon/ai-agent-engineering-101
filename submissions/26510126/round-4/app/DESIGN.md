# The shop's screens: one look

Every screen of the shop (the chat, 현황, the Tailscale dashboard, and any screen added later) uses `app/ui.css`.
The look is webtoon-review-board's design system with Hermes orange as its one accent; the frame is the mini app's.

## Rules
- **One accent.** Hermes orange `#F37021` with black text on it (white on orange is 2.9:1). Orange text on white is
  the darker `--accent-ink`. Red (`--danger`) is for errors, losses and STOP only.
- **Type.** Nanum Gothic for text. Every number (money, counts, times, ids) is D2Coding: `.num`, `.value`, `.big`,
  `.time`, `.mono`.
- **Frame.** A thin `header`: `.avatar` (the shop's initial), `.who` with the name and a `.status` dot, then the screen
  switch `.seg` (the current screen's link has `aria-current="page"`), then buttons (`.btn`). The orange 3 px line
  under the header is the only decoration.
- **Body.** A screen other than the chat is `body.screen` with `main.page`: panels (`.panel`, `.panel.accent` for the
  one number that matters most), a two-column `.stats` grid that stays two columns on a phone, lists (`.list`), and
  key-value tables (`.kv`). Section titles are `.panel h2`; small labels are `.label` and `.sub`.
- **States.** `.tag` (neutral), `.tag.ok`/`.tag.alert` (orange), `.tag.stop` (red); `.up`/`.down` for gains and losses.
- **Phone first.** 390 px wide with no sideways scroll, light and dark from the same tokens.

## A new screen
1. Write it as `app/<name>.html` (or a page the dashboard writes there), link `/ui.css`, and use the parts above.
2. Add its link to the `.seg` of every screen.
3. Check it at 390 px in light and dark with the stub `miniapp.js` before it goes live (the kit serves `app/` straight
   from disk, so a change is live at once).
4. Keep `<script src="/miniapp.js"></script>` in `index.html` (ROUND4.md: the one line the kit needs).
