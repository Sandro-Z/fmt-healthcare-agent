#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${WGS_APP_ROOT:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
DATA_ROOT="${WGS_WORKSPACE:-$ROOT/var}"

for name in workspace-web workspace-api agent-daemon; do
  pid_file="$DATA_ROOT/run/$name.pid"
  if [[ ! -f "$pid_file" ]]; then
    echo "$name not running"
    continue
  fi
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "$name stopped: PID $pid"
  else
    echo "$name stale PID: $pid"
  fi
  rm -f "$pid_file"
done
