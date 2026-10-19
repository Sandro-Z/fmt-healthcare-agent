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

for name in workspace-api workspace-web agent-daemon; do
  pid_file="$DATA_ROOT/run/$name.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "$name running: PID $(cat "$pid_file")"
  else
    echo "$name stopped"
  fi
done
