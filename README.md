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
- chart keeps previous delay samples even if an outbound goes down

## Quick install from GitHub
After you upload this repo to GitHub, users will be able to install it with a single command like this:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/YOUR_USERNAME/RayPulse/main/install.sh)
```

## Manual install from ZIP
1. Download the ZIP from GitHub.
2. Extract it on the server.
3. Enter the extracted folder.
4. Run:

```bash
chmod +x install.sh
./install.sh
```

## Files
- `raypulse.py` - main app
- `install.sh` - interactive installer
- `uninstall.sh` - remove service and files
- `RayPulse.service.example` - example systemd service

## Default paths
- Metrics URL: `http://127.0.0.1:11112/debug/vars`
- Access log: `/usr/local/x-ui/access.log`

## Notes
- Port `443` must be free if you want to use it.
- If your domain is behind a CDN, make sure the origin can still reach your server.
- Traffic values stay zero if Xray does not expose outbound stats in `debug/vars`.

## License
MIT
