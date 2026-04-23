<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.fa.md">فارسی</a>
</p>

<h1 align="center">RayPulse</h1>

<p align="center">
  Lightweight Xray outbound monitoring dashboard
</p>

<p align="center">
  <a href="https://github.com/Matialz7/RayPulse/releases/tag/v1.0.0">
    <img src="https://img.shields.io/badge/release-v1.0.0-3b82f6?style=flat-square" alt="release">
  </a>
  <a href="https://github.com/Matialz7/RayPulse/releases/download/v1.0.0/RayPulse-v1.0.0.zip">
    <img src="https://img.shields.io/badge/download-ZIP-22c55e?style=flat-square" alt="download zip">
  </a>
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-f59e0b?style=flat-square" alt="license">
  </a>
  <a href="./README.fa.md">
    <img src="https://img.shields.io/badge/docs-Persian-8b5cf6?style=flat-square" alt="Persian docs">
  </a>
</p>

<p align="center">
  A simple and lightweight web dashboard for monitoring Xray outbounds, delay history, online users, and traffic.
</p>

---

## Quick Install

```bash
bash <(curl -Ls https://raw.githubusercontent.com/Matialz7/RayPulse/main/install.sh)
```

## What RayPulse Shows

- outbound delay and health
- best outbound right now
- most stable outbounds
- online users from access log
- outbound traffic if stats are exposed in `debug/vars`

## Features

- single-file Python app
- simple systemd service install
- optional HTTPS with your own certificate
- interactive installer
- online users based on access log
- 30-minute delay charts
- outbound traffic table
- live outbound health view

## Screenshot

<details>
<summary>Click to view screenshot</summary>

<p align="center">
  <img src="screenshots/1.png" alt="RayPulse Dashboard" width="100%">
</p>

</details>

## Persian Documentation

If you want the Persian guide, open:

**[README.fa.md](./README.fa.md)**

## Install from ZIP

1. Download the release ZIP
2. Extract it on your server
3. Run:

```bash
chmod +x install.sh
./install.sh
```

## What the Installer Asks For

- Metrics URL
- Access log path
- Bind host
- Bind port
- TLS mode
- TLS certificate path
- TLS key path

## Default Paths

- Metrics URL: `http://127.0.0.1:11112/debug/vars`
- Access log: `/usr/local/x-ui/access.log`

## Service Management

```bash
systemctl status RayPulse
systemctl restart RayPulse
systemctl stop RayPulse
journalctl -u RayPulse -f
```

## Uninstall

```bash
chmod +x uninstall.sh
./uninstall.sh
```

## Notes

- Make sure port `443` is free before using it.
- If you use a CDN, ensure your origin and TLS settings are correct.
- Outbound traffic works only if Xray exposes the required stats in `debug/vars`.

## Release

- Repository: <https://github.com/Matialz7/RayPulse>
- Release: <https://github.com/Matialz7/RayPulse/releases/tag/v1.0.0>
- ZIP: <https://github.com/Matialz7/RayPulse/releases/download/v1.0.0/RayPulse-v1.0.0.zip>

## License

MIT
