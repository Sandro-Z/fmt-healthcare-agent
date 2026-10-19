#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

for name in workspace-api workspace-web agent-daemon; do
  pid_file="$DATA_ROOT/run/$name.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "$name running: PID $(cat "$pid_file")"
  else
    echo "$name stopped"
  fi
done
