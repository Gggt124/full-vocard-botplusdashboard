#!/bin/bash
# Install + enable systemd unit that re-runs compose up after boot.
# Substitutes __VOCARD_SETUP_DIR__ with this checkout's my_vocard_setup path.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="$ROOT/deploy/vocard-stack.service"
UNIT_DST="/etc/systemd/system/vocard-stack.service"

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "missing $UNIT_SRC" >&2
  exit 1
fi

tmp="$(mktemp)"
sed "s|__VOCARD_SETUP_DIR__|${ROOT}|g" "$UNIT_SRC" > "$tmp"
if grep -q '__VOCARD_SETUP_DIR__' "$tmp"; then
  echo "placeholder substitution failed" >&2
  exit 1
fi

sudo cp "$tmp" "$UNIT_DST"
rm -f "$tmp"
sudo chmod 644 "$UNIT_DST"
sudo systemctl daemon-reload
sudo systemctl enable vocard-stack.service
# Validate by starting once (idempotent if stack already up).
sudo systemctl start vocard-stack.service
sudo systemctl --no-pager --full status vocard-stack.service || true
echo "Installed and started vocard-stack.service (WorkingDirectory=$ROOT)"
