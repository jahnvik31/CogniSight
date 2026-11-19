#!/usr/bin/env bash
# Start CogniSight and open the dashboard on the Pi's screen.
# Extra options are passed through, for example:
#   ./start.sh --flip          camera mounted upside down
#   ./start.sh --swap-colors   faces look blue in the dashboard
#   ./start.sh --no-listen     do not listen for voice commands
set -uo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/cognisight ]; then
  echo "CogniSight is not installed yet. Run ./setup.sh first."
  exit 1
fi

PORT=8765
if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && [ "${COGNISIGHT_NO_BROWSER:-0}" != 1 ]; then
  (
    for _ in $(seq 1 90); do
      curl -fs "http://localhost:$PORT/api/status" >/dev/null 2>&1 && break
      sleep 1
    done
    if command -v chromium-browser >/dev/null; then
      chromium-browser --app="http://localhost:$PORT" --start-fullscreen --noerrdialogs >/dev/null 2>&1
    elif command -v chromium >/dev/null; then
      chromium --app="http://localhost:$PORT" --start-fullscreen --noerrdialogs >/dev/null 2>&1
    elif command -v firefox >/dev/null; then
      firefox "http://localhost:$PORT" >/dev/null 2>&1
    fi
  ) &
fi

exec .venv/bin/cognisight start --port "$PORT" "$@"
