#!/usr/bin/env bash
# Install/refresh the collector as a system service on claude-box. Idempotent.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
unit=pdxtrafficmonster-collector.service

install -d -m 700 -o claude -g claude /home/claude/.config/pdxtrafficmonster
install -d -m 755 -o claude -g claude /home/claude/data/pdxtrafficmonster
sudo install -m 644 "$here/systemd/$unit" "/etc/systemd/system/$unit"
sudo systemctl daemon-reload
sudo systemctl enable --now "$unit"
sudo systemctl restart "$unit"
sleep 2
systemctl status "$unit" --no-pager -n 5
echo
echo "Keys go in /home/claude/.config/pdxtrafficmonster/env (mode 600), one per line:"
echo "  TRIMET_APP_ID=..."
echo "  TOMTOM_API_KEY=..."
echo "No restart needed; the collector re-reads that file every cycle."
