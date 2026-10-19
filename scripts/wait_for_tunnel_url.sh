#!/usr/bin/env bash
set -u

for _attempt in $(seq 1 30); do
  tunnel_url=$(docker compose "$@" logs --no-color tunnel 2>&1 \
    | grep -Eo 'https://[[:alnum:]-]+\.trycloudflare\.com' \
    | tail -n 1 || true)
  if [[ -n "$tunnel_url" ]]; then
    printf 'Showcase URL: %s\n' "$tunnel_url"
    exit 0
  fi
  sleep 1
done

printf 'Quick Tunnel URL has not appeared yet. Current tunnel logs:\n' >&2
docker compose "$@" logs --tail=50 tunnel >&2
exit 1
