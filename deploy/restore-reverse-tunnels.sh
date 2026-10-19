#!/usr/bin/env bash
set -Eeuo pipefail

JUMP_HOST="${FMT_JUMP_HOST:-}"
KEY_PATH="${FMT_TUNNEL_KEY:-}"
SSH_REMOTE_PORT="${FMT_SSH_REMOTE_PORT:-20013}"
WEB_REMOTE_PORT="${FMT_WEB_REMOTE_PORT:-18502}"
API_REMOTE_PORT="${FMT_API_REMOTE_PORT:-18503}"

[[ -n "$JUMP_HOST" ]] || { echo "FMT_JUMP_HOST is not configured" >&2; exit 2; }
[[ -n "$KEY_PATH" ]] || { echo "FMT_TUNNEL_KEY is not configured" >&2; exit 2; }

if [[ ! -r "$KEY_PATH" ]]; then
  echo "reverse-tunnel key is missing or unreadable: $KEY_PATH" >&2
  exit 2
fi

start_tunnel() {
  local marker="$1"
  shift
  if pgrep -af ssh | grep -F -- "$marker" >/dev/null; then
    echo "$marker already forwarded"
    return
  fi
  ssh -N -f \
    -o BatchMode=yes \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o StrictHostKeyChecking=no \
    -i "$KEY_PATH" "$@" "$JUMP_HOST"
  echo "$marker forwarding started"
}

# The base container normally creates the SSH forward. This fallback restores
# it when the entrypoint did not do so.
start_tunnel "$SSH_REMOTE_PORT:localhost:22" -R "$SSH_REMOTE_PORT:localhost:22"
start_tunnel "$WEB_REMOTE_PORT:127.0.0.1:8502" \
  -R "$WEB_REMOTE_PORT:127.0.0.1:8502" \
  -R "$API_REMOTE_PORT:127.0.0.1:8503"
