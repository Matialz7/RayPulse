#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import ssl
import time
from collections import Counter, OrderedDict, defaultdict, deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

APP_NAME = "RayPulse"
APP_VERSION = "v1.0.07"

METRICS_URL = os.environ.get("RAYPULSE_METRICS_URL", "http://127.0.0.1:11112/debug/vars")
ACCESS_LOG = Path(os.environ.get("RAYPULSE_ACCESS_LOG", "/usr/local/x-ui/access.log"))
HOST = os.environ.get("RAYPULSE_HOST", "0.0.0.0")
PORT = int(os.environ.get("RAYPULSE_PORT", "443"))

TLS_CERT = os.environ.get("RAYPULSE_TLS_CERT", "/root/certs/vip1.matialz.click.fullchain.pem")
TLS_KEY = os.environ.get("RAYPULSE_TLS_KEY", "/root/certs/vip1.matialz.click.key")
ENABLE_TLS = os.environ.get("RAYPULSE_TLS", "auto").lower()

RECENT_LINES = int(os.environ.get("RAYPULSE_RECENT_LINES", "8000"))
MAX_ACTIVE_USERS = 120
LIVE_WINDOW_SECONDS = int(os.environ.get("RAYPULSE_LIVE_WINDOW_SECONDS", "300"))
SHORT_DELAY_POINTS = int(os.environ.get("RAYPULSE_SHORT_DELAY_POINTS", "900"))
SHORT_DELAY_WINDOW_SECONDS = int(os.environ.get("RAYPULSE_SHORT_DELAY_WINDOW_SECONDS", "1800"))
STABILITY_WINDOW_SECONDS = 12 * 3600
STABILITY_STORE_FILE = Path(os.environ.get("RAYPULSE_STABILITY_STORE", "/root/raypulse_delay_history.json"))
STORE_SAVE_EVERY_SECONDS = 30
OUTBOUND_EXCLUDE = {"blocked", "direct", "api", "-"}

LOG_PATTERNS = [
    re.compile(
        r"^(?P<ts>\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
        r".*?\[(?P<inbound>[^\]]+?)\s*(?:>>|->)\s*(?P<outbound>[^\]]+?)\]"
        r"(?:.*?email:\s*(?P<email>.+))?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<ts>\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
        r".*?email:\s*(?P<email>.+?)\s+.*?\[(?P<inbound>[^\]]+?)\s*(?:>>|->)\s*(?P<outbound>[^\]]+?)\]",
        re.IGNORECASE,
    ),
]

SHORT_DELAY_HISTORY: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=SHORT_DELAY_POINTS))
SHORT_STATE_HISTORY: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=SHORT_DELAY_POINTS))
LONG_DELAY_HISTORY: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
DOWN_SINCE: dict[str, int] = {}
LAST_STORE_SAVE_TS = 0


def clean_email(value: str | None) -> str:
    if not value:
        return "-"
    v = value.strip()
    for sep in [" from ", " accepted ", " rejected ", " tcp:", " udp:", " ["]:
        if sep in v:
            v = v.split(sep, 1)[0].strip()
    return v or "-"


def parse_ts_to_epoch(ts: str) -> int | None:
    ts = ts.strip()
    for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            return int(datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    return None


def load_stability_store() -> None:
    global LONG_DELAY_HISTORY
    if not STABILITY_STORE_FILE.exists():
        return
    try:
        data = json.loads(STABILITY_STORE_FILE.read_text(encoding="utf-8"))
        now_ts = int(time.time())
        cutoff = now_ts - STABILITY_WINDOW_SECONDS
        for tag, rows in data.items():
            dq: deque[dict[str, Any]] = deque()
            for row in rows:
                t = int(row.get("t", 0))
                v = row.get("v")
                if t >= cutoff and isinstance(v, (int, float)):
                    dq.append({"t": t, "v": int(v)})
            if dq:
                LONG_DELAY_HISTORY[tag] = dq
    except Exception:
        LONG_DELAY_HISTORY = defaultdict(deque)


def maybe_save_stability_store(now_ts: int) -> None:
    global LAST_STORE_SAVE_TS
    if now_ts - LAST_STORE_SAVE_TS < STORE_SAVE_EVERY_SECONDS:
        return
    payload = {tag: list(dq) for tag, dq in LONG_DELAY_HISTORY.items() if dq}
    try:
        STABILITY_STORE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        LAST_STORE_SAVE_TS = now_ts
    except Exception:
        pass


def prune_delay_histories(now_ts: int) -> None:
    short_cutoff = now_ts - SHORT_DELAY_WINDOW_SECONDS
    long_cutoff = now_ts - STABILITY_WINDOW_SECONDS
    for store in (SHORT_DELAY_HISTORY, SHORT_STATE_HISTORY):
        for tag in list(store.keys()):
            dq = store[tag]
            while dq and dq[0]["t"] < short_cutoff:
                dq.popleft()
            if not dq:
                del store[tag]
    for tag in list(LONG_DELAY_HISTORY.keys()):
        dq = LONG_DELAY_HISTORY[tag]
        while dq and dq[0]["t"] < long_cutoff:
            dq.popleft()
        if not dq:
            del LONG_DELAY_HISTORY[tag]


load_stability_store()


def read_proc_stats() -> dict[str, Any]:
    result: dict[str, Any] = {"cpu": None, "ram_used_pct": None}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            meminfo = f.read().splitlines()
        mem = {}
        for line in meminfo:
            if ":" in line:
                k, v = line.split(":", 1)
                mem[k.strip()] = int(v.strip().split()[0])
        total = mem.get("MemTotal", 0)
        avail = mem.get("MemAvailable", 0)
        if total > 0:
            result["ram_used_pct"] = round(((total - avail) / total) * 100, 2)
    except OSError:
        pass

    try:
        def cpu_times() -> tuple[int, int]:
            with open("/proc/stat", "r", encoding="utf-8") as f:
                first = f.readline().strip().split()
            vals = list(map(int, first[1:]))
            idle = vals[3] + vals[4]
            total = sum(vals)
            return idle, total

        idle1, total1 = cpu_times()
        time.sleep(0.12)
        idle2, total2 = cpu_times()
        totald = total2 - total1
        idled = idle2 - idle1
        if totald > 0:
            result["cpu"] = round((1 - (idled / totald)) * 100, 2)
    except OSError:
        pass
    return result


def tail_lines(path: Path, max_lines: int) -> list[str]:
    if not path.exists():
        return []
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        size = min(end, 8 * 1024 * 1024)
        f.seek(max(0, end - size))
        data = f.read().decode("utf-8", errors="replace")
    return data.splitlines()[-max_lines:]


def parse_line(line: str) -> dict[str, Any] | None:
    for pattern in LOG_PATTERNS:
        m = pattern.search(line)
        if m:
            gd = m.groupdict()
            ts = (gd.get("ts") or "").strip()
            outbound = (gd.get("outbound") or "-").strip()
            if outbound.lower() in OUTBOUND_EXCLUDE:
                return None
            return {
                "timestamp": ts,
                "timestamp_epoch": parse_ts_to_epoch(ts),
                "email": clean_email(gd.get("email")),
                "inbound": (gd.get("inbound") or "-").strip(),
                "outbound": outbound,
                "raw": line.strip(),
            }
    return None


def is_real_user_connection(item: dict[str, Any]) -> bool:
    inbound = str(item.get("inbound", "")).strip().lower()
    outbound = str(item.get("outbound", "")).strip().lower()
    if inbound == "api" and outbound == "api":
        return False
    if inbound in {"api", "-"}:
        return False
    if outbound in OUTBOUND_EXCLUDE:
        return False
    return True


def parse_access_log(path: Path, max_lines: int) -> dict[str, Any]:
    lines = tail_lines(path, max_lines)
    latest_by_email: OrderedDict[str, dict[str, Any]] = OrderedDict()
    counts_by_outbound: Counter[str] = Counter()
    users_by_outbound: defaultdict[str, set[str]] = defaultdict(set)
    now_ts = int(time.time())
    live_users: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for line in reversed(lines):
        item = parse_line(line)
        if not item or not is_real_user_connection(item):
            continue

        outbound = str(item["outbound"])
        counts_by_outbound[outbound] += 1
        email = str(item["email"])
        ts_epoch = item.get("timestamp_epoch")
        if email not in {"-", "", "api"}:
            users_by_outbound[outbound].add(email)
            if email not in latest_by_email:
                latest_by_email[email] = item
            if ts_epoch and now_ts - int(ts_epoch) <= LIVE_WINDOW_SECONDS and email not in live_users:
                live_users[email] = item

    return {
        "latest_by_email": list(latest_by_email.values())[:200],
        "counts_by_outbound": dict(counts_by_outbound),
        "users_count_by_outbound": {k: len(v) for k, v in users_by_outbound.items()},
        "active_connections": list(live_users.values())[:MAX_ACTIVE_USERS],
        "online_users_count": len(live_users),
        "log_exists": path.exists(),
        "log_path": str(path),
    }


def remember_delay(tag: str, delay_ms: int | float | None, alive: bool, now_ts: int) -> None:
    if tag.lower() in OUTBOUND_EXCLUDE:
        return
    SHORT_STATE_HISTORY[tag].append({"t": now_ts, "alive": bool(alive), "v": None if delay_ms is None else int(delay_ms)})
    if alive and delay_ms is not None:
        SHORT_DELAY_HISTORY[tag].append({"t": now_ts, "v": int(delay_ms)})
        LONG_DELAY_HISTORY[tag].append({"t": now_ts, "v": int(delay_ms)})
        DOWN_SINCE.pop(tag, None)
    else:
        if tag not in DOWN_SINCE:
            DOWN_SINCE[tag] = now_ts


def collect_numeric_pairs(obj: Any, prefix: str = "") -> list[tuple[str, float]]:
    pairs: list[tuple[str, float]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_prefix = f"{prefix}.{k}" if prefix else str(k)
            pairs.extend(collect_numeric_pairs(v, new_prefix))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            pairs.extend(collect_numeric_pairs(v, f"{prefix}[{i}]"))
    elif isinstance(obj, (int, float)):
        pairs.append((prefix, float(obj)))
    return pairs


def extract_outbound_traffic(stats: dict[str, Any], observatory_tags: list[str]) -> list[dict[str, Any]]:
    numeric = collect_numeric_pairs(stats)
    tag_map: dict[str, dict[str, float]] = {}
    all_tags = set(observatory_tags)
    for name, value in numeric:
        lname = name.lower()
        if not any(key in lname for key in ["outbound", "uplink", "downlink", "traffic", "link"]):
            continue
        matched_tag = None
        for tag in observatory_tags:
            if tag and tag.lower() in lname:
                matched_tag = tag
                break
        if not matched_tag:
            continue
        bucket = tag_map.setdefault(matched_tag, {"upload": 0.0, "download": 0.0})
        if any(x in lname for x in ["uplink", "upload"]):
            bucket["upload"] = max(bucket["upload"], value)
        elif any(x in lname for x in ["downlink", "download"]):
            bucket["download"] = max(bucket["download"], value)
    rows = []
    for tag in sorted(all_tags):
        if tag.lower() in OUTBOUND_EXCLUDE:
            continue
        bucket = tag_map.get(tag, {"upload": 0.0, "download": 0.0})
        rows.append({"tag": tag, "upload": int(bucket["upload"]), "download": int(bucket["download"]), "total": int(bucket["upload"] + bucket["download"])})
    return rows


def read_metrics(url: str) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=3) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"error": str(exc), "observatory": [], "stats": {}, "traffic": []}

    observatory = data.get("observatory", {}) or {}
    stats = data.get("stats", {}) or {}
    delays: list[dict[str, Any]] = []
    now_ts = int(time.time())

    for tag, info in observatory.items():
        if not isinstance(info, dict):
            continue
        tag = str(tag)
        if tag.lower() in OUTBOUND_EXCLUDE:
            continue
        delay_ms = info.get("delay")
        alive = bool(info.get("alive"))
        delays.append({"tag": tag, "delay_ms": delay_ms, "alive": alive})
        remember_delay(tag, delay_ms, alive, now_ts)

    prune_delay_histories(now_ts)
    maybe_save_stability_store(now_ts)
    delays.sort(key=lambda x: (not x["alive"], x["delay_ms"] is None, x["delay_ms"] if x["delay_ms"] is not None else 10**9, x["tag"]))
    traffic = extract_outbound_traffic(stats, [x["tag"] for x in delays])
    return {"observatory": delays, "stats": stats, "traffic": traffic, "error": None}


def compute_top2_stable() -> list[dict[str, Any]]:
    rows = []
    for tag, dq in LONG_DELAY_HISTORY.items():
        if tag.lower() in OUTBOUND_EXCLUDE:
            continue
        vals = [int(x["v"]) for x in dq if isinstance(x.get("v"), (int, float))]
        if len(vals) < 3:
            continue
        avg = sum(vals) / len(vals)
        rows.append({"tag": tag, "avg_delay_ms": round(avg, 1), "samples": len(vals)})
    rows.sort(key=lambda x: (x["avg_delay_ms"], -x["samples"], x["tag"]))
    return rows[:2]


def build_chart_series(observatory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now_ts = int(time.time())
    cutoff = now_ts - SHORT_DELAY_WINDOW_SECONDS
    latest_state = {row["tag"]: bool(row.get("alive")) for row in observatory}
    series: list[dict[str, Any]] = []
    for row in observatory:
        tag = row["tag"]
        state_points = [x for x in SHORT_STATE_HISTORY.get(tag, []) if int(x["t"]) >= cutoff]
        delay_points = [x for x in SHORT_DELAY_HISTORY.get(tag, []) if int(x["t"]) >= cutoff]
        merged: list[dict[str, Any]] = []
        bucket_seconds = max(2, SHORT_DELAY_WINDOW_SECONDS // 180)
        t = cutoff
        while t <= now_ts:
            bucket_end = t + bucket_seconds
            bucket_states = [s for s in state_points if t <= int(s["t"]) < bucket_end]
            bucket_delays = [d for d in delay_points if t <= int(d["t"]) < bucket_end]
            alive = bucket_states[-1]["alive"] if bucket_states else None
            val = None
            if bucket_delays:
                vals = [int(d["v"]) for d in bucket_delays if isinstance(d.get("v"), (int, float))]
                if vals:
                    val = round(sum(vals) / len(vals), 1)
            merged.append({"t": t, "alive": alive, "v": val})
            t = bucket_end
        series.append({"tag": tag, "alive": latest_state.get(tag, False), "points": merged})
    return series


def build_status() -> dict[str, Any]:
    cpu_ram = read_proc_stats()
    metrics = read_metrics(METRICS_URL)
    logs = parse_access_log(ACCESS_LOG, RECENT_LINES)
    now_ts = int(time.time())
    observatory = metrics.get("observatory", [])
    active_count = sum(1 for x in observatory if x.get("alive"))
    down_outbounds = []
    for row in observatory:
        if not row.get("alive"):
            tag = row.get("tag")
            down_since = DOWN_SINCE.get(tag)
            down_for = now_ts - down_since if down_since else None
            down_outbounds.append({"tag": tag, "down_for_seconds": down_for})
    best_now = next((x for x in observatory if x.get("alive")), observatory[0] if observatory else None)
    top2_stable_12h = compute_top2_stable()
    traffic_state = {row["tag"]: ("alive" if row["alive"] else "down") for row in observatory}
    traffic_rows = [{**row, "state": traffic_state.get(row["tag"], "-")} for row in metrics.get("traffic", [])]
    return {
        "now": now_ts,
        "metrics_url": METRICS_URL,
        **metrics,
        **logs,
        "delay_series": build_chart_series(observatory),
        "cpu": cpu_ram.get("cpu"),
        "ram_used_pct": cpu_ram.get("ram_used_pct"),
        "active_outbound_count": active_count,
        "down_outbounds": down_outbounds,
        "best_now": best_now,
        "top2_stable_12h": top2_stable_12h,
        "traffic_rows": traffic_rows,
    }


HTML = """<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>RayPulse</title>
<style>
:root{--bg:#08111f;--bg2:#0d1830;--panel:rgba(18,30,56,.74);--panel2:rgba(13,22,42,.88);--text:#eaf2ff;--muted:#9ab0d7;--line:rgba(125,166,255,.18);--green:#26d68b;--amber:#ffbf5f;--red:#ff6f7f;--cyan:#59d8ff;--blue:#71a7ff;--violet:#aa87ff;--shadow:0 16px 40px rgba(0,0,0,.34)}
*{box-sizing:border-box} body{margin:0;color:var(--text);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:radial-gradient(circle at 0% 0%, rgba(89,216,255,.12), transparent 30%),radial-gradient(circle at 100% 0%, rgba(170,135,255,.12), transparent 28%),linear-gradient(180deg,var(--bg),var(--bg2))}
.wrap{max-width:1480px;margin:0 auto;padding:20px}
.topbar{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:18px}
.h1{font-size:28px;font-weight:900;letter-spacing:-.03em}
.sub{color:var(--muted);font-size:13px}.actions{display:flex;gap:10px;flex-wrap:wrap}
button,input,select{background:rgba(16,26,48,.78);color:var(--text);border:1px solid rgba(131,167,255,.22);border-radius:14px;padding:10px 12px;font-size:13px}
.grid-top{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
@media(max-width:1100px){.grid-top{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.grid-top{grid-template-columns:1fr}}
.card{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:22px;padding:16px;box-shadow:var(--shadow)}
.label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}
.big{font-size:28px;font-weight:900}.big-sm{font-size:18px;font-weight:850}
.kv{display:flex;justify-content:space-between;gap:8px;margin-top:10px;font-size:12px;color:var(--muted)}
.row{display:grid;grid-template-columns:1.25fr .95fr;gap:12px;margin-top:12px}@media(max-width:1100px){.row{grid-template-columns:1fr}}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}@media(max-width:1100px){.row2{grid-template-columns:1fr}}
.sectiontitle{display:flex;justify-content:space-between;gap:10px;align-items:flex-end;margin-bottom:12px}.sectiontitle strong{font-size:14px}.sectiontitle span{font-size:12px;color:var(--muted)}
.status-grid{display:grid;gap:8px}.status-row{display:grid;grid-template-columns:130px 1fr 80px 74px;gap:8px;align-items:center}
@media(max-width:760px){.status-row{grid-template-columns:1fr}}
.bar{height:12px;background:#0a1324;border:1px solid rgba(132,177,255,.12);border-radius:999px;overflow:hidden}
.fill{height:100%;display:block;background:linear-gradient(90deg,var(--blue),var(--green))}.fill.mid{background:linear-gradient(90deg,#facc15,#f59e0b)}.fill.bad{background:linear-gradient(90deg,#fb923c,#ef4444)}
.pill{display:inline-flex;align-items:center;justify-content:center;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:800}
.good{background:rgba(38,214,139,.12);color:var(--green)}.midc{background:rgba(255,191,95,.12);color:var(--amber)}.badc{background:rgba(255,111,127,.12);color:var(--red)}
.warnbox{display:grid;gap:8px;margin-top:10px}.warnitem{padding:10px 12px;border-radius:14px;background:rgba(255,111,127,.09);border:1px solid rgba(255,111,127,.16);color:#ffd4db;font-size:12px}
.chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}@media(max-width:1100px){.chart-grid{grid-template-columns:1fr}}
.chart-card{padding:14px}.spark-wrap{position:relative;height:210px;border-radius:18px;background:linear-gradient(180deg, rgba(7,13,28,.82), rgba(10,17,32,.90));border:1px solid rgba(122,146,199,.12);overflow:hidden}
.spark-head{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:10px}.spark-tag{font-weight:800;font-size:14px}.spark-meta{display:flex;gap:8px;flex-wrap:wrap}.spark-meta span{font-size:11px;color:var(--muted);padding:3px 8px;border-radius:999px;border:1px solid var(--line)}
svg.spark{width:100%;height:100%;display:block}
.tablewrap{overflow:auto;max-height:420px;border-radius:18px;border:1px solid rgba(132,177,255,.12)}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:10px 12px;border-bottom:1px solid rgba(132,177,255,.10);text-align:left;white-space:nowrap}th{position:sticky;top:0;background:#13213e;z-index:1;color:#aac0ea;font-size:11px;text-transform:uppercase;letter-spacing:.08em}
tr:hover td{background:rgba(132,177,255,.04)}.muted{color:var(--muted)}.footer-note{margin-top:10px;font-size:11px;color:var(--muted)}
</style>
</head>
<body>
<div class='wrap'>
<div class='topbar'>
<div><div class='h1'>RayPulse</div><div class='sub'>Live outbound health, delay, online users and traffic.</div></div>
<div class='actions'><input id='searchEmail' placeholder='Filter email / config'><select id='outboundFilter'><option value=''>All outbounds</option></select><button id='refreshBtn'>Refresh</button></div>
</div>

<div class='grid-top'>
<div class='card'><div class='label'>Best outbound now</div><div class='big-sm' id='bestOutbound'>-</div><div class='kv'><span>Delay</span><span id='bestDelay'>-</span></div></div>
<div class='card'><div class='label'>Most stable</div><div class='big-sm' id='stableLine1'>-</div><div class='kv'><span id='stableLine2'>-</span><span id='stableLine3'>-</span></div></div>
<div class='card'><div class='label'>Online users</div><div class='big' id='onlineUsers'>-</div><div class='kv'><span>Last 5 minutes</span><span>unique emails</span></div></div>
<div class='card'><div class='label'>Alive outbounds</div><div class='big' id='activeCount'>-</div><div class='kv'><span>Observed now</span><span id='lastRefresh'>-</span></div></div>
<div class='card'><div class='label'>Server</div><div class='big' id='ramPct'>-</div><div class='kv'><span>RAM</span><span id='cpuPct'>CPU -</span></div></div>
</div>

<div class='row'>
<div class='card'>
<div class='sectiontitle'><strong>Delay trend</strong><span>Last 30 minutes · one chart per outbound</span></div>
<div id='chartGrid' class='chart-grid'></div>
</div>
<div class='card'>
<div class='sectiontitle'><strong>Outbound health</strong><span>Live delay</span></div>
<div id='delayBars' class='status-grid'></div>
<div id='downWarn' class='warnbox'></div>
<div class='footer-note'>Metrics: <span id='metricsUrl'>-</span> · Log: <span id='logPath'>-</span></div>
</div>
</div>

<div class='row2'>
<div class='card'><div class='sectiontitle'><strong>Online users now</strong><span>Latest unique users in last 5 minutes</span></div><div class='tablewrap'><table><thead><tr><th>Time</th><th>User / config</th><th>Inbound</th><th>Outbound</th></tr></thead><tbody id='activeBody'></tbody></table></div></div>
<div class='card'><div class='sectiontitle'><strong>Outbound traffic</strong><span>Upload, download, total</span></div><div class='tablewrap'><table><thead><tr><th>Outbound</th><th>Upload</th><th>Download</th><th>Total</th><th>State</th></tr></thead><tbody id='trafficBody'></tbody></table></div></div>
</div>
</div>
<script>
let latestStatus = null;
const palette=['#59e0ff','#a786ff','#1ed08a','#efb342','#ff6a7d','#63b3ff','#ff8cc6','#4ee39a','#ffcf5a','#6de0ff'];
function esc(s){return String(s ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}
function fmtMs(ms){ if(ms==null || ms===undefined) return '-'; return ms>=1000 ? (ms/1000).toFixed(2)+' s' : Math.round(ms)+' ms'; }
function fmtPct(v){ return v==null ? '-' : Number(v).toFixed(2)+'%'; }
function fmtBytes(n){ const v = Number(n||0); if(!isFinite(v) || v<=0) return '0.00 B'; const units=['B','KB','MB','GB','TB']; let i=0, x=v; while(x>=1024 && i<units.length-1){ x/=1024; i++; } return x.toFixed(2)+' '+units[i]; }
function cls(ms){ if(ms==null) return 'badc'; if(ms<600) return 'good'; if(ms<1200) return 'midc'; return 'badc'; }
function fillCls(ms){ if(ms==null) return 'bad'; if(ms<600) return ''; if(ms<1200) return 'mid'; return 'bad'; }
function niceDown(sec){ if(sec==null) return '-'; if(sec<60) return sec+'s'; if(sec<3600) return Math.floor(sec/60)+'m'; return Math.floor(sec/3600)+'h '+Math.floor((sec%3600)/60)+'m'; }
function filterRows(rows){ const q=document.getElementById('searchEmail').value.trim().toLowerCase(); const outbound=document.getElementById('outboundFilter').value; return rows.filter(r=>{ const qok=!q||String(r.email||'').toLowerCase().includes(q); const ook=!outbound||r.outbound===outbound; return qok&&ook; });}
function renderSelect(observatory){ const sel=document.getElementById('outboundFilter'); const cur=sel.value; const tags=observatory.map(x=>x.tag); sel.innerHTML='<option value="">All outbounds</option>'+tags.map(t=>`<option value="${esc(t)}">${esc(t)}</option>`).join(''); if(tags.includes(cur)) sel.value=cur; }
function renderBars(data){ const obs=(data.observatory||[]).filter(x=>x.tag && !['blocked','direct'].includes(String(x.tag).toLowerCase())); const max=Math.max(1600,...obs.map(x=>Number(x.delay_ms||0))); document.getElementById('delayBars').innerHTML=obs.map(x=>{ const pct=x.delay_ms==null?4:Math.max(3,Math.round((Number(x.delay_ms||0)/max)*100)); return `<div class='status-row'><div>${esc(x.tag)}</div><div class='bar'><span class='fill ${fillCls(x.delay_ms)}' style='width:${pct}%'></span></div><div class='${cls(x.delay_ms)} pill'>${x.alive?'alive':'down'}</div><div class='${cls(x.delay_ms)}'>${x.alive?fmtMs(x.delay_ms):'-'}</div></div>`; }).join(''); const down=data.down_outbounds||[]; document.getElementById('downWarn').innerHTML=down.length?down.map(d=>`<div class='warnitem'>${esc(d.tag)} is down${d.down_for_seconds!=null?` · about ${niceDown(d.down_for_seconds)}`:''}</div>`).join(''):''; }
function renderActiveUsers(data){ const rows=filterRows(data.active_connections||[]); document.getElementById('activeBody').innerHTML=rows.length?rows.map(r=>`<tr><td>${esc(r.timestamp)}</td><td>${esc(r.email)}</td><td>${esc(r.inbound)}</td><td>${esc(r.outbound)}</td></tr>`).join(''):'<tr><td colspan="4" class="muted">No users in the last 5 minutes</td></tr>'; }
function renderTraffic(data){ const rows=(data.traffic_rows||[]).filter(r=>!['blocked','direct'].includes(String(r.tag).toLowerCase())); document.getElementById('trafficBody').innerHTML=rows.length?rows.map(r=>`<tr><td>${esc(r.tag)}</td><td>${fmtBytes(r.upload)}</td><td>${fmtBytes(r.download)}</td><td>${fmtBytes(r.total)}</td><td>${esc(r.state||'-')}</td></tr>`).join(''):'<tr><td colspan="5" class="muted">No traffic stats found in debug/vars</td></tr>'; }
function buildSparkSvg(points, color){ const liveVals = points.filter(p=>p.v!=null).map(p=>Number(p.v)); const w=560, h=210, left=48, right=12, top=18, bottom=30; const pw=w-left-right, ph=h-top-bottom; let max=Math.max(1400,...liveVals, 1); const ticks=[0,.25,.5,.75,1]; const yLabels=ticks.map(t=>Math.round(max-(max*t))); const lines=ticks.map((t,idx)=>{ const y=top+ph*t; return `<line x1="${left}" y1="${y}" x2="${left+pw}" y2="${y}" stroke="rgba(160,186,230,.14)" stroke-width="1"/><text x="6" y="${y+4}" fill="#9cb2db" font-size="11">${yLabels[idx]}ms</text>`; }).join(''); const xTick=[0,.333,.666,1].map((t,i)=>{ const x=left+pw*t; const lbl=['30m ago','20m','10m','now'][i]; return `<line x1="${x}" y1="${top}" x2="${x}" y2="${top+ph}" stroke="rgba(160,186,230,.08)" stroke-width="1"/><text x="${x-18}" y="${h-10}" fill="#9cb2db" font-size="11">${lbl}</text>`; }).join(''); let d='', a='', pathPoints=[]; points.forEach((p,i)=>{ const x=left+(i/Math.max(1,points.length-1))*pw; if(p.v!=null){ const y=top+ph-((Number(p.v))/max)*ph; pathPoints.push({x,y}); d += `${pathPoints.length===1?'M':'L'} ${x} ${y} `; }}); if(pathPoints.length){ a = `M ${pathPoints[0].x} ${top+ph} ` + pathPoints.map(p=>`L ${p.x} ${p.y} `).join('') + `L ${pathPoints[pathPoints.length-1].x} ${top+ph} Z`; } const downRects = []; let downStart = null; points.forEach((p,i)=>{ const x=left+(i/Math.max(1,points.length-1))*pw; const isDown = p.alive === false; if(isDown && downStart === null) downStart = x; const nextIsDown = i < points.length-1 ? points[i+1].alive === false : false; if(downStart !== null && (!nextIsDown || i === points.length-1)){ const endX = x + (pw/Math.max(1,points.length-1)); downRects.push(`<rect x="${downStart}" y="${top}" width="${Math.max(3,endX-downStart)}" height="${ph}" fill="rgba(255,106,125,.12)"/>`); downStart = null; }}); const dots=pathPoints.length ? `<circle cx="${pathPoints[pathPoints.length-1].x}" cy="${pathPoints[pathPoints.length-1].y}" r="3.5" fill="${color}" stroke="#081426" stroke-width="1.5"/>` : ''; return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${lines}${xTick}${downRects.join('')}${a?`<path d="${a}" fill="${color}" opacity=".12"/>`:''}${d?`<path d="${d}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`:''}${dots}</svg>`; }
function renderCharts(data){ const rows=(data.delay_series||[]).filter(s=>s.tag && !['blocked','direct'].includes(String(s.tag).toLowerCase())); const grid=document.getElementById('chartGrid'); if(!rows.length){ grid.innerHTML='<div class="muted">No delay data yet.</div>'; return; } grid.innerHTML = rows.map((row,idx)=>{ const color=palette[idx % palette.length]; const livePoints=(row.points||[]).filter(p=>p.v!=null); const latest=livePoints.length?livePoints[livePoints.length-1].v:null; const avg=livePoints.length?Math.round(livePoints.reduce((a,b)=>a+Number(b.v||0),0)/livePoints.length):null; const hadSamples = (row.points||[]).some(p=>p.v!=null); return `<div class="card chart-card"><div class="spark-head"><div><div class="spark-tag">${esc(row.tag)}</div><div class="spark-meta"><span>${row.alive?'alive':'down'}</span><span>avg ${avg!=null?fmtMs(avg):'-'}</span><span>last ${latest!=null?fmtMs(latest):'-'}</span></div></div></div><div class="spark-wrap">${hadSamples ? buildSparkSvg(row.points||[], color) : `<div class="muted" style="padding:88px 20px 0">No samples yet</div>`}</div></div>`; }).join(''); }
async function refresh(){ try{ const r=await fetch('/api/status',{cache:'no-store'}); const data=await r.json(); latestStatus=data; const obs=(data.observatory||[]).filter(x=>!['blocked','direct'].includes(String(x.tag).toLowerCase())); renderSelect(obs); const bestNow=data.best_now||(obs.find(x=>x.alive)||obs[0]); document.getElementById('bestOutbound').textContent=bestNow?bestNow.tag:'-'; document.getElementById('bestDelay').textContent=bestNow&&bestNow.alive?fmtMs(bestNow.delay_ms):'-'; const stable=(data.top2_stable_12h||[]); document.getElementById('stableLine1').textContent=stable[0]?`1. ${stable[0].tag} · ${fmtMs(stable[0].avg_delay_ms)}`:'-'; document.getElementById('stableLine2').textContent=stable[1]?`2. ${stable[1].tag} · ${fmtMs(stable[1].avg_delay_ms)}`:'-'; document.getElementById('stableLine3').textContent=stable.length?'2 best by average':'-'; document.getElementById('onlineUsers').textContent=data.online_users_count ?? '-'; document.getElementById('cpuPct').textContent='CPU '+fmtPct(data.cpu); document.getElementById('ramPct').textContent=fmtPct(data.ram_used_pct); document.getElementById('activeCount').textContent=data.active_outbound_count ?? '-'; document.getElementById('lastRefresh').textContent=new Date((data.now||0)*1000).toLocaleTimeString(); document.getElementById('metricsUrl').textContent=data.metrics_url||'-'; document.getElementById('logPath').textContent=data.log_path||'-'; renderBars(data); renderCharts(data); renderActiveUsers(data); renderTraffic(data);}catch(e){ console.error(e); }}
document.getElementById('refreshBtn').addEventListener('click',refresh);
document.getElementById('searchEmail').addEventListener('input',()=>latestStatus&&renderActiveUsers(latestStatus));
document.getElementById('outboundFilter').addEventListener('change',()=>latestStatus&&renderActiveUsers(latestStatus));
refresh(); setInterval(refresh,10000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        try:
            if self.path in ("/", "/index.html"):
                html = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
            if self.path == "/api/status":
                payload = json.dumps(build_status(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()
        except BrokenPipeError:
            return

    def log_message(self, fmt: str, *args: Any) -> None:
        return


if __name__ == "__main__":
    print(f"Starting {APP_NAME} on {HOST}:{PORT}")
    print(f"Metrics: {METRICS_URL}")
    print(f"Access log: {ACCESS_LOG}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)

    use_tls = ENABLE_TLS == "true" or (ENABLE_TLS == "auto" and Path(TLS_CERT).exists() and Path(TLS_KEY).exists())
    if use_tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(TLS_CERT, TLS_KEY)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        print(f"TLS enabled with cert: {TLS_CERT}")

    server.serve_forever()
