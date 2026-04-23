# RayPulse

RayPulse is a lightweight web dashboard for Xray outbound monitoring.

It shows:

- outbound delay and health
- best outbound now
- most stable outbounds
- online users from access log
- outbound traffic if stats are exposed in `debug/vars`

## Features

- single-file Python app
- systemd service install
- optional HTTPS with your own certificate
- interactive installer
- online users based on access log
- 30-minute delay charts
- outbound traffic table
- live health view

## Screenshot

![RayPulse Dashboard](screenshots/1.png)

## Quick install

```bash
bash <(curl -Ls https://raw.githubusercontent.com/Matialz7/RayPulse/main/install.sh)
Install from ZIP
Download the repository ZIP
Extract it on your server
Run:
chmod +x install.sh
./install.sh
What the installer asks for

The installer asks for:

Metrics URL
Access log path
Bind host
Bind port
TLS mode
TLS certificate path
TLS key path
Default paths
Metrics URL: http://127.0.0.1:11112/debug/vars
Access log: /usr/local/x-ui/access.log
Service management
systemctl status RayPulse
systemctl restart RayPulse
systemctl stop RayPulse
journalctl -u RayPulse -f
Uninstall
chmod +x uninstall.sh
./uninstall.sh
Notes
Port 443 must be free before using RayPulse on it.
If you use a CDN, make sure your origin is reachable and your TLS setup is correct.
Outbound traffic works only if Xray exposes the needed stats in debug/vars.
License

MIT
