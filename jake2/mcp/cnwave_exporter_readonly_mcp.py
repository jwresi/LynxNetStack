#!/usr/bin/env python3
"""
cnWave Prometheus MCP — queries Prometheus directly for live RF metrics.
Supports both Prometheus API mode (CNWAVE_PROMETHEUS_MODE=1) and legacy
text-format exporter mode.
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

TOOLS = [
    {
        "name": "get_server_info",
        "description": "Return cnWave Prometheus MCP configuration status and connectivity.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_link_rssi",
        "description": "Return live RSSI values for cnWave links, optionally filtered by site_id or node name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "node": {"type": "string"},
                "link_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_link_snr",
        "description": "Return live SNR values for cnWave links, optionally filtered by site_id or node name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "node": {"type": "string"},
            },
        },
    },
    {
        "name": "get_link_mcs",
        "description": "Return live MCS (modulation coding scheme) for cnWave links — indicates alignment quality.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "node": {"type": "string"},
            },
        },
    },
    {
        "name": "get_link_status",
        "description": "Return cnWave link up/down status. Returns all links or filtered by site_id or node name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "node": {"type": "string"},
                "down_only": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "get_link_health_summary",
        "description": (
            "Return a ranked health summary of cnWave links including RSSI, SNR, MCS, and status. "
            "Flags weak signal, low MCS, or degraded links. Optionally filtered by site_id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "worst_only": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "get_device_status",
        "description": "Return cnWave device online/offline status, optionally filtered by site_id or name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_metrics_summary",
        "description": "Return summary counts from cnWave Prometheus metrics, optionally filtered by site_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
            },
        },
    },
]

# RSSI thresholds for Cambium cnWave (60GHz mmWave)
RSSI_WARN = -70   # dBm — degraded but functional
RSSI_CRIT = -80   # dBm — likely dropping or marginal

# MCS thresholds — MCS 9+ is healthy, below 5 is degraded
MCS_WARN = 9
MCS_CRIT = 5


def get_base_url() -> str:
    return os.environ.get("CNWAVE_EXPORTER_URL", "").rstrip("/")


def is_prometheus_mode() -> bool:
    return bool(os.environ.get("CNWAVE_PROMETHEUS_MODE", ""))


def prometheus_query(metric: str, extra_filter: str = "") -> list[dict[str, Any]]:
    base = get_base_url()
    if not base:
        return []
    query = metric
    if extra_filter:
        query = f'{metric}{{{extra_filter}}}'
    url = f"{base}/api/v1/query?query={urllib.parse.quote(query)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jake-cnwave-mcp/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        results = data.get("data", {}).get("result", [])
        rows = []
        for r in results:
            metric_labels = r.get("metric", {})
            value = r.get("value", [None, None])
            rows.append({
                "labels": metric_labels,
                "value": float(value[1]) if value[1] is not None else None,
                "timestamp": value[0],
            })
        return rows
    except Exception:
        return []


def node_matches(labels: dict, site_id: str | None, node: str | None) -> bool:
    if site_id:
        s = site_id.lower()
        a = (labels.get("a_node") or "").lower()
        z = (labels.get("z_node") or "").lower()
        ln = (labels.get("link_name") or "").lower()
        name = (labels.get("name") or "").lower()
        if not (s in a or s in z or s in ln or s in name):
            return False
    if node:
        n = node.lower()
        a = (labels.get("a_node") or "").lower()
        z = (labels.get("z_node") or "").lower()
        name = (labels.get("name") or "").lower()
        if not (n in a or n in z or n in name):
            return False
    return True


def dedupe_links(rows: list[dict]) -> list[dict]:
    """Deduplicate bidirectional link entries — keep the one with better signal."""
    seen: dict[str, dict] = {}
    for row in rows:
        ln = row["labels"].get("link_name", "")
        # Normalize link name by sorting the two endpoints
        parts = ln.replace("link-", "").split("-", 1)
        key = "link-" + "-".join(sorted(parts))
        if key not in seen:
            seen[key] = row
        else:
            # Keep higher RSSI (less negative) or higher MCS
            existing_val = seen[key].get("value") or -999
            new_val = row.get("value") or -999
            if new_val > existing_val:
                seen[key] = row
    return list(seen.values())


def rssi_label(rssi: float) -> str:
    if rssi >= RSSI_WARN:
        return "good"
    if rssi >= RSSI_CRIT:
        return "warn"
    return "crit"


def mcs_label(mcs: float) -> str:
    if mcs >= MCS_WARN:
        return "good"
    if mcs >= MCS_CRIT:
        return "warn"
    return "crit"


def handle_get_server_info(_args: dict) -> dict:
    base = get_base_url()
    mode = "prometheus_api" if is_prometheus_mode() else "text_exporter"
    reachable = False
    detail = ""
    if base:
        try:
            url = f"{base}/api/v1/query?query=cnwave_link_count"
            with urllib.request.urlopen(url, timeout=5) as r:
                data = json.loads(r.read())
                reachable = data.get("status") == "success"
                count = len(data.get("data", {}).get("result", []))
                detail = f"cnwave_link_count returned {count} result(s)"
        except Exception as exc:
            detail = str(exc)
    return {
        "configured": bool(base),
        "base_url": base,
        "mode": mode,
        "reachable": reachable,
        "detail": detail,
    }


def handle_get_link_rssi(args: dict) -> dict:
    site_id = args.get("site_id")
    node = args.get("node")
    link_name = args.get("link_name")
    rows = prometheus_query("cnwave_link_rssi")
    filtered = []
    for row in rows:
        if not node_matches(row["labels"], site_id, node):
            continue
        if link_name and link_name.lower() not in (row["labels"].get("link_name") or "").lower():
            continue
        filtered.append(row)
    deduped = dedupe_links(filtered)
    results = []
    for row in sorted(deduped, key=lambda r: (r.get("value") or 0)):
        rssi = row.get("value")
        results.append({
            "link_name": row["labels"].get("link_name"),
            "a_node": row["labels"].get("a_node"),
            "z_node": row["labels"].get("z_node"),
            "rssi_dbm": rssi,
            "health": rssi_label(rssi) if rssi is not None else "unknown",
        })
    return {
        "count": len(results),
        "links": results,
        "thresholds": {"warn_dbm": RSSI_WARN, "crit_dbm": RSSI_CRIT},
    }


def handle_get_link_snr(args: dict) -> dict:
    site_id = args.get("site_id")
    node = args.get("node")
    rows = prometheus_query("cnwave_link_snr")
    filtered = [r for r in rows if node_matches(r["labels"], site_id, node)]
    deduped = dedupe_links(filtered)
    results = []
    for row in sorted(deduped, key=lambda r: (r.get("value") or 0)):
        snr = row.get("value")
        results.append({
            "link_name": row["labels"].get("link_name"),
            "a_node": row["labels"].get("a_node"),
            "z_node": row["labels"].get("z_node"),
            "snr_db": snr,
            "health": "good" if snr and snr >= 20 else ("warn" if snr and snr >= 10 else "crit"),
        })
    return {"count": len(results), "links": results}


def handle_get_link_mcs(args: dict) -> dict:
    site_id = args.get("site_id")
    node = args.get("node")
    rows = prometheus_query("cnwave_link_mcs")
    filtered = [r for r in rows if node_matches(r["labels"], site_id, node)]
    deduped = dedupe_links(filtered)
    results = []
    for row in sorted(deduped, key=lambda r: (r.get("value") or 0)):
        mcs = row.get("value")
        results.append({
            "link_name": row["labels"].get("link_name"),
            "a_node": row["labels"].get("a_node"),
            "z_node": row["labels"].get("z_node"),
            "mcs": mcs,
            "health": mcs_label(mcs) if mcs is not None else "unknown",
            "note": "MCS 12=max(QPSK-16), MCS 9+=healthy, <5=degraded alignment",
        })
    return {"count": len(results), "links": results}


def handle_get_link_status(args: dict) -> dict:
    site_id = args.get("site_id")
    node = args.get("node")
    down_only = args.get("down_only", False)
    rows = prometheus_query("cnwave_link_status")
    filtered = [r for r in rows if node_matches(r["labels"], site_id, node)]
    deduped = dedupe_links(filtered)
    results = []
    for row in deduped:
        status_val = row.get("value")
        is_up = status_val == 1.0
        if down_only and is_up:
            continue
        results.append({
            "link_name": row["labels"].get("link_name"),
            "a_node": row["labels"].get("a_node"),
            "z_node": row["labels"].get("z_node"),
            "status": "up" if is_up else "down",
            "status_value": status_val,
        })
    down_count = sum(1 for r in results if r["status"] == "down")
    return {
        "total": len(results),
        "down_count": down_count,
        "up_count": len(results) - down_count,
        "links": sorted(results, key=lambda r: r["status"]),
    }


def handle_get_link_health_summary(args: dict) -> dict:
    site_id = args.get("site_id")
    worst_only = args.get("worst_only", False)

    rssi_rows = {
        r["labels"].get("link_name"): r
        for r in dedupe_links(prometheus_query("cnwave_link_rssi"))
        if node_matches(r["labels"], site_id, None)
    }
    snr_rows = {
        r["labels"].get("link_name"): r
        for r in dedupe_links(prometheus_query("cnwave_link_snr"))
        if node_matches(r["labels"], site_id, None)
    }
    mcs_rows = {
        r["labels"].get("link_name"): r
        for r in dedupe_links(prometheus_query("cnwave_link_mcs"))
        if node_matches(r["labels"], site_id, None)
    }
    status_rows = {
        r["labels"].get("link_name"): r
        for r in dedupe_links(prometheus_query("cnwave_link_status"))
        if node_matches(r["labels"], site_id, None)
    }

    all_links = set(rssi_rows) | set(snr_rows) | set(mcs_rows) | set(status_rows)
    results = []
    for ln in all_links:
        rssi_row = rssi_rows.get(ln, {})
        snr_row = snr_rows.get(ln, {})
        mcs_row = mcs_rows.get(ln, {})
        status_row = status_rows.get(ln, {})
        labels = rssi_row.get("labels") or snr_row.get("labels") or mcs_row.get("labels") or {}

        rssi = rssi_row.get("value")
        snr = snr_row.get("value")
        mcs = mcs_row.get("value")
        status_val = status_row.get("value")
        is_up = status_val == 1.0 if status_val is not None else None

        issues = []
        if rssi is not None and rssi < RSSI_CRIT:
            issues.append(f"RSSI critical ({rssi:.1f} dBm)")
        elif rssi is not None and rssi < RSSI_WARN:
            issues.append(f"RSSI weak ({rssi:.1f} dBm)")
        if mcs is not None and mcs < MCS_CRIT:
            issues.append(f"MCS degraded ({int(mcs)})")
        elif mcs is not None and mcs < MCS_WARN:
            issues.append(f"MCS marginal ({int(mcs)})")
        if is_up is False:
            issues.append("link DOWN")

        health = "good"
        if any("critical" in i or "DOWN" in i for i in issues):
            health = "crit"
        elif issues:
            health = "warn"

        if worst_only and health == "good":
            continue

        results.append({
            "link_name": ln,
            "a_node": labels.get("a_node"),
            "z_node": labels.get("z_node"),
            "rssi_dbm": rssi,
            "snr_db": snr,
            "mcs": mcs,
            "status": "up" if is_up else ("down" if is_up is False else "unknown"),
            "health": health,
            "issues": issues,
        })

    results.sort(key=lambda r: (
        0 if r["health"] == "crit" else (1 if r["health"] == "warn" else 2),
        r.get("rssi_dbm") or 0,
    ))

    crit = sum(1 for r in results if r["health"] == "crit")
    warn = sum(1 for r in results if r["health"] == "warn")
    good = sum(1 for r in results if r["health"] == "good")

    return {
        "total_links": len(results),
        "critical": crit,
        "warn": warn,
        "good": good,
        "links": results,
        "thresholds": {
            "rssi_warn_dbm": RSSI_WARN,
            "rssi_crit_dbm": RSSI_CRIT,
            "mcs_warn": MCS_WARN,
            "mcs_crit": MCS_CRIT,
        },
    }


def handle_get_device_status(args: dict) -> dict:
    site_id = args.get("site_id")
    name = args.get("name")
    rows = prometheus_query("cnwave_device_status")
    filtered = [r for r in rows if node_matches(r["labels"], site_id, name)]
    results = []
    for row in filtered:
        status_val = row.get("value")
        results.append({
            "name": row["labels"].get("name") or row["labels"].get("node"),
            "status": "online" if status_val == 1.0 else "offline",
            "status_value": status_val,
            "site": row["labels"].get("site"),
        })
    offline = sum(1 for r in results if r["status"] == "offline")
    return {
        "total": len(results),
        "offline": offline,
        "online": len(results) - offline,
        "devices": sorted(results, key=lambda r: r["status"]),
    }


def handle_get_metrics_summary(args: dict) -> dict:
    site_id = args.get("site_id")
    link_count_rows = prometheus_query("cnwave_link_count")
    device_count_rows = prometheus_query("cnwave_device_count")
    online_links = prometheus_query("cnwave_online_link_count")
    online_devices = prometheus_query("cnwave_online_device_count")

    def first_val(rows: list) -> int | None:
        for r in rows:
            if not site_id or node_matches(r["labels"], site_id, None):
                v = r.get("value")
                return int(v) if v is not None else None
        return None

    return {
        "site_id": site_id,
        "total_links": first_val(link_count_rows),
        "total_devices": first_val(device_count_rows),
        "online_links": first_val(online_links),
        "online_devices": first_val(online_devices),
        "source": "prometheus_api",
        "prometheus_url": get_base_url(),
    }


HANDLERS = {
    "get_server_info": handle_get_server_info,
    "get_link_rssi": handle_get_link_rssi,
    "get_link_snr": handle_get_link_snr,
    "get_link_mcs": handle_get_link_mcs,
    "get_link_status": handle_get_link_status,
    "get_link_health_summary": handle_get_link_health_summary,
    "get_device_status": handle_get_device_status,
    "get_metrics_summary": handle_get_metrics_summary,
}


def handle_request(req: dict) -> dict:
    method = req.get("method", "")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cnwave_prometheus_mcp", "version": "2.0"},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = req.get("params", {}).get("name", "")
        arguments = req.get("params", {}).get("arguments", {})
        handler = HANDLERS.get(name)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }
        try:
            result = handler(arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                },
            }
        except Exception:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": traceback.format_exc()},
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            print(json.dumps(resp), flush=True)
        except Exception:
            print(
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": traceback.format_exc()},
                }),
                flush=True,
            )


if __name__ == "__main__":
    main()
