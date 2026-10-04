#!/usr/bin/env python3
"""Push three NYCHA live Prometheus dashboards to Grafana.

Pure Prometheus — no static data, no joins, no Infinity datasource.
location_address label on mikrotik_switch_port_state carries the building address.

Dashboards pushed:
  nycha-developments   — one stat card per development, UP/total ports
  nycha-buildings      — variable $development → one card per building
  nycha-ports          — variable $address → per-switch table with port state + traffic

Usage:
    .venv/bin/python audits/push_nycha_live_dashboard.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOTE_HOST   = "grafana_prometheus"
GRAFANA_HOST  = "localhost:3000"
GRAFANA_AUTH  = "admin:happySt3el49"
PROM_UID      = "PBFA97CFB590B2093"
INFINITY_UID  = "jake-nycha"
JAKE_DATA_DIR = "/home/jonathan/jake-data"
# Grafana container reaches host via this gateway — used in Infinity URLs
JAKE_DATA_URL = "http://172.22.0.1:9099"

# Lefferts is site 000020 (standalone — too far to join 000007 circuit).
# All other NYCHA buildings are site 000007.
NYCHA_SITE_FILTER = 'site_id=~"000007|000020"'

# Exclude uplinks, SFP ports, CPU ports — these are never CPE ports
CPE_PORT_FILTER = f'{NYCHA_SITE_FILTER},port!~"sfp.*|qsfpplus.*|sfp28.*|switch.*-cpu"'

DEVELOPMENTS: dict[str, list[str]] = {
    "1. 104-14 Tapscott":               ["104 Tapscott", "170 Tapscott", "175 Tapscott",
                                          "184 Tapscott", "187 Tapscott", "192 Tapscott",
                                          "199 Tapscott", "9 Tapscott", "40 Grafton"],
    "2. Fenimore-Lefferts":             ["Fenimore", "Lefferts"],
    "3. Lenox Rd - Rockaway Pkwy":      ["Lenox Rd", "1196 E New York"],
    "4. Ralph Ave Rehab":               ["672 Ralph", "682 Ralph", "692 Ralph", "698 Ralph"],
    "5. Reid Apartments":               ["728 E New York"],
    "6. Rutland Towers":                ["955 Rutland"],
    "7. Sutter Ave - Union St":         ["2020 Pacific", "2041 Pacific", "2045 Union",
                                          "2058 Union", "2065 Dean", "2069 Union"],
    "9. Crown Heights":                 ["1367 St Marks", "1371 St Marks"],
    "10. Howard Ave":                   ["324 Howard", "504 Howard", "511 Howard",
                                          "578 Howard", "595 Howard", "606 Howard",
                                          "725 Howard", "728 Howard"],
    "11. Howard Ave - Park Pl":         ["1468 Park", "1474 Park", "1480 Park",
                                          "1629 Park", "1630 Park", "1636 Park",
                                          "1640 Park", "1646 Park"],
    "12. Oceanhill - Brownsville":      ["208 Rochester", "218 Rochester", "232 Rochester"],
    "14. Sterling Place - Saint Johns": ["1448 Sterling", "1452 Sterling", "1483 St Johns",
                                          "1491 St Johns", "1506 Sterling", "1511 Sterling",
                                          "1521 Sterling", "1522 Sterling", "1568 Sterling",
                                          "1578 Sterling", "1588 Sterling", "1598 Sterling",
                                          "1679 St Johns", "1720 Sterling"],
    "15. Sterling Place - Buffalo":     ["1634 Sterling", "1640 Sterling"],
}


def prom_ds() -> dict:
    return {"type": "prometheus", "uid": PROM_UID}


def grafana_post(payload: dict) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        tmp = Path(f.name)
    try:
        r = subprocess.run(
            ["scp", "-q", str(tmp), f"{REMOTE_HOST}:/tmp/_nycha_push.json"],
            capture_output=True,
        )
        if r.returncode != 0:
            print(f"SCP failed: {r.stderr.decode()}", file=sys.stderr)
            return {}
        cmd = (
            f"curl -s -X POST http://{GRAFANA_AUTH}@{GRAFANA_HOST}/api/dashboards/db "
            f'-H "Content-Type: application/json" -d @/tmp/_nycha_push.json'
        )
        result = subprocess.run(["ssh", REMOTE_HOST, cmd], capture_output=True, text=True)
        return json.loads(result.stdout) if result.stdout.strip() else {}
    finally:
        tmp.unlink(missing_ok=True)


def infinity_ds() -> dict:
    return {"type": "yesoreyeram-infinity-datasource", "uid": INFINITY_UID}


def addr_re(fragments: list[str]) -> str:
    """Build a Prometheus =~ regex matching any of the address fragments."""
    return ".*(" + "|".join(fragments) + ").*"


# Regex to extract device + port from audit implication text.
# Matches patterns like: "Live bridge host on 000007.008.SW01 ether1 matches..."
_IMPL_RE = re.compile(r'\bon (\d{6}\.\d{3}\.\w+) (ether\d+)\b')


def build_port_unit_files() -> None:
    """Read _rows.json files from the server, parse device+port from implication text,
    and write {address}_port_units.json files that map switch port → unit number.

    Only rows where we have a confirmed live sighting (implication contains device+port)
    are included. These files are fetched by the port detail dashboard Infinity panel.
    """
    # Read the list of _rows.json files from the server
    result = subprocess.run(
        ["ssh", REMOTE_HOST, f"ls {JAKE_DATA_DIR}/nycha_building/*_rows.json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("WARNING: could not list _rows.json files on server", file=sys.stderr)
        return

    remote_paths = [p.strip() for p in result.stdout.splitlines() if p.strip()]

    # Fetch all rows files in one shot — stream JSON blobs separated by newlines
    # using a server-side python one-liner so we don't have to scp each file individually
    fetch_script = (
        "import json, glob, sys\n"
        "out = {}\n"
        f"for f in glob.glob('{JAKE_DATA_DIR}/nycha_building/*_rows.json'):\n"
        "    addr = f.split('/')[-1].replace('_rows.json', '')\n"
        "    rows = json.load(open(f))\n"
        "    out[addr] = rows\n"
        "json.dump(out, sys.stdout)\n"
    )
    result = subprocess.run(
        ["ssh", REMOTE_HOST, f"python3 -c \"{fetch_script}\""],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("WARNING: could not fetch _rows.json data from server", file=sys.stderr)
        return

    try:
        all_data: dict[str, list[dict]] = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"WARNING: bad JSON from server rows fetch: {e}", file=sys.stderr)
        return

    # Build per-address port→unit mapping files
    port_unit_files: dict[str, list[dict]] = {}
    for addr, rows in all_data.items():
        entries = []
        seen: set[str] = set()
        for row in rows:
            impl = row.get("implication", "")
            unit = row.get("unit", "")
            if not impl or not unit:
                continue
            m = _IMPL_RE.search(impl)
            if not m:
                continue
            key = f"{m.group(1)}|{m.group(2)}"
            if key in seen:
                continue  # skip duplicate mappings (multiple audit rows for same port)
            seen.add(key)
            entries.append({
                "switch_port": key,
                "unit":        unit,
            })
        port_unit_files[addr] = entries

    # Write files locally and scp in one batch
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        for addr, entries in port_unit_files.items():
            (tmppath / f"{addr}_port_units.json").write_text(json.dumps(entries))

        files = list((tmppath).glob("*_port_units.json"))
        if not files:
            return

        file_args = " ".join(f'"{f}"' for f in files)
        r = subprocess.run(
            ["bash", "-c",
             f"scp -q {file_args} {REMOTE_HOST}:{JAKE_DATA_DIR}/nycha_building/"],
            capture_output=True,
        )
        if r.returncode != 0:
            print(f"WARNING: scp of port_unit files failed: {r.stderr.decode()}", file=sys.stderr)
        else:
            n_mapped = sum(len(v) for v in port_unit_files.values())
            print(f"  Port-unit mapping: {n_mapped} ports mapped across {len(port_unit_files)} buildings")


# ── Thresholds ────────────────────────────────────────────────────────────────

THRESH_UP_RATIO = {
    "mode": "absolute",
    "steps": [
        {"color": "#d44a3a", "value": None},
        {"color": "#e0b400", "value": 0.4},
        {"color": "#299c46", "value": 0.7},
    ],
}

THRESH_PORT_STATE = {
    "mode": "absolute",
    "steps": [
        {"color": "#d44a3a", "value": None},
        {"color": "#299c46", "value": 1},
    ],
}

THRESH_ERRORS = {
    "mode": "absolute",
    "steps": [
        {"color": "text",    "value": None},
        {"color": "#e0b400", "value": 1},
        {"color": "#d44a3a", "value": 100},
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard 1 — Developments overview
# ══════════════════════════════════════════════════════════════════════════════

def dev_stat_panel(panel_id: int, dev_name: str, fragments: list[str],
                   grid_x: int, grid_y: int) -> dict:
    """Stat card: Active CPE ports / Total CPE ports, colored by ratio."""
    re_str = addr_re(fragments)
    sel    = f'{CPE_PORT_FILTER},location_address=~"{re_str}"'

    # Active = has RX traffic in last 10m (CPE is passing data)
    active_expr = f'count(rate(mikrotik_switch_port_rx_bytes_total{{{sel}}}[10m]) > 0)'
    total_expr  = f'count(mikrotik_switch_port_rx_bytes_total{{{sel}}})'
    ratio_expr  = f'{active_expr} / {total_expr}'

    return {
        "id": panel_id, "type": "stat",
        "title": dev_name,
        "datasource": prom_ds(),
        "gridPos": {"h": 5, "w": 8, "x": grid_x, "y": grid_y},
        "targets": [
            {
                "datasource": prom_ds(), "refId": "A",
                "expr": active_expr,
                "legendFormat": "Active", "instant": True, "range": False,
            },
            {
                "datasource": prom_ds(), "refId": "T",
                "expr": total_expr,
                "legendFormat": "Total", "instant": True, "range": False,
            },
            {
                "datasource": prom_ds(), "refId": "R",
                "expr": ratio_expr,
                "legendFormat": "Ratio", "instant": True, "range": False,
                "hide": True,
            },
        ],
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode":    "value_and_name",
            "colorMode":   "background",
            "graphMode":   "none",
            "justifyMode": "center",
            "orientation": "horizontal",
            "text": {"titleSize": 12, "valueSize": 28},
        },
        "fieldConfig": {
            "defaults": {
                "color":      {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                "mappings":   [],
                "decimals":   0,
                "unit":       "short",
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": "Active"},
                    "properties": [
                        {"id": "color", "value": {"mode": "fixed", "fixedColor": "#299c46"}},
                    ],
                },
                {
                    "matcher": {"id": "byName", "options": "Total"},
                    "properties": [
                        {"id": "color", "value": {"mode": "fixed", "fixedColor": "#5794F2"}},
                    ],
                },
            ],
        },
        "links": [{
            "title": "Buildings",
            "url": f"/d/nycha-buildings/nycha-buildings?var-address=All",
            "targetBlank": False,
        }],
    }


def build_developments_dashboard() -> dict:
    panels = []
    devs = list(DEVELOPMENTS.items())
    for i, (dev_name, fragments) in enumerate(devs):
        col    = i % 3
        row    = i // 3
        grid_x = col * 8
        grid_y = row * 5
        panels.append(dev_stat_panel(i + 1, dev_name, fragments, grid_x, grid_y))

    return {
        "id": None, "uid": "nycha-developments",
        "title": "NYCHA — Developments",
        "description": "Live port state per development. Click a card to drill into buildings.",
        "tags": ["nycha", "live"],
        "schemaVersion": 39, "version": 1, "refresh": "5m",
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {}, "timezone": "browser",
        "fiscalYearStartMonth": 0, "graphTooltip": 0,
        "annotations": {"list": []}, "templating": {"list": []},
        "links": [{"title": "Buildings", "url": "/d/nycha-buildings", "type": "link",
                   "icon": "arrow-right", "targetBlank": False, "keepTime": False,
                   "tags": [], "asDropdown": False, "includeVars": False}],
        "panels": panels,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard 2 — Buildings (filtered by $development variable)
# ══════════════════════════════════════════════════════════════════════════════

def building_stat_panel(panel_id: int, grid_x: int, grid_y: int) -> dict:
    """One stat card per building — driven by $address repeat variable."""
    return {
        "id": panel_id, "type": "stat",
        "title": "$address",
        "datasource": prom_ds(),
        "gridPos": {"h": 5, "w": 8, "x": grid_x, "y": grid_y},
        "repeat": "address",
        "repeatDirection": "h",
        "maxPerRow": 3,
        "targets": [
            {
                "datasource": prom_ds(), "refId": "A",
                "expr": f'count(rate(mikrotik_switch_port_rx_bytes_total{{{CPE_PORT_FILTER},location_address=~"$address"}}[10m]) > 0)',
                "legendFormat": "Active", "instant": True, "range": False,
            },
            {
                "datasource": prom_ds(), "refId": "T",
                "expr": f'count(mikrotik_switch_port_rx_bytes_total{{{CPE_PORT_FILTER},location_address=~"$address"}})',
                "legendFormat": "Total", "instant": True, "range": False,
            },
        ],
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode":    "value_and_name",
            "colorMode":   "background",
            "graphMode":   "none",
            "justifyMode": "center",
            "orientation": "horizontal",
            "text": {"titleSize": 11, "valueSize": 26},
        },
        "fieldConfig": {
            "defaults": {
                "color":      {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                "mappings":   [],
                "decimals":   0,
                "unit":       "short",
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": "Active"},
                    "properties": [
                        {"id": "color", "value": {"mode": "fixed", "fixedColor": "#299c46"}},
                    ],
                },
                {
                    "matcher": {"id": "byName", "options": "Total"},
                    "properties": [
                        {"id": "color", "value": {"mode": "fixed", "fixedColor": "#5794F2"}},
                    ],
                },
            ],
        },
        "links": [{
            "title": "Port detail",
            "url": "/d/nycha-ports/nycha-port-detail?var-address=${__data.fields.address}",
            "targetBlank": False,
        }],
    }


def build_buildings_dashboard() -> dict:
    # $development variable: custom list of all development names
    dev_options = [
        {"selected": False, "text": name, "value": name}
        for name in DEVELOPMENTS
    ]
    dev_options[0]["selected"] = True

    # $address variable: query Prometheus for addresses matching $development
    # Uses label_values scoped to the regex for the selected development
    dev_var = {
        "name":        "development",
        "label":       "Development",
        "type":        "custom",
        "options":     dev_options,
        "current":     dev_options[0],
        "includeAll":  False,
        "multi":       False,
        "hide":        0,
    }

    # Build per-development regex strings for the address variable query
    # The address variable uses a Prometheus query scoped to $development
    # We map development name → fragments regex at query time using a long regex
    # that covers all addresses for the selected development.
    # Simpler: use a single label_values query filtered by the per-development regex.
    # The development custom var drives a text input which drives address query.

    addr_var = {
        "name":         "address",
        "label":        "Building",
        "type":         "query",
        "datasource":   prom_ds(),
        "query": {
            "query": f'label_values(mikrotik_switch_port_state{{{NYCHA_SITE_FILTER}}}, location_address)',
            "refId": "StandardVariableQuery",
        },
        "refresh":      2,
        "includeAll":   False,
        "multi":        True,
        "allValue":     ".*",
        "sort":         1,
        "hide":         0,
        "current":      {},
    }

    return {
        "id": None, "uid": "nycha-buildings",
        "title": "NYCHA — Buildings",
        "description": "Port state per building. Select a development to filter. Click a card to see port detail.",
        "tags": ["nycha", "live"],
        "schemaVersion": 39, "version": 1, "refresh": "5m",
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {}, "timezone": "browser",
        "fiscalYearStartMonth": 0, "graphTooltip": 0,
        "annotations": {"list": []},
        "templating": {"list": [addr_var]},
        "links": [
            {"title": "Developments", "url": "/d/nycha-developments", "type": "link",
             "icon": "arrow-left", "targetBlank": False, "keepTime": False,
             "tags": [], "asDropdown": False, "includeVars": False},
            {"title": "Port Detail", "url": "/d/nycha-ports", "type": "link",
             "icon": "arrow-right", "targetBlank": False, "keepTime": False,
             "tags": [], "asDropdown": False, "includeVars": False},
        ],
        "panels": [building_stat_panel(1, 0, 0)],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard 3 — Port detail ($address variable)
# ══════════════════════════════════════════════════════════════════════════════

def build_ports_dashboard() -> dict:
    addr_var = {
        "name":       "address",
        "label":      "Building",
        "type":       "query",
        "datasource": prom_ds(),
        "query": {
            "query": f'label_values(mikrotik_switch_port_state{{{NYCHA_SITE_FILTER}}}, location_address)',
            "refId": "StandardVariableQuery",
        },
        "refresh":    2,
        "includeAll": False,
        "multi":      False,
        "sort":       1,
        "hide":       0,
        "current":    {},
    }

    # Summary stats row
    summary_panels = [
        {
            "id": 1, "type": "stat",
            "title": "Active Ports",
            "datasource": prom_ds(),
            "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
            "targets": [{
                "datasource": prom_ds(), "refId": "A",
                "expr": f'count(rate(mikrotik_switch_port_rx_bytes_total{{{CPE_PORT_FILTER},location_address=~"$address"}}[10m]) > 0)',
                "instant": True, "range": False,
            }],
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "colorMode": "background", "graphMode": "none",
                "textMode": "auto", "justifyMode": "center",
                "text": {"titleSize": 14, "valueSize": 40},
            },
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "#299c46"},
                    "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                    "mappings": [], "decimals": 0,
                },
                "overrides": [],
            },
        },
        {
            "id": 2, "type": "stat",
            "title": "Inactive Ports",
            "datasource": prom_ds(),
            "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
            "targets": [{
                "datasource": prom_ds(), "refId": "I",
                "expr": f'count(rate(mikrotik_switch_port_rx_bytes_total{{{CPE_PORT_FILTER},location_address=~"$address"}}[10m]) == 0)',
                "instant": True, "range": False,
            }],
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "colorMode": "background", "graphMode": "none",
                "textMode": "auto", "justifyMode": "center",
                "text": {"titleSize": 14, "valueSize": 40},
            },
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "#d44a3a"},
                    "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                    "mappings": [], "decimals": 0,
                },
                "overrides": [],
            },
        },
        {
            "id": 3, "type": "stat",
            "title": "RX Errors",
            "datasource": prom_ds(),
            "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
            "targets": [{
                "datasource": prom_ds(), "refId": "E",
                "expr": f'sum(increase(mikrotik_switch_port_rx_errors_total{{{NYCHA_SITE_FILTER},location_address=~"$address"}}[10m]))',
                "instant": True, "range": False,
            }],
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "colorMode": "background", "graphMode": "none",
                "textMode": "auto", "justifyMode": "center",
                "text": {"titleSize": 14, "valueSize": 40},
            },
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "thresholds"},
                    "thresholds": THRESH_ERRORS,
                    "mappings": [], "decimals": 0,
                },
                "overrides": [],
            },
        },
        {
            "id": 4, "type": "stat",
            "title": "Total Ports",
            "datasource": prom_ds(),
            "gridPos": {"h": 4, "w": 6, "x": 18, "y": 0},
            "targets": [{
                "datasource": prom_ds(), "refId": "T",
                "expr": f'count(mikrotik_switch_port_state{{{NYCHA_SITE_FILTER},location_address=~"$address"}})',
                "instant": True, "range": False,
            }],
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "colorMode": "none", "graphMode": "none",
                "textMode": "auto", "justifyMode": "center",
                "text": {"titleSize": 14, "valueSize": 40},
            },
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "text"},
                    "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                    "mappings": [], "decimals": 0,
                },
                "overrides": [],
            },
        },
    ]

    # labelsToFields{columns} always names the value column "Value" regardless of legendFormat.
    # Multiple queries therefore all produce "Value" — merge collapses them incorrectly.
    # Solution: ONE query that encodes RX/TX/Errors into the PromQL result via label_join,
    # producing a composite label "rx_bps|tx_bps" is not possible in PromQL.
    #
    # Real solution: use label_replace to add a "direction" discriminator label to each
    # metric, then use `or` to combine them into one query. Each series will have a unique
    # "direction" label value (rx/tx), and labelsToFields will include "direction" as a column.
    # But this still gives us "Value" for the number — we'd need pivot which Grafana can't do.
    #
    # The actual correct path: use a Prometheus recording rule (server-side) that produces
    # a single metric with both rx and tx as labels. Without server changes, the only
    # reliable single-table approach is to compute a meaningful single value per port
    # in PromQL and show that. For operators, the most useful single value is:
    #   - traffic state: active (both dirs) / asymmetric (one dir) / dead (neither)
    # Encoded as: clamp(rate_rx > 0, 0, 1) * 2 + clamp(rate_tx > 0, 0, 1)
    #   = 3 → both active (green)
    #   = 2 → RX only (yellow)
    #   = 1 → TX only (yellow)
    #   = 0 → dead (red)
    #
    # Show this as a colored state column, plus the raw RX value for reference.
    # For full RX+TX detail: two separate panels.

    SEL = f'{CPE_PORT_FILTER},location_address=~"$address"'

    port_table = {
        "id": 10, "type": "table",
        "title": "Port Traffic — $address",
        "datasource": prom_ds(),
        "gridPos": {"h": 30, "w": 24, "x": 0, "y": 4},
        "targets": [
            {
                # label_join creates a composite "switch_port" label = device + "|" + port
                # This becomes the join key after labelsToFields, avoiding calculateField string concat
                "datasource": prom_ds(), "refId": "A",
                "expr": (
                    f'label_join(rate(mikrotik_switch_port_rx_bytes_total{{{SEL}}}[10m]) * 8,'
                    f' "switch_port", "|", "device", "port")'
                ),
                "instant": True, "range": False, "legendFormat": "",
            },
            {
                # Infinity: fetch per-building port→unit mapping written by build_port_unit_files()
                # switch_port field format: "000007.008.SW01|ether1"
                "datasource": infinity_ds(), "refId": "U",
                "type": "json", "source": "url", "format": "table",
                "parser": "backend",
                "url": f"{JAKE_DATA_URL}/nycha_building/${{address:raw}}_port_units.json",
                "url_options": {"method": "GET", "data": ""},
                "root_selector": "",
                "columns": [
                    {"selector": "switch_port", "text": "switch_port", "type": "string"},
                    {"selector": "unit",        "text": "unit",        "type": "string"},
                ],
                "filters": [],
                "json_options": {"columnar": False, "root_is_not_array": False},
                "global_query_id": "", "cacheTimeout": "0", "queryCachingTTL": 0,
            },
        ],
        "transformations": [
            # Step 1: Expand Prometheus label metadata into columns (one frame per series)
            {"id": "labelsToFields", "options": {"mode": "columns", "keepTime": False}},
            # Step 2: Stack all per-series frames into one table
            {"id": "merge", "options": {}},
            # Step 3: Join Prometheus table with Infinity unit-mapping on switch_port key
            {
                "id": "joinByField",
                "options": {"byField": "switch_port", "mode": "outer"},
            },
            # Step 4: Rename, reorder, drop noise columns
            {
                "id": "organize",
                "options": {
                    "renameByName": {
                        "device": "Switch", "port": "Port",
                        "Value": "RX", "unit": "Unit",
                    },
                    "excludeByName": {
                        "Time": True, "switch": True, "instance": True, "job": True,
                        "location_address": True, "location_id": True,
                        "role": True, "site_id": True, "switch_port": True,
                    },
                    "indexByName": {"device": 0, "port": 1, "unit": 2, "Value": 3},
                },
            },
        ],
        "options": {
            "showHeader": True, "cellHeight": "sm",
            "footer": {"show": True, "reducer": ["count"], "countRows": True},
        },
        "fieldConfig": {
            "defaults": {
                "custom": {"align": "left", "filterable": True,
                           "cellOptions": {"type": "plain"}},
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": "Switch"},
                    "properties": [
                        {"id": "custom.width", "value": 180},
                        {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}},
                        {"id": "color", "value": {"mode": "thresholds"}},
                        {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "#555555", "value": None}]}},
                        {"id": "mappings", "value": [
                            {"type": "regex", "options": {"pattern": r".*\.SW01$",  "result": {"color": "#1F60C4", "index": 0}}},
                            {"type": "regex", "options": {"pattern": r".*\.SW02$",  "result": {"color": "#8F3BB8", "index": 1}}},
                            {"type": "regex", "options": {"pattern": r".*\.SW03$",  "result": {"color": "#E05B14", "index": 2}}},
                            {"type": "regex", "options": {"pattern": r".*\.SW04$",  "result": {"color": "#1A7C4F", "index": 3}}},
                            {"type": "regex", "options": {"pattern": r".*\.SW05$",  "result": {"color": "#C4A000", "index": 4}}},
                            {"type": "regex", "options": {"pattern": r".*\.SW06$",  "result": {"color": "#0F7F7F", "index": 5}}},
                            {"type": "regex", "options": {"pattern": r".*\.SW07$",  "result": {"color": "#A0522D", "index": 6}}},
                            {"type": "regex", "options": {"pattern": r".*\.SW08$",  "result": {"color": "#3D6B8C", "index": 7}}},
                            {"type": "regex", "options": {"pattern": r".*\.SW09$",  "result": {"color": "#7B5EA7", "index": 8}}},
                            {"type": "regex", "options": {"pattern": r".*\.SW10$",  "result": {"color": "#B5553A", "index": 9}}},
                            {"type": "regex", "options": {"pattern": r".*\.SW11$",  "result": {"color": "#2E7D32", "index": 10}}},
                            {"type": "regex", "options": {"pattern": r"^000020\.",  "result": {"color": "#5794F2", "index": 11}}},
                        ]},
                    ],
                },
                {
                    "matcher": {"id": "byName", "options": "Port"},
                    "properties": [{"id": "custom.width", "value": 75}],
                },
                {
                    "matcher": {"id": "byName", "options": "Unit"},
                    "properties": [{"id": "custom.width", "value": 60}],
                },
                {
                    "matcher": {"id": "byName", "options": "RX"},
                    "properties": [
                        {"id": "unit", "value": "bps"},
                        {"id": "decimals", "value": 1},
                        {"id": "custom.width", "value": 120},
                        {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}},
                        {"id": "color", "value": {"mode": "thresholds"}},
                        {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                            {"color": "#d44a3a", "value": None},
                            {"color": "#299c46", "value": 8},
                        ]}},
                    ],
                },
            ],
        },
    }

    return {
        "id": None, "uid": "nycha-ports",
        "title": "NYCHA — Port Detail",
        "description": "Live per-port state and traffic. Select a building with the $address variable.",
        "tags": ["nycha", "live"],
        "schemaVersion": 39, "version": 1, "refresh": "1m",
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {}, "timezone": "browser",
        "fiscalYearStartMonth": 0, "graphTooltip": 0,
        "annotations": {"list": []},
        "templating": {"list": [addr_var]},
        "links": [
            {"title": "Buildings", "url": "/d/nycha-buildings", "type": "link",
             "icon": "arrow-left", "targetBlank": False, "keepTime": False,
             "tags": [], "asDropdown": False, "includeVars": False},
        ],
        "panels": summary_panels + [port_table],
    }


def push(dash: dict, label: str) -> None:
    resp = grafana_post({"dashboard": dash, "overwrite": True, "folderId": 0})
    if resp.get("status") == "success":
        print(f"  {label}: {resp.get('url')}")
    else:
        print(f"  ERROR {label}: {resp}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    print("Pushing NYCHA live dashboards...")
    print("Building port-unit mapping files...")
    build_port_unit_files()
    push(build_developments_dashboard(), "Developments")
    push(build_buildings_dashboard(),    "Buildings")
    push(build_ports_dashboard(),        "Port Detail")
    print("Done.")


if __name__ == "__main__":
    main()
