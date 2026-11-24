#!/usr/bin/env bash
# Starts the Round 4 agent with everything it needs, and keeps it up (run it inside tmux on the Mac mini):
#   1. llm_relay.py   the model, through the subscriptions (Claude, then GPT, then a free model)
#   2. agent_kit.py   the agent: shop only for now (decision of 11/23), its endpoint and tunnel, the mini app
#   3. watch_r4.py    the model-free watch (stops the agent for a leaked secret or a draining wallet)
# The Mac is kept awake for as long as this script runs (caffeinate).
#
#   export MARKET_OWNER=<claim code from https://market.ourolabs.ai/join>
#   ./run_r4.sh                      # AGENT_NAME (thisjonghoon), MARKET (https://market.ourolabs.ai), APP_PORT (8800)
#
# Stopping: Ctrl-C stops all three. `touch .kit/STOP` stops the restarts. A stop by the watch is never undone here: the
# kit is restarted only when it ended on its own (a crash, a tunnel that did not come up), never after the watch stopped
# it, and never after .kit/STOP exists; a person reads logs/watch-r4.jsonl and starts it again.
#
# The kit prints the app's links with the access code on its terminal and never in its log. That output goes to
# .kit/kit-terminal.log (git-ignored), not logs/: in logs/ it would be committed, and the watch would stop the agent.
# A restart gives the app a new tunnel URL (the access code stays): take the newest link from .kit/kit-terminal.log.
#
# Key backup: all of the shop's money is in shop_wallet.key and an account has one shop, so the first time the kit
# writes a wallet key it is copied to KEY_BACKUP_DIR ($HOME/Drop/round4-keys: outside git and iCloud), mode 700/600.
set -u
cd "$(dirname "$0")"
HERE=$(pwd)
ROOT=$(cd ../../.. && pwd)
PY="$ROOT/.venv/bin/python"
KIT="$ROOT/scripts/round4/agent_kit.py"
NAME="${AGENT_NAME:-thisjonghoon}"
MARKET="${MARKET:-https://market.ourolabs.ai}"
APP_PORT="${APP_PORT:-8800}"
KEY_BACKUP_DIR="${KEY_BACKUP_DIR:-$HOME/Drop/round4-keys}"
unset ANTHROPIC_API_KEY OPENAI_API_KEY      # the relay uses the logged-in subscriptions; no API key reaches the kit

[ -x "$PY" ] || { echo "[run] no venv at $PY (uv venv --python 3.12 .venv, then install the kit's packages)"; exit 1; }
[ -n "${MARKET_OWNER:-}" ] || { echo "[run] export MARKET_OWNER=<claim code> first (the watch checks it is never leaked)"; exit 1; }
for port in 8790 "$APP_PORT"; do          # a port already taken would leave the relay or the app silently dead
  "$PY" -c "import socket,sys; s=socket.socket(); s.bind(('127.0.0.1', $port))" 2>/dev/null \
    || { echo "[run] port $port is in use (an earlier run still up?); stop it first"; exit 1; }
done
mkdir -p logs .kit
touch .kit/started                      # a STOP older than this start is from an earlier run
# one key per start, shared by the relay and the kit through the environment only (never written to a file)
export RELAY_KEY=$("$PY" -c "import secrets; print(secrets.token_hex(16))")
export RELAY_PORT=8790

stopped() { [ -e .kit/STOP ] && [ .kit/STOP -nt .kit/started ]; }
stamp() { date "+%m/%d %H:%M:%S"; }
watch_stopped_since() {   # did the watch stop the agent after this start time?
  "$PY" -c "import json,sys; s=json.load(open('.kit/watch-state.json')); sys.exit(0 if s.get('stopped_at',0) >= $1 else 1)" 2>/dev/null
}

backup_keys() {   # copy each wallet key once it exists; a different key never overwrites an earlier copy
  mkdir -p "$KEY_BACKUP_DIR" && chmod 700 "$KEY_BACKUP_DIR" || return
  for k in shop_wallet.key buyer_wallet.key; do
    [ -s "$k" ] || continue
    dst="$KEY_BACKUP_DIR/$k"
    if [ -e "$dst" ] && ! cmp -s "$k" "$dst"; then dst="$KEY_BACKUP_DIR/$k.$(date +%Y%m%d%H%M%S)"; fi
    if [ ! -e "$dst" ]; then
      (umask 077; cp "$k" "$dst") && chmod 600 "$dst" && echo "[run $(stamp)] $k backed up to the key backup folder"
    fi
  done
}

backup_loop() {
  while ! stopped; do backup_keys; sleep 5; done
}

relay_loop() {
  while ! stopped; do
    echo "[run $(stamp)] relay starting"
    "$PY" llm_relay.py >> .kit/relay-terminal.log 2>&1
    echo "[run $(stamp)] relay exited ($?); restarting in 10 s"
    sleep 10
  done
}

kit_loop() {
  while ! stopped; do
    started=$(date +%s)
    echo "[run $(stamp)] agent starting: $NAME on $MARKET, shop only, app on $APP_PORT"
    "$PY" "$KIT" run --dir "$HERE" --market "$MARKET" --name "$NAME" --shop-only --tunnel \
        --app "$APP_PORT" --app-tunnel >> .kit/kit-terminal.log 2>&1
    code=$?
    if watch_stopped_since "$started"; then
      echo "[run $(stamp)] the watch stopped the agent: not restarting. Read logs/watch-r4.jsonl, then start again."
      touch .kit/STOP; break
    fi
    echo "[run $(stamp)] agent exited ($code); restarting in 30 s"
    sleep 30
  done
}

cleanup() { trap - INT TERM; touch .kit/STOP; kill 0 2>/dev/null; }
trap cleanup INT TERM

relay_loop &
sleep 3                                   # the relay takes its port before the kit picks a free one
kit_loop &
"$PY" watch_r4.py >> .kit/watch-terminal.log 2>&1 &
backup_loop &
"$PY" dashboard_r4.py --no-serve >> .kit/dash-terminal.log 2>&1 &   # writes the mini app's 현황 page every 30 s
echo "[run $(stamp)] started. Links with the app's code: grep '\[app\] open' .kit/kit-terminal.log"
caffeinate -is -w $$ &
wait
