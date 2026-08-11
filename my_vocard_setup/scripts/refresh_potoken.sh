#!/usr/bin/env bash
# Refresh YouTube poToken from local bgutil-pot (port 4416) into .env and recreate Lavalink.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
BGUTIL_URL="${BGUTIL_URL:-http://127.0.0.1:4416/get_pot}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE" >&2
  exit 1
fi

json="$(curl -fsS -m 60 -X POST "$BGUTIL_URL" -H 'Content-Type: application/json' -d '{}')"
po_token="$(python3 -c 'import json,sys,urllib.parse; d=json.load(sys.stdin); print(d["poToken"])' <<<"$json")"
visitor="$(python3 -c 'import json,sys,urllib.parse; d=json.load(sys.stdin); print(urllib.parse.unquote(d["contentBinding"]))' <<<"$json")"
expires="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("expiresAt",""))' <<<"$json")"

if [[ -z "$po_token" || -z "$visitor" ]]; then
  echo "bgutil returned empty pot/visitor" >&2
  exit 1
fi

tmp="$(mktemp)"
awk -v pot="$po_token" -v vis="$visitor" '
  BEGIN { done_pot=0; done_vis=0 }
  /^YOUTUBE_POT_TOKEN=/ { print "YOUTUBE_POT_TOKEN=" pot; done_pot=1; next }
  /^YOUTUBE_POT_VISITOR_DATA=/ { print "YOUTUBE_POT_VISITOR_DATA=" vis; done_vis=1; next }
  { print }
  END {
    if (!done_pot) print "YOUTUBE_POT_TOKEN=" pot
    if (!done_vis) print "YOUTUBE_POT_VISITOR_DATA=" vis
  }
' "$ENV_FILE" > "$tmp"
mv "$tmp" "$ENV_FILE"

echo "Updated poToken (expiresAt=$expires)"
cd "$ROOT"
sudo docker compose up -d --force-recreate lavalink
# Wait until Lavalink is healthy so the bot can reconnect cleanly.
for i in $(seq 1 30); do
  status="$(sudo docker inspect -f '{{.State.Health.Status}}' vocard-lavalink 2>/dev/null || echo missing)"
  if [[ "$status" == "healthy" ]]; then
    break
  fi
  sleep 2
done
sudo docker compose restart vocard
echo "Lavalink recreated with fresh poToken; vocard restarted"
