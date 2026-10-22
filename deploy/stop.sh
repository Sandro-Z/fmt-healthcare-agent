#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

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

manage_elasticsearch stop
