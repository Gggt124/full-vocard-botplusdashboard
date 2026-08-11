#!/bin/bash
# Post-boot healthcheck for Vocard stack. Exit 0 only if critical services are good.
set -euo pipefail

need_healthy=(vocard-mongo vocard-lavalink)
need_running=(vocard-bot vocard-ytcipher vocard-bgutil vocard-dashboard vocard-cloudflared)
fail=0

echo "==== docker ===="
systemctl is-active docker
systemctl is-active vocard-stack.service || true

echo "==== containers ===="
sudo docker ps -a --format 'table {{.Names}}\t{{.Status}}'

for c in "${need_healthy[@]}"; do
  status="$(sudo docker inspect -f '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$c" 2>/dev/null || echo missing)"
  echo "$c => $status"
  if [[ "$status" != "running/healthy" ]]; then
    echo "FAIL: $c not healthy"
    fail=1
  fi
done

for c in "${need_running[@]}"; do
  status="$(sudo docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo missing)"
  echo "$c => $status"
  if [[ "$status" != "running" ]]; then
    echo "FAIL: $c not running"
    fail=1
  fi
done

echo "==== bot node ===="
# Only accept a connect log from the current bot container lifetime.
started_at="$(sudo docker inspect -f '{{.State.StartedAt}}' vocard-bot)"
if ! sudo docker logs vocard-bot --since "$started_at" 2>&1 | grep -q "Node \[DEFAULT\] is connected!"; then
  echo "FAIL: bot has not connected to DEFAULT node since container start ($started_at)"
  sudo docker logs vocard-bot --since "$started_at" --tail 40 || true
  fail=1
else
  last="$(sudo docker logs vocard-bot --since "$started_at" 2>&1 | grep "Node \[DEFAULT\] is connected!" | tail -1 || true)"
  echo "OK: $last"
fi

echo "==== lavalink api ===="
code="$(curl -sS -m 5 -o /dev/null -w '%{http_code}' -H 'Authorization: youshallnotpass' http://127.0.0.1:2333/v4/info || echo 000)"
echo "lavalink HTTP $code"
[[ "$code" == "200" ]] || fail=1

echo "==== ytsearch ===="
curl -sS -m 30 -G -H 'Authorization: youshallnotpass' \
  --data-urlencode 'identifier=ytsearch:test' \
  'http://127.0.0.1:2333/v4/loadtracks' > /tmp/vocard_boot_search.json || true
python3 - <<'PY'
import json,sys
try:
  d=json.load(open('/tmp/vocard_boot_search.json'))
except Exception as e:
  print('parse_fail', e); sys.exit(0)
print('loadType', d.get('loadType'))
PY

if [[ "$fail" -ne 0 ]]; then
  echo "HEALTHCHECK FAILED"
  exit 1
fi
echo "HEALTHCHECK PASSED"
