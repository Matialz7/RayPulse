#!/usr/bin/env bash
set -euo pipefail

APP_NAME="RayPulse"
INSTALL_DIR="/opt/RayPulse"
SERVICE_NAME="RayPulse"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
DEFAULT_METRICS_URL="http://127.0.0.1:11112/debug/vars"
DEFAULT_ACCESS_LOG="/usr/local/x-ui/access.log"
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="443"
DEFAULT_TLS="auto"
DEFAULT_CERT="/root/certs/fullchain.pem"
DEFAULT_KEY="/root/certs/privkey.pem"

if [ "${EUID}" -ne 0 ]; then
  echo "Please run as root."
  exit 1
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing command: $1"; exit 1; }
}

need_cmd systemctl
need_cmd python3

ask() {
  local prompt="$1"
  local default="$2"
  local value
  read -r -p "$prompt [$default]: " value || true
  if [ -z "$value" ]; then
    printf '%s' "$default"
  else
    printf '%s' "$value"
  fi
}

echo "== ${APP_NAME} installer =="
echo "This will install ${APP_NAME} as a systemd service."
echo

RAYPULSE_METRICS_URL="$(ask 'Metrics URL' "$DEFAULT_METRICS_URL")"
RAYPULSE_ACCESS_LOG="$(ask 'Access log path' "$DEFAULT_ACCESS_LOG")"
RAYPULSE_HOST="$(ask 'Bind host' "$DEFAULT_HOST")"
RAYPULSE_PORT="$(ask 'Bind port' "$DEFAULT_PORT")"
RAYPULSE_TLS="$(ask 'TLS mode (auto/true/false)' "$DEFAULT_TLS")"
RAYPULSE_TLS_CERT="$(ask 'TLS cert path' "$DEFAULT_CERT")"
RAYPULSE_TLS_KEY="$(ask 'TLS key path' "$DEFAULT_KEY")"

echo
echo "Installing to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
cp raypulse.py "$INSTALL_DIR/raypulse.py"
chmod 755 "$INSTALL_DIR/raypulse.py"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=${APP_NAME}
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/raypulse.py
Restart=always
RestartSec=3
User=root
Environment=RAYPULSE_HOST=${RAYPULSE_HOST}
Environment=RAYPULSE_PORT=${RAYPULSE_PORT}
Environment=RAYPULSE_TLS=${RAYPULSE_TLS}
Environment=RAYPULSE_TLS_CERT=${RAYPULSE_TLS_CERT}
Environment=RAYPULSE_TLS_KEY=${RAYPULSE_TLS_KEY}
Environment=RAYPULSE_METRICS_URL=${RAYPULSE_METRICS_URL}
Environment=RAYPULSE_ACCESS_LOG=${RAYPULSE_ACCESS_LOG}

[Install]
WantedBy=multi-user.target
EOF

echo "Disabling old xray-mini-dashboard service if it exists ..."
systemctl stop xray-mini-dashboard 2>/dev/null || true
systemctl disable xray-mini-dashboard 2>/dev/null || true
rm -f /etc/systemd/system/xray-mini-dashboard.service
rm -f /etc/cron.d/xray-mini-dashboard-reset

echo "Reloading systemd ..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo
echo "Done. Current status:"
systemctl --no-pager --full status "$SERVICE_NAME" || true

echo
echo "Test locally with:"
echo "  curl -k -I https://127.0.0.1:${RAYPULSE_PORT}/"
