#!/usr/bin/env bash
set -euo pipefail

ROOT="${WGS_APP_ROOT:-/storage/main/users/zhangrongpeng/data/fmt/apps/WGS-FMT-Agent-v2}"
ENV_ROOT="${WGS_ENV_ROOT:-/storage/main/users/zhangrongpeng/data/fmt/runtime/envs/wgs-fmt-agent-v2}"
DATA_ROOT="${WGS_WORKSPACE:-/storage/main/users/zhangrongpeng/data/fmt/wgs-fmt-agent-v2-data}"

cd "$ROOT"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

mkdir -p "$DATA_ROOT/logs" "$DATA_ROOT/run" "$DATA_ROOT/results" \
  "$DATA_ROOT/traces" "$DATA_ROOT/knowledge-index"

start_service() {
  local name="$1"
  local pid_file="$DATA_ROOT/run/$name.pid"
  local log_file="$DATA_ROOT/logs/$name.log"
  shift
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "$name already running: PID $(cat "$pid_file")"
    return
  fi
  nohup "$@" >"$log_file" 2>&1 &
  echo "$!" >"$pid_file"
  echo "$name started: PID $!"
}

start_service workspace-api "$ENV_ROOT/bin/python" -m uvicorn app.main:app \
  --app-dir "$ROOT/apps/workspace-api" --host 0.0.0.0 --port 8503
start_service workspace-web "$ROOT/apps/workspace-web/node_modules/.bin/next" \
  start "$ROOT/apps/workspace-web" -p 8502 -H 0.0.0.0

bash "$ROOT/deploy/restore-reverse-tunnels.sh"

if [[ -n "${DEEPSEEK_API_KEY:-}" || -n "${ANTHROPIC_API_KEY:-}" ]]; then
  start_service agent-daemon "$ENV_ROOT/bin/wgs-agent" daemon --host 127.0.0.1 --port 7438
else
  echo "agent-daemon skipped: configure DEEPSEEK_API_KEY or ANTHROPIC_API_KEY"
fi
