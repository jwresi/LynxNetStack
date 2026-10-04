#!/usr/bin/env python3
"""Push NYCHA security handoff port dashboard to Grafana.

All data comes from Prometheus — no file uploads, no SQLite reads at runtime.
Firewall names (from CDP/LLDP, not in Prometheus) are embedded as static
value mappings keyed on the `device` label.

Usage:
    .venv/bin/python audits/push_nycha_security_handoffs.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOTE_HOST  = "grafana_prometheus"
GRAFANA_HOST = "localhost:3000"
GRAFANA_AUTH = "admin:happySt3el49"
PROM_UID     = "PBFA97CFB590B2093"

# Static firewall name lookup — device identity -> CDP/LLDP neighbor name.
# These come from the neighbors table and don't change unless hardware changes.
FIREWALL_NAMES: dict[str, str] = {
    "000007.001.SW02": "nycha-sec-104-17 tapscott-int-fw-01",
    "000007.003.SW01": "nycha-lennox-int-fw-01",
    "000007.008.SW01": "nycha-1448buffalo-int-fw-01",
    "000007.031.SW01": "nycha-tsr-170_184_192-int-fw-01",
    "000007.032.SW02": "nycha-tsr-175_187_199-int-fw-01",
    "000007.036.SW02": "nycha-sec-sutter_ave-int-fw-01",
    "000007.042.SW01": "nycha-324howardAve-idf-sw-03",
    "000007.045.SW01": "nycha-sec-howard-int-fw-01",    # ether49
    "000007.049.SW01": "nycha-sec-howard-int-fw-01",
    "000007.051.SW03": "nycha-sec-ralph_ave",
    "000007.056.SW02": "nycha-tsr-725_728-int-fw-01",
    "000007.058.SW01": "nycha-rutland_towers-int-fw-01",
    "000007.060.SW02": "682_ralph-idf",
    "000007.066.SW01": "nycha-sec-tapscott-int-fw-01",
    "000007.068.SW01": "nycha-1720-1736B-sterling_place-int-fw-01",
}

# Which interface to watch per device (most are ether24; a few are ether49)
HANDOFF_PORT: dict[str, str] = {
    "000007.042.SW01": "ether49",
    "000007.045.SW01": "ether49",
    "000007.049.SW01": "ether49",
    "000007.066.SW01": "ether49",
    "000007.068.SW01": "ether49",
}


def prom_ds():
    return {"type": "prometheus", "uid": PROM_UID}


def grafana_post(payload: dict) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        tmp = Path(f.name)
    try:
        r = subprocess.run(
            ["scp", "-q", str(tmp), f"{REMOTE_HOST}:/tmp/_sec_push.json"],
            capture_output=True,
        )
        if r.returncode != 0:
            print(f"SCP failed: {r.stderr}", file=sys.stderr)
            return {}
        cmd = (
            f"curl -s -X POST "
            f"http://{GRAFANA_AUTH}@{GRAFANA_HOST}/api/dashboards/db "
            f'-H "Content-Type: application/json" '
            f"-d @/tmp/_sec_push.json"
        )
        result = subprocess.run(["ssh", REMOTE_HOST, cmd], capture_output=True, text=True)
        return json.loads(result.stdout) if result.stdout.strip() else {}
    finally:
        tmp.unlink(missing_ok=True)


def build_dashboard() -> dict:
    # Ordered list: sort by address for a geographic feel
    devices_ordered = sorted(FIREWALL_NAMES, key=lambda d: FIREWALL_NAMES[d])

    # ── Card grid: two stacked panels per site ───────────────────────────────
    # Layout: 3 sites per row × 8 cols each = 24 cols
    # Per site:
    #   Top panel (h=5): stat — UP/DOWN color background, address + port as name
    #   Bottom panel (h=3): stat — ↓ RX  /  ↑ TX  side-by-side, rate-colored

    SITES_PER_ROW = 3
    SITE_W  = 8   # each site is 8 cols wide
    TOP_H   = 5   # status card height
    BOT_H   = 3   # rate bar height

    no_threshold  = {"mode": "absolute", "steps": [{"color": "text", "value": None}]}
    up_thresholds = {
        "mode": "absolute",
        "steps": [
            {"color": "#d44a3a", "value": None},  # 0 → red
            {"color": "#299c46", "value": 1},      # 1 → green
        ],
    }
    rate_thresholds = {
        "mode": "absolute",
        "steps": [
            {"color": "#e02f44", "value": None},   # 0 B/s → red
            {"color": "#37872D", "value": 8},       # any traffic → green (1 B/s = 8 bits/s)
        ],
    }

    def status_panel(panel_id: int, device: str, grid_x: int, grid_y: int) -> dict:
        """Top card: large UP/DOWN, colored background, address as subtitle."""
        fw_name = FIREWALL_NAMES[device]
        port    = HANDOFF_PORT.get(device, "ether24")
        sel     = f'device="{device}",interface="{port}"'
        return {
            "id": panel_id, "type": "stat",
            "title": fw_name,
            "datasource": prom_ds(),
            "gridPos": {"h": TOP_H, "w": SITE_W, "x": grid_x, "y": grid_y},
            "targets": [{
                "datasource": prom_ds(), "refId": "U",
                "expr": f'mikrotik_interface_up{{{sel}}}',
                "legendFormat": "{{location_address}}",
                "instant": True, "range": False,
            }],
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "textMode":    "value_and_name",
                "colorMode":   "background",
                "graphMode":   "none",
                "justifyMode": "end",
                "text": {"titleSize": 13, "valueSize": 36},
            },
            "fieldConfig": {
                "defaults": {
                    "color":      {"mode": "thresholds"},
                    "thresholds": up_thresholds,
                    "mappings": [{"type": "value", "options": {
                        "1": {"text": "UP",   "color": "#299c46", "index": 0},
                        "0": {"text": "DOWN", "color": "#d44a3a", "index": 1},
                    }}],
                    "unit": "short", "custom": {},
                },
                "overrides": [],
            },
        }

    def rate_panel(panel_id: int, device: str, grid_x: int, grid_y: int) -> dict:
        """Bottom bar: ↓ RX  and  ↑ TX  side-by-side, rate-colored cells."""
        port = HANDOFF_PORT.get(device, "ether24")
        sel  = f'device="{device}",interface="{port}"'
        # Scrape interval is 3m — use 10m window to guarantee ≥2 samples
        return {
            "id": panel_id, "type": "stat",
            "title": "",
            "datasource": prom_ds(),
            "gridPos": {"h": BOT_H, "w": SITE_W, "x": grid_x, "y": grid_y},
            "targets": [
                {
                    "datasource": prom_ds(), "refId": "RR",
                    "expr": f'rate(mikrotik_interface_rx_bytes_total{{{sel}}}[10m]) * 8',
                    "legendFormat": "↓ RX",
                    "instant": True, "range": False,
                },
                {
                    "datasource": prom_ds(), "refId": "TR",
                    "expr": f'rate(mikrotik_interface_tx_bytes_total{{{sel}}}[10m]) * 8',
                    "legendFormat": "↑ TX",
                    "instant": True, "range": False,
                },
            ],
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                "textMode":    "value_and_name",
                "colorMode":   "background",
                "graphMode":   "none",
                "justifyMode": "center",
                "orientation": "horizontal",
                "text": {"titleSize": 11, "valueSize": 22},
            },
            "fieldConfig": {
                "defaults": {
                    "unit":     "bps",
                    "color":    {"mode": "thresholds"},
                    "thresholds": rate_thresholds,
                    "mappings": [],
                    "custom":   {},
                },
                "overrides": [],
            },
        }

    # ── Summary strip ─────────────────────────────────────────────────────────
    e24 = [d for d in FIREWALL_NAMES if HANDOFF_PORT.get(d, "ether24") == "ether24"]
    e49 = [d for d in FIREWALL_NAMES if HANDOFF_PORT.get(d, "ether24") == "ether49"]
    e24_re = "|".join(sorted(e24))
    e49_re = "|".join(sorted(e49))

    up_count_expr = (
        f'count(mikrotik_interface_up{{interface="ether24",device=~"{e24_re}"}} == 1)'
        f' + count(mikrotik_interface_up{{interface="ether49",device=~"{e49_re}"}} == 1)'
    )
    down_count_expr = (
        f'(count(mikrotik_interface_up{{interface="ether24",device=~"{e24_re}"}} == 0) or vector(0))'
        f' + (count(mikrotik_interface_up{{interface="ether49",device=~"{e49_re}"}} == 0) or vector(0))'
    )

    def summary_stat(panel_id, title, expr, color, x, w=8):
        return {
            "id": panel_id, "type": "stat", "title": title,
            "datasource": prom_ds(),
            "gridPos": {"h": 3, "w": w, "x": x, "y": 0},
            "targets": [{"datasource": prom_ds(), "refId": "S",
                         "expr": expr, "instant": True, "range": False}],
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "textMode": "auto", "colorMode": "background",
                "graphMode": "none", "justifyMode": "center",
                "text": {"titleSize": 12, "valueSize": 40},
            },
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": color},
                    "thresholds": no_threshold, "mappings": [],
                },
                "overrides": [],
            },
        }

    summary_panels = [
        summary_stat(900, "Connected",      up_count_expr,          "#299c46", 0),
        summary_stat(901, "Down",           down_count_expr,        "#d44a3a", 8),
        summary_stat(902, "Total Handoffs", str(len(FIREWALL_NAMES)), "#5794F2", 16),
    ]

    # ── Build card grid ───────────────────────────────────────────────────────
    # Each site occupies a (TOP_H + BOT_H) tall slot in its column.
    card_panels = []
    ROW_Y_START  = 3
    SLOT_H       = TOP_H + BOT_H

    for i, device in enumerate(devices_ordered):
        col    = i % SITES_PER_ROW
        row    = i // SITES_PER_ROW
        grid_x = col * SITE_W
        base_y = ROW_Y_START + row * SLOT_H
        pid    = i * 2 + 1
        card_panels.append(status_panel(pid,     device, grid_x, base_y))
        card_panels.append(rate_panel  (pid + 1, device, grid_x, base_y + TOP_H))

    return {
        "id": None, "uid": "nycha-security-handoffs",
        "title": "NYCHA — Security Handoff Ports",
        "description": "Live ether24/ether49 firewall handoff port status. Auto-refresh 1m.",
        "tags": ["nycha", "security", "handoff"],
        "schemaVersion": 39, "version": 1,
        "refresh": "1m",
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {},
        "timezone": "browser",
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "links": [{"title": "NYCHA Readiness",
                   "url": "/d/nycha-cpe-readiness/nycha-cpe-deployment-readiness",
                   "type": "link", "icon": "arrow-left", "targetBlank": False,
                   "keepTime": False, "tags": [], "asDropdown": False,
                   "includeVars": False}],
        "annotations": {"list": []},
        "templating": {"list": []},
        "panels": summary_panels + card_panels,
    }


def main():
    print(f"Pushing security handoff dashboard ({len(FIREWALL_NAMES)} known firewalls)...")
    dash = build_dashboard()
    resp = grafana_post({"dashboard": dash, "overwrite": True, "folderId": 0})
    if resp.get("status") == "success":
        print(f"Dashboard pushed: {resp.get('url')}")
    else:
        print(f"ERROR: {resp}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
