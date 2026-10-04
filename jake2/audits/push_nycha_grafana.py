#!/usr/bin/env python3
"""Push NYCHA readiness data to Grafana as inline dashboards.

Usage:
    .venv/bin/python audits/push_nycha_grafana.py

Runs live audit via JakeOps for all buildings, then pushes two inline dashboards:
  nycha-cpe-readiness      — main dashboard (phases, devs, building table)
  nycha-building-detail    — single building detail dashboard (all rows inline,
                             filtered by $address custom dropdown variable)
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
XLSX_DIR = PROJECT_ROOT / "output" / "spreadsheet"

# Development -> Phase mapping derived from NYCHA project structure.
# Update this if new phases or developments are added.
DEV_TO_PHASE: dict[str, int] = {
    "1. 104-14 Tapscott":               3,
    "2. Fenimore-Lefferts":             2,
    "3. Lenox Rd - Rockaway Pkwy":      2,
    "4. Ralph Ave Rehab":               3,
    "5. Reid Apartments":               1,
    "6. Rutland Towers":                1,
    "7. Sutter Ave - Union St":         3,
    "8. Tapscott St Rehab":             3,
    "9. Crown Heights":                 5,
    "10. Howard Ave":                   4,
    "11. Howard Ave - Park Pl":         4,
    "12. Oceanhill - Brownsville":      5,
    "13. Park Rock Rehab":              5,
    "14. Sterling Place - Saint Johns": 5,
    "15. Sterling Place - Buffalo":     5,
}

# Address → development name. Derived from building prefix groupings in NetBox.
# This replaces the nycha_info.csv dependency for phase/development metadata.
ADDR_TO_DEV: dict[str, str] = {
    # 1. 104-14 Tapscott (phase 3)
    "104 Tapscott St":              "1. 104-14 Tapscott",
    "170 Tapscott St":              "1. 104-14 Tapscott",
    "175 Tapscott St":              "1. 104-14 Tapscott",
    "184 Tapscott St":              "1. 104-14 Tapscott",
    "187 Tapscott St":              "1. 104-14 Tapscott",
    "192 Tapscott St":              "1. 104-14 Tapscott",
    "199 Tapscott St":              "1. 104-14 Tapscott",
    "32-48 Grafton St":             "1. 104-14 Tapscott",
    "1-17 Tapscott St":             "1. 104-14 Tapscott",
    # 2. Fenimore-Lefferts (phase 2)
    "726-752 Fenimore":             "2. Fenimore-Lefferts",
    "334-344 Lefferts":             "2. Fenimore-Lefferts",
    # 3. Lenox Rd - Rockaway Pkwy (phase 2)
    "1142 Lenox Rd":                "3. Lenox Rd - Rockaway Pkwy",
    "1144 Lenox Rd":                "3. Lenox Rd - Rockaway Pkwy",
    "1145 Lenox Rd":                "3. Lenox Rd - Rockaway Pkwy",
    "1196 East New York Ave":       "3. Lenox Rd - Rockaway Pkwy",
    # 4. Ralph Ave Rehab (phase 3)
    "537 Ralph Ave":                "4. Ralph Ave Rehab",
    "672 Ralph Ave":                "4. Ralph Ave Rehab",
    "682 Ralph Ave":                "4. Ralph Ave Rehab",
    "692 Ralph Ave":                "4. Ralph Ave Rehab",
    "698 Ralph Ave":                "4. Ralph Ave Rehab",
    # 5. Reid Apartments (phase 1)
    "728 East New York Ave":        "5. Reid Apartments",
    # 6. Rutland Towers (phase 1)
    "955 Rutland Rd":               "6. Rutland Towers",
    # 7. Sutter Ave - Union St (phase 3)
    "2020 Pacific St":              "7. Sutter Ave - Union St",
    "2041 Pacific St":              "7. Sutter Ave - Union St",
    "2045 Union St":                "7. Sutter Ave - Union St",
    "2058 Union St":                "7. Sutter Ave - Union St",
    "2065 Dean St":                 "7. Sutter Ave - Union St",
    "2069 Union St":                "7. Sutter Ave - Union St",
    # 8. Tapscott St Rehab (phase 3) — same site as 104-14 Tapscott
    # 9. Crown Heights (phase 5)
    "1367 Saint Marks Ave":         "9. Crown Heights",
    "1371 Saint Marks Ave":         "9. Crown Heights",
    "1448 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1452 Sterling Pl":             "14. Sterling Place - Saint Johns",
    # 10. Howard Ave (phase 4)
    "324 Howard Ave":               "10. Howard Ave",
    "334 Howard Ave":               "10. Howard Ave",
    "497 Howard Ave":               "10. Howard Ave",
    "574-582 Howard Ave":           "10. Howard Ave",
    "583-611 Howard Ave":           "10. Howard Ave",
    "602-614 Howard Ave":           "10. Howard Ave",
    "725 Howard Ave":               "10. Howard Ave",
    "726 Howard Ave":               "10. Howard Ave",
    "728 Howard Ave":               "10. Howard Ave",
    "504 Howard Ave":               "10. Howard Ave",
    # 11. Howard Ave - Park Pl (phase 4)
    "1468 Park Pl":                 "11. Howard Ave - Park Pl",
    "1474 Park Pl":                 "11. Howard Ave - Park Pl",
    "1480 Park Pl":                 "11. Howard Ave - Park Pl",
    "1629 Park Pl":                 "11. Howard Ave - Park Pl",
    "1630 Park Pl":                 "11. Howard Ave - Park Pl",
    "1636 Park Pl":                 "11. Howard Ave - Park Pl",
    "1640 Park Pl":                 "11. Howard Ave - Park Pl",
    "1646 Park Pl":                 "11. Howard Ave - Park Pl",
    # 12. Oceanhill - Brownsville (phase 5)
    "208 Rochester Ave":            "12. Oceanhill - Brownsville",
    "218 Rochester Ave":            "12. Oceanhill - Brownsville",
    "232 Rochester Ave":            "12. Oceanhill - Brownsville",
    "234 Rochester Ave":            "12. Oceanhill - Brownsville",
    "225 Buffalo Ave":              "15. Sterling Place - Buffalo",
    # 13. Park Rock Rehab (phase 5)
    # 14. Sterling Place - Saint Johns (phase 5)
    "1483 Saint Johns Pl":          "14. Sterling Place - Saint Johns",
    "1491 Saint Johns Pl":          "14. Sterling Place - Saint Johns",
    "1506 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1511 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1521 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1522 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1568 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1578 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1588 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1598 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1679 Saint Johns Pl":          "14. Sterling Place - Saint Johns",
    "1720 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1761 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1766 Sterling Pl":             "14. Sterling Place - Saint Johns",
    "1790 Sterling Pl":             "14. Sterling Place - Saint Johns",
    # 15. Sterling Place - Buffalo (phase 5)
    "1634 Sterling Pl":             "15. Sterling Place - Buffalo",
    "1636 Sterling Pl":             "15. Sterling Place - Buffalo",
    "1640 Sterling Pl":             "15. Sterling Place - Buffalo",
}
REMOTE_HOST = "grafana_prometheus"
GRAFANA_HOST = "localhost:3000"
GRAFANA_AUTH = "admin:happySt3el49"
DS_UID = "jake-nycha"
JAKE_DATA_DIR = "/home/jonathan/jake-data"
JAKE_DATA_URL = "http://172.22.0.1:9099"

THRESHOLDS = {
    "mode": "absolute",
    "steps": [
        {"color": "#d44a3a", "value": None},
        {"color": "#e0b400", "value": 40},
        {"color": "#299c46", "value": 70},
    ],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def ds():
    return {"type": "yesoreyeram-infinity-datasource", "uid": DS_UID}


def inline_query(ref_id, data_str, columns, root_selector="", filters=None):
    return {
        "datasource": ds(), "refId": ref_id, "type": "json", "source": "inline",
        "data": data_str, "root_selector": root_selector, "format": "table",
        "parser": "backend", "columns": columns, "filters": filters or [],
        "url_options": {"method": "GET", "data": ""},
        "json_options": {"columnar": False, "root_is_not_array": False},
        "global_query_id": "",
        "cacheTimeout": "0",
        "queryCachingTTL": 0,
    }


def _safe_filename(address: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", address).strip("_")


def grafana_post(payload: dict) -> dict:
    """POST dashboard payload to Grafana via SCP + SSH."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        tmp = Path(f.name)
    try:
        r = subprocess.run(
            ["scp", "-q", str(tmp), f"{REMOTE_HOST}:/tmp/_grafana_push.json"],
            capture_output=True,
        )
        if r.returncode != 0:
            print(f"SCP failed: {r.stderr}", file=sys.stderr)
            return {}
        cmd = (
            f"curl -s -X POST "
            f"http://{GRAFANA_AUTH}@{GRAFANA_HOST}/api/dashboards/db "
            f"-H \"Content-Type: application/json\" "
            f"-d @/tmp/_grafana_push.json"
        )
        result = subprocess.run(["ssh", REMOTE_HOST, cmd], capture_output=True, text=True)
        return json.loads(result.stdout) if result.stdout.strip() else {}
    finally:
        tmp.unlink(missing_ok=True)


def upload_building_json_files(buildings: list[dict], all_rows: list[dict]) -> None:
    """Write per-building JSON files to the jake-data HTTP server on the remote host.

    Each building gets two files:
      nycha_building/{filename}_rows.json  — unit audit rows (list)
      nycha_building/{filename}_meta.json  — single-item list with meta fields

    These are fetched by the detail dashboard via URL source, which re-fetches on
    every variable change — solving the inline-data-doesn't-refilter problem.
    """
    rows_by_addr: dict[str, list[dict]] = {}
    for row in all_rows:
        rows_by_addr.setdefault(row["address"], []).append(row)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        for b in buildings:
            addr = b["address"]
            rows = rows_by_addr.get(addr, [])
            meta = [{"address": addr, "ready_pct": b.get("ready_pct", 0),
                     "development": b["development"], "phase": b["phase"]}]
            # Named by raw address — SimpleHTTPServer decodes %20 to spaces on request.
            # ${address:raw} in the Grafana URL passes the value as-is (spaces → %20 by browser).
            (tmppath / f"{addr}_rows.json").write_text(json.dumps(rows))
            (tmppath / f"{addr}_meta.json").write_text(json.dumps(meta))

        # scp contents of tmpdir into remote nycha_building/ directory
        r = subprocess.run(
            ["bash", "-c",
             f"scp -q {tmppath}/*_rows.json {tmppath}/*_meta.json {REMOTE_HOST}:{JAKE_DATA_DIR}/nycha_building/"],
            capture_output=True,
        )
        if r.returncode != 0:
            print(f"WARNING: scp of building JSON files failed: {r.stderr.decode()}", file=sys.stderr)
        else:
            print(f"  Uploaded {len(buildings) * 2} building JSON files to {REMOTE_HOST}:{JAKE_DATA_DIR}/nycha_building/")


def grafana_get_dashboard_urls() -> dict[str, str]:
    """Return uid -> url map for all NYCHA building dashboards."""
    result = subprocess.run(
        ["ssh", REMOTE_HOST,
         f"curl -s 'http://{GRAFANA_AUTH}@{GRAFANA_HOST}/api/search?type=dash-db&query=NYCHA+Audit&limit=200'"],
        capture_output=True, text=True,
    )
    results = json.loads(result.stdout) if result.stdout.strip() else []
    return {r["uid"]: r["url"] for r in results}


# ── Data loading ──────────────────────────────────────────────────────────────

def load_buildings() -> list[dict]:
    """Discover all NYCHA buildings from nycha_expected_units.json (authoritative unit roster).

    nycha_expected_units.json is the network-derived source of truth for which buildings
    and units exist. nycha_info.csv is consulted only to enrich phase/development metadata
    where available — it is not required.
    """
    expected_path = PROJECT_ROOT / "data" / "nycha_expected_units.json"
    if not expected_path.exists():
        print(f"ERROR: {expected_path} not found", file=sys.stderr)
        sys.exit(1)

    import json as _json
    addresses: list[str] = sorted(_json.loads(expected_path.read_text()).keys())
    if not addresses:
        print("ERROR: nycha_expected_units.json is empty", file=sys.stderr)
        sys.exit(1)

    buildings = []
    for address in addresses:
        development = ADDR_TO_DEV.get(address, "Unknown")
        phase = DEV_TO_PHASE.get(development, 9)
        buildings.append({
            "phase": phase,
            "development": development,
            "address": address,
            "filename": _safe_filename(address),
            "ready_pct": 0,
        })

    buildings.sort(key=lambda b: (b["phase"], b["development"], b["address"]))
    print(f"Discovered {len(buildings)} buildings from nycha_expected_units.json")
    return buildings


def load_rows_from_xlsx(address: str) -> list[dict]:
    """Read per-unit audit rows from the existing xlsx generated by the batch audit."""
    xlsx_path = XLSX_DIR / f"{address}_audit.xlsx"
    if not xlsx_path.exists():
        return []
    try:
        from openpyxl import load_workbook
        wb = load_workbook(xlsx_path, data_only=True)
        ws = wb.active
        headers = None
        rows = []
        for row in ws.iter_rows(values_only=True):
            if headers is None:
                if any(str(c).strip() == "Unit" for c in row if c):
                    headers = [str(c).strip() if c else "" for c in row]
                continue
            if not any(c for c in row if c is not None):
                continue
            r = dict(zip(headers, row))
            unit = r.get("Unit") or r.get("unit")
            if not unit:
                continue
            notes = str(r.get("Notes - On Site") or r.get("Notes") or "")
            if notes in ("GOOD", "Live online", "Live online via router evidence"):
                state = "green"
            elif notes in ("WRONG UNIT", "MOVE CPE TO CORRECT UNIT", "MOVE CPE TO WAN PORT",
                           "UNKNOWN MAC ON PORT", "UNPLUGGED / BAD CABLE"):
                state = "yellow"
            else:
                state = "red"
            rows.append({
                "unit": str(unit),
                "notes": notes,
                "image_ap_make": str(r.get("Image AP Make") or ""),
                "mac_cpe": str(r.get("MAC (Inventory/CSV)") or ""),
                "pppoe_unit": str(r.get("PPPoE Unit") or ""),
                "inventory_mac_verification": str(r.get("Inventory MAC Verification") or ""),
                "implication": str(r.get("Implication") or ""),
                "action": str(r.get("Action") or ""),
                "state": state,
            })
        return rows
    except Exception as e:
        print(f"  WARNING: could not read {xlsx_path}: {e}", file=sys.stderr)
        return []


# ── Aggregations ──────────────────────────────────────────────────────────────

def build_phase_summary(buildings: list[dict]) -> list[dict]:
    # Weighted by unit count: sum(green_units) / sum(total_units) per phase
    buckets: dict[int, dict] = defaultdict(lambda: {"green": 0, "total": 0, "count": 0})
    for b in buildings:
        p = b["phase"]
        buckets[p]["green"] += b.get("green_units", 0)
        buckets[p]["total"] += b.get("total_units", 0)
        buckets[p]["count"] += 1
    phases = []
    for p in sorted(buckets):
        info = buckets[p]
        avg = round(info["green"] / info["total"] * 100) if info["total"] else 0
        phases.append({"label": f"Phase {p}", "phase": p,
                        "avg_pct": avg, "count": info["count"]})
    total_green = sum(b.get("green_units", 0) for b in buildings)
    total_units = sum(b.get("total_units", 0) for b in buildings)
    overall = round(total_green / total_units * 100) if total_units else 0
    phases.append({"label": "Overall", "phase": 0,
                   "avg_pct": overall, "count": len(buildings)})
    return phases


def build_dev_summary(buildings: list[dict]) -> list[dict]:
    # Weighted by unit count: sum(green_units) / sum(total_units) per development
    buckets: dict[str, dict] = {}
    for b in buildings:
        dev = b["development"]
        if dev not in buckets:
            buckets[dev] = {"phase": b["phase"], "green": 0, "total": 0, "count": 0}
        buckets[dev]["green"] += b.get("green_units", 0)
        buckets[dev]["total"] += b.get("total_units", 0)
        buckets[dev]["count"] += 1
    devs = []
    for dev, info in buckets.items():
        avg = round(info["green"] / info["total"] * 100) if info["total"] else 0
        devs.append({"development": dev, "phase": info["phase"],
                     "avg_pct": avg, "count": info["count"]})
    devs.sort(key=lambda x: (x["phase"], x["development"]))
    return devs


# ── Dashboard builders ────────────────────────────────────────────────────────

ROW_COLS = [
    {"selector": "unit",                       "text": "Unit",         "type": "string"},
    {"selector": "notes",                      "text": "Status",       "type": "string"},
    {"selector": "image_ap_make",              "text": "Make",         "type": "string"},
    {"selector": "mac_cpe",                    "text": "MAC CPE",      "type": "string"},
    {"selector": "pppoe_unit",                 "text": "PPPoE",        "type": "string"},
    {"selector": "inventory_mac_verification", "text": "Verification", "type": "string"},
    {"selector": "implication",                "text": "Implication",  "type": "string"},
    {"selector": "action",                     "text": "Action",       "type": "string"},
    {"selector": "state",                      "text": "state",        "type": "string"},
]

TABLE_OVERRIDES = [
    {"matcher": {"id": "byName", "options": "Unit"},
     "properties": [{"id": "custom.width", "value": 70}]},
    {"matcher": {"id": "byName", "options": "Status"}, "properties": [
        {"id": "custom.width", "value": 180},
        {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}},
        {"id": "mappings", "value": [{"type": "value", "options": {
            "Good":                              {"color": "#299c46", "index": 0},
            "GOOD":                              {"color": "#299c46", "index": 1},
            "Live online":                       {"color": "#299c46", "index": 2},
            "LIVE ONLINE":                       {"color": "#299c46", "index": 3},
            "Live online via router evidence":   {"color": "#299c46", "index": 4},
            "LIVE ONLINE VIA ROUTER EVIDENCE":   {"color": "#299c46", "index": 5},
            "WRONG UNIT":                        {"color": "#e0b400", "index": 6},
            "MOVE CPE TO CORRECT UNIT":          {"color": "#e0b400", "index": 7},
            "MOVE CPE TO WAN PORT":              {"color": "#e0b400", "index": 8},
            "UNKNOWN MAC ON PORT":               {"color": "#e0b400", "index": 9},
            "UNPLUGGED / BAD CABLE":             {"color": "#e0b400", "index": 10},
            "CONTROLLER MISMATCH":               {"color": "#e0b400", "index": 11},
            "PPPOE LABEL MISMATCH":              {"color": "#e0b400", "index": 12},
            "CONTROLLER VERIFIED":               {"color": "#d44a3a", "index": 13},
            "NOT INSTALLED":                     {"color": "#d44a3a", "index": 14},
            "LIVE LOOKUP FAILED":                {"color": "#d44a3a", "index": 15},
            "NO LIVE EVIDENCE":                  {"color": "#d44a3a", "index": 16},
        }}]},
    ]},
    {"matcher": {"id": "byName", "options": "Make"},
     "properties": [{"id": "custom.width", "value": 80}]},
    {"matcher": {"id": "byName", "options": "MAC CPE"},
     "properties": [{"id": "custom.width", "value": 150}]},
    {"matcher": {"id": "byName", "options": "PPPoE"},
     "properties": [{"id": "custom.width", "value": 80}]},
    {"matcher": {"id": "byName", "options": "Verification"}, "properties": [
        {"id": "custom.width", "value": 130},
        {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}},
        {"id": "mappings", "value": [{"type": "value", "options": {
            "Match":              {"color": "#299c46", "index": 0},
            "Bug-adjusted match": {"color": "#299c46", "index": 1},
            "Mismatch":           {"color": "#d44a3a", "index": 2},
            "LAN-port MAC":       {"color": "#e0b400", "index": 3},
        }}]},
    ]},
    {"matcher": {"id": "byName", "options": "Implication"},
     "properties": [{"id": "custom.width", "value": 340}]},
    {"matcher": {"id": "byName", "options": "Action"},
     "properties": [{"id": "custom.width", "value": 200}]},
    {"matcher": {"id": "byName", "options": "state"},
     "properties": [{"id": "custom.hidden", "value": True}]},
]


def build_building_dashboard(b: dict, rows: list[dict]) -> dict:
    meta_data = json.dumps([{
        "ready_pct": b["ready_pct"],
        "development": b["development"],
        "phase": b["phase"],
    }])
    rows_data = json.dumps(rows)
    address = b["address"]

    return {
        "id": None,
        "uid": f"nycha-bld-{b['filename'][:40]}",
        "title": f"NYCHA Audit \u2014 {address}",
        "tags": ["nycha", "cpe", "building"],
        "schemaVersion": 39, "version": 1, "refresh": "",
        "time": {"from": "2020-01-01T00:00:00.000Z", "to": "2030-01-01T00:00:00.000Z"},
        "timepicker": {"hidden": True},
        "timezone": "browser", "fiscalYearStartMonth": 0, "graphTooltip": 0,
        "links": [{"title": "Back to Readiness Dashboard",
                   "url": "/d/nycha-cpe-readiness/nycha-cpe-deployment-readiness",
                   "type": "link", "icon": "arrow-left", "targetBlank": False,
                   "keepTime": False, "tags": [], "asDropdown": False, "includeVars": False}],
        "annotations": {"list": []},
        "templating": {"list": []},
        "panels": [
            {
                "id": 1, "type": "stat", "title": "Readiness", "datasource": ds(),
                "gridPos": {"h": 4, "w": 4, "x": 0, "y": 0},
                "targets": [inline_query("R", meta_data, [{"selector": "ready_pct", "text": "ready_pct", "type": "number"}])],
                "transformations": [],
                "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                            "textMode": "auto", "colorMode": "background", "graphMode": "none",
                            "justifyMode": "center", "text": {"titleSize": 14, "valueSize": 48}},
                "fieldConfig": {"defaults": {"unit": "percent", "decimals": 0, "thresholds": THRESHOLDS,
                                             "color": {"mode": "thresholds"}, "mappings": [], "min": 0, "max": 100},
                                "overrides": []},
            },
            {
                "id": 2, "type": "stat", "title": "Development", "datasource": ds(),
                "gridPos": {"h": 4, "w": 12, "x": 4, "y": 0},
                "targets": [inline_query("D", meta_data, [{"selector": "development", "text": "development", "type": "string"}])],
                "transformations": [],
                "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                            "textMode": "auto", "colorMode": "none", "graphMode": "none",
                            "justifyMode": "auto", "text": {"titleSize": 14, "valueSize": 20}},
                "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "text"},
                                             "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                                             "mappings": []}, "overrides": []},
            },
            {
                "id": 3, "type": "stat", "title": "Phase", "datasource": ds(),
                "gridPos": {"h": 4, "w": 4, "x": 16, "y": 0},
                "targets": [inline_query("P", meta_data, [{"selector": "phase", "text": "phase", "type": "number"}])],
                "transformations": [],
                "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                            "textMode": "auto", "colorMode": "none", "graphMode": "none",
                            "justifyMode": "center", "text": {"titleSize": 14, "valueSize": 36}},
                "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "text"},
                                             "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                                             "mappings": [], "decimals": 0, "unit": "short"}, "overrides": []},
            },
            {
                "id": 9, "type": "text", "title": "",
                "gridPos": {"h": 4, "w": 4, "x": 20, "y": 0},
                "options": {"mode": "html", "content":
                    '<div style="padding:8px;font-size:13px;line-height:2">'
                    '<span style="color:#299c46;font-weight:bold">&#9632; Green</span> \u2014 CPE confirmed good<br>'
                    '<span style="color:#e0b400;font-weight:bold">&#9632; Yellow</span> \u2014 Needs move / attention<br>'
                    '<span style="color:#d44a3a;font-weight:bold">&#9632; Red</span> \u2014 Not installed / missing'
                    '</div>', "transparent": True},
            },
            {
                "id": 10, "type": "table", "title": f"Unit Audit \u2014 {address}",
                "datasource": ds(),
                "gridPos": {"h": 28, "w": 24, "x": 0, "y": 4},
                "targets": [inline_query("A", rows_data, ROW_COLS)],
                "transformations": [{"id": "organize", "options": {
                    "indexByName": {"Unit": 0, "Status": 1, "Make": 2, "MAC CPE": 3,
                                    "PPPoE": 4, "Verification": 5, "Implication": 6, "Action": 7, "state": 8},
                }}],
                "options": {"cellHeight": "sm", "showHeader": True,
                            "footer": {"show": False, "enablePagination": False}},
                "fieldConfig": {
                    "defaults": {"custom": {"align": "left", "cellOptions": {"type": "auto"},
                                            "filterable": True, "minWidth": 80},
                                 "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                                 "mappings": []},
                    "overrides": TABLE_OVERRIDES,
                },
            },
        ],
    }


def build_main_dashboard(buildings: list[dict], phases: list[dict], devs: list[dict],
                         url_map: dict[str, str]) -> dict:
    # Add url to each building entry
    buildings_with_url = []
    for b in buildings:
        uid = f"nycha-bld-{b['filename'][:40]}"
        entry = dict(b)
        entry["url"] = url_map.get(uid, "")
        buildings_with_url.append(entry)

    phases_inline = json.dumps(phases)
    devs_inline = json.dumps(devs)
    buildings_inline = json.dumps(buildings_with_url)

    PHASE_COLS = [
        {"selector": "label", "text": "label", "type": "string"},
        {"selector": "avg_pct", "text": "avg_pct", "type": "number"},
    ]
    DEV_COLS = [
        {"selector": "development", "text": "Development", "type": "string"},
        {"selector": "avg_pct", "text": "Ready %", "type": "number"},
    ]
    BUILDING_COLS = [
        {"selector": "phase",       "text": "phase",       "type": "number"},
        {"selector": "development", "text": "development", "type": "string"},
        {"selector": "address",     "text": "address",     "type": "string"},
        {"selector": "url",         "text": "url",         "type": "string"},
        {"selector": "ready_pct",   "text": "ready_pct",   "type": "number"},
    ]

    def stat_panel(panel_id, title, ref_id, phase_label, x_pos):
        return {
            "id": panel_id, "type": "stat", "title": title, "datasource": ds(),
            "gridPos": {"h": 4, "w": 4, "x": x_pos, "y": 1},
            "targets": [inline_query(ref_id, phases_inline, PHASE_COLS)],
            "transformations": [{"id": "filterByValue", "options": {
                "filters": [{"fieldName": "label", "config": {"id": "equal", "options": {"value": phase_label}}}],
                "match": "all", "type": "include",
            }}],
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "/^avg_pct$/", "values": False},
                "orientation": "auto", "textMode": "auto", "colorMode": "background",
                "graphMode": "none", "justifyMode": "center",
                "text": {"titleSize": 16, "valueSize": 40},
            },
            "fieldConfig": {
                "defaults": {"unit": "percent", "decimals": 0, "thresholds": THRESHOLDS,
                             "color": {"mode": "thresholds"}, "mappings": [], "min": 0, "max": 100},
                "overrides": [],
            },
        }

    address_link = [{"title": "View building audit",
                     "url": "/d/nycha-building-detail/nycha-building-audit-detail?var-address=${__data.fields.Address}",
                     "targetBlank": False}]

    return {
        "id": None, "uid": "nycha-cpe-readiness",
        "title": "NYCHA CPE Deployment Readiness",
        "description": "CPE deployment readiness by Phase, Development, and Building",
        "tags": ["nycha", "cpe", "deployment"],
        "schemaVersion": 39, "version": 1, "refresh": "",
        "time": {"from": "now-6h", "to": "now"}, "timepicker": {},
        "timezone": "browser", "fiscalYearStartMonth": 0, "graphTooltip": 0,
        "links": [], "annotations": {"list": []},
        "panels": [
            {"id": 10, "type": "row", "title": "Phase Summary", "collapsed": False,
             "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0}},
            stat_panel(21, "Phase 1", "P1", "Phase 1", 0),
            stat_panel(22, "Phase 2", "P2", "Phase 2", 4),
            stat_panel(23, "Phase 3", "P3", "Phase 3", 8),
            stat_panel(24, "Phase 4", "P4", "Phase 4", 12),
            stat_panel(25, "Phase 5", "P5", "Phase 5", 16),
            stat_panel(26, "Overall",  "ALL", "Overall",  20),
            {"id": 30, "type": "row", "title": "Readiness by Development", "collapsed": False,
             "gridPos": {"h": 1, "w": 24, "x": 0, "y": 5}},
            {
                "id": 31, "type": "bargauge", "title": "Development Readiness",
                "datasource": ds(),
                "gridPos": {"h": 14, "w": 24, "x": 0, "y": 6},
                "targets": [inline_query("D", devs_inline, DEV_COLS)],
                "transformations": [],
                "options": {
                    "displayMode": "lcd", "orientation": "horizontal", "namePlacement": "left",
                    "showUnfilled": True, "valueMode": "color", "sizing": "auto",
                    "minVizHeight": 40, "maxVizHeight": 300, "minVizWidth": 0,
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "/^Ready %$/", "values": True},
                    "legend": {"displayMode": "hidden", "placement": "bottom"},
                },
                "fieldConfig": {
                    "defaults": {"unit": "percent", "decimals": 0, "min": 0, "max": 100,
                                 "thresholds": THRESHOLDS, "color": {"mode": "thresholds"}, "mappings": []},
                    "overrides": [],
                },
            },
            {"id": 40, "type": "row", "title": "Building Detail", "collapsed": False,
             "gridPos": {"h": 1, "w": 24, "x": 0, "y": 20}},
            {
                "id": 41, "type": "table", "title": "All Buildings",
                "description": "Click an address to view building audit detail",
                "datasource": ds(),
                "gridPos": {"h": 22, "w": 16, "x": 0, "y": 21},
                "targets": [inline_query("T", buildings_inline, BUILDING_COLS)],
                "transformations": [
                    {"id": "organize", "options": {
                        "renameByName": {"phase": "Phase", "development": "Development",
                                         "address": "Address", "url": "url", "ready_pct": "Ready %"},
                        "indexByName": {"phase": 0, "development": 1, "address": 2, "url": 3, "ready_pct": 4},
                        "excludeByName": {"url": True},
                    }},
                    {"id": "sortBy", "options": {"fields": [{"desc": False, "displayName": "Phase"}]}},
                ],
                "options": {"cellHeight": "sm", "showHeader": True,
                            "footer": {"show": False, "enablePagination": False}},
                "fieldConfig": {
                    "defaults": {"custom": {"align": "left", "cellOptions": {"type": "auto"}, "filterable": True},
                                 "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                                 "mappings": []},
                    "overrides": [
                        {"matcher": {"id": "byName", "options": "Ready %"}, "properties": [
                            {"id": "unit", "value": "percent"}, {"id": "min", "value": 0}, {"id": "max", "value": 100},
                            {"id": "custom.width", "value": 180},
                            {"id": "custom.cellOptions", "value": {"mode": "gradient", "type": "gauge", "valueDisplayMode": "text"}},
                            {"id": "thresholds", "value": THRESHOLDS},
                        ]},
                        {"matcher": {"id": "byName", "options": "Phase"},
                         "properties": [{"id": "custom.width", "value": 65}]},
                        {"matcher": {"id": "byName", "options": "Development"},
                         "properties": [{"id": "custom.width", "value": 260}]},
                        {"matcher": {"id": "byName", "options": "Address"}, "properties": [
                            {"id": "custom.width", "value": 200},
                            {"id": "links", "value": address_link},
                        ]},
                    ],
                },
            },
            {
                "id": 42, "type": "table", "title": "Needs Attention  (< 40%)",
                "datasource": ds(),
                "gridPos": {"h": 22, "w": 8, "x": 16, "y": 21},
                "targets": [inline_query("NA", buildings_inline, BUILDING_COLS)],
                "transformations": [
                    {"id": "filterByValue", "options": {
                        "filters": [{"fieldName": "ready_pct", "config": {"id": "lower", "options": {"value": 40}}}],
                        "match": "all", "type": "include",
                    }},
                    {"id": "organize", "options": {
                        "renameByName": {"phase": "Ph", "development": "Dev", "address": "Address",
                                         "url": "url", "ready_pct": "Ready %"},
                        "indexByName": {"phase": 0, "development": 1, "address": 2, "url": 3, "ready_pct": 4},
                        "excludeByName": {"development": True, "url": True},
                    }},
                    {"id": "sortBy", "options": {"fields": [{"desc": False, "displayName": "Ready %"}]}},
                ],
                "options": {"cellHeight": "sm", "showHeader": True,
                            "footer": {"show": True, "reducer": ["count"], "countRows": True,
                                       "enablePagination": False, "fields": ""}},
                "fieldConfig": {
                    "defaults": {"custom": {"align": "left", "cellOptions": {"type": "auto"}, "filterable": False},
                                 "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                                 "mappings": []},
                    "overrides": [
                        {"matcher": {"id": "byName", "options": "Ready %"}, "properties": [
                            {"id": "unit", "value": "percent"}, {"id": "min", "value": 0}, {"id": "max", "value": 40},
                            {"id": "custom.width", "value": 100},
                            {"id": "custom.cellOptions", "value": {"mode": "gradient", "type": "gauge", "valueDisplayMode": "text"}},
                            {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                                {"color": "#d44a3a", "value": None}, {"color": "#e0b400", "value": 20}]}},
                        ]},
                        {"matcher": {"id": "byName", "options": "Ph"},
                         "properties": [{"id": "custom.width", "value": 40}]},
                        {"matcher": {"id": "byName", "options": "Address"}, "properties": [
                            {"id": "custom.width", "value": 170},
                            {"id": "links", "value": address_link},
                        ]},
                    ],
                },
            },
        ],
        "templating": {"list": []},
    }


# ── Live audit via JakeOps ────────────────────────────────────────────────────

AUDIT_WORKERS = 4       # parallel buildings — fewer workers reduces switch SSH contention
AUDIT_TIMEOUT = 300    # seconds per building before giving up (large buildings can have 200+ units)


def run_live_audit(buildings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Run live audit for all buildings concurrently. Returns (all_rows, updated_buildings).

    Uses a thread pool (AUDIT_WORKERS) and a per-building timeout (AUDIT_TIMEOUT seconds).
    Buildings that time out or raise are skipped with a warning; their CSV ready_pct is kept.
    """
    try:
        from core.shared import seed_project_envs
        seed_project_envs(PROJECT_ROOT)
        from mcp.jake_ops_mcp import JakeOps
        ops = JakeOps()
        # Pre-warm the NetBox device cache before the thread pool starts.
        # Without this, all 4 workers simultaneously miss the cache on their first
        # resolve_building_from_address call, each firing a separate NetBox API request
        # under contention — causing the 8s timeout to be exceeded.
        try:
            ops._netbox_all_devices()
            ops._location_prefix_index()
        except Exception:
            pass  # non-fatal — threads will warm it themselves
    except Exception as e:
        print(f"ERROR: Cannot initialize JakeOps: {e}", file=sys.stderr)
        sys.exit(1)

    def audit_one(b: dict) -> tuple[dict, list[dict]]:
        """Runs a single building audit. Returns (updated_b, rows).

        Calls generate_nycha_audit_workbook directly (not via the JakeOps wrapper)
        so that live SSH bridge reads are performed — the JakeOps wrapper uses a
        DB-only context to stay within the 30s API timeout, which produces stale data.
        """
        from audits.jake_audit_workbook import generate_nycha_audit_workbook as _gen
        xlsx_path = XLSX_DIR / f"{b['filename']}_audit.xlsx"
        XLSX_DIR.mkdir(parents=True, exist_ok=True)
        result = _gen(address_text=b["address"], out_path=str(xlsx_path), ops=ops)
        rows = result.get("rows") or []
        if not rows:
            raise ValueError(result.get("error") or "no rows returned")
        green = sum(1 for r in rows if r.get("state") == "green")
        total = len(rows)
        ready_pct = round(green / total * 100)
        b = dict(b)
        b["ready_pct"] = ready_pct
        b["green_units"] = green
        b["total_units"] = total
        out_rows = []
        for r in rows:
            note = r.get("notes", "")
            # Normalize PPPoE label notes to fixed display string for Grafana mapping
            if str(note).upper().startswith("PPPOE LABEL MAPS THIS CPE TO"):
                note = "PPPOE LABEL MISMATCH"
            out_rows.append({
                "address": b["address"],
                "filename": b["filename"],
                "development": b["development"],
                "phase": b["phase"],
                "ready_pct": ready_pct,
                "unit": r.get("unit", ""),
                "notes": note,
                "image_ap_make": r.get("image_ap_make", ""),
                "mac_cpe": r.get("mac_cpe", ""),
                "mac_live": r.get("mac_live", ""),
                "mac_controller": r.get("mac_controller", ""),
                "pppoe_unit": r.get("pppoe_unit", ""),
                "inventory_mac_verification": r.get("inventory_mac_verification", ""),
                "implication": r.get("implication", ""),
                "action": r.get("action", ""),
                "state": r.get("state", "red"),
            })
        return b, out_rows

    all_rows: list[dict] = []
    updated: list[dict] = list(buildings)  # default: keep original

    pool = ThreadPoolExecutor(max_workers=AUDIT_WORKERS)
    futures = {pool.submit(audit_one, dict(b)): i for i, b in enumerate(buildings)}
    done_count = 0
    for fut, idx in futures.items():
        b = buildings[idx]
        try:
            updated_b, rows = fut.result(timeout=AUDIT_TIMEOUT)
            updated[idx] = updated_b
            all_rows.extend(rows)
            done_count += 1
            if done_count % 10 == 0:
                print(f"  [{done_count}/{len(buildings)}] audited")
        except FuturesTimeoutError:
            print(f"  TIMEOUT [{idx+1}] {b['address']} (>{AUDIT_TIMEOUT}s) — skipped", file=sys.stderr)
            fut.cancel()
        except Exception as e:
            print(f"  SKIP [{idx+1}] {b['address']}: {e}", file=sys.stderr)
    pool.shutdown(wait=False, cancel_futures=True)

    print(f"  [{done_count}/{len(buildings)}] buildings audited successfully")
    return all_rows, updated


# ── Single building detail dashboard ─────────────────────────────────────────

STATUS_MAPPINGS = [{"type": "value", "options": {
    # Green — CPE confirmed good
    "Good":                              {"color": "#299c46", "index": 0},
    "GOOD":                              {"color": "#299c46", "index": 1},
    "Live online":                       {"color": "#299c46", "index": 2},
    "LIVE ONLINE":                       {"color": "#299c46", "index": 3},
    "Live online via router evidence":   {"color": "#299c46", "index": 4},
    "LIVE ONLINE VIA ROUTER EVIDENCE":   {"color": "#299c46", "index": 5},
    # Yellow — needs attention / action required
    "WRONG UNIT":                        {"color": "#e0b400", "index": 6},
    "MOVE CPE TO CORRECT UNIT":          {"color": "#e0b400", "index": 7},
    "MOVE CPE TO WAN PORT":              {"color": "#e0b400", "index": 8},
    "UNKNOWN MAC ON PORT":               {"color": "#e0b400", "index": 9},
    "UNPLUGGED / BAD CABLE":             {"color": "#e0b400", "index": 10},
    "CONTROLLER MISMATCH":               {"color": "#e0b400", "index": 11},
    "PPPOE LABEL MISMATCH":              {"color": "#e0b400", "index": 12},
    # Red — not installed / no evidence
    "CONTROLLER VERIFIED":               {"color": "#d44a3a", "index": 13},
    "NOT INSTALLED":                     {"color": "#d44a3a", "index": 14},
    "LIVE LOOKUP FAILED":                {"color": "#d44a3a", "index": 15},
    "NO LIVE EVIDENCE":                  {"color": "#d44a3a", "index": 16},
    "Inventory MAC present":             {"color": "#d44a3a", "index": 17},
}}]


def build_building_detail_dashboard(buildings: list[dict], all_rows: list[dict]) -> dict:
    options = [{"selected": i == 0, "text": b["address"], "value": b["address"]}
               for i, b in enumerate(buildings)]
    default = buildings[0]["address"]

    # URL-based queries: the infinity datasource re-fetches on every variable change,
    # solving the inline-data-doesn't-refilter problem. Files are written by
    # upload_building_json_files() to the jake-data HTTP server.
    # ${address_filename} is a second variable derived from $address.
    def url_query(ref_id, url, columns):
        return {
            "datasource": ds(), "refId": ref_id, "type": "json", "source": "url",
            "url": url, "url_options": {"method": "GET", "data": ""},
            "root_selector": "", "format": "table", "parser": "backend",
            "columns": columns, "filters": [],
            "json_options": {"columnar": False, "root_is_not_array": False},
            "global_query_id": "", "cacheTimeout": "0", "queryCachingTTL": 0,
        }

    # Files are named by _safe_filename(address). Use ${address:raw} in the URL —
    # we store files under both the raw address name AND the safe filename to handle
    # whatever encoding Grafana uses.
    rows_url = f"{JAKE_DATA_URL}/nycha_building/${{address:raw}}_rows.json"
    meta_url = f"{JAKE_DATA_URL}/nycha_building/${{address:raw}}_meta.json"

    ROW_COLS = [
        {"selector": "unit",                       "text": "Unit",               "type": "string"},
        {"selector": "notes",                       "text": "Status",             "type": "string"},
        {"selector": "image_ap_make",              "text": "Make",               "type": "string"},
        {"selector": "mac_cpe",                    "text": "MAC (Inventory/CSV)","type": "string"},
        {"selector": "mac_live",                   "text": "MAC (Live/Bridge)",  "type": "string"},
        {"selector": "mac_controller",             "text": "MAC (Controller)",   "type": "string"},
        {"selector": "pppoe_unit",                 "text": "PPPoE",              "type": "string"},
        {"selector": "inventory_mac_verification", "text": "Verification",       "type": "string"},
        {"selector": "state",                      "text": "state",              "type": "string"},
    ]
    META_COLS = [
        {"selector": "ready_pct",   "text": "ready_pct",   "type": "number"},
        {"selector": "development", "text": "development", "type": "string"},
        {"selector": "phase",       "text": "phase",       "type": "number"},
    ]

    return {
        "id": None,
        "uid": "nycha-building-detail",
        "title": "NYCHA Building Audit Detail",
        "tags": ["nycha", "cpe"],
        "schemaVersion": 39, "version": 1, "refresh": "",
        "time": {"from": "2020-01-01T00:00:00.000Z", "to": "2030-01-01T00:00:00.000Z"},
        "timepicker": {"hidden": True},
        "timezone": "browser", "fiscalYearStartMonth": 0, "graphTooltip": 0,
        "links": [{"title": "Back to Readiness Dashboard",
                   "url": "/d/nycha-cpe-readiness/nycha-cpe-deployment-readiness",
                   "type": "link", "icon": "arrow-left", "targetBlank": False,
                   "keepTime": False, "tags": [], "asDropdown": False, "includeVars": False}],
        "annotations": {"list": []},
        "templating": {"list": [{
            "name": "address", "type": "custom", "label": "Building",
            "current": {"selected": True, "text": default, "value": default},
            "hide": 0, "options": options,
            "query": ",".join(b["address"] for b in buildings),
            "skipUrlSync": False, "includeAll": False, "multi": False,
            "refresh": 0,
        }]},
        "panels": [
            {
                "id": 1, "type": "stat", "title": "Readiness", "datasource": ds(),
                "gridPos": {"h": 4, "w": 4, "x": 0, "y": 0},
                "targets": [url_query("R", meta_url, META_COLS)],
                "transformations": [],
                "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "/^ready_pct$/", "values": False},
                            "textMode": "auto", "colorMode": "background", "graphMode": "none",
                            "justifyMode": "center", "text": {"titleSize": 14, "valueSize": 48}},
                "fieldConfig": {"defaults": {"unit": "percent", "decimals": 0, "thresholds": THRESHOLDS,
                                             "color": {"mode": "thresholds"}, "mappings": [], "min": 0, "max": 100},
                                "overrides": []},
            },
            {
                "id": 2, "type": "stat", "title": "Development", "datasource": ds(),
                "gridPos": {"h": 4, "w": 12, "x": 4, "y": 0},
                "targets": [url_query("D", meta_url, META_COLS)],
                "transformations": [],
                "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "/^development$/", "values": False},
                            "textMode": "auto", "colorMode": "none", "graphMode": "none",
                            "justifyMode": "auto", "text": {"titleSize": 14, "valueSize": 20}},
                "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "text"},
                                             "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                                             "mappings": []}, "overrides": []},
            },
            {
                "id": 3, "type": "stat", "title": "Phase", "datasource": ds(),
                "gridPos": {"h": 4, "w": 4, "x": 16, "y": 0},
                "targets": [url_query("P", meta_url, META_COLS)],
                "transformations": [],
                "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "/^phase$/", "values": False},
                            "textMode": "auto", "colorMode": "none", "graphMode": "none",
                            "justifyMode": "center", "text": {"titleSize": 14, "valueSize": 36}},
                "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "text"},
                                             "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                                             "mappings": [], "decimals": 0, "unit": "short"}, "overrides": []},
            },
            {
                "id": 9, "type": "text", "title": "",
                "gridPos": {"h": 4, "w": 4, "x": 20, "y": 0},
                "options": {"mode": "html", "content":
                    '<div style="padding:8px;font-size:13px;line-height:2">'
                    '<span style="color:#299c46;font-weight:bold">&#9632; Green</span> \u2014 CPE confirmed good<br>'
                    '<span style="color:#e0b400;font-weight:bold">&#9632; Yellow</span> \u2014 Needs move / attention<br>'
                    '<span style="color:#d44a3a;font-weight:bold">&#9632; Red</span> \u2014 Not installed / missing'
                    '</div>', "transparent": True},
            },
            {
                "id": 10, "type": "table", "title": "Unit Audit \u2014 ${address}",
                "datasource": ds(),
                "gridPos": {"h": 28, "w": 24, "x": 0, "y": 4},
                "targets": [url_query("A", rows_url, ROW_COLS)],
                "transformations": [],
                "options": {"cellHeight": "sm", "showHeader": True,
                            "footer": {"show": False, "enablePagination": False}},
                "fieldConfig": {
                    "defaults": {"custom": {"align": "left", "cellOptions": {"type": "auto"},
                                            "filterable": True, "minWidth": 80},
                                 "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                                 "mappings": []},
                    "overrides": [
                        {"matcher": {"id": "byName", "options": "Unit"},
                         "properties": [{"id": "custom.width", "value": 70}]},
                        {"matcher": {"id": "byName", "options": "Status"}, "properties": [
                            {"id": "custom.width", "value": 200},
                            {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}},
                            {"id": "mappings", "value": STATUS_MAPPINGS},
                        ]},
                        {"matcher": {"id": "byName", "options": "Make"},
                         "properties": [{"id": "custom.width", "value": 80}]},
                        {"matcher": {"id": "byName", "options": "MAC (Inventory/CSV)"},
                         "properties": [{"id": "custom.width", "value": 150}]},
                        {"matcher": {"id": "byName", "options": "MAC (Live/Bridge)"},
                         "properties": [{"id": "custom.width", "value": 150}]},
                        {"matcher": {"id": "byName", "options": "MAC (Controller)"},
                         "properties": [{"id": "custom.width", "value": 150}]},
                        {"matcher": {"id": "byName", "options": "PPPoE"},
                         "properties": [{"id": "custom.width", "value": 80}]},
                        {"matcher": {"id": "byName", "options": "Verification"}, "properties": [
                            {"id": "custom.width", "value": 130},
                            {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}},
                            {"id": "mappings", "value": [{"type": "value", "options": {
                                "Match":               {"color": "#299c46", "index": 0},
                                "Bug-adjusted match":  {"color": "#299c46", "index": 1},
                                "Mismatch":            {"color": "#d44a3a", "index": 2},
                                "LAN-port MAC":        {"color": "#e0b400", "index": 3},
                            }}]},
                        ]},
                        {"matcher": {"id": "byName", "options": "state"},
                         "properties": [{"id": "custom.hidden", "value": True}]},
                    ],
                },
            },
        ],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    buildings = load_buildings()
    print(f"Loaded {len(buildings)} buildings")

    # Step 1: Run live audit for all buildings
    print("Running live audit...")
    all_rows, buildings = run_live_audit(buildings)
    from collections import Counter
    states = Counter(r["state"] for r in all_rows)
    print(f"Audit complete: {len(all_rows)} rows — {dict(states)}")

    # Step 2: Build aggregates
    phases = build_phase_summary(buildings)
    devs = build_dev_summary(buildings)

    # Step 3: Upload per-building JSON files to jake-data HTTP server
    print("Uploading per-building JSON files...")
    upload_building_json_files(buildings, all_rows)

    # Step 4: Push building detail dashboard (URL-based, fetches per-building JSON)
    print("Pushing building detail dashboard...")
    detail_dash = build_building_detail_dashboard(buildings, all_rows)
    resp = grafana_post({"dashboard": detail_dash, "overwrite": True, "folderId": 0})
    if resp.get("status") == "success":
        print(f"Building detail dashboard pushed: {resp.get('url')}")
    else:
        print(f"ERROR pushing building detail dashboard: {resp}", file=sys.stderr)
        sys.exit(1)

    # Step 5: Push main dashboard
    print("Pushing main dashboard...")
    main_dash = build_main_dashboard(buildings, phases, devs, {})
    resp = grafana_post({"dashboard": main_dash, "overwrite": True, "folderId": 0})
    if resp.get("status") == "success":
        print(f"Main dashboard pushed: {resp.get('url')}")
    else:
        print(f"ERROR pushing main dashboard: {resp}", file=sys.stderr)
        sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
