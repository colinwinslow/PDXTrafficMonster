#!/usr/bin/env bash
# Install/refresh the collector as a system service on claude-box. Idempotent.
# Copies the script out of the worktree so a git checkout can't change what runs.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
unit=pdxtrafficmonster-collector.service

(cd "$here/.." && python3 -W error::ResourceWarning -m unittest tests.test_collect_live)

install -d -m 700 -o claude -g claude /home/claude/.config/pdxtrafficmonster
install -d -m 755 -o claude -g claude /home/claude/data/pdxtrafficmonster
sudo install -D -m 755 "$here/collect_live.py" /usr/local/lib/pdxtrafficmonster/collect_live.py
sudo install -m 644 "$here/systemd/$unit" "/etc/systemd/system/$unit"
sudo systemctl daemon-reload
sudo systemctl enable "$unit"
sudo systemctl restart "$unit"
sleep 3
systemctl status "$unit" --no-pager -n 6
echo
echo "Keys go in /home/claude/.config/pdxtrafficmonster/env, owned by claude, mode 600, one per line:"
echo "  TRIMET_APP_ID=..."
echo "  TOMTOM_API_KEY=..."
echo "  PDXTM_TOMTOM_ENABLED=1    # only after reading TomTom's developer T&C (ADR-0001 Open)"
echo "No restart needed; the collector re-reads that file every cycle."
