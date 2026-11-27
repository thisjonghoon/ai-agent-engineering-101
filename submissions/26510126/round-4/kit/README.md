# kit/: this shop's copy of the course's Round 4 kit

`scripts/` is read-only in this repository (AGENTS.md), so the kit runs from here (11/27, the owner's decision).
`run_r4.sh` starts `kit/agent_kit.py`.

Copied from `scripts/round4/` at upstream `df59456` (kit v5.2): agent_kit.py, miniapp.py, maroo.py, forge_runner.py,
market_kit.py, cli_model.py, LICENSE. Only `miniapp.py` differs from upstream (every change is marked `thisjonghoon`):
- 11/26 the chat is kept in `.kit/chat.jsonl` across kit restarts
- 11/26 an `app/` with its own icons is served those (the shop's logo), and the icon links carry `?v=2`
- 11/27 `/api/board` and `miniapp.board(id, approved)`: the 보드 tab's 허용/거절, written by `board_r4.py answer`

When the course updates the kit: diff `scripts/round4/` against the upstream commit above, bring the changes in here,
and keep the marked parts.
