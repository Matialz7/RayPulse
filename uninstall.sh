#!/usr/bin/env bash
set -euo pipefail
systemctl stop RayPulse 2>/dev/null || true
systemctl disable RayPulse 2>/dev/null || true
rm -f /etc/systemd/system/RayPulse.service
systemctl daemon-reload
rm -rf /opt/RayPulse
rm -f /root/raypulse_delay_history.json
echo "RayPulse removed."
