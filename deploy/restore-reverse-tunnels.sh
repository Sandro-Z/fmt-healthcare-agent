#!/usr/bin/env bash
set -euo pipefail

JUMP_HOST="${FMT_JUMP_HOST:-zhangrongpeng@10.181.9.172}"
KEY_PATH="${FMT_TUNNEL_KEY:-/storage/main/users/zhangrongpeng/.ssh/id_rsa_jump}"

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
start_tunnel "20013:localhost:22" -R 20013:localhost:22
start_tunnel "18502:127.0.0.1:8502" \
  -R 18502:127.0.0.1:8502 \
  -R 18503:127.0.0.1:8503
