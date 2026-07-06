from __future__ import annotations

from typing import Any


MCP_SERVER_LAYOUT: dict[str, dict[str, Any]] = {
    "frontdoor": {
        "summary": "Natural-language front door that routes plain-English questions into deterministic Jake actions.",
        "servers": [
            {"name": "jake_frontdoor_mcp", "module": "mcp/jake_frontdoor_mcp.py"},
        ],
    },
    "core_ops": {
        "summary": "Deterministic network-operations server that correlates NetBox, RouterOS, TAUC, Vilo, artifacts, and local exports.",
        "servers": [
            {"name": "jake_ops_mcp", "module": "mcp/jake_ops_mcp.py"},
        ],
    },
    "inventory_observability": {
        "summary": "Inventory and read-only observability sources for site/device metadata and alert context.",
        "servers": [
            {"name": "netbox_readonly_mcp", "module": "mcp/netbox_readonly_mcp.py"},
            {"name": "alertmanager_readonly_mcp", "module": "mcp/alertmanager_readonly_mcp.py"},
            {"name": "bigmac_readonly_mcp", "module": "mcp/bigmac_readonly_mcp.py"},
            {"name": "site_observability_mcp", "module": "mcp/site_observability_mcp.py"},
        ],
    },
    "wireless_transport": {
        "summary": "Wireless transport metrics and RF-state sources.",
        "servers": [
            {"name": "cnwave_exporter_readonly_mcp", "module": "mcp/cnwave_exporter_readonly_mcp.py"},
        ],
    },
    "vendor_controllers": {
        "summary": "Vendor-specific controller adapters and hidden-api access paths.",
        "servers": [
            {"name": "tauc_mcp", "module": "mcp/tauc_mcp.py"},
            {"name": "vilo_mcp", "module": "mcp/vilo_mcp.py"},
            {"name": "tplink_access_mcp", "module": "mcp/tplink_access_mcp.py"},
            {"name": "vilo_access_mcp", "module": "mcp/vilo_access_mcp.py"},
        ],
    },
    "routeros_troubleshooting": {
        "summary": "RouterOS troubleshooting scenario servers grouped by operator intent rather than flat changelog bullets.",
        "servers": [
            {"name": "routeros_dispatch_mcp", "module": "mcp/routeros_dispatch_mcp.py"},
            {"name": "routeros_access_mcp", "module": "mcp/routeros_access_mcp.py"},
            {"name": "routeros_switching_mcp", "module": "mcp/routeros_switching_mcp.py"},
            {"name": "routeros_routing_mcp", "module": "mcp/routeros_routing_mcp.py"},
            {"name": "routeros_platform_mcp", "module": "mcp/routeros_platform_mcp.py"},
            {"name": "routeros_ops_mcp", "module": "mcp/routeros_ops_mcp.py"},
            {"name": "routeros_wireless_mcp", "module": "mcp/routeros_wireless_mcp.py"},
        ],
    },
    "swos_troubleshooting": {
        "summary": "SwOS/CSS switching scenarios kept separate from RouterOS bridge-engine troubleshooting.",
        "servers": [
            {"name": "swos_switching_mcp", "module": "mcp/swos_switching_mcp.py"},
        ],
    },
}
