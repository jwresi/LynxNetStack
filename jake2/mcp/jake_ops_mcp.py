#!/usr/bin/env python3
from __future__ import annotations

import base64
import concurrent.futures
import csv
import hashlib
import hmac
import http.cookiejar
import importlib
import importlib.util
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.shared import (
    SITE_ALIAS_MAP,
    SITE_SERVICE_PROFILES,
    SUBSCRIBER_NAME_TO_MAC,
    classify_port_role,
    get_site_uplink_ports,
    get_site_mgmt_subnet,
    project_env_candidates,
    normalize_subscriber_label,
    load_env_file as shared_load_env_file,
    seed_project_envs as shared_seed_project_envs,
)
from mcp.bigmac_readonly_mcp import BigmacClient
from mcp.vendor_adapters import CnwaveControllerAdapter, TaucOpsAdapter, ViloOpsAdapter

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERATOR_NOTES_PATH = REPO_ROOT / "docs" / "jake" / "JAKE_OPERATOR_LEARNED_NOTES.md"

TOOLS = [
    {"name": "get_server_info", "description": "Return Jake Ops MCP status and latest scan diagnostics.", "inputSchema": {"type": "object", "properties": {}}},
    {
        "name": "query_summary",
        "description": "Accept a natural-language network operations question and return the deterministic Jake answer with matched action, summary, and raw result.",
        "inputSchema": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}},
    },
    {
        "name": "get_outage_context",
        "description": "Return deterministic outage context for an address/unit report by resolving building scope, checking PPP evidence, related bridge sightings, and active alerts.",
        "inputSchema": {
            "type": "object",
            "required": ["address_text", "unit"],
            "properties": {
                "address_text": {"type": "string"},
                "unit": {"type": "string"},
            },
        },
    },
    {
        "name": "audit_device_labels",
        "description": "Audit network-scan and NetBox device names against the required label format <6 digit location>.<3 digit site>.<device type><2 digit number>.",
        "inputSchema": {"type": "object", "properties": {"include_valid": {"type": "boolean", "default": False}, "limit": {"type": "integer", "default": 500}}},
    },
    {
        "name": "get_subnet_health",
        "description": "Return deterministic health summary for a subnet or site using latest scan, alerts, and cached topology context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subnet": {"type": "string"},
                "site_id": {"type": "string"},
                "include_alerts": {"type": "boolean", "default": True},
                "include_bigmac": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "get_online_customers",
        "description": "Return customer online count using latest PPP evidence from the local network map.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string"},
                "site_id": {"type": "string"},
                "building_id": {"type": "string"},
                "router_identity": {"type": "string"},
            },
        },
    },
    {
        "name": "compare_customer_evidence",
        "description": "Compare customer-count evidence for a site using PPP, router ARP, and the freshest local subscriber export.",
        "inputSchema": {
            "type": "object",
            "required": ["site_id"],
            "properties": {
                "site_id": {"type": "string"},
            },
        },
    },
    {
        "name": "trace_mac",
        "description": "Trace a MAC through the latest scan and optionally corroborate with Bigmac.",
        "inputSchema": {"type": "object", "required": ["mac"], "properties": {"mac": {"type": "string"}, "include_bigmac": {"type": "boolean", "default": True}}},
    },
    {
        "name": "get_netbox_device",
        "description": "Return deterministic NetBox device lookup by exact name.",
        "inputSchema": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}},
    },
    {
        "name": "get_netbox_device_by_ip",
        "description": "Return deterministic NetBox device lookup by primary management IP.",
        "inputSchema": {"type": "object", "required": ["ip"], "properties": {"ip": {"type": "string"}}},
    },
    {
        "name": "get_site_alerts",
        "description": "Return active alerts for a site from Alertmanager.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}},
    },
    {
        "name": "get_site_logs",
        "description": "Return a structured Loki-backed log summary for a site over a recent time window.",
        "inputSchema": {
            "type": "object",
            "required": ["site_id"],
            "properties": {
                "site_id": {"type": "string"},
                "window_minutes": {"type": "integer", "default": 15},
                "log_filter": {"type": "string", "default": "all"},
                "limit": {"type": "integer", "default": 500},
            },
        },
    },
    {
        "name": "get_device_logs",
        "description": "Return a structured Loki-backed log summary for one device hostname over a recent time window.",
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
                "window_minutes": {"type": "integer", "default": 15},
                "log_filter": {"type": "string", "default": "all"},
                "limit": {"type": "integer", "default": 500},
            },
        },
    },
    {
        "name": "correlate_event_window",
        "description": "Correlate Loki events for a site over a time window into an ordered multi-device timeline.",
        "inputSchema": {
            "type": "object",
            "required": ["site_id"],
            "properties": {
                "site_id": {"type": "string"},
                "window_minutes": {"type": "integer", "default": 15},
                "limit": {"type": "integer", "default": 500},
            },
        },
    },
    {
        "name": "get_site_summary",
        "description": "Return deterministic site summary using latest scan data, PPP counts, outliers, and optional alerts.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}, "include_alerts": {"type": "boolean", "default": True}}},
    },
    {
        "name": "get_site_historical_evidence",
        "description": "Return archived outage evidence for a site using saved transport logs, flap history, alert patterns, and local field-note artifacts.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}},
    },
    {
        "name": "get_site_syslog_summary",
        "description": "Return ingested local syslog evidence for a site from archived hardware logs when live devices may no longer be reachable.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}},
    },
    {
        "name": "get_dhcp_findings_summary",
        "description": "Return DHCP and Option 82 findings from the local relay-state snapshot, including drift and relay health warnings.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_dhcp_relay_summary",
        "description": "Return DHCP relay and Option 82 summary for a named relay such as DHCP-RELAY-KH-02.",
        "inputSchema": {"type": "object", "required": ["relay_name"], "properties": {"relay_name": {"type": "string"}}},
    },
    {
        "name": "get_dhcp_circuit_summary",
        "description": "Return DHCP subscriber and relay-path details for a Circuit-ID such as khub/ge-0/0/22:1117.",
        "inputSchema": {"type": "object", "required": ["circuit_id"], "properties": {"circuit_id": {"type": "string"}}},
    },
    {
        "name": "get_dhcp_subscriber_summary",
        "description": "Return DHCP subscriber correlation by MAC, IP, Circuit-ID, Remote-ID, relay name, or subscriber id using the local relay-state snapshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mac": {"type": "string"},
                "ip": {"type": "string"},
                "circuit_id": {"type": "string"},
                "remote_id": {"type": "string"},
                "subscriber_id": {"type": "string"},
                "relay_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_live_dhcp_lease_summary",
        "description": "Return live DHCP lease evidence from LynxMSP API when reachable, with local DB fallback and optional filtering by site, MAC, or IP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "mac": {"type": "string"},
                "ip": {"type": "string"},
                "limit": {"type": "integer", "default": 25},
            },
        },
    },
    {
        "name": "get_live_splynx_online_summary",
        "description": "Return live Splynx online-customer evidence when API credentials are configured, with optional filtering by site hint or search text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "search": {"type": "string"},
                "limit": {"type": "integer", "default": 25},
            },
        },
    },
    {
        "name": "get_live_cnwave_rf_summary",
        "description": "Return live cnWave RF and health metrics grouped by device or site when exporter metrics are available.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "name": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "get_live_cnwave_radio_neighbors",
        "description": "Return controller-backed IPv4 neighbors for a cnWave radio when the controller remote-command path is configured, with explicit diagnostics when only exporter metrics exist.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "name": {"type": "string"},
                "query": {"type": "string"},
            },
        },
    },
    {
        "name": "run_live_positron_read",
        "description": "Execute a read-only Positron G.Hn CLI command on a known Positron target when direct SSH is available.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_name": {"type": "string"},
                "ip": {"type": "string"},
                "command": {"type": "string"},
            },
        },
    },
    {
        "name": "get_live_ghn_summary",
        "description": "Pull a read-only live Positron summary including version, interfaces, uplink/VLAN hints, and parsed G.Hn subscriber mappings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_name": {"type": "string"},
                "ip": {"type": "string"},
                "site_id": {"type": "string"},
            },
        },
    },
    {
        "name": "run_live_routeros_read",
        "description": "Execute an approved read-only RouterOS command through ssh_mcp for a device already present in the ssh_mcp inventory and allowlist.",
        "inputSchema": {
            "type": "object",
            "required": ["device_name", "intent"],
            "properties": {
                "device_name": {"type": "string"},
                "intent": {"type": "string"},
                "reason": {"type": "string"},
                "params": {"type": "object"},
            },
        },
    },
    {
        "name": "get_live_routeros_export",
        "description": "Pull a fresh read-only RouterOS export from a live device when ssh_mcp access is available, with local export fallback when present.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "device_name": {"type": "string"},
                "show_sensitive": {"type": "boolean", "default": True},
                "terse": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "review_live_upgrade_risk",
        "description": "Audit a live RouterOS device for upgrade risk using current live state plus the freshest available export and return required changes or preflight-only guidance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "device_name": {"type": "string"},
                "target_version": {"type": "string", "default": "7.22.1"},
            },
        },
    },
    {
        "name": "generate_upgrade_preflight_plan",
        "description": "Generate the exact preflight plan and checks for a RouterOS upgrade target using live state and export audit findings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "device_name": {"type": "string"},
                "target_version": {"type": "string", "default": "7.22.1"},
            },
        },
    },
    {
        "name": "render_upgrade_change_explanation",
        "description": "Render an operator-facing explanation of what should change before a RouterOS upgrade, or explicitly say when no config changes are needed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "device_name": {"type": "string"},
                "target_version": {"type": "string", "default": "7.22.1"},
            },
        },
    },
    {
        "name": "get_live_source_readiness",
        "description": "Summarize whether live RouterOS, LynxMSP DHCP, Splynx, cnWave exporter, and syslog sources are currently ready on this host.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_live_rogue_dhcp_scan",
        "description": "Run a bounded read-only RouterOS sniffer capture against a site router or specific RouterOS device and summarize DHCP talkers without asserting rogue status blindly.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "device_name": {"type": "string"},
                "interface": {"type": "string"},
                "seconds": {"type": "integer", "default": 5},
                "mac": {"type": "string"},
            },
        },
    },
    {
        "name": "get_port_physical_state",
        "description": "Return live RouterOS physical-port state including negotiated speed, partner speed, counters, and flap hints for one interface.",
        "inputSchema": {
            "type": "object",
            "required": ["interface"],
            "properties": {
                "interface": {"type": "string"},
                "site_id": {"type": "string"},
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_pppoe_diagnostics",
        "description": "Return PPPoE activity and recent failure diagnostics for one unit using live log evidence when available.",
        "inputSchema": {
            "type": "object",
            "required": ["unit"],
            "properties": {
                "unit": {"type": "string"},
                "site_id": {"type": "string"},
            },
        },
    },
    {
        "name": "get_dhcp_behavior",
        "description": "Return DHCP observe/offer behavior for one unit using live sniffer, lease, and log evidence when available.",
        "inputSchema": {
            "type": "object",
            "required": ["unit"],
            "properties": {
                "unit": {"type": "string"},
                "site_id": {"type": "string"},
                "device_name": {"type": "string"},
                "interface": {"type": "string"},
                "mac": {"type": "string"},
            },
        },
    },
    {
        "name": "get_live_capsman_summary",
        "description": "Run read-only live RouterOS API reads for CAPsMAN / WiFi controller state on a site router or specific device.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_live_wifi_registration_summary",
        "description": "Run read-only live RouterOS API reads for WiFi client registration state from CAPsMAN v1 and WiFi v2 tables.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "device_name": {"type": "string"},
                "limit": {"type": "integer", "default": 25},
            },
        },
    },
    {
        "name": "get_live_wifi_provisioning_summary",
        "description": "Run read-only live RouterOS API reads for CAPsMAN / WiFi provisioning and configuration rows.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "run_live_olt_read",
        "description": "Execute a read-only telnet CLI command on a TP-Link OLT using the local olt_user and olt_password credentials.",
        "inputSchema": {
            "type": "object",
            "required": ["olt_ip", "command"],
            "properties": {
                "olt_ip": {"type": "string"},
                "command": {"type": "string"},
                "olt_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_live_olt_ont_summary",
        "description": "Resolve an ONU by MAC/serial/local OLT path and run a read-only show ont info gpon command on the associated OLT.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mac": {"type": "string"},
                "serial": {"type": "string"},
                "olt_name": {"type": "string"},
                "olt_ip": {"type": "string"},
                "pon": {"type": "string"},
                "onu_id": {"type": "string"},
            },
        },
    },
    {
        "name": "get_live_olt_log_summary",
        "description": "Run read-only OLT log queries using show logging flash with optional severity, module, or search-word filters, optionally resolving the OLT from a MAC or serial.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "olt_name": {"type": "string"},
                "olt_ip": {"type": "string"},
                "mac": {"type": "string"},
                "serial": {"type": "string"},
                "word": {"type": "string"},
                "module": {"type": "string"},
                "level": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_tp_link_subscriber_join",
        "description": "Use local TP-Link subscriber export, TAUC web-session runtime reads, HC220 adjacent-MAC reasoning, and live OLT MAC-table probes to explain or join a TP-Link subscriber to OLT-side evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "network_name": {"type": "string"},
                "network_id": {"type": "string"},
                "mac": {"type": "string"},
                "serial": {"type": "string"},
                "site_id": {"type": "string"},
            },
        },
    },
    {
        "name": "get_cpe_management_surface",
        "description": "Explain what local management, controller management, and current blind spots Jake has for a Vilo or TP-Link HC220 style CPE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "network_name": {"type": "string"},
                "network_id": {"type": "string"},
                "mac": {"type": "string"},
                "serial": {"type": "string"},
                "site_id": {"type": "string"},
            },
        },
    },
    {
        "name": "get_cpe_management_readiness",
        "description": "Audit Jake's current management readiness for TP-Link HC220 and Vilo CPEs, including controller surfaces, local evidence, and direct local-adapter gaps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
            },
        },
    },
    {
        "name": "list_sites_inventory",
        "description": "Return a consolidated list of sites with known real addresses and 172.x router IPs from NetBox inventory.",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 200}}},
    },
    {
        "name": "search_sites_inventory",
        "description": "Search NetBox-backed site inventory by site id, site name, address text, or device sample.",
        "inputSchema": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 25}}},
    },
    {
        "name": "get_site_topology",
        "description": "Return deterministic site topology including radios, radio links, resolved addresses, and known unit lists grouped by address.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}},
    },
    {
        "name": "get_tauc_network_name_list",
        "description": "Return TAUC cloud network names by status with optional prefix filtering.",
        "inputSchema": {
            "type": "object",
            "required": ["status"],
            "properties": {
                "status": {"type": "string", "enum": ["ONLINE", "ABNORMAL"]},
                "page": {"type": "integer", "default": 0},
                "page_size": {"type": "integer", "default": 100},
                "name_prefix": {"type": "string"},
            },
        },
    },
    {
        "name": "get_tauc_network_details",
        "description": "Return TAUC cloud network details for a network id.",
        "inputSchema": {"type": "object", "required": ["network_id"], "properties": {"network_id": {"type": "string"}}},
    },
    {
        "name": "get_tauc_preconfiguration_status",
        "description": "Return TAUC Aginet preconfiguration status for a network id.",
        "inputSchema": {"type": "object", "required": ["network_id"], "properties": {"network_id": {"type": "string"}}},
    },
    {
        "name": "get_tauc_pppoe_status",
        "description": "Return TAUC Aginet PPPoE configured status for a network id.",
        "inputSchema": {
            "type": "object",
            "required": ["network_id"],
            "properties": {
                "network_id": {"type": "string"},
                "refresh": {"type": "boolean", "default": True},
                "include_credentials": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "get_tauc_device_id",
        "description": "Resolve TAUC cloud device id from serial number and MAC address. Falls back to ACS only if cloud is unavailable.",
        "inputSchema": {
            "type": "object",
            "required": ["sn", "mac"],
            "properties": {"sn": {"type": "string"}, "mac": {"type": "string"}},
        },
    },
    {
        "name": "get_tauc_device_detail",
        "description": "Return TAUC cloud device detail by device id. Falls back to ACS only if cloud is unavailable.",
        "inputSchema": {"type": "object", "required": ["device_id"], "properties": {"device_id": {"type": "string"}}},
    },
    {
        "name": "get_tauc_device_internet",
        "description": "Return TAUC ACS WAN/internet state by device id.",
        "inputSchema": {"type": "object", "required": ["device_id"], "properties": {"device_id": {"type": "string"}}},
    },
    {
        "name": "get_tauc_olt_devices",
        "description": "Return TAUC OLT devices with optional filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mac": {"type": "string"},
                "sn": {"type": "string"},
                "status": {"type": "string"},
                "page": {"type": "integer", "default": 0},
                "page_size": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "get_vilo_server_info",
        "description": "Return Vilo API configuration and token cache status as seen by Jake.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_vilo_inventory",
        "description": "Return Vilo inventory page.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_index": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "get_vilo_inventory_audit",
        "description": "Reconcile Vilo inventory against the latest scan and customer port map, optionally scoped to one site or building.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "building_id": {"type": "string"},
                "limit": {"type": "integer", "default": 500},
            },
        },
    },
    {
        "name": "export_vilo_inventory_audit",
        "description": "Write Vilo audit JSON, CSV, and Markdown artifacts under output/vilo_audit for one site, one building, or global scope.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "building_id": {"type": "string"},
                "limit": {"type": "integer", "default": 500},
            },
        },
    },
    {
        "name": "search_vilo_inventory",
        "description": "Search Vilo inventory by supported filter keys such as status, device_mac, device_sn, or subscriber_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_index": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 20},
                "filter": {"type": "array", "items": {"type": "object"}, "default": []},
            },
        },
    },
    {
        "name": "get_vilo_subscribers",
        "description": "Return Vilo subscriber page.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_index": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "search_vilo_subscribers",
        "description": "Search Vilo subscribers by subscriber_id, first_name, last_name, email, or phone.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_index": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 20},
                "filter": {"type": "array", "items": {"type": "object"}, "default": []},
            },
        },
    },
    {
        "name": "get_vilo_networks",
        "description": "Return Vilo networks page.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_index": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "search_vilo_networks",
        "description": "Search Vilo networks by network_id, subscriber_id, user_email, main_vilo_mac, or network_name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_index": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 20},
                "filter": {"type": "array", "items": {"type": "object"}, "default": []},
                "sort": {"type": "array", "items": {"type": "object"}, "default": []},
            },
        },
    },
    {
        "name": "get_vilo_devices",
        "description": "Return Vilo device details for one network_id.",
        "inputSchema": {"type": "object", "required": ["network_id"], "properties": {"network_id": {"type": "string"}}},
    },
    {
        "name": "get_vilo_target_summary",
        "description": "Return a deterministic Vilo summary for a main MAC, device MAC, network_id, or exact network_name, including cloud state, device detail, latest-scan placement, and likely failure domain.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mac": {"type": "string"},
                "network_id": {"type": "string"},
                "network_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_transport_radio_summary",
        "description": "Return deterministic Cambium or Siklu radio detail by exact/partial name, IP, or MAC using the local transport scan artifact and any available cnWave topology hints.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "name": {"type": "string"},
                "ip": {"type": "string"},
                "mac": {"type": "string"},
            },
        },
    },
    {
        "name": "get_transport_radio_issues",
        "description": "Return deterministic issue rollups for Cambium and Siklu radios from the local transport scan artifact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string", "enum": ["cambium", "siklu"]},
                "site_id": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "get_radio_handoff_trace",
        "description": "Return the current radio-to-building handoff trace using radio inventory, site topology, building device inventory, and SFP/uplink bridge-host evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_site_radio_inventory",
        "description": "Return deterministic site radio inventory using transport scan, NetBox radio devices, and site alert evidence.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}},
    },
    {
        "name": "search_vilo_devices",
        "description": "Search Vilo devices for one network_id with optional sort_group.",
        "inputSchema": {
            "type": "object",
            "required": ["network_id"],
            "properties": {
                "network_id": {"type": "string"},
                "sort_group": {"type": "array", "items": {"type": "object"}, "default": []},
            },
        },
    },
    {
        "name": "get_building_health",
        "description": "Return deterministic building/switch-block summary for identities such as 000007.055.",
        "inputSchema": {"type": "object", "required": ["building_id"], "properties": {"building_id": {"type": "string"}, "include_alerts": {"type": "boolean", "default": True}}},
    },
    {
        "name": "get_building_model",
        "description": "Return deterministic building model evidence including unit inventory, exact unit-port matches, switches, and direct neighbor edges for a building such as 000007.058.",
        "inputSchema": {"type": "object", "required": ["building_id"], "properties": {"building_id": {"type": "string"}}},
    },
    {
        "name": "get_switch_summary",
        "description": "Return deterministic switch summary for an exact switch identity such as 000007.055.SW04.",
        "inputSchema": {"type": "object", "required": ["switch_identity"], "properties": {"switch_identity": {"type": "string"}}},
    },
    {
        "name": "get_building_customer_count",
        "description": "Return deterministic customer count for a building scope such as 000007.055 across all switches in that building block.",
        "inputSchema": {"type": "object", "required": ["building_id"], "properties": {"building_id": {"type": "string"}}},
    },
    {
        "name": "get_building_flap_history",
        "description": "Return attention ports with flap history for a building scope such as 000007.055 from the customer port map artifact.",
        "inputSchema": {"type": "object", "required": ["building_id"], "properties": {"building_id": {"type": "string"}}},
    },
    {
        "name": "get_site_flap_history",
        "description": "Return attention ports with flap history for an entire site scope such as 000007 from the customer port map artifact.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}},
    },
    {
        "name": "get_rogue_dhcp_suspects",
        "description": "Return isolated or suspected rogue DHCP ports for a building or site scope from the customer port map artifact.",
        "inputSchema": {"type": "object", "properties": {"building_id": {"type": "string"}, "site_id": {"type": "string"}}},
    },
    {
        "name": "get_site_rogue_dhcp_summary",
        "description": "Return a deterministic site-wide summary of rogue DHCP ports grouped by building and status from the customer port map artifact.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}},
    },
    {
        "name": "get_recovery_ready_cpes",
        "description": "Return recovery-ready or recovery-hold CPE ports for a building or site scope from the customer port map artifact.",
        "inputSchema": {"type": "object", "properties": {"building_id": {"type": "string"}, "site_id": {"type": "string"}}},
    },
    {
        "name": "get_site_punch_list",
        "description": "Return a deterministic site-wide operational punch list from the customer port map artifact, grouped by action class.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}},
    },
    {
        "name": "find_cpe_candidates",
        "description": "List probable CPEs from the latest bridge-host view with optional OUI/site/building filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {"type": "string"},
                "building_id": {"type": "string"},
                "oui": {"type": "string"},
                "access_only": {"type": "boolean", "default": True},
                "limit": {"type": "integer", "default": 100},
            },
        },
    },
    {
        "name": "get_cpe_state",
        "description": "Return deterministic latest-scan state for a CPE MAC, including bridge, PPP, and ARP correlations.",
        "inputSchema": {"type": "object", "required": ["mac"], "properties": {"mac": {"type": "string"}, "include_bigmac": {"type": "boolean", "default": True}}},
    },
    {
        "name": "get_customer_access_trace",
        "description": "Walk a customer across the access network using bridge hosts, PPP/ARP, building access matches, and current fault-domain reasoning.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "network_name": {"type": "string"},
                "mac": {"type": "string"},
                "serial": {"type": "string"},
                "site_id": {"type": "string"},
            },
        },
    },
    {
        "name": "get_vendor_site_presence",
        "description": "Summarize where a CPE vendor is physically seen in the latest scan by site and building.",
        "inputSchema": {
            "type": "object",
            "required": ["vendor"],
            "properties": {
                "vendor": {"type": "string", "enum": ["vilo", "tplink"]},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "get_vendor_alt_mac_clusters",
        "description": "Show likely single-device alternate-MAC clusters for a vendor on the same access port and VLAN.",
        "inputSchema": {
            "type": "object",
            "required": ["vendor"],
            "properties": {
                "vendor": {"type": "string", "enum": ["vilo", "tplink"]},
                "site_id": {"type": "string"},
                "building_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "capture_operator_note",
        "description": "Append an operator-taught network reasoning note to Jake's grounded notes log.",
        "inputSchema": {
            "type": "object",
            "required": ["note"],
            "properties": {
                "note": {"type": "string"},
                "site_id": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "get_local_ont_path",
        "description": "Resolve a MAC or serial to local OLT/ONU/PON placement using field notes and local TP-Link exporter-style telemetry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mac": {"type": "string"},
                "serial": {"type": "string"},
            },
        },
    },
]

LOCAL_OLT_EVIDENCE_BY_MAC = {
    "d8:44:89:a7:03:0c": {
        "kind": "uplink-side",
        "summary": "Field notes show this MAC on Te1/0/1 across multiple Savoy OLTs, not on a single GPON ONT.",
        "details": [
            "Observed on 000002.OLT05 Te1/0/1 during direct MAC lookup.",
            "The same pattern was seen across multiple Savoy OLTs, suggesting mesh/backhaul visibility rather than one ONU.",
        ],
    },
    "e4:fa:c4:b2:5e:92": {
        "kind": "gpon-ont",
        "summary": "Field notes tied this MAC to 000002.OLT01 Gpon1/0/2 ONT 2.",
        "olt_name": "000002.OLT01",
        "olt_ip": "192.168.55.98",
        "pon": "Gpon1/0/2",
        "onu_id": "2",
    },
    "d8:44:89:a7:05:c8": {
        "kind": "gpon-ont",
        "summary": "Field notes tied this MAC to 000002.OLT05 Gpon1/0/1 ONT 4.",
        "olt_name": "000002.OLT05",
        "olt_ip": "192.168.55.95",
        "pon": "Gpon1/0/1",
        "onu_id": "4",
    },
    "30:68:93:c1:c5:cd": {
        "kind": "gpon-ont",
        "summary": "Field notes tied this MAC to 000002.OLT01 Gpon1/0/2 ONT 4.",
        "olt_name": "000002.OLT01",
        "olt_ip": "192.168.55.98",
        "pon": "Gpon1/0/2",
        "onu_id": "4",
        "serial": "TPLG-31A11BB2",
    },
    "60:83:e7:af:5f:ce": {
        "kind": "gpon-ont",
        "subscriber": "Savoy1Unit3F",
        "summary": "Field notes: Savoy1Unit3F AginetOS router. OLT placement not yet confirmed — Unit3F ONU serial needs physical identification.",
        "olt_name": None,
        "olt_ip": None,
        "pon": "unknown",
        "onu_id": "unknown",
        "note": "AginetOS router",
    },
    "e4:fa:c4:b2:5e:92": {
        "kind": "gpon-ont",
        "subscriber": "Savoy1Unit3N",
        "summary": "Field notes: Savoy1Unit3N AginetOS router on 000002.OLT01 Gpon1/0/2 ONT 2. Last seen 2026-04-03. Status OUTAGE.",
        "olt_name": "000002.OLT01",
        "olt_ip": "192.168.55.98",
        "pon": "Gpon1/0/2",
        "onu_id": "2",
        "note": "AginetOS router",
    },
}

LOCAL_OLT_EVIDENCE_BY_SERIAL = {
    "TPLG-31A11BB2": {
        "kind": "gpon-ont",
        "summary": "Local rollback notes place this serial on 000002.OLT01 Gpon1/0/2 ONT 4.",
        "olt_name": "000002.OLT01",
        "olt_ip": "192.168.55.98",
        "pon": "Gpon1/0/2",
        "onu_id": "4",
        "serial": "TPLG-31A11BB2",
    },
}

LOCAL_OLT_TELEMETRY_FILES = [
    REPO_ROOT / "references" / "tplink-olt" / "ont_to_delete.json",
    REPO_ROOT / "references" / "tplink-olt" / "ont-online-euclid.json",
    REPO_ROOT / "artifacts" / "tplink-olt" / "ont_to_delete.json",
    REPO_ROOT / "artifacts" / "tplink-olt" / "ont-online-euclid.json",
]

OLT_ONU_METRIC_RE = re.compile(r'([a-zA-Z0-9_]+)="([^"]*)"')
OLT_ONT_ROW_RE = re.compile(
    r"^\s*(?P<row_no>\d+)\s+"
    r"(?P<pon>\d+)\s+"
    r"(?P<onu_id>\d+)\s+"
    r"(?P<serial>TPLG-[A-Z0-9]+)\s+"
    r"(?P<online_status>\w+)\s+"
    r"(?P<admin_status>\w+)\s+"
    r"(?P<active_status>\w+)\s+"
    r"(?P<config_status>\w+)\s+"
    r"(?P<match_status>\w+)",
    re.I,
)

DHCP_RATE_ELEVATED_PER_HOUR = 60
DHCP_RATE_ABNORMAL_PER_HOUR = 200


def norm_mac(value: str) -> str:
    clean = "".join(ch for ch in value.lower() if ch in "0123456789abcdef")
    if len(clean) != 12:
        return value.lower()
    return ":".join(clean[i : i + 2] for i in range(0, 12, 2))


def mac_to_int(value: str | None) -> int | None:
    clean = "".join(ch for ch in str(value or "").lower() if ch in "0123456789abcdef")
    if len(clean) != 12:
        return None
    try:
        return int(clean, 16)
    except ValueError:
        return None


def related_mac_delta(mac_a: str | None, mac_b: str | None) -> dict[str, Any] | None:
    a = "".join(ch for ch in str(mac_a or "").lower() if ch in "0123456789abcdef")
    b = "".join(ch for ch in str(mac_b or "").lower() if ch in "0123456789abcdef")
    if len(a) != 12 or len(b) != 12:
        return None
    vendor = mac_vendor_group(a)
    if vendor != mac_vendor_group(b):
        return None
    if vendor == "vilo":
        # Vilo drift commonly shows up as +/- 1 in the last octet.
        prefix_a, last_a = a[:10], int(a[10:], 16)
        prefix_b, last_b = b[:10], int(b[10:], 16)
        if prefix_a == prefix_b and abs(last_a - last_b) == 1:
            return {"vendor": vendor, "kind": "last_octet_adjacent", "distance": abs(last_a - last_b)}
        return None
    if vendor == "tplink":
        # HC220-style drift often appears in first octet or last octet adjacency.
        mid_a, first_a, last_a = a[2:10], int(a[:2], 16), int(a[10:], 16)
        mid_b, first_b, last_b = b[2:10], int(b[:2], 16), int(b[10:], 16)
        if mid_a == mid_b and abs(last_a - last_b) == 1:
            return {"vendor": vendor, "kind": "last_octet_adjacent", "distance": abs(last_a - last_b)}
        if a[2:] == b[2:] and abs(first_a - first_b) in {1, 2}:
            return {"vendor": vendor, "kind": "first_octet_adjacent", "distance": abs(first_a - first_b)}
        return None
    return None


def is_probable_uplink_interface(name: str | None) -> bool:
    value = str(name or "").strip().lower()
    if not value:
        return False
    return value.startswith("sfp") or value.startswith("qsfp") or "uplink" in value or value.startswith("combo")


def dedupe_vendor_mac_groups(rows: list[dict[str, Any]], vendor: str) -> dict[str, Any]:
    filtered = [row for row in rows if mac_vendor_group(row.get("mac")) == vendor]
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for row in filtered:
        mac = norm_mac(str(row.get("mac") or ""))
        if not mac or len(mac.split(":")) != 6:
            continue
        key = (
            canonical_identity(row.get("identity")),
            str(row.get("on_interface") or "").strip(),
            str(row.get("vid") or "").strip(),
        )
        grouped.setdefault(key, [])
        if mac not in grouped[key]:
            grouped[key].append(mac)

    clusters: list[dict[str, Any]] = []
    raw_count = 0
    for key, macs in grouped.items():
        raw_count += len(macs)
        parents = {mac: mac for mac in macs}

        def find(mac: str) -> str:
            while parents[mac] != mac:
                parents[mac] = parents[parents[mac]]
                mac = parents[mac]
            return mac

        def union(a: str, b: str) -> None:
            ra = find(a)
            rb = find(b)
            if ra != rb:
                parents[rb] = ra

        for idx, left in enumerate(macs):
            for right in macs[idx + 1 :]:
                if related_mac_delta(left, right):
                    union(left, right)

        by_root: dict[str, list[str]] = {}
        for mac in macs:
            by_root.setdefault(find(mac), []).append(mac)

        for members in by_root.values():
            members = sorted(members)
            identity, on_interface, vid = key
            relation = None
            if len(members) >= 2:
                relation = related_mac_delta(members[0], members[1])
            clusters.append(
                {
                    "identity": identity,
                    "on_interface": on_interface,
                    "vid": vid,
                    "vendor": vendor,
                    "macs": members,
                    "primary_mac": members[0],
                    "alternate_mac_count": max(0, len(members) - 1),
                    "relation": relation,
                }
            )

    return {
        "vendor": vendor,
        "raw_mac_count": raw_count,
        "estimated_cpe_count": len(clusters),
        "duplicate_mac_delta_count": max(0, raw_count - len(clusters)),
        "clusters": sorted(
            clusters,
            key=lambda row: (
                str(row.get("identity") or ""),
                str(row.get("on_interface") or ""),
                str(row.get("vid") or ""),
                str(row.get("primary_mac") or ""),
            ),
        ),
    }


def mac_vendor_group(mac: str | None) -> str:
    m = norm_mac(mac or "")
    # Locally-administered MACs (bit 1 of first octet set) are mesh backhaul addresses
    # derived from real vendor OUIs — not CPE WAN MACs. Reject before OUI matching.
    if m and int(m[0:2], 16) & 0x02:
        return "local"
    if m.startswith("e8:da:00:"):
        return "vilo"
    if m.startswith(("30:68:93:", "60:83:e7:", "7c:f1:7e:", "d8:44:89:", "dc:62:79:", "e4:fa:c4:")):
        return "tplink"
    # d4:01:c3 is the NYCHA switch hardware OUI (TP-Link TL-SG series) — not CPE
    if m.startswith("d4:01:c3:"):
        return "switch"
    return "unknown"


@lru_cache(maxsize=1)
def load_local_olt_telemetry() -> dict[str, list[dict[str, Any]]]:
    by_serial: dict[str, list[dict[str, Any]]] = {}
    for path in LOCAL_OLT_TELEMETRY_FILES:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            if "tplink_onu_online_status{" not in line:
                continue
            labels = dict(OLT_ONU_METRIC_RE.findall(line))
            serial = str(labels.get("serial_number") or "").strip().upper()
            if not serial:
                continue
            port_id = str(labels.get("port_id") or "").strip()
            row = {
                "olt_ip": str(labels.get("olt_ip") or "").strip() or None,
                "olt_name": str(labels.get("olt_name") or "").strip() or None,
                "onu_id": str(labels.get("onu_id") or "").strip() or None,
                "port_id": port_id or None,
                "serial": serial,
                "site_name": str(labels.get("site_name") or "").strip() or None,
                "pon": f"Gpon1/0/{port_id}" if port_id else None,
                "source": str(path),
            }
            by_serial.setdefault(serial, []).append(row)
    return by_serial


def is_edge_port(interface: str | None) -> bool:
    return bool(interface) and str(interface).startswith("ether")


def is_uplink_like_port(interface: str | None) -> bool:
    if not interface:
        return False
    iface = str(interface).lower()
    return iface.startswith(("sfp", "qsfp", "combo", "bond", "bridge", "vlan"))


def _bigmac_seen_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    last_seen = str(row.get("last_seen") or "").strip()
    return (1 if last_seen else 0, last_seen)


def normalize_bigmac_sighting(row: dict[str, Any]) -> dict[str, Any]:
    interface = str(row.get("port_name") or row.get("interface_name") or "").strip() or None
    return {
        "mac": norm_mac(str(row.get("mac_address") or row.get("mac") or "")),
        "ip": None,
        "identity": str(row.get("device_name") or "").strip() or None,
        "device_name": str(row.get("device_name") or "").strip() or None,
        "device_site": canonical_scope(row.get("device_site")),
        "device_platform": str(row.get("device_platform") or "").strip() or None,
        "device_role": str(row.get("device_role") or "").strip() or None,
        "device_location": str(row.get("device_location") or "").strip() or None,
        "on_interface": interface,
        "port_name": interface,
        "vid": row.get("vlan_id"),
        "vlan_id": row.get("vlan_id"),
        "hostname": str(row.get("hostname") or "").strip() or None,
        "client_ip": str(row.get("client_ip") or "").strip() or None,
        "last_seen": str(row.get("last_seen") or "").strip() or None,
        "source": str(row.get("source") or "").strip() or "bigmac",
        "status": str(row.get("status") or "").strip() or None,
    }


def is_direct_physical_interface(interface: str | None) -> bool:
    primary = str(interface or "").split(",", 1)[0].strip().lower()
    return primary.startswith(("ether", "sfp", "qsfp", "combo"))


def is_probable_customer_bridge_host(row: dict[str, Any]) -> bool:
    interface = str(row.get("on_interface") or "")
    if not is_edge_port(interface):
        return False
    if bool(row.get("local")):
        return False
    if bool(row.get("external")):
        return True
    return mac_vendor_group(row.get("mac")) in {"tplink", "vilo"}


def normalize_scope_segment(segment: str) -> str:
    seg = str(segment).strip()
    return str(int(seg)) if seg.isdigit() else seg.upper()


def address_stem_compact(address_text: str | None) -> str:
    text = str(address_text or "").strip()
    if not text:
        return ""
    stem = text.split(",", 1)[0].strip()
    return compact_free_text(stem)


def identity_matches_scope(identity: str | None, scope: str | None) -> bool:
    if not identity or not scope:
        return False
    ident_parts = [normalize_scope_segment(p) for p in str(identity).split(".") if p]
    scope_parts = [normalize_scope_segment(p) for p in str(scope).split(".") if p]
    if len(ident_parts) < len(scope_parts):
        return False
    return ident_parts[: len(scope_parts)] == scope_parts


def canonical_scope(value: str | None) -> str | None:
    if not value:
        return value
    lowered = str(value).strip().lower()
    if lowered in SITE_ALIAS_MAP:
        return SITE_ALIAS_MAP[lowered]
    parts = str(value).split(".")
    out: list[str] = []
    for idx, part in enumerate(parts):
        if part.isdigit():
            width = 6 if idx == 0 else 3
            out.append(part.zfill(width))
        else:
            out.append(part.upper())
    return ".".join(out)


def canonical_identity(identity: str | None) -> str | None:
    return canonical_scope(identity)


def normalize_free_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def compact_free_text(value: str | None) -> str:
    return normalize_free_text(value).replace(" ", "")


def parse_unit_token(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).upper().strip()
    # Compound label: "N - NNA" or "N-NNA" (building prefix + apartment).
    # Return as "N-NNA" so different buildings within a complex don't collide on the same token.
    m = re.match(r'^(\d+)\s*[-–]\s*0*(\d+[A-Z]+)\s*$', text)
    if m:
        return f"{int(m.group(1))}-{m.group(2)}"
    m = re.search(r'(\d+[A-Z])\s*$', text)
    if m:
        return m.group(1)
    return None


def parse_unit_parts(value: str | None) -> tuple[int | None, str | None]:
    token = parse_unit_token(value)
    if not token:
        return None, None
    m = re.match(r"(\d+)([A-Z])$", token)
    if not m:
        return None, None
    return int(m.group(1)), m.group(2)


def expand_compact_address(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^(?:NYCHA)", "", text, flags=re.I)
    unit = parse_unit_token(text)
    if unit:
        text = re.sub(rf"{re.escape(unit)}\s*$", "", text, flags=re.I)
    text = re.sub(r"([0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"\bSt\b", "St", text)
    text = re.sub(r"\bAve\b", "Ave", text)
    text = re.sub(r"\bPl\b", "Pl", text)
    return re.sub(r"\s+", " ", text).strip()


def best_bridge_hit(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None

    def sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
        iface = row.get("on_interface")
        return (
            0 if is_edge_port(iface) else 1,
            0 if bool(row.get("external")) else 1,
            0 if bool(row.get("local")) else 1,
            str(iface or ""),
        )

    return sorted(rows, key=sort_key)[0]


def parse_olt_ont_rows(text: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in str(text or "").splitlines():
        match = OLT_ONT_ROW_RE.match(raw_line.rstrip())
        if not match:
            continue
        row = dict(match.groupdict())
        row["pon"] = str(row.get("pon") or "").strip()
        row["onu_id"] = str(row.get("onu_id") or "").strip()
        row["serial"] = str(row.get("serial") or "").strip().upper()
        rows.append(row)
    return rows


def infer_unit_port_candidates(
    target_unit_token: str | None,
    target_floor: int | None,
    target_letter: str | None,
    neighboring_unit_port_hints: list[dict[str, Any]],
    unit_comment_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    # Highest-confidence path: exact unit comment on a customer-facing port.
    for row in unit_comment_rows:
        iface = str(row.get("port") or row.get("interface") or "")
        identity = canonical_identity(row.get("switch_identity") or row.get("device_name") or row.get("identity"))
        if identity and is_edge_port(iface):
            candidates.append(
                {
                    "unit_token": target_unit_token,
                    "identity": identity,
                    "on_interface": iface,
                    "confidence": "high",
                    "reason": f"Exact unit comment match on {identity} {iface}.",
                    "evidence": [row],
                }
            )

    if candidates or target_floor is None or not target_letter:
        return candidates

    floor_rows = []
    for row in neighboring_unit_port_hints:
        unit_token = row.get("unit_token")
        floor, letter = parse_unit_parts(unit_token)
        best_hit = row.get("best_bridge_hit") or {}
        iface = str(best_hit.get("on_interface") or "")
        port_match = re.fullmatch(r"ether(\d+)", iface)
        identity = canonical_identity(best_hit.get("identity"))
        if floor == target_floor and letter and port_match and identity:
            floor_rows.append(
                {
                    "unit_token": unit_token,
                    "floor": floor,
                    "letter": letter,
                    "identity": identity,
                    "on_interface": iface,
                    "ether_number": int(port_match.group(1)),
                    "source_name": row.get("name"),
                }
            )

    floor_rows.sort(key=lambda r: (r["identity"], r["ether_number"], r["letter"]))
    target_ord = ord(target_letter)
    by_identity: dict[str, list[dict[str, Any]]] = {}
    for row in floor_rows:
        by_identity.setdefault(str(row["identity"]), []).append(row)

    for identity, rows in by_identity.items():
        # Best case: infer from two known same-floor units with linear port progression.
        for i, left in enumerate(rows):
            for right in rows[i + 1 :]:
                left_ord = ord(left["letter"])
                right_ord = ord(right["letter"])
                port_delta = right["ether_number"] - left["ether_number"]
                letter_delta = right_ord - left_ord
                if letter_delta <= 0 or port_delta != letter_delta:
                    continue
                if left_ord <= target_ord <= right_ord:
                    inferred_port = left["ether_number"] + (target_ord - left_ord)
                    candidates.append(
                        {
                            "unit_token": target_unit_token,
                            "identity": identity,
                            "on_interface": f"ether{inferred_port}",
                            "confidence": "medium",
                            "reason": f"Same-floor units {left['unit_token']} and {right['unit_token']} map linearly on {identity}; inferred placement for {target_unit_token}.",
                            "evidence": [left, right],
                        }
                    )
                    break
            if candidates:
                break
        if candidates:
            break

    if candidates:
        return candidates

    # Fallback: one-sided adjacent guess if only a single nearby same-floor unit is known.
    nearest: dict[str, Any] | None = None
    nearest_distance: int | None = None
    for rows in by_identity.values():
        for row in rows:
            distance = abs(ord(row["letter"]) - target_ord)
            if nearest is None or distance < (nearest_distance or 999):
                nearest = row
                nearest_distance = distance
    if nearest and nearest_distance is not None and 0 < nearest_distance <= 2:
        offset = target_ord - ord(nearest["letter"])
        inferred_port = nearest["ether_number"] + offset
        if inferred_port > 0:
            candidates.append(
                {
                    "unit_token": target_unit_token,
                    "identity": nearest["identity"],
                    "on_interface": f"ether{inferred_port}",
                    "confidence": "low",
                    "reason": f"Nearest same-floor unit {nearest['unit_token']} is on {nearest['identity']} {nearest['on_interface']}; inferred adjacent placement for {target_unit_token}.",
                    "evidence": [nearest],
                }
            )

    return candidates
ARTIFACT_PORT_MAP = Path(os.environ.get("JAKE_PORT_MAP", str(REPO_ROOT / "artifacts/customer_port_map/customer_port_map.json")))
ARTIFACT_TRANSPORT_RADIO_SCAN = Path(os.environ.get("JAKE_TRANSPORT_RADIO_SCAN", str(REPO_ROOT / "artifacts/transport_radio_scan/transport_radio_scan.json")))
ARTIFACT_SYSLOG_DIR = Path(os.environ.get("JAKE_SYSLOG_DIR", str(REPO_ROOT / "artifacts/syslog")))
VILO_AUDIT_OUT_DIR = Path(os.environ.get("JAKE_VILO_AUDIT_OUT_DIR", str(REPO_ROOT / "output/vilo_audit")))
TAUC_NYCHA_AUDIT_CSV = Path(os.environ.get("JAKE_TAUC_AUDIT_CSV", str(REPO_ROOT / "output/tauc_nycha_cpe_audit_latest.csv")))
NYCHA_INFO_CSV = next(
    (
        candidate
        for candidate in [
            Path(os.environ["JAKE_NYCHA_INFO_CSV"]) if os.environ.get("JAKE_NYCHA_INFO_CSV") else None,
            REPO_ROOT / "data" / "nycha_info.csv",
            REPO_ROOT / "output" / "nycha_info.csv",
        ]
        if candidate and candidate.exists()
    ),
    REPO_ROOT / "data" / "nycha_info.csv",
)
JAKE_EVIDENCE_DB = Path(os.environ.get("JAKE_EVIDENCE_DB", str(REPO_ROOT / "output/jake_evidence.sqlite3")))
SYSLOG_LINE_RE = re.compile(
    r"^(?P<ts>(?:[A-Z][a-z]{2}\s+\d{1,2}\s+\d\d:\d\d:\d\d)|(?:\d{4}-\d{2}-\d{2}[T\s]\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?))\s+(?P<host>[A-Za-z0-9._:-]+)\s+(?P<msg>.*)$"
)
DEVICE_LABEL_RE = re.compile(r"^\d{6}\.\d{3}\.[A-Z]+\d{2}$")

LYNXMSP_DB_CANDIDATES = [
    Path(os.environ.get("LYNXMSP_DB_PATH", "")) if os.environ.get("LYNXMSP_DB_PATH") else None,
    REPO_ROOT / "data" / "lynxcrm.db",
]
LYNXMSP_API_CANDIDATES = [
    os.environ.get("LYNXMSP_API_URL", "").rstrip("/"),
    os.environ.get("LYNX_API_URL", "").rstrip("/"),
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8010",
]
DEFAULT_SPLYNX_BASE_URL = "https://crm.resibridge.com"


def _normalize_base_url(value: str | None, *, default_scheme: str = "https") -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"{default_scheme}://{raw}"
    return raw.rstrip("/")


SPLYNX_API_CANDIDATES = [
    _normalize_base_url(os.environ.get("SPLYNX_API_URL")),
    _normalize_base_url(os.environ.get("SPYLNX_API_URL")),
    _normalize_base_url(os.environ.get("REACT_APP_SPLYNX_URL")),
    DEFAULT_SPLYNX_BASE_URL,
]
SSH_MCP_ROOT = next(
    (
        candidate
        for candidate in [
            Path(os.environ["SSH_MCP_ROOT"]) if os.environ.get("SSH_MCP_ROOT") else None,
            REPO_ROOT / "external" / "ssh_mcp",
        ]
        if candidate and candidate.exists()
    ),
    REPO_ROOT / "external" / "ssh_mcp",
)
OLT_TELNET_READ_SCRIPT = REPO_ROOT / "scripts" / "olt_telnet_read.py"
LYNXDHCP_STATE_CANDIDATES = [
    Path(os.environ.get("LYNXDHCP_STATE_PATH", "")) if os.environ.get("LYNXDHCP_STATE_PATH") else None,
    REPO_ROOT / "data" / "lynxdhcp_state.json",
]


def infer_site_service_mode(site_id: str | None, has_local_export: bool, has_ppp_sessions: bool, has_dhcp_leases: bool = False) -> str | None:
    canonical_site = canonical_scope(site_id) if site_id else None
    explicit = SITE_SERVICE_PROFILES.get(canonical_site or "") or {}
    explicit_mode = str(explicit.get("service_mode") or "").strip() or None
    if explicit_mode == "dhcp_tauc_tp_link":
        if (has_local_export or has_dhcp_leases) and has_ppp_sessions:
            return "dhcp_tauc_tp_link_with_ppp_evidence"
        if has_local_export and has_dhcp_leases:
            return "dhcp_tauc_tp_link_with_dhcp_lease_evidence"
        if has_local_export or has_dhcp_leases:
            return explicit_mode
        if has_ppp_sessions:
            return "dhcp_tauc_tp_link_profile_but_ppp_only_evidence"
    if explicit_mode == "routeros_ppp_primary":
        if (has_local_export or has_dhcp_leases) and has_ppp_sessions:
            return "routeros_ppp_primary_with_local_online_cpe_export"
        if has_local_export or has_dhcp_leases:
            return "routeros_ppp_profile_but_dhcp_or_export_evidence_present"
        if has_ppp_sessions:
            return explicit_mode
    if (has_local_export or has_dhcp_leases) and has_ppp_sessions:
        return "mixed_dhcp_and_ppp_evidence"
    if has_local_export and has_dhcp_leases:
        return "dhcp_tauc_tp_link_inferred_with_dhcp_lease_evidence"
    if has_local_export or has_dhcp_leases:
        return "dhcp_tauc_tp_link_inferred"
    if has_ppp_sessions:
        return "routeros_ppp_primary_inferred"
    return None


def find_lynxmsp_db_path() -> Path | None:
    for candidate in LYNXMSP_DB_CANDIDATES:
        if candidate and candidate.exists():
            return candidate
    return None


def _probe_http_json(url: str, timeout: float = 1.5) -> tuple[bool, str]:
    if not url:
        return False, "not configured"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return True, f"http {resp.status}"
            return False, f"http {resp.status}"
    except Exception as exc:
        return False, str(exc)


def _http_json_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 8.0,
) -> tuple[bool, Any, str]:
    req_headers = {"Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, method=method, headers=req_headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
            if not payload:
                return True, {}, f"http {resp.status}"
            try:
                return True, json.loads(payload), f"http {resp.status}"
            except Exception:
                return False, payload, f"invalid json http {resp.status}"
    except urllib.error.HTTPError as exc:
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body_text = ""
        return False, body_text, f"http {exc.code}"
    except Exception as exc:
        return False, None, str(exc)


def _splynx_credentials() -> dict[str, str]:
    base_url = (
        _normalize_base_url(os.environ.get("SPLYNX_API_URL"))
        or _normalize_base_url(os.environ.get("SPLYNX_BASE_URL"))
        or _normalize_base_url(os.environ.get("SPYLNX_API_URL"))
        or _normalize_base_url(os.environ.get("REACT_APP_SPLYNX_URL"))
        or DEFAULT_SPLYNX_BASE_URL
    )
    # Strip /api/2.0 suffix if present — it gets added in the request
    base_url = base_url.rstrip("/")
    if base_url.endswith("/api/2.0"):
        base_url = base_url[:-len("/api/2.0")]
    return {
        "base_url": base_url,
        "api_key": (os.environ.get("SPLYNX_API_KEY")
                    or os.environ.get("SPLYNX_KEY")
                    or os.environ.get("REACT_APP_SPLYNX_DEV_API_KEY") or ""),
        "api_secret": (os.environ.get("SPLYNX_API_SECRET")
                       or os.environ.get("SPLYNX_SECRET")
                       or os.environ.get("REACT_APP_SPLYNX_DEV_API_SECRET") or ""),
    }


def _splynx_access_token() -> tuple[bool, str | None, str]:
    cfg = _splynx_credentials()
    if not cfg["base_url"]:
        return False, None, "SPLYNX_API_URL is not configured"
    if not cfg["api_key"] or not cfg["api_secret"]:
        return False, None, "Splynx API credentials are not configured"
    nonce = int(time.time())
    message = f"{nonce}{cfg['api_key']}"
    signature = hmac.new(cfg["api_secret"].encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest().upper()
    ok, payload, detail = _http_json_request(
        f"{cfg['base_url']}/api/2.0/admin/auth/tokens",
        method="POST",
        body={"auth_type": "api_key", "key": cfg["api_key"], "signature": signature, "nonce": nonce},
        timeout=10.0,
    )
    if not ok or not isinstance(payload, dict):
        return False, None, detail
    token = str(payload.get("access_token") or "").strip()
    if not token:
        return False, None, "Splynx auth returned no access token"
    return True, token, detail


def _splynx_request(endpoint: str, *, params: dict[str, Any] | None = None) -> tuple[bool, Any, str]:
    ok, token, detail = _splynx_access_token()
    if not ok or not token:
        return False, None, detail
    base_url = _splynx_credentials()["base_url"]
    url = f"{base_url}/api/2.0/{endpoint.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    return _http_json_request(url, headers={"Authorization": f"Splynx-EA (access_token={token})"}, timeout=12.0)


def lynxmsp_source_status(site_id: str | None = None) -> dict[str, Any]:
    canonical_site = canonical_scope(site_id) if site_id else None
    status: dict[str, Any] = {
        "db": {"configured": False, "available": False},
        "api": {"configured": False, "available": False},
    }
    db_path = find_lynxmsp_db_path()
    if db_path:
        status["db"]["configured"] = True
        status["db"]["path"] = str(db_path)
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            table_counts: dict[str, int] = {}
            for table in ["dhcp_leases", "tplink_ont_provisions", "tplink_devices", "cgnat_sessions", "customers", "sites", "routers"]:
                try:
                    table_counts[table] = int(cur.execute(f"select count(*) from {table}").fetchone()[0])
                except Exception:
                    table_counts[table] = 0
            status["db"]["table_counts"] = table_counts
            status["db"]["available"] = any(table_counts.values())
            if canonical_site and table_counts.get("dhcp_leases", 0) > 0:
                try:
                    dhcp_site_count = int(
                        cur.execute(
                            """
                            select count(*)
                            from dhcp_leases d
                            join routers r on r.id = d.router_id
                            join sites s on s.id = r.site_id
                            where s.name = ? or s.name like ? or s.id = ?
                            """,
                            (canonical_site, f"%{canonical_site}%", canonical_site),
                        ).fetchone()[0]
                    )
                except Exception:
                    dhcp_site_count = 0
                status["db"]["site_dhcp_lease_count"] = dhcp_site_count
            conn.close()
        except Exception as exc:
            status["db"]["error"] = str(exc)

    api_tried: list[dict[str, str]] = []
    preferred_api_base = next((base for base in LYNXMSP_API_CANDIDATES if base), None)
    for base in LYNXMSP_API_CANDIDATES:
        if not base:
            continue
        status["api"]["configured"] = True
        ok, detail = _probe_http_json(f"{base}/docs")
        api_tried.append({"base_url": base, "detail": detail, "available": str(ok).lower()})
        status["api"]["available"] = ok
        if ok:
            status["api"]["base_url"] = base
            status["api"]["detail"] = detail
            break
    if status["api"]["configured"]:
        status["api"]["base_url"] = status["api"].get("base_url") or preferred_api_base
        if not status["api"].get("detail") and api_tried:
            status["api"]["detail"] = api_tried[0]["detail"]
        status["api"]["tried"] = api_tried
    return status


def find_lynxdhcp_state_path() -> Path | None:
    for candidate in LYNXDHCP_STATE_CANDIDATES:
        if candidate and candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def load_lynxdhcp_state() -> dict[str, Any]:
    path = find_lynxdhcp_state_path()
    if not path:
        return {}
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return {}
    payload["_source_path"] = str(path)
    return payload


POSITRON_ALLOWED_COMMANDS = {
    "show version",
    "show ip interface brief",
    "show ip route",
    "show running-config",
    "show startup-config",
    "dir",
}

POSITRON_IP_OVERRIDES = {
    canonical_identity(f"000004.Positron{idx:02d}"): f"192.168.111.{9 + idx}"
    for idx in range(1, 9)
}

# Deterministic overrides for radios/sites that should not rely on fuzzy location matching.
# Use `None` when the address should remain unresolved until a canonical NetBox prefix exists.
ADDRESS_RESOLUTION_OVERRIDES: dict[str, dict[str, Any] | None] = {
    normalize_free_text("104 Tapscott"): {
        "location": "104 Tapscott St, Brooklyn, NY 11212",
        "prefix": "000007.001",
        "site_code": "000007",
        "score": 999,
        "device_names": ["000007.001.SW01", "000007.001.SW02", "000007.001.V5K01"],
    },
    normalize_free_text("104 Tapscott St"): {
        "location": "104 Tapscott St, Brooklyn, NY 11212",
        "prefix": "000007.001",
        "site_code": "000007",
        "score": 999,
        "device_names": ["000007.001.SW01", "000007.001.SW02", "000007.001.V5K01"],
    },
    normalize_free_text("104 Tapscott St, Brooklyn, NY 11212"): {
        "location": "104 Tapscott St, Brooklyn, NY 11212",
        "prefix": "000007.001",
        "site_code": "000007",
        "score": 999,
        "device_names": ["000007.001.SW01", "000007.001.SW02", "000007.001.V5K01"],
    },
    normalize_free_text("726 Fenimore St, Brooklyn, NY 11203"): None,
}

# Explicit topology edges should be avoided unless there is no other authoritative source.
# cnWave peer links are now expected to come from exporter metrics when configured.
RADIO_LINK_OVERRIDES: list[dict[str, Any]] = []

# Some radio names are already intentionally mapped elsewhere in the repo and should
# not drift based on naive building-number parsing alone.
RADIO_BUILDING_ID_OVERRIDES: dict[str, str] = {
    normalize_free_text("Savoy Building 1 v5000"): "000002.004",
    normalize_free_text("Savoy Building 2 v5000"): "000002.005",
    normalize_free_text("Savoy Building 3 v5000"): "000002.006",
    normalize_free_text("Savoy Building 4 v5000"): "000002.007",
    normalize_free_text("Savoy Building 5 v5000"): "000002.008",
    normalize_free_text("Savoy Building 6 v5000"): "000002.009",
    normalize_free_text("Savoy - Building 7 v5000"): "000002.010",
}


@lru_cache(maxsize=1)
def load_customer_port_map() -> dict[str, Any]:
    if not ARTIFACT_PORT_MAP.exists():
        return {"summary": {}, "ports": []}
    return json.loads(ARTIFACT_PORT_MAP.read_text())


@lru_cache(maxsize=1)
def load_transport_radio_scan() -> dict[str, Any]:
    if not ARTIFACT_TRANSPORT_RADIO_SCAN.exists():
        return {"summary": {}, "results": []}
    return json.loads(ARTIFACT_TRANSPORT_RADIO_SCAN.read_text())


def normalize_inventory_status(status: str | None) -> str:
    return str(status or "").strip().lower()


def inventory_deployment_bucket(status: str | None) -> str:
    normalized = normalize_inventory_status(status)
    if normalized == "active":
        return "active"
    if normalized == "staging":
        return "staging"
    if normalized in {"inventory", "storage", "offline", "planned", "decommissioning", "failed", "retired"}:
        return "storage"
    return "other"


def inventory_is_live_expected(status: str | None) -> bool:
    return inventory_deployment_bucket(status) == "active"


def inventory_radio_status(status: str | None) -> str:
    bucket = inventory_deployment_bucket(status)
    if bucket == "active":
        return "netbox_active_no_live_scan"
    if bucket == "staging":
        return "netbox_staging_predeploy"
    if bucket == "storage":
        return "netbox_nonlive_inventory"
    return "netbox_inventory_only"


def _infer_syslog_vendor(text: str) -> str | None:
    lowered = text.lower()
    if "routeros" in lowered or "mikrotik" in lowered:
        return "mikrotik"
    if "cambium" in lowered or "cnwave" in lowered or re.search(r"\bv[125]000\b", lowered):
        return "cambium"
    if "siklu" in lowered or "eh-" in lowered:
        return "siklu"
    if "tplink" in lowered or "aginet" in lowered or "hc220" in lowered or "onu" in lowered or "olt" in lowered:
        return "tplink_or_olt"
    if "vilo" in lowered:
        return "vilo"
    return None


def _parse_syslog_line(line: str, source_path: Path) -> dict[str, Any] | None:
    raw = line.strip()
    if not raw:
        return None
    match = SYSLOG_LINE_RE.match(raw)
    if match:
        ts = match.group("ts")
        host = match.group("host")
        message = match.group("msg")
    else:
        ts = None
        host = source_path.stem
        message = raw
    site_match = re.search(r"\b(\d{6})\b", f"{host} {message} {source_path}")
    device_match = re.search(r"\b(\d{6}(?:\.\d{3})?(?:\.[A-Z0-9-]+)?)\b", f"{host} {message}", re.I)
    building_match = re.search(r"\b(\d{6}\.\d{3})\b", f"{host} {message}", re.I)
    lowered = f"{host} {message}"
    vendor = _infer_syslog_vendor(lowered) or _infer_syslog_vendor(str(source_path))
    severity = None
    for token in ("critical", "error", "warning", "notice", "info", "debug"):
        if re.search(rf"\b{token}\b", lowered, re.I):
            severity = token
            break
    return {
        "timestamp": ts,
        "host": host,
        "message": message,
        "source_path": str(source_path),
        "site_id": canonical_scope(site_match.group(1)) if site_match else None,
        "building_id": canonical_scope(building_match.group(1)) if building_match else None,
        "device_hint": canonical_identity(device_match.group(1)) if device_match else None,
        "vendor": vendor,
        "severity": severity,
    }


@lru_cache(maxsize=1)
def load_syslog_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    candidates: list[Path] = []
    if ARTIFACT_SYSLOG_DIR.exists():
        candidates.extend(
            sorted(
                [
                    path
                    for path in ARTIFACT_SYSLOG_DIR.rglob("*")
                    if path.is_file() and path.suffix.lower() in {".log", ".txt", ".syslog"}
                ]
            )
        )
    for path in candidates[:200]:
        try:
            for raw in path.read_text(errors="ignore").splitlines():
                parsed = _parse_syslog_line(raw, path)
                if parsed:
                    events.append(parsed)
        except Exception:
            continue
    return events


@lru_cache(maxsize=1)
def load_tauc_nycha_audit_rows() -> list[dict[str, Any]]:
    path = _current_tauc_audit_csv()
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=1)
def load_local_online_cpe_rows() -> list[dict[str, Any]]:
    candidates: list[Path] = []
    explicit = os.environ.get("JAKE_LOCAL_ONLINE_CPE_CSV")
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(REPO_ROOT / "output" / "online_cpes_latest.csv")
    for candidate_dir in (REPO_ROOT / "output", REPO_ROOT / "artifacts", REPO_ROOT / "data"):
        if candidate_dir.exists():
            candidates.extend(sorted(candidate_dir.glob("online-*.csv"), key=lambda p: p.stat().st_mtime, reverse=True))
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            if rows and {"networkName", "status"}.issubset(rows[0].keys()):
                return rows
        except Exception:
            continue
    return []


def find_local_online_cpe_row(
    network_name: str | None = None,
    network_id: str | None = None,
    mac: str | None = None,
    serial: str | None = None,
) -> dict[str, Any] | None:
    rows = load_local_online_cpe_rows()
    target_name = str(network_name or "").strip().lower()
    target_id = str(network_id or "").strip()
    target_mac = norm_mac(mac or "") if mac else ""
    target_serial = str(serial or "").strip().upper()
    for row in rows:
        row_name = str(row.get("networkName") or "").strip().lower()
        row_id = str(row.get("networkId") or "").strip()
        row_mac = norm_mac(str(row.get("mac") or ""))
        row_serial = str(row.get("sn") or "").strip().upper()
        if target_name and row_name == target_name:
            return row
        if target_id and row_id == target_id:
            return row
        if target_mac and row_mac == target_mac:
            return row
        if target_serial and row_serial == target_serial:
            return row
    return None


def tp_link_mac_variants(mac: str | None) -> list[str]:
    base = norm_mac(mac or "")
    clean = "".join(ch for ch in base if ch in "0123456789abcdef")
    if len(clean) != 12:
        return [base] if base else []
    octets = [int(clean[i : i + 2], 16) for i in range(0, 12, 2)]
    variants: list[str] = []
    first_candidates = {octets[0]}
    if mac_vendor_group(base) == "tplink":
        # HC220-style drift commonly shows up as 30: -> 32: on the WAN side.
        first_candidates.add((octets[0] + 0x02) & 0xFF)
        first_candidates.add((octets[0] - 0x02) & 0xFF)
    for first in sorted(first_candidates):
        for delta in (-1, 0, 1):
            probe = octets.copy()
            probe[0] = first
            probe[5] = (probe[5] + delta) & 0xFF
            variants.append(":".join(f"{value:02x}" for value in probe))
    deduped: list[str] = []
    seen: set[str] = set()
    for value in variants:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def adjacent_mac_variants(mac: str | None, deltas: tuple[int, ...] = (-1, 1)) -> list[str]:
    base = norm_mac(mac or "")
    clean = "".join(ch for ch in base if ch in "0123456789abcdef")
    if len(clean) != 12:
        return []
    value = int(clean, 16)
    variants: list[str] = []
    seen: set[str] = set()
    for delta in deltas:
        probe = (value + delta) & ((1 << 48) - 1)
        candidate = ":".join(f"{(probe >> shift) & 0xFF:02x}" for shift in range(40, -1, -8))
        if candidate in seen:
            continue
        seen.add(candidate)
        variants.append(candidate)
    return variants


def load_dotenv(path: Path) -> None:
    shared_load_env_file(path)


def apply_env_aliases() -> None:
    aliases = [
        ("SSH_MCP_USERNAME", "username"),
        ("SSH_MCP_PASSWORD", "password"),
        ("TAUC_PASSWORD", "TPLINK_ID_PASSWORD"),
    ]
    for target, source in aliases:
        if not os.environ.get(target) and os.environ.get(source):
            os.environ[target] = os.environ[source]


def seed_project_envs() -> None:
    shared_seed_project_envs(REPO_ROOT)
    apply_env_aliases()


def _ssh_mcp_username() -> str:
    return str(os.environ.get("SSH_MCP_USERNAME") or "").strip()


def _ssh_mcp_password() -> str:
    return str(os.environ.get("SSH_MCP_PASSWORD") or "").strip()


def _tauc_password() -> str:
    return str(os.environ.get("TAUC_PASSWORD") or "").strip()


def _positron_username() -> str:
    return str(os.environ.get("POSITRON_USERNAME") or "").strip()


def _positron_password() -> str:
    return str(os.environ.get("POSITRON_PASSWORD") or "").strip()


def _olt_telnet_password() -> str:
    return str(os.environ.get("OLT_TELNET_PASSWORD") or os.environ.get("olt_telnet_password") or "").strip()


def _looks_like_nycha_info_header(row: list[str] | None) -> bool:
    if not row:
        return False
    normalized = {str(value or "").strip().lower() for value in row}
    required = {"address", "unit", "mac address"}
    return required.issubset(normalized)


def _rows_from_csv_matrix(data: list[list[str]], header_index: int) -> list[dict[str, str]]:
    if header_index < 0 or header_index >= len(data):
        return []
    header = data[header_index]
    rows: list[dict[str, str]] = []
    for raw in data[header_index + 1:]:
        if not raw or not any(str(cell or "").strip() for cell in raw):
            continue
        rows.append({header[i]: (raw[i] if i < len(raw) else "") for i in range(len(header))})
    return rows


@lru_cache(maxsize=1)
def load_nycha_info_rows() -> list[dict[str, str]]:
    path = _current_nycha_info_csv()
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        data = list(csv.reader(handle))
    if not data:
        return []

    # WHY: Jake has historically consumed the installation-tracker export whose header starts on row 13,
    # but real validation also uses a simpler inventory CSV with the header on row 1. The loader must
    # accept both formats so runtime evidence reflects the actual available artifact instead of silently
    # collapsing to zero rows.
    if _looks_like_nycha_info_header(data[0]):
        return _rows_from_csv_matrix(data, 0)
    if len(data) >= 13 and _looks_like_nycha_info_header(data[12]):
        return _rows_from_csv_matrix(data, 12)
    return []


def infer_cpe_vendor_hint(
    network_name: str | None = None,
    mac: str | None = None,
    serial: str | None = None,
) -> dict[str, Any]:
    network_text = str(network_name or "").strip()
    normalized_mac = norm_mac(mac or "")
    serial_text = str(serial or "").strip().upper()
    if serial_text.startswith("TPLG-") or serial_text.startswith("Y"):
        return {"vendor": "tplink_hc220", "source": "serial_prefix"}
    if normalized_mac.startswith("e8:da:00:"):
        return {"vendor": "vilo", "source": "mac_oui"}

    if network_text:
        lowered = network_text.lower()
        for row in load_nycha_info_rows():
            if str(row.get("PPPoE") or "").strip().lower() != lowered:
                continue
            ap_make = str(row.get("AP Make") or "").strip().lower()
            if "tp-link" in ap_make:
                return {"vendor": "tplink_hc220", "source": "nycha_ap_make", "row": row}
            if "vilo" in ap_make:
                return {"vendor": "vilo", "source": "nycha_ap_make", "row": row}
            scan = str(row.get("Scan") or "").strip()
            if "DM=HC220" in scan.upper():
                return {"vendor": "tplink_hc220", "source": "nycha_scan", "row": row}
            if scan.startswith("E8:DA:00:") or "VILO_" in scan.upper():
                return {"vendor": "vilo", "source": "nycha_scan", "row": row}
            break
    return {"vendor": "unknown", "source": None}


def infer_site_from_network_name(network_name: str | None) -> str | None:
    lowered = str(network_name or "").strip().lower()
    for alias, site_id in SITE_ALIAS_MAP.items():
        if lowered.startswith(alias):
            return site_id
    return None


def normalize_address_text(value: str | None) -> str:
    return normalize_free_text(value)


def load_anythingllm_mcp_env(server_name: str) -> dict[str, str]:
    path = Path(os.environ.get(
        "JAKE_ANYTHINGLLM_MCP_CONFIG",
        str(REPO_ROOT / "config" / "anythingllm_mcp_servers.json"),
    ))
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return (data.get('mcpServers', {}).get(server_name, {}) or {}).get('env', {}) or {}
    except Exception:
        return {}


def getenv_fallback(name: str, server_name: str) -> str:
    return os.environ.get(name, '') or load_anythingllm_mcp_env(server_name).get(name, '') or ''


def load_local_env_file() -> None:
    shared_seed_project_envs(REPO_ROOT)


def _current_tauc_audit_csv() -> Path:
    env_value = os.environ.get("JAKE_TAUC_AUDIT_CSV")
    if env_value:
        return Path(env_value)
    return TAUC_NYCHA_AUDIT_CSV


def _current_nycha_info_csv() -> Path:
    env_value = os.environ.get("JAKE_NYCHA_INFO_CSV")
    if env_value:
        return Path(env_value)
    candidate = NYCHA_INFO_CSV
    if candidate.exists():
        return candidate
    fallback_candidates = [
        REPO_ROOT / "data" / "nycha_info.csv",
        REPO_ROOT / "output" / "nycha_info.csv",
    ]
    for fallback in fallback_candidates:
        if fallback.exists():
            return fallback
    return candidate


def _load_package_from_src(package_name: str, src_root: Path) -> None:
    package_init = src_root / package_name / "__init__.py"
    if not package_init.exists():
        raise ImportError(f"{package_name} package not found under {src_root}")
    spec = importlib.util.spec_from_file_location(
        package_name,
        package_init,
        submodule_search_locations=[str(src_root / package_name)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not build import spec for {package_name} from {src_root}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)


def _load_ssh_mcp_runtime() -> tuple[Any, Any, Any]:
    try:
        from ssh_mcp.config import ServerConfig
        from ssh_mcp.db import Store
        from ssh_mcp.executor import SSHExecutor
        return ServerConfig, Store, SSHExecutor
    except Exception as import_exc:
        ssh_src = Path(os.environ.get("JAKE_SSH_MCP_SRC", str(SSH_MCP_ROOT / "src")))
        if not ssh_src.exists():
            raise ImportError(f"ssh_mcp import failed and JAKE_SSH_MCP_SRC is unavailable: {import_exc}") from import_exc
        _load_package_from_src("ssh_mcp", ssh_src)
        from ssh_mcp.config import ServerConfig
        from ssh_mcp.db import Store
        from ssh_mcp.executor import SSHExecutor
        return ServerConfig, Store, SSHExecutor


class HttpJSONClient:
    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}

    def request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))


class HttpTextClient:
    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}

    def request(self, path: str) -> str:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")


class ThreadLocalSQLite:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def execute(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        return self._conn().execute(*args, **kwargs)


PROM_METRIC_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})?\s+([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)$")
PROM_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


def parse_prometheus_metrics(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PROM_METRIC_RE.match(line)
        if not match:
            continue
        name, label_blob, value = match.groups()
        labels: dict[str, str] = {}
        if label_blob:
            for key, label_value in PROM_LABEL_RE.findall(label_blob):
                labels[key] = bytes(label_value, "utf-8").decode("unicode_escape")
        numeric = float(value)
        rows.append({"name": name, "labels": labels, "value": int(numeric) if numeric.is_integer() else numeric})
    return rows


class JakeOps:
    def __init__(self) -> None:
        load_local_env_file()
        load_nycha_info_rows.cache_clear()
        load_tauc_nycha_audit_rows.cache_clear()
        db_path = os.environ.get("JAKE_OPS_DB", str(REPO_ROOT / "network_map.db"))
        self.db = ThreadLocalSQLite(db_path)

        self.bigmac: BigmacClient | None = None
        self.alerts = None
        self.netbox = None
        self.cnwave = None
        self.cnwave_controller = None
        self.tauc = None
        self.vilo_api = None

        self.bigmac = BigmacClient.from_env(REPO_ROOT)
        if not self.bigmac.configured():
            self.bigmac = None

        alert_url = getenv_fallback("ALERTMANAGER_URL", "alertmanager_mcp").rstrip("/")
        if alert_url:
            self.alerts = HttpJSONClient(alert_url, {"Accept": "application/json"})

        netbox_url = getenv_fallback("NETBOX_URL", "netbox_mcp").rstrip("/")
        netbox_token = getenv_fallback("NETBOX_TOKEN", "netbox_mcp")
        if netbox_url and netbox_token:
            self.netbox = HttpJSONClient(netbox_url, {"Authorization": f"Token {netbox_token}", "Accept": "application/json"})

        cnwave_exporter_url = getenv_fallback("CNWAVE_EXPORTER_URL", "cnwave_exporter_mcp").rstrip("/")
        if cnwave_exporter_url:
            self.cnwave = HttpTextClient(cnwave_exporter_url, {"Accept": "text/plain"})
        self.cnwave_controller = CnwaveControllerAdapter()

        self.tauc = TaucOpsAdapter()
        self.vilo_api = ViloOpsAdapter()

        self._netbox_devices_cache: list[dict[str, Any]] | None = None
        self._location_prefix_index_cache: list[dict[str, Any]] | None = None
        self._site_topology_cache: dict[str, dict[str, Any]] = {}
        self._positron_read_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def _recent_site_router_candidates(self, site_id: str | None, limit_scans: int = 8) -> list[dict[str, Any]]:
        canonical_site_id = canonical_scope(site_id)
        if not canonical_site_id:
            return []
        scan_ids = [
            int(row[0])
            for row in self.db.execute("select id from scans order by id desc limit ?", (limit_scans,)).fetchall()
        ]
        if not scan_ids:
            return []
        placeholders = ",".join("?" for _ in scan_ids)
        rows = [
            dict(r)
            for r in self.db.execute(
                f"""
                select scan_id, identity, ip
                from devices
                where scan_id in ({placeholders})
                  and identity like ?
                order by scan_id desc, identity
                """,
                (*scan_ids, f"{canonical_site_id}%"),
            ).fetchall()
        ]
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            identity = canonical_identity(row.get("identity"))
            ip = str(row.get("ip") or "").strip()
            if not identity or not ip:
                continue
            if not re.search(r"(?:^|\.)R\d{1,2}$", identity, re.IGNORECASE):
                continue
            key = (identity, ip)
            if key in seen:
                continue
            seen.add(key)
            out.append({"identity": identity, "ip": ip})
        return out

    def _evidence_conn(self) -> sqlite3.Connection:
        JAKE_EVIDENCE_DB.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(JAKE_EVIDENCE_DB)
        conn.row_factory = sqlite3.Row
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(ppp_unit_evidence)").fetchall()
        }
        if existing and "source_scan_id" not in existing:
            conn.execute("drop table if exists ppp_unit_evidence")
        conn.execute(
            """
            create table if not exists ppp_unit_evidence (
                building_id text not null,
                address text,
                unit text not null,
                network_name text,
                mac text,
                router_ip text,
                source_scan_id integer not null,
                sources_json text not null,
                primary key (building_id, unit, network_name, mac)
            )
            """
        )
        conn.execute("create index if not exists idx_ppp_unit_evidence_building on ppp_unit_evidence(building_id, source_scan_id)")
        conn.execute(
            """
            create table if not exists evidence_meta (
                key text primary key,
                value text not null
            )
            """
        )
        return conn

    def _resolve_building_from_network_name(self, network_name: str) -> dict[str, Any] | None:
        name_compact = compact_free_text(network_name)
        if not name_compact:
            return None
        best: dict[str, Any] | None = None
        for row in self._location_prefix_index():
            stem = address_stem_compact(row.get("location"))
            if not stem or stem not in name_compact:
                continue
            if best is None or len(stem) > len(best["stem"]):
                best = {
                    "building_id": canonical_scope(row.get("prefix")),
                    "address": str(row.get("location") or "").strip(),
                    "stem": stem,
                }
        return best

    def _refresh_ppp_unit_evidence(self) -> None:
        scan_id = self.latest_scan_id()
        with self._evidence_conn() as conn:
            current = conn.execute("select value from evidence_meta where key='ppp_unit_evidence_scan_id'").fetchone()
            existing_count = conn.execute("select count(*) from ppp_unit_evidence").fetchone()[0]
            if current and str(current["value"]) == str(scan_id) and existing_count:
                return
            recent_scan_ids = [
                row[0]
                for row in self.db.execute("select id from scans order by id desc limit 5").fetchall()
            ]
            if not recent_scan_ids:
                return
            placeholders = ",".join("?" for _ in recent_scan_ids)
            rows = [
                dict(r)
                for r in self.db.execute(
                    f"""
                    select distinct p.scan_id, p.name, p.caller_id, p.router_ip
                    from router_ppp_active p
                    where p.scan_id in ({placeholders})
                    and p.name is not null and trim(p.name) != ''
                    order by p.scan_id desc, p.name
                    """,
                    recent_scan_ids,
                ).fetchall()
            ]
            conn.execute("delete from ppp_unit_evidence")
            seen_units: set[tuple[str, str]] = set()
            for row in rows:
                network_name = str(row.get("name") or "").strip()
                resolved = self._resolve_building_from_network_name(network_name)
                if not resolved:
                    continue
                remainder = compact_free_text(network_name).split(resolved["stem"], 1)
                suffix = remainder[1] if len(remainder) == 2 else ""
                unit = parse_unit_token(suffix)
                if not unit:
                    continue
                dedupe_key = (resolved["building_id"], unit)
                if dedupe_key in seen_units:
                    continue
                seen_units.add(dedupe_key)
                conn.execute(
                    """
                    insert or replace into ppp_unit_evidence (
                        building_id, address, unit, network_name, mac, router_ip, source_scan_id, sources_json
                    ) values (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resolved["building_id"],
                        resolved["address"],
                        unit,
                        network_name,
                        norm_mac(row.get("caller_id") or ""),
                        str(row.get("router_ip") or ""),
                        int(row.get("scan_id") or scan_id),
                        json.dumps(["router_pppoe_session"]),
                    ),
                )
            conn.execute(
                "insert into evidence_meta(key, value) values('ppp_unit_evidence_scan_id', ?) on conflict(key) do update set value=excluded.value",
                (str(scan_id),),
            )
            conn.commit()

    def _ppp_unit_evidence_for_building(self, building_id: str) -> list[dict[str, Any]]:
        building_id = canonical_scope(building_id)
        if not building_id:
            return []
        self._refresh_ppp_unit_evidence()
        with self._evidence_conn() as conn:
            rows = conn.execute(
                """
                select building_id, address, unit, network_name, mac, router_ip, source_scan_id, sources_json
                from ppp_unit_evidence
                where building_id=?
                order by source_scan_id desc, unit, network_name
                """,
                (building_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "sources": json.loads(row["sources_json"]) if row["sources_json"] else [],
            }
            for row in rows
        ]

    def latest_scan_id(self) -> int:
        row = self.db.execute("select max(id) as id from scans").fetchone()
        if not row or row["id"] is None:
            raise ValueError("No scan data found in network_map.db")
        return int(row["id"])

    def latest_scan_meta(self) -> dict[str, Any]:
        row = self.db.execute("select id, started_at, finished_at, subnet, hosts_tested, api_reachable from scans order by id desc limit 1").fetchone()
        return dict(row) if row else {}

    def _local_scan_trigger_command(self, subnet: str | None = None) -> list[str] | None:
        mapper_path = REPO_ROOT / "scripts" / "network_mapper.py"
        if not mapper_path.exists():
            return None
        env_path = next((candidate for candidate in project_env_candidates(REPO_ROOT) if candidate.exists()), None)
        if env_path is None:
            return None
        python_bin = REPO_ROOT / ".venv" / "bin" / "python"
        python_exec = str(python_bin if python_bin.exists() else sys.executable)
        db_path = Path(os.environ.get("JAKE_OPS_DB", str(REPO_ROOT / "data" / "network_map.db")))
        effective_subnet = str(subnet or os.environ.get("JAKE_SCAN_SUBNET") or "192.168.44.0/24")
        keep_scans = str(os.environ.get("JAKE_SCAN_KEEP_SCANS") or "20")
        workers = str(os.environ.get("JAKE_SCAN_WORKERS") or "48")
        host_vid = str(os.environ.get("JAKE_SCAN_HOST_VID") or "20")
        return [
            python_exec,
            str(mapper_path),
            "--db",
            str(db_path),
            "--env",
            str(env_path),
            "scan",
            "--subnet",
            effective_subnet,
            "--workers",
            workers,
            "--keep-scans",
            keep_scans,
            "--host-vid",
            host_vid,
        ]

    def trigger_scan_refresh(
        self,
        site_id: str | None = None,
        building_id: str | None = None,
        address_text: str | None = None,
    ) -> dict[str, Any]:
        before_scan = self.latest_scan_meta()
        trigger_cmd = str(os.environ.get("JAKE_SCAN_TRIGGER_CMD") or "").strip()
        command = shlex.split(trigger_cmd) if trigger_cmd else self._local_scan_trigger_command(str(before_scan.get("subnet") or ""))
        if not command:
            return {
                "available": False,
                "triggered": False,
                "error": "No Jake2-local scan trigger command is configured, and no local network_mapper scanner is available.",
                "before_scan": before_scan,
                "site_id": site_id,
                "building_id": building_id,
                "address_text": address_text,
            }

        timeout_seconds = max(int(os.environ.get("JAKE_SCAN_TRIGGER_TIMEOUT_SECONDS") or "60"), 1)
        wait_seconds = max(int(os.environ.get("JAKE_SCAN_WAIT_SECONDS") or "15"), 0)
        poll_seconds = max(float(os.environ.get("JAKE_SCAN_POLL_SECONDS") or "1"), 0.2)
        env = dict(os.environ)
        if site_id:
            env["JAKE_TRIGGER_SITE_ID"] = str(site_id)
        if building_id:
            env["JAKE_TRIGGER_BUILDING_ID"] = str(building_id)
        if address_text:
            env["JAKE_TRIGGER_ADDRESS_TEXT"] = str(address_text)
        before_scan_id = before_scan.get("id")
        started_at = time.time()
        try:
            proc = subprocess.run(
                command,
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "available": True,
                "triggered": False,
                "error": f"Scan trigger command timed out after {timeout_seconds} seconds.",
                "before_scan": before_scan,
                "site_id": site_id,
                "building_id": building_id,
                "address_text": address_text,
                "command": command,
                "stdout": str(exc.stdout or "")[-1000:],
                "stderr": str(exc.stderr or "")[-1000:],
            }
        except Exception as exc:
            return {
                "available": True,
                "triggered": False,
                "error": f"Scan trigger command failed to start: {exc}",
                "before_scan": before_scan,
                "site_id": site_id,
                "building_id": building_id,
                "address_text": address_text,
                "command": command,
            }

        after_scan = before_scan
        scan_changed = False
        deadline = started_at + wait_seconds
        while time.time() <= deadline:
            after_scan = self.latest_scan_meta()
            if after_scan.get("id") != before_scan_id:
                scan_changed = True
                break
            if wait_seconds <= 0:
                break
            time.sleep(poll_seconds)

        return {
            "available": True,
            "triggered": proc.returncode == 0,
            "scan_changed": scan_changed,
            "before_scan": before_scan,
            "after_scan": after_scan,
            "site_id": site_id,
            "building_id": building_id,
            "address_text": address_text,
            "command": command,
            "returncode": proc.returncode,
            "stdout": str(proc.stdout or "")[-1000:],
            "stderr": str(proc.stderr or "")[-1000:],
            "error": None if proc.returncode == 0 else f"Scan trigger command exited with status {proc.returncode}.",
        }

    def _device_rows_for_prefix(self, scan_id: int, prefix: str | None) -> list[dict[str, Any]]:
        if prefix:
            rows = self.db.execute(
                "select identity, ip, model, version from devices where scan_id=? and identity like ? order by identity",
                (scan_id, f"{prefix}%"),
            ).fetchall()
        else:
            rows = self.db.execute(
                "select identity, ip, model, version from devices where scan_id=? order by identity",
                (scan_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _outlier_rows_for_prefix(self, scan_id: int, prefix: str | None) -> list[dict[str, Any]]:
        query = """
            select o.ip, d.identity, o.interface, o.direction, o.severity, o.note
            from one_way_outliers o
            left join devices d on d.scan_id=o.scan_id and d.ip=o.ip
            where o.scan_id=?
        """
        params: list[Any] = [scan_id]
        if prefix:
            query += " and d.identity like ?"
            params.append(f"{prefix}%")
        query += " order by d.identity, o.interface"
        return [dict(r) for r in self.db.execute(query, tuple(params))]

    def _alerts_for_site(self, site_id: str) -> list[dict[str, Any]]:
        if not self.alerts:
            return []
        try:
            return self.alerts.request("/api/v2/alerts", {"active": "true", "filter": [f"site_id={site_id}"]})
        except Exception:
            return []

    def _netbox_all_devices(self) -> list[dict[str, Any]]:
        if self._netbox_devices_cache is not None:
            return self._netbox_devices_cache
        if not self.netbox:
            raise ValueError("NetBox is not configured")
        offset = 0
        limit = 200
        results: list[dict[str, Any]] = []
        try:
            while True:
                payload = self.netbox.request("/api/dcim/devices/", {"limit": limit, "offset": offset})
                batch = payload.get("results") or []
                results.extend(batch)
                if not payload.get("next") or not batch:
                    break
                offset += limit
        except Exception:
            self._netbox_devices_cache = []
            return self._netbox_devices_cache
        self._netbox_devices_cache = results
        return results

    def _netbox_interface(self, device_name: str, interface_name: str) -> dict[str, Any] | None:
        if not self.netbox:
            return None
        payload = self.netbox.request("/api/dcim/interfaces/", {"device": device_name, "name": interface_name, "limit": 1})
        results = payload.get("results") or []
        return results[0] if results else None

    def _netbox_device_interfaces(self, device_name: str) -> list[dict[str, Any]]:
        if not self.netbox:
            return []
        offset = 0
        limit = 100
        results: list[dict[str, Any]] = []
        while True:
            payload = self.netbox.request("/api/dcim/interfaces/", {"device": device_name, "limit": limit, "offset": offset})
            batch = payload.get("results") or []
            results.extend(batch)
            if not payload.get("next") or not batch:
                break
            offset += limit
        return results

    def _netbox_site_devices(self, site_id: str) -> list[dict[str, Any]]:
        target = canonical_scope(site_id)
        rows: list[dict[str, Any]] = []
        for device in self._netbox_all_devices():
            device_site = canonical_scope((device.get("site") or {}).get("slug") or (device.get("site") or {}).get("name"))
            if device_site == target:
                rows.append(device)
        return sorted(rows, key=lambda row: str(row.get("name") or ""))

    def _netbox_primary_ip(self, device: dict[str, Any]) -> str | None:
        primary = device.get("primary_ip4") or device.get("primary_ip")
        if isinstance(primary, dict):
            address = str(primary.get("address") or primary.get("display") or "").strip()
        else:
            address = str(primary or "").strip()
        return address.split("/", 1)[0] if address else None

    def _netbox_radio_rows(self, site_id: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        target_site = canonical_scope(site_id) if site_id else None
        for device in self._netbox_all_devices():
            role = str(((device.get("role") or {}).get("name")) or "").strip()
            if role.lower() != "radio":
                continue
            row_site = canonical_scope((device.get("site") or {}).get("slug") or (device.get("site") or {}).get("name"))
            if target_site and row_site != target_site:
                continue
            status = str(((device.get("status") or {}).get("label")) or (device.get("status") or "")).strip() or None
            rows.append(
                {
                    "name": str(device.get("name") or "").strip(),
                    "primary_ip": self._netbox_primary_ip(device),
                    "site_id": row_site,
                    "role": role or None,
                    "device_type": str(((device.get("device_type") or {}).get("model")) or "").strip() or None,
                    "location": str(((device.get("location") or {}).get("display")) or ((device.get("location") or {}).get("name")) or "").strip() or None,
                    "status": status,
                    "status_bucket": inventory_deployment_bucket(status),
                    "is_live_expected": inventory_is_live_expected(status),
                    "serial": str(device.get("serial") or "").strip() or None,
                }
            )
        return rows

    def _match_netbox_radio(self, query: str | None = None, name: str | None = None, ip: str | None = None, site_id: str | None = None) -> dict[str, Any] | None:
        needle_name = normalize_free_text(name or query or "")
        needle_ip = str(ip or "").strip()
        rows = self._netbox_radio_rows(site_id)
        exact_name: list[dict[str, Any]] = []
        contains_name: list[dict[str, Any]] = []
        exact_ip: list[dict[str, Any]] = []
        for row in rows:
            row_name = str(row.get("name") or "").strip()
            row_ip = str(row.get("primary_ip") or "").strip()
            if needle_ip and row_ip == needle_ip:
                exact_ip.append(row)
            if needle_name:
                normalized_row = normalize_free_text(row_name)
                if needle_name == normalized_row:
                    exact_name.append(row)
                elif needle_name in normalized_row:
                    contains_name.append(row)
        if len(exact_ip) == 1:
            return exact_ip[0]
        if len(exact_name) == 1:
            return exact_name[0]
        if len(contains_name) == 1:
            return contains_name[0]
        return None

    def _netbox_radio_replacement_for_scan_row(self, scan_row: dict[str, Any], site_id: str | None = None) -> dict[str, Any] | None:
        target_site = canonical_scope(site_id)
        location = str(scan_row.get("location") or "").strip()
        if not location:
            return None
        location_key = normalize_free_text(location)
        candidates = [
            row for row in self._netbox_radio_rows(target_site)
            if normalize_free_text(str(row.get("location") or "")) == location_key and inventory_is_live_expected(row.get("status"))
        ]
        if len(candidates) != 1:
            return None
        candidate = candidates[0]
        same_name = normalize_free_text(str(candidate.get("name") or "")) == normalize_free_text(str(scan_row.get("name") or ""))
        same_ip = str(candidate.get("primary_ip") or "").strip() == str(scan_row.get("ip") or "").strip()
        if same_name and same_ip:
            return None
        return candidate

    def _netbox_site_inventory(self, site_id: str) -> list[dict[str, Any]]:
        inventory: list[dict[str, Any]] = []
        for device in self._netbox_site_devices(site_id):
            name = str(device.get("name") or "").strip()
            interfaces = self._netbox_device_interfaces(name)
            status = str(((device.get("status") or {}).get("label")) or (device.get("status") or "")).strip() or None
            macs = sorted(
                {
                    norm_mac(row.get("mac_address") or "")
                    for row in interfaces
                    if norm_mac(row.get("mac_address") or "")
                }
            )
            peers: list[dict[str, Any]] = []
            seen_peers: set[tuple[str, str]] = set()
            for row in interfaces:
                interface_name = str(row.get("name") or "").strip()
                for peer in row.get("link_peers") or []:
                    peer_device = str(((peer.get("device") or {}).get("name")) or "").strip()
                    peer_interface = str(peer.get("name") or "").strip()
                    if not peer_device:
                        continue
                    dedupe_key = (peer_device, peer_interface)
                    if dedupe_key in seen_peers:
                        continue
                    seen_peers.add(dedupe_key)
                    peers.append(
                        {
                            "from_interface": interface_name,
                            "to_device": peer_device,
                            "to_interface": peer_interface or None,
                        }
                    )
            inventory.append(
                {
                    "name": name,
                    "primary_ip": self._netbox_primary_ip(device),
                    "role": str(((device.get("role") or {}).get("name")) or "").strip() or None,
                    "device_type": str(((device.get("device_type") or {}).get("model")) or "").strip() or None,
                    "location": str(((device.get("location") or {}).get("display")) or ((device.get("location") or {}).get("name")) or "").strip() or None,
                    "status": status,
                    "status_bucket": inventory_deployment_bucket(status),
                    "is_live_expected": inventory_is_live_expected(status),
                    "serial": str(device.get("serial") or "").strip() or None,
                    "interface_count": len(interfaces),
                    "known_macs": macs[:20],
                    "connected_to": peers[:20],
                }
            )
        return inventory

    def _netbox_site_inventory_light(self, site_id: str) -> list[dict[str, Any]]:
        inventory: list[dict[str, Any]] = []
        for device in self._netbox_site_devices(site_id):
            status = str(((device.get("status") or {}).get("label")) or (device.get("status") or "")).strip() or None
            inventory.append(
                {
                    "name": str(device.get("name") or "").strip(),
                    "primary_ip": self._netbox_primary_ip(device),
                    "role": str(((device.get("role") or {}).get("name")) or "").strip() or None,
                    "device_type": str(((device.get("device_type") or {}).get("model")) or "").strip() or None,
                    "location": str(((device.get("location") or {}).get("display")) or ((device.get("location") or {}).get("name")) or "").strip() or None,
                    "status": status,
                    "status_bucket": inventory_deployment_bucket(status),
                    "is_live_expected": inventory_is_live_expected(status),
                    "serial": str(device.get("serial") or "").strip() or None,
                    "interface_count": int(device.get("interfaces_count") or 0) if str(device.get("interfaces_count") or "").isdigit() else 0,
                    "known_macs": [],
                    "connected_to": [],
                }
            )
        return inventory

    def list_sites_inventory(self, limit: int = 200) -> dict[str, Any]:
        if not self.netbox:
            raise ValueError("NetBox is not configured")
        sites: dict[str, dict[str, Any]] = {}
        for device in self._netbox_all_devices():
            raw_site = (device.get("site") or {})
            site_id = canonical_scope(raw_site.get("slug") or raw_site.get("name"))
            if not site_id:
                continue
            entry = sites.setdefault(
                site_id,
                {
                    "site_id": site_id,
                    "site_name": raw_site.get("name") or raw_site.get("slug") or site_id,
                    "locations": set(),
                    "router_172_ips": set(),
                    "device_count": 0,
                    "sample_devices": [],
                },
            )
            entry["device_count"] += 1
            location = str(((device.get("location") or {}).get("display")) or ((device.get("location") or {}).get("name")) or "").strip()
            if location:
                entry["locations"].add(location)
            ip = self._netbox_primary_ip(device)
            if ip and ip.startswith("172."):
                entry["router_172_ips"].add(ip)
            name = str(device.get("name") or "").strip()
            if name and len(entry["sample_devices"]) < 8:
                entry["sample_devices"].append(name)

        rows: list[dict[str, Any]] = []
        for site_id, row in sorted(sites.items()):
            rows.append(
                {
                    "site_id": site_id,
                    "site_name": row["site_name"],
                    "locations": sorted(row["locations"]),
                    "router_172_ips": sorted(row["router_172_ips"]),
                    "device_count": row["device_count"],
                    "sample_devices": row["sample_devices"],
                }
            )
        return {"count": len(rows), "sites": rows[:limit]}

    def search_sites_inventory(self, query: str, limit: int = 25) -> dict[str, Any]:
        q = normalize_free_text(query)
        payload = self.list_sites_inventory(limit=1000)
        matches: list[dict[str, Any]] = []
        for row in payload.get("sites") or []:
            haystacks = [
                str(row.get("site_id") or ""),
                str(row.get("site_name") or ""),
                " ".join(row.get("locations") or []),
                " ".join(row.get("sample_devices") or []),
            ]
            text = normalize_free_text(" ".join(haystacks))
            if q and q in text:
                matches.append(row)
        return {"query": query, "count": len(matches), "sites": matches[:limit]}

    def _location_prefix_index(self) -> list[dict[str, Any]]:
        if self._location_prefix_index_cache is not None:
            return self._location_prefix_index_cache
        index: dict[tuple[str, str], dict[str, Any]] = {}
        for device in self._netbox_all_devices():
            name = str(device.get("name") or "").strip()
            if not DEVICE_LABEL_RE.match(name):
                continue
            identity = canonical_identity(name)
            if not identity:
                continue
            prefix = ".".join(identity.split(".")[:2])
            location = str((device.get("location") or {}).get("display") or (device.get("location") or {}).get("name") or "").strip()
            if not location:
                continue
            site_code = canonical_scope((device.get("site") or {}).get("slug") or (device.get("site") or {}).get("name"))
            key = (location, prefix)
            row = index.setdefault(
                key,
                {
                    "location": location,
                    "location_norm": normalize_free_text(location),
                    "location_compact": compact_free_text(location),
                    "prefix": prefix,
                    "site_code": site_code,
                    "device_names": [],
                },
            )
            row["device_names"].append(identity)
        self._location_prefix_index_cache = sorted(index.values(), key=lambda x: (x["location"], x["prefix"]))
        return self._location_prefix_index_cache

    def _resolve_building_from_address(self, address_text: str) -> dict[str, Any]:
        addr_norm = normalize_free_text(address_text)
        if addr_norm in ADDRESS_RESOLUTION_OVERRIDES:
            override = ADDRESS_RESOLUTION_OVERRIDES[addr_norm]
            if override is None:
                return {
                    "address_text": address_text,
                    "normalized_query": addr_norm,
                    "resolved": False,
                    "best_match": None,
                    "candidates": [],
                    "override_applied": True,
                }
            return {
                "address_text": address_text,
                "normalized_query": addr_norm,
                "resolved": True,
                "best_match": override,
                "candidates": [override],
                "override_applied": True,
            }
        addr_compact = compact_free_text(address_text)
        query_tokens = [t for t in addr_norm.split() if t]
        candidates: list[dict[str, Any]] = []
        for row in self._location_prefix_index():
            loc_norm = row["location_norm"]
            loc_compact = row["location_compact"]
            score = 0
            if addr_compact and addr_compact in loc_compact:
                score += 100
            elif loc_compact and loc_compact in addr_compact:
                score += 80
            shared = [t for t in query_tokens if t in loc_norm.split()]
            score += len(shared) * 10
            if query_tokens and query_tokens[0].isdigit() and query_tokens[0] in loc_norm.split():
                score += 25
            if len(query_tokens) >= 2 and all(t in loc_norm.split() for t in query_tokens[:2]):
                score += 20
            if score > 0:
                candidates.append(
                    {
                        "location": row["location"],
                        "prefix": row["prefix"],
                        "site_code": row["site_code"],
                        "score": score,
                        "device_names": row["device_names"][:10],
                    }
                )
        candidates.sort(key=lambda x: (-x["score"], x["location"], x["prefix"]))
        best = candidates[0] if candidates else None
        return {
            "address_text": address_text,
            "normalized_query": addr_norm,
            "resolved": bool(best),
            "best_match": best,
            "candidates": candidates[:10],
        }

    def _label_audit_rows(self, rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
        invalid = []
        valid = []
        for row in rows:
            name = str(row.get("name") or row.get("identity") or "").strip()
            item = {"name": name, "source": source}
            if "ip" in row:
                item["ip"] = row.get("ip")
            if "id" in row:
                item["id"] = row.get("id")
            if DEVICE_LABEL_RE.match(name):
                valid.append(item)
            else:
                invalid.append(item)
        return {"total": len(rows), "valid": valid, "invalid": invalid}

    def get_server_info(self) -> dict[str, Any]:
        return {
            "latest_scan": self.latest_scan_meta(),
            "bigmac_configured": self.bigmac is not None,
            "alertmanager_configured": self.alerts is not None,
            "netbox_configured": self.netbox is not None,
            "cnwave_exporter_configured": self.cnwave is not None,
            "tauc": {
                **(self.tauc.summary() if self.tauc else {"cloud_configured": False, "acs_configured": False, "olt_configured": False}),
            },
            "vilo": self.vilo_api.summary() if self.vilo_api else {"configured": False},
            "tools": [tool["name"] for tool in TOOLS],
        }

    def _tauc_summary(self) -> dict[str, Any]:
        return self.tauc.summary() if self.tauc else {"cloud_configured": False, "acs_configured": False, "olt_configured": False}

    def _vilo_summary(self) -> dict[str, Any]:
        return self.vilo_api.summary() if self.vilo_api else {"configured": False}

    def _cnwave_metrics(self) -> list[dict[str, Any]]:
        import urllib.request, urllib.parse, json as _json
        base = os.environ.get("CNWAVE_EXPORTER_URL", "").rstrip("/")
        if not base:
            return []
        prometheus_mode = bool(os.environ.get("CNWAVE_PROMETHEUS_MODE", ""))
        if not prometheus_mode and self.cnwave:
            try:
                return parse_prometheus_metrics(self.cnwave.request("/metrics"))
            except Exception:
                return []
        # Prometheus API mode — query all cnwave metrics
        metric_names = [
            "cnwave_link_rssi", "cnwave_link_snr", "cnwave_link_mcs",
            "cnwave_link_status", "cnwave_link_throughput", "cnwave_link_eirp",
            "cnwave_device_status", "cnwave_device_alarms", "cnwave_device_uptime",
        ]
        rows = []
        for metric in metric_names:
            try:
                url = f"{base}/api/v1/query?query={urllib.parse.quote(metric)}"
                req = urllib.request.Request(url, headers={"User-Agent": "jake/1.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = _json.loads(resp.read())
                for result in data.get("data", {}).get("result", []):
                    labels = result.get("metric", {})
                    value = result.get("value", [None, None])
                    row = {"name": metric, "labels": labels, "value": float(value[1]) if value[1] is not None else None}
                    # Flatten common label fields for compatibility
                    for k in ("a_node", "z_node", "link_name", "site_id", "name", "node"):
                        if k in labels:
                            row[k] = labels[k]
                    rows.append(row)
            except Exception:
                continue
        return rows

    def _cnwave_site_summary(self, site_id: str) -> dict[str, Any]:
        rows = self._cnwave_metrics()
        if not rows:
            return {"configured": self.cnwave is not None, "available": False}
        scoped = [r for r in rows if str(r.get("labels", {}).get("site_id", "")) == str(site_id)]
        device_status = [r for r in scoped if r["name"] == "cnwave_device_status"]
        link_status = [r for r in scoped if r["name"] == "cnwave_link_status"]
        device_alarms = [r for r in scoped if r["name"] == "cnwave_device_alarms"]
        down_devices = [r for r in device_status if float(r["value"]) < 1]
        down_links = [r for r in link_status if float(r["value"]) < 1]
        return {
            "configured": True,
            "available": True,
            "site_id": site_id,
            "device_rows": len(device_status),
            "device_up": sum(1 for r in device_status if float(r["value"]) >= 1),
            "device_down": len(down_devices),
            "link_rows": len(link_status),
            "link_up": sum(1 for r in link_status if float(r["value"]) >= 1),
            "link_down": len(down_links),
            "alarm_total": sum(int(float(r["value"])) for r in device_alarms),
            "down_device_names": sorted({r.get("labels", {}).get("name") for r in down_devices if r.get("labels", {}).get("name")})[:20],
            "down_link_names": sorted({r.get("labels", {}).get("link_name") for r in down_links if r.get("labels", {}).get("link_name")})[:20],
        }

    def _cnwave_site_links(self, site_id: str) -> list[dict[str, Any]]:
        rows = self._cnwave_metrics()
        links: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add_link(link: dict[str, Any]) -> None:
            left = str(link.get("from_label") or "").strip()
            right = str(link.get("to_label") or "").strip()
            if not left or not right:
                return
            dedupe_key = tuple(sorted((normalize_free_text(left), normalize_free_text(right))))
            if dedupe_key in seen:
                return
            seen.add(dedupe_key)
            links.append(link)

        if rows:
            scoped = [
                r
                for r in rows
                if r["name"] == "cnwave_link_status" and str(r.get("labels", {}).get("site_id", "")) == str(site_id)
            ]
            if scoped:
                def labels_for(row: dict[str, Any]) -> dict[str, Any]:
                    return row.get("labels", {}) or {}

                def name_pair_from_labels(labels: dict[str, Any]) -> tuple[str | None, str | None]:
                    candidate_pairs = [
                        ("from_name", "to_name"),
                        ("src_name", "dst_name"),
                        ("source_name", "target_name"),
                        ("local_name", "remote_name"),
                        ("a_name", "z_name"),
                        ("node_a_name", "node_z_name"),
                        ("dn_name", "cn_name"),
                        ("pop_name", "cn_name"),
                        ("name", "peer_name"),
                    ]
                    for left_key, right_key in candidate_pairs:
                        left = str(labels.get(left_key) or "").strip()
                        right = str(labels.get(right_key) or "").strip()
                        if left and right:
                            return left, right

                    link_name = str(labels.get("link_name") or labels.get("name") or "").strip()
                    for sep in (" <-> ", " -> ", " - ", " to "):
                        if sep in link_name:
                            left, right = [part.strip() for part in link_name.split(sep, 1)]
                            if left and right:
                                return left, right
                    return None, None

                for row in scoped:
                    labels = labels_for(row)
                    left, right = name_pair_from_labels(labels)
                    if not left or not right:
                        continue
                    add_link(
                        {
                            "name": str(labels.get("link_name") or f"{left} - {right}"),
                            "kind": "cambium",
                            "from_label": left,
                            "to_label": right,
                            "status": "ok" if float(row.get("value") or 0) >= 1 else "down",
                            "metric_labels": labels,
                            "evidence_source": "cnwave_exporter",
                        }
                    )

        if links:
            return links

        # WHY: The local radio scan covers cnWave devices across all sites.
        # We no longer gate this on 000007 — instead we filter by site prefix
        # when site_id is provided, so other sites with cnWave transport
        # (e.g. 000007, 000008, future sites) get results from the same path.
        radio_scan = load_transport_radio_scan()
        mac_to_name: dict[str, str] = {}
        neighbors_by_name: dict[str, set[str]] = {}
        # WHY: Filter by site_id prefix when provided so only devices belonging
        # to the requested site are returned. When site_id is None, return all.
        effective_prefix = (canonical_scope(site_id) + ".") if site_id else None
        for row in radio_scan.get("results") or []:
            if row.get("type") != "cambium" or row.get("status") != "ok":
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            if effective_prefix and not name.startswith(effective_prefix):
                continue
            seen_macs = {
                norm_mac(str(value))
                for value in [row.get("device_mac"), *(row.get("wlan_macs") or []), *(row.get("initiator_macs") or [])]
                if str(value or "").strip()
            }
            for mac in seen_macs:
                mac_to_name[mac] = name
            neighbors_by_name[name] = {
                norm_mac(str(value))
                for value in (row.get("neighbor_macs") or [])
                if str(value or "").strip()
            }

        for name, neighbor_macs in neighbors_by_name.items():
            for neighbor_mac in neighbor_macs:
                peer_name = mac_to_name.get(neighbor_mac)
                if not peer_name or peer_name == name:
                    continue
                add_link(
                    {
                        "name": f"{name} - {peer_name}",
                        "kind": "cambium",
                        "from_label": name,
                        "to_label": peer_name,
                        "status": "ok",
                        "evidence_source": "transport_scan_neighbor",
                    }
                )

        return links

    def query_summary(self, query: str) -> dict[str, Any]:
        from core.query_core import run_operator_query

        return run_operator_query(self, query)

    def get_outage_context(self, address_text: str, unit: str) -> dict[str, Any]:
        scan_id = self.latest_scan_id()
        unit_norm = normalize_free_text(unit).replace("unit ", "").replace("apt ", "").replace("apartment ", "").strip()
        target_unit_token = parse_unit_token(unit_norm)
        target_floor, target_letter = parse_unit_parts(unit_norm)
        building = self._resolve_building_from_address(address_text)
        best = building.get("best_match") or {}
        building_id = canonical_scope(best.get("prefix"))
        site_id = canonical_scope(best.get("site_code")) if best.get("site_code") else (building_id.split(".")[0] if building_id else None)

        sessions_for_address: list[dict[str, Any]] = []
        exact_unit_sessions: list[dict[str, Any]] = []
        if building_id:
            router_prefix = canonical_scope(site_id)
            recent_scan_ids = [
                int(row[0])
                for row in self.db.execute("select id from scans order by id desc limit 5").fetchall()
            ]
            placeholders = ",".join("?" for _ in recent_scan_ids) if recent_scan_ids else "?"
            ppp_rows = [
                dict(r)
                for r in self.db.execute(
                    """
                    select p.router_ip, p.name, p.service, p.caller_id, p.address, p.uptime, d.identity
                    from router_ppp_active p
                    left join devices d on d.scan_id=p.scan_id and d.ip=p.router_ip
                    where p.scan_id in (""" + placeholders + """) and d.identity like ?
                    order by p.scan_id desc, p.name
                    """,
                    (*recent_scan_ids, f"{router_prefix}%"),
                ).fetchall()
            ]
            building_tokens = [t for t in compact_free_text(address_text).split() if t]
            address_compact = compact_free_text(address_text)
            seen_sessions: set[tuple[str, str, str]] = set()
            for row in ppp_rows:
                name = str(row.get("name") or "")
                name_compact = compact_free_text(name)
                if address_compact and address_compact in name_compact:
                    dedupe_key = (
                        name,
                        norm_mac(row.get("caller_id") or ""),
                        str(row.get("router_ip") or ""),
                    )
                    if dedupe_key in seen_sessions:
                        continue
                    seen_sessions.add(dedupe_key)
                    sessions_for_address.append(row)
                    if unit_norm and compact_free_text(unit_norm) in name_compact:
                        exact_unit_sessions.append(row)

        address_caller_ids = sorted({norm_mac(r.get("caller_id") or "") for r in sessions_for_address if r.get("caller_id")})
        bridge_hits: list[dict[str, Any]] = []
        bridge_hits_by_mac: dict[str, list[dict[str, Any]]] = {}
        if address_caller_ids:
            placeholders = ",".join("?" for _ in address_caller_ids)
            all_bridge_hits = [
                dict(r)
                for r in self.db.execute(
                    f"""
                    select d.identity, d.ip, bh.on_interface, bh.vid, bh.mac, bh.local, bh.external
                    from bridge_hosts bh
                    left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                    where bh.scan_id=? and lower(bh.mac) in ({placeholders})
                    order by d.identity, bh.on_interface
                    """,
                    [scan_id, *address_caller_ids],
                ).fetchall()
            ]
            for row in all_bridge_hits:
                mac = norm_mac(row.get("mac") or "")
                bridge_hits_by_mac.setdefault(mac, []).append(row)
            exact_caller_ids = {norm_mac(r.get("caller_id") or "") for r in exact_unit_sessions if r.get("caller_id")}
            bridge_hits = [row for row in all_bridge_hits if norm_mac(row.get("mac") or "") in exact_caller_ids]

        same_address_edge_context: list[dict[str, Any]] = []
        for row in sessions_for_address:
            caller_id = norm_mac(row.get("caller_id") or "")
            hits = bridge_hits_by_mac.get(caller_id, [])
            same_address_edge_context.append(
                {
                    "name": row.get("name"),
                    "unit_token": parse_unit_token(row.get("name")),
                    "caller_id": caller_id,
                    "best_bridge_hit": best_bridge_hit(hits),
                    "all_bridge_hits": hits[:10],
                }
            )

        port_rows = self._port_map_scope_rows(building_id=building_id) if building_id else []
        unit_comment_rows = []
        if unit_norm:
            unit_tokens = {unit_norm, f"unit {unit_norm}", unit_norm.replace(" ", "")}
            for row in port_rows:
                comment = normalize_free_text(row.get("comment"))
                if comment and any(token in comment for token in unit_tokens):
                    unit_comment_rows.append(row)

        neighboring_unit_port_hints = []
        if target_unit_token:
            target_floor_match = re.match(r"(\d+)", target_unit_token)
            target_floor_value = target_floor_match.group(1) if target_floor_match else None
            for row in same_address_edge_context:
                unit_token = row.get("unit_token")
                if not unit_token:
                    continue
                if unit_token == target_unit_token:
                    continue
                if target_floor_value and not str(unit_token).startswith(target_floor_value):
                    continue
                if row.get("best_bridge_hit"):
                    neighboring_unit_port_hints.append(row)

        inferred_unit_port_candidates = infer_unit_port_candidates(
            target_unit_token,
            target_floor,
            target_letter,
            neighboring_unit_port_hints,
            unit_comment_rows,
        )

        likely_causes: list[dict[str, Any]] = []
        suggested_checks: list[dict[str, Any]] = []
        if building_id and not exact_unit_sessions:
            likely_causes.append(
                {
                    "type": "single_unit_service_loss",
                    "confidence": "high" if sessions_for_address else "medium",
                    "reason": "The reported unit has no active PPP session while other units at the same address do, which points away from a whole-building outage.",
                }
            )
            suggested_checks.extend(
                [
                    {
                        "priority": 1,
                        "category": "physical_layer",
                        "check": "Verify the CPE has power and the WAN/LAN link LEDs are lit. Reseat or replace the patch cable and inspect the wall jack.",
                    },
                    {
                        "priority": 2,
                        "category": "cpe_mode",
                        "check": "Confirm the CPE is in router/WAN mode and not AP mode. A common AP-mode sign is the client MAC differing from the expected CPE MAC only in the last digit or last two hex digits.",
                    },
                    {
                        "priority": 3,
                        "category": "wan_config",
                        "check": "If this service is PPPoE-backed, confirm the CPE WAN is set to PPPoE and not DHCP. If DHCP is seen on VLAN 20 where PPPoE is expected, treat that as misconfiguration or fallback behavior.",
                    },
                    {
                        "priority": 4,
                        "category": "rogue_dhcp",
                        "check": "If the client is receiving the wrong address family, check for a rogue DHCP server. A common sign on TP-Link CPEs is the first octet pair shifting from 30: to 32:, which often indicates locally administered MAC behavior on a misbehaving DHCP-serving CPE.",
                    },
                ]
            )
        if inferred_unit_port_candidates:
            candidate_ports = ", ".join(f"{c['identity']} {c['on_interface']}" for c in inferred_unit_port_candidates[:3])
            likely_causes.append(
                {
                    "type": "probable_local_edge_port_issue",
                    "confidence": "medium",
                    "reason": f"Adjacent same-floor units are online and map to nearby ports, so {target_unit_token} likely lands on a neighboring access port that can be field-checked directly.",
                }
            )
            suggested_checks.insert(
                1,
                {
                    "priority": 1,
                    "category": "edge_port",
                    "check": f"Field-check the inferred access port candidate(s): {candidate_ports}. Look for link, flap history, and whether the wrong device is patched there.",
                },
            )
        if any(alert.get("labels", {}).get("severity") == "critical" for alert in (self._alerts_for_site(site_id) if self.alerts and site_id else [])):
            likely_causes.append(
                {
                    "type": "site_alert_present_but_not_unit_specific",
                    "confidence": "low",
                    "reason": "There is an active site alert, but it does not currently identify the reported unit or building as the failed path.",
                }
            )

        netbox_physical_context: list[dict[str, Any]] = []
        for candidate in inferred_unit_port_candidates[:3]:
            device_name = str(candidate.get("identity") or "")
            interface_name = str(candidate.get("on_interface") or "")
            device = None
            iface = None
            lookup_error = None
            if self.netbox and device_name:
                try:
                    device_payload = self.get_netbox_device(device_name)
                    device_results = device_payload.get("results") or []
                    device = device_results[0] if device_results else None
                except Exception as exc:
                    lookup_error = str(exc)
            if self.netbox and device_name and interface_name:
                try:
                    iface = self._netbox_interface(device_name, interface_name)
                except Exception as exc:
                    lookup_error = lookup_error or str(exc)
            netbox_physical_context.append(
                {
                    "device_name": device_name,
                    "interface_name": interface_name,
                    "device_location": (((device or {}).get("location") or {}).get("display")) or best.get("location"),
                    "device_primary_ip4": ((device or {}).get("primary_ip4") or {}).get("address"),
                    "interface_label": (iface or {}).get("label"),
                    "interface_type": (((iface or {}).get("type") or {}).get("label")),
                    "interface_enabled": (iface or {}).get("enabled"),
                    "interface_occupied": (iface or {}).get("_occupied"),
                    "cable_present": bool((iface or {}).get("cable")),
                    "connected_endpoints": (iface or {}).get("connected_endpoints"),
                    "lookup_error": lookup_error,
                }
            )

        plain_english_summary = (
            f"{address_text.title()} unit {target_unit_token or unit.upper()} is not currently online. "
            f"The building resolved to {building_id or 'unknown'}, and other units at the same address are online, so this looks more like a unit-level issue than a whole-building outage."
        )
        if inferred_unit_port_candidates:
            plain_english_summary += (
                f" Based on nearby same-floor units, the most likely access port is "
                f"{inferred_unit_port_candidates[0]['identity']} {inferred_unit_port_candidates[0]['on_interface']}."
            )
        if netbox_physical_context:
            top_ctx = netbox_physical_context[0]
            cable_text = "has a NetBox cable record" if top_ctx.get("cable_present") else "does not currently have a NetBox cable record"
            plain_english_summary += f" NetBox shows that port at {top_ctx.get('device_location') or 'the switch location'} and it {cable_text}."

        return {
            "address_text": address_text,
            "unit": unit,
            "resolution": building,
            "building_id": building_id,
            "site_id": site_id,
            "exact_unit_online": bool(exact_unit_sessions),
            "exact_unit_sessions": exact_unit_sessions[:25],
            "same_address_online_sessions": sessions_for_address[:50],
            "exact_unit_bridge_hits": bridge_hits[:25],
            "same_address_edge_context": same_address_edge_context[:50],
            "neighboring_unit_port_hints": neighboring_unit_port_hints[:25],
            "inferred_unit_port_candidates": inferred_unit_port_candidates[:10],
            "netbox_physical_context": netbox_physical_context,
            "unit_comment_matches": unit_comment_rows[:25],
            "active_alerts": self._alerts_for_site(site_id) if self.alerts and site_id else [],
            "plain_english_summary": plain_english_summary,
            "likely_causes": likely_causes,
            "suggested_checks": sorted(suggested_checks, key=lambda x: (x["priority"], x["category"])),
            "notes": {
                "unit_mapping_complete": bool(unit_comment_rows or bridge_hits),
                "ppp_name_match_method": "compact address/unit substring match against live router_ppp_active names",
                "bridge_match_method": "caller_id MACs from exact unit PPP sessions correlated against latest bridge_hosts snapshot",
                "neighboring_unit_port_hint_method": "same-address online PPP sessions correlated to latest bridge_hosts; edge ports preferred over uplinks",
            },
        }

    def audit_device_labels(self, include_valid: bool = False, limit: int = 500) -> dict[str, Any]:
        scan_id = self.latest_scan_id()
        network_rows = [
            dict(r)
            for r in self.db.execute(
                "select distinct identity, ip from devices where scan_id=? and identity is not null and trim(identity) != '' order by identity",
                (scan_id,),
            ).fetchall()
        ]
        netbox_rows = [{"name": d.get("name"), "id": d.get("id")} for d in self._netbox_all_devices() if d.get("name")]

        network = self._label_audit_rows(network_rows, "network")
        netbox = self._label_audit_rows(netbox_rows, "netbox")
        invalid_unique = sorted({row["name"] for row in [*network["invalid"], *netbox["invalid"]]})

        result = {
            "pattern": DEVICE_LABEL_RE.pattern,
            "rule": "<6 digit location>.<3 digit site>.<device type><2 digit number>",
            "network": {
                "total": network["total"],
                "invalid_count": len(network["invalid"]),
                "invalid": network["invalid"][:limit],
            },
            "netbox": {
                "total": netbox["total"],
                "invalid_count": len(netbox["invalid"]),
                "invalid": netbox["invalid"][:limit],
            },
            "combined_invalid_unique_count": len(invalid_unique),
            "combined_invalid_unique": invalid_unique[:limit],
        }
        if include_valid:
            result["network"]["valid"] = network["valid"][:limit]
            result["netbox"]["valid"] = netbox["valid"][:limit]
        return result

    def get_subnet_health(self, subnet: str | None, site_id: str | None, include_alerts: bool, include_bigmac: bool) -> dict[str, Any]:
        scan_id = self.latest_scan_id()
        # WHY: Resolve site_prefix from the site registry — never hardcode subnet-to-site.
        # Each site's mgmt_subnet is declared in SITE_SERVICE_PROFILES via get_site_mgmt_subnet().
        if site_id:
            site_prefix = site_id
        elif subnet:
            from core.shared import SITE_SERVICE_PROFILES
            site_prefix = next(
                (sid for sid, profile in SITE_SERVICE_PROFILES.items()
                 if profile.get("mgmt_subnet") == subnet),
                None,
            )
        else:
            site_prefix = None

        devices = self._device_rows_for_prefix(scan_id, site_prefix)
        outliers = self._outlier_rows_for_prefix(scan_id, site_prefix)

        result: dict[str, Any] = {
            "verified": {
                "scan": self.latest_scan_meta(),
                "device_count": len(devices),
                "outlier_count": len(outliers),
                "devices": devices[:100],
                "outliers": outliers[:100],
            },
            "inferred": [],
        }
        if include_alerts and self.alerts and site_prefix:
            result["verified"]["active_alerts"] = self._alerts_for_site(site_prefix)
        if include_bigmac and self.bigmac and site_prefix:
            result["verified"]["bigmac_stats"] = self.bigmac.request("/api/stats")
        if outliers:
            result["inferred"].append("one_way_outliers_present")
        return result

    def get_online_customers(self, scope: str | None, site_id: str | None, building_id: str | None, router_identity: str | None) -> dict[str, Any]:
        scan_id = self.latest_scan_id()
        if not site_id and scope and scope.startswith("000"):
            site_id = scope
        if not building_id and scope and scope.count(".") >= 1 and scope != site_id:
            building_id = scope
        if not router_identity and scope and re.search(r"\.R\d{1,2}$", scope, re.IGNORECASE):
            router_identity = scope

        # Resolve routers from actual PPP activity rather than assuming an old naming pattern
        # such as *.R1. This keeps counts working after identity normalization to *.R01.
        sessions = [
            dict(r)
            for r in self.db.execute(
                """
                select p.router_ip, p.name, p.service, p.caller_id, p.address, p.uptime, d.identity
                from router_ppp_active p
                left join devices d on d.scan_id=p.scan_id and d.ip=p.router_ip
                where p.scan_id=?
                order by d.identity, p.name
                """,
                (scan_id,),
            ).fetchall()
        ]
        routers_map: dict[tuple[str, str], dict[str, Any]] = {}
        filtered_sessions: list[dict[str, Any]] = []
        canonical_router_identity = canonical_identity(router_identity) if router_identity else None
        canonical_site_id = canonical_scope(site_id) if site_id else None
        canonical_building_id = canonical_scope(building_id) if building_id else None
        profile = SITE_SERVICE_PROFILES.get(canonical_site_id or "")
        for session in sessions:
            identity = canonical_identity(session.get("identity"))
            router_ip = session.get("router_ip")
            if not identity or not router_ip:
                continue
            if canonical_router_identity and identity != canonical_router_identity:
                continue
            if canonical_building_id and not identity_matches_scope(identity, canonical_building_id):
                continue
            if not canonical_building_id and canonical_site_id and not identity_matches_scope(identity, canonical_site_id):
                continue
            filtered_sessions.append(session)
            routers_map[(identity, router_ip)] = {"identity": identity, "ip": router_ip}
        routers = list(routers_map.values())
        if canonical_site_id and (not routers or not any(re.search(r"(?:^|\.)R\d{1,2}$", str(row.get("identity") or ""), re.IGNORECASE) for row in routers)):
            fallback_routers = self._recent_site_router_candidates(canonical_site_id)
            if fallback_routers:
                routers = fallback_routers
        local_rows = load_local_online_cpe_rows()
        matched_local_rows: list[dict[str, Any]] = []
        if local_rows and canonical_site_id and not building_id and not router_identity:
            matched_local_rows = [
                row for row in local_rows
                if str(row.get("status") or "").upper() == "ONLINE"
                and infer_site_from_network_name(row.get("networkName")) == canonical_site_id
            ]
        lynx_status = lynxmsp_source_status(canonical_site_id)
        has_dhcp_lease_source = bool((lynx_status.get("db") or {}).get("site_dhcp_lease_count"))
        inferred_service_mode = infer_site_service_mode(canonical_site_id, bool(matched_local_rows), bool(filtered_sessions), has_dhcp_lease_source)

        if profile and profile.get("service_mode") == "dhcp_tauc_tp_link":
            if matched_local_rows:
                return {
                    "count": len(matched_local_rows),
                    "counting_method": "local_online_cpe_export",
                    "matched_routers": routers,
                    "verified_sessions": filtered_sessions[:500],
                    "sample_networks": [str(row.get("networkName") or "") for row in matched_local_rows[:25]],
                    "source_note": "Count derived from the freshest local TP-Link online subscriber export for this site.",
                    "site_service_mode": inferred_service_mode,
                    "source_status": lynx_status,
                }

        if routers:
            return {
                "count": len(filtered_sessions),
                "counting_method": "router_ppp_active",
                "matched_routers": routers,
                "verified_sessions": filtered_sessions[:500],
                "site_service_mode": inferred_service_mode,
                "source_status": lynx_status,
            }
        if matched_local_rows:
            return {
                "count": len(matched_local_rows),
                "counting_method": "local_online_cpe_export",
                "matched_routers": [],
                "verified_sessions": [],
                "sample_networks": [str(row.get("networkName") or "") for row in matched_local_rows[:25]],
                "source_note": "Count derived from the freshest local TP-Link online subscriber export for this site.",
                "site_service_mode": inferred_service_mode,
                "source_status": lynx_status,
            }

        return {
            "count": 0,
            "counting_method": "unverified_no_site_specific_customer_source",
            "matched_routers": [],
            "verified_sessions": [],
            "error": "No matching live PPP routers or site-specific DHCP/CPE export source were found for the requested scope.",
            "site_service_mode": inferred_service_mode,
            "source_status": lynx_status,
        }

    def compare_customer_evidence(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        scan_id = self.latest_scan_id()
        profile = SITE_SERVICE_PROFILES.get(site_id or "")
        sessions = [
            dict(r)
            for r in self.db.execute(
                """
                select p.router_ip, p.name, p.service, p.caller_id, p.address, p.uptime, d.identity
                from router_ppp_active p
                left join devices d on d.scan_id=p.scan_id and d.ip=p.router_ip
                where p.scan_id=?
                order by d.identity, p.name
                """,
                (scan_id,),
            ).fetchall()
        ]
        ppp_sessions = [
            row for row in sessions
            if identity_matches_scope(canonical_identity(row.get("identity")), site_id)
        ]
        ppp_routers = sorted(
            {
                (canonical_identity(row.get("identity")), row.get("router_ip"))
                for row in ppp_sessions
                if row.get("identity") and row.get("router_ip")
            }
        )
        if site_id and (not ppp_routers or not any(re.search(r"(?:^|\.)R\d{1,2}$", str(identity or ""), re.IGNORECASE) for identity, _ in ppp_routers)):
            ppp_routers = [
                (row.get("identity"), row.get("ip"))
                for row in self._recent_site_router_candidates(site_id)
            ]

        arp_rows = [
            dict(r)
            for r in self.db.execute(
                """
                select a.router_ip, d.identity, a.address, a.mac, a.interface, a.dynamic
                from router_arp a
                left join devices d on d.scan_id=a.scan_id and d.ip=a.router_ip
                where a.scan_id=?
                order by d.identity, a.address
                """,
                (scan_id,),
            ).fetchall()
        ]
        site_arp = [
            row
            for row in arp_rows
            if identity_matches_scope(canonical_identity(row.get("identity")), site_id)
        ]
        arp_dynamic = [row for row in site_arp if int(row.get("dynamic") or 0) == 1]
        arp_unique_macs = sorted(
            {
                norm_mac(str(row.get("mac") or ""))
                for row in arp_dynamic
                if row.get("mac") and norm_mac(str(row.get("mac") or "")) != "ff:ff:ff:ff:ff:ff"
            }
        )

        local_rows = [
            row for row in load_local_online_cpe_rows()
            if str(row.get("status") or "").upper() == "ONLINE"
            and infer_site_from_network_name(row.get("networkName")) == site_id
        ]
        lynx_status = lynxmsp_source_status(site_id)
        db_status = lynx_status.get("db") or {}
        api_status = lynx_status.get("api") or {}
        site_dhcp_lease_count = int(db_status.get("site_dhcp_lease_count") or 0)
        inferred_service_mode = infer_site_service_mode(site_id, bool(local_rows), bool(ppp_sessions), bool(site_dhcp_lease_count))

        sources: list[dict[str, Any]] = []
        if local_rows:
            sources.append(
                {
                    "source": "local_online_cpe_export",
                    "count": len(local_rows),
                    "sample": [str(row.get("networkName") or "") for row in local_rows[:10]],
                }
            )
        if ppp_sessions:
            sources.append(
                {
                    "source": "router_ppp_active",
                    "count": len(ppp_sessions),
                    "routers": [{"identity": ident, "ip": ip} for ident, ip in ppp_routers],
                }
            )
        if site_arp:
            sources.append(
                {
                    "source": "router_arp",
                    "count": len(arp_unique_macs),
                    "sample": arp_unique_macs[:10],
                    "router_count": len({canonical_identity(row.get("identity")) for row in site_arp if row.get("identity")}),
                }
            )
        if site_dhcp_lease_count:
            sources.append(
                {
                    "source": "lynxmsp_dhcp_leases",
                    "count": site_dhcp_lease_count,
                    "detail": "Count derived from LynxMSP local database DHCP leases joined through routers and sites.",
                }
            )

        counts = {row["source"]: int(row["count"]) for row in sources}
        count_values = sorted(set(counts.values()))
        discrepancy = len(count_values) > 1
        max_gap = max(count_values) - min(count_values) if len(count_values) > 1 else 0

        note = "No evidence sources were available for this site."
        if discrepancy:
            note = (
                "The counts do not match across sources. Jake can compare PPP, router ARP, local subscriber export, and any available LynxMSP DHCP lease evidence here."
            )
        elif sources:
            note = (
                "The available sources are broadly aligned or only one source is available."
            )
        blockers: list[str] = []
        if not site_dhcp_lease_count:
            if db_status.get("configured") and not db_status.get("available"):
                blockers.append("LynxMSP local database is present but currently has no populated DHCP/site/customer rows.")
            elif db_status.get("configured") and db_status.get("table_counts"):
                blockers.append("LynxMSP local database is present but has no site-matched DHCP lease rows for this scope.")
            if api_status.get("configured") and not api_status.get("available"):
                blockers.append("LynxMSP API is not reachable from this host right now.")
        if blockers:
            note = (note + " " + " ".join(blockers)).strip()

        return {
            "site_id": site_id,
            "site_service_mode": inferred_service_mode,
            "sources": sources,
            "counts": counts,
            "has_discrepancy": discrepancy,
            "max_gap": max_gap,
            "note": note,
            "source_status": lynx_status,
        }

    def trace_mac(self, mac: str, include_bigmac: bool) -> dict[str, Any]:
        scan_id = self.latest_scan_id()
        mac = norm_mac(mac)
        result: dict[str, Any] = {"mac": mac}
        bigmac_rows: list[dict[str, Any]] = []
        if include_bigmac and self.bigmac:
            try:
                bigmac_payload = self.bigmac.search_macs(mac)
                result["bigmac_corroboration"] = bigmac_payload
                raw_bigmac_rows = bigmac_payload.get("results") or []
                bigmac_rows = [normalize_bigmac_sighting(row) for row in raw_bigmac_rows if isinstance(row, dict)]
                result["bigmac_results"] = bigmac_rows
            except Exception as exc:
                result["bigmac_corroboration_error"] = str(exc)
        rows = self.db.execute(
            """
            select bh.ip, d.identity, bh.mac, bh.on_interface, bh.vid, bh.local, bh.external
            from bridge_hosts bh
            left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
            where bh.scan_id=? and lower(bh.mac)=lower(?)
            order by case when bh.on_interface like 'ether%' then 0 else 1 end, bh.external desc, bh.local asc, d.identity
            """,
            (scan_id, mac),
        ).fetchall()
        sightings = [dict(r) for r in rows]
        result["verified_sightings"] = sightings
        if rows:
            best = dict(rows[0])
            result["best_guess"] = best
            neighbors = self.db.execute(
                "select interface, neighbor_identity, neighbor_address, platform, version from neighbors where scan_id=? and ip=? order by interface",
                (scan_id, best["ip"]),
            ).fetchall()
            result["neighbor_context"] = [dict(r) for r in neighbors]
        else:
            result["best_guess"] = None
            result["neighbor_context"] = []
        edge_sightings = [s for s in sightings if is_edge_port(s.get("on_interface"))]
        uplink_sightings = [s for s in sightings if is_uplink_like_port(s.get("on_interface"))]
        bigmac_edge = [r for r in bigmac_rows if is_edge_port(r.get("port_name") or r.get("on_interface"))]
        bigmac_uplink = [r for r in bigmac_rows if is_uplink_like_port(r.get("port_name") or r.get("on_interface"))]

        best_bigmac_edge_guess = None
        if bigmac_edge:
            best_bigmac_edge_guess = sorted(bigmac_edge, key=_bigmac_seen_sort_key, reverse=True)[0]
            result["bigmac_best_edge_guess"] = best_bigmac_edge_guess
        if bigmac_rows:
            result["bigmac_primary_guess"] = sorted(bigmac_rows, key=_bigmac_seen_sort_key, reverse=True)[0]
        else:
            result["bigmac_primary_guess"] = None
        result["primary_sighting"] = result.get("bigmac_primary_guess") or result.get("best_guess")

        if edge_sightings:
            result["trace_status"] = "edge_trace_found"
            result["reason"] = "A current latest-scan bridge-host sighting exists on an access port."
        elif sightings:
            result["trace_status"] = "latest_scan_uplink_only"
            result["reason"] = "The MAC is visible in the latest scan, but only on uplink or non-edge interfaces."
        elif bigmac_edge:
            result["trace_status"] = "bigmac_edge_corroboration_only"
            result["reason"] = "No latest-scan sighting exists, but Bigmac has cached edge-port corroboration."
        elif bigmac_uplink or bigmac_rows:
            result["trace_status"] = "upstream_or_cached_corroboration_only"
            result["reason"] = "No latest-scan sighting exists; only upstream or cached Bigmac corroboration is available."
        else:
            result["trace_status"] = "not_found_in_latest_scan"
            result["reason"] = "No matching bridge-host sighting for this MAC exists in the latest local scan."
        result["edge_sighting_count"] = len(edge_sightings)
        result["uplink_sighting_count"] = len(uplink_sightings)
        return result

    def get_netbox_device(self, name: str) -> dict[str, Any]:
        if not self.netbox:
            raise ValueError("NetBox is not configured")
        return self.netbox.request("/api/dcim/devices/", {"name": name, "limit": 1})

    def get_netbox_device_by_ip(self, ip: str) -> dict[str, Any]:
        if not self.netbox:
            raise ValueError("NetBox is not configured")
        ip = str(ip or "").strip().split("/", 1)[0]
        matches: list[dict[str, Any]] = []
        for row in self.list_sites_inventory(limit=1000).get("sites", []):
            if ip in (row.get("router_172_ips") or []):
                matches.append({"site_id": row.get("site_id"), "site_name": row.get("site_name"), "locations": row.get("locations") or []})
        inventory_rows: list[dict[str, Any]] = []
        for device in self._netbox_all_devices():
            primary_ip = self._netbox_primary_ip(device)
            if primary_ip != ip:
                continue
            name = str(device.get("name") or "").strip()
            site = canonical_scope(((device.get("site") or {}).get("slug")) or ((device.get("site") or {}).get("name")))
            location = str(((device.get("location") or {}).get("display")) or ((device.get("location") or {}).get("name")) or "").strip() or None
            inventory_rows.append(
                {
                    "name": name,
                    "primary_ip": primary_ip,
                    "site_id": site,
                    "role": str(((device.get("role") or {}).get("name")) or "").strip() or None,
                    "device_type": str(((device.get("device_type") or {}).get("model")) or "").strip() or None,
                    "location": location,
                    "status": str(((device.get("status") or {}).get("label")) or (device.get("status") or "")).strip() or None,
                    "serial": str(device.get("serial") or "").strip() or None,
                }
            )
        return {
            "ip": ip,
            "count": len(inventory_rows),
            "devices": inventory_rows,
            "site_matches": matches,
        }

    def rag_search(self, query: str, limit: int = 4) -> dict[str, Any]:
        """Search Jake's RAG knowledge base using the .venv chromadb index."""
        venv_python = Path(os.environ.get("JAKE_RAG_PYTHON", str(REPO_ROOT / ".venv" / "bin" / "python")))
        rag_root = Path(os.environ.get("JAKE_RAG_ROOT", str(REPO_ROOT / "references" / "rag")))
        rag_script = Path(os.environ.get("JAKE_RAG_QUERY_SCRIPT", str(rag_root / "query.py")))
        if not venv_python.exists():
            return {"error": "RAG .venv not found", "results": []}
        if not rag_script.exists():
            return {"error": "RAG query.py not found", "results": []}
        try:
            _env = os.environ.copy()
            _env["PYTHONPATH"] = str(rag_root)
            proc = subprocess.run(
                [str(venv_python), "-c", f"""
import json
from query import search
results = search({query!r})
out = []
for item in results[:{limit}]:
    _, doc, meta, dist, _ = item
    out.append({{"path": meta.get("relative_path","?"), "text": doc[:600], "distance": dist}})
print(json.dumps(out))
"""],
                capture_output=True, text=True, timeout=30, env=_env
            )
            if proc.returncode != 0:
                return {"error": proc.stderr[:200], "results": []}
            results = json.loads(proc.stdout.strip())
            return {"results": results, "count": len(results), "query": query}
        except Exception as exc:
            return {"error": str(exc), "results": []}

    def get_new_devices_today(self, site_id: str | None = None) -> dict[str, Any]:
        """Find devices that came online or appeared in the last 24h using Prometheus probe_success."""
        import time as _time
        import urllib.request as _ur
        import urllib.parse as _up
        prom = os.environ.get("PROMETHEUS_URL", "").rstrip("/")
        if not prom:
            return {"error": "PROMETHEUS_URL is not configured", "new_devices": [], "count": 0}
        now = int(_time.time())
        day_ago = now - 86400
        site_filter = f',site_id="{site_id}"' if site_id else ''
        def pq(q):
            url = f"{prom}/api/v1/query?query={_up.quote(q)}"
            with _ur.urlopen(url, timeout=15) as r:
                return json.loads(r.read())
        try:
            r = pq(f'probe_success{{{("site_id=" + chr(34) + site_id + chr(34)) if site_id else "job=\"blackbox_icmp\""} }} == 1')
            results = (r.get('data') or {}).get('result') or []
            new_devices = []
            for res in results:
                inst = res['metric'].get('instance')
                name = res['metric'].get('device_name', inst)
                loc = res['metric'].get('location', '')
                role = res['metric'].get('role', '')
                sid = res['metric'].get('site_id', '')
                r2 = pq(f'probe_success{{instance="{inst}"}} @ {day_ago}')
                past = (r2.get('data') or {}).get('result') or []
                if not past or past[0]['value'][1] == '0':
                    new_devices.append({'name': name, 'ip': inst, 'location': loc, 'role': role, 'site_id': sid})
            return {'new_devices': new_devices, 'count': len(new_devices), 'site_id': site_id, 'window_hours': 24}
        except Exception as exc:
            return {'error': str(exc), 'new_devices': [], 'count': 0}

    def get_site_alerts(self, site_id: str) -> dict[str, Any]:
        if not self.alerts:
            raise ValueError("Alertmanager is not configured")
        alerts = self._alerts_for_site(site_id)
        return {"site_id": site_id, "alerts": alerts, "count": len(alerts)}

    def _loki_base_url(self) -> str:
        return str(os.environ.get("LOKI_URL") or "").rstrip("/")

    def _loki_query_range(
        self,
        query: str,
        *,
        start_ns: int,
        end_ns: int,
        limit: int = 500,
    ) -> tuple[bool, list[dict[str, Any]], str]:
        base = self._loki_base_url()
        if not base:
            return False, [], "LOKI_URL is not configured"
        url = f"{base}/loki/api/v1/query_range"
        ok, payload, detail = _http_json_request(
            url + "?" + urllib.parse.urlencode(
                {
                    "query": query,
                    "start": str(start_ns),
                    "end": str(end_ns),
                    "limit": str(limit),
                    "direction": "BACKWARD",
                }
            ),
            timeout=12.0,
        )
        if not ok or not isinstance(payload, dict):
            return False, [], detail
        data = payload.get("data") or {}
        result = data.get("result") or []
        return True, result if isinstance(result, list) else [], detail

    def _is_noise_line(self, line: str) -> bool:
        if os.environ.get("JAKE_LOKI_FILTER_NOISE", "true").lower() == "false":
            return False
        text = str(line or "").lower()
        if "failed" in text or "error" in text:
            return False
        if "mktxp_user" in text and "via api" in text:
            return True
        mgmt_ips = [
            ip.strip()
            for ip in os.environ.get("JAKE_MGMT_IPS", "172.27.72.179,172.27.226.246").split(",")
            if ip.strip()
        ]
        if (
            "via api" in text
            and ("logged in" in text or "logged out" in text)
            and any(ip in text for ip in mgmt_ips)
        ):
            return True
        return False

    def _loki_normalize_entries(self, streams: list[dict[str, Any]], *, limit: int = 500) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for stream in streams:
            labels = stream.get("stream") or {}
            values = stream.get("values") or []
            for raw_ts, raw_line in values:
                try:
                    ts = datetime.fromtimestamp(int(raw_ts) / 1_000_000_000, tz=UTC)
                    iso_ts = ts.isoformat().replace("+00:00", "Z")
                except Exception:
                    iso_ts = str(raw_ts)
                line = str(raw_line or "").strip()
                if not line:
                    continue
                if self._is_noise_line(line):
                    continue
                device = (
                    str(labels.get("hostname") or "").strip()
                    or str(labels.get("host") or "").strip()
                    or str(labels.get("device") or "").strip()
                    or str(labels.get("device_name") or "").strip()
                    or str(labels.get("instance") or "").strip()
                    or None
                )
                site_id = canonical_scope(
                    labels.get("site_id")
                    or labels.get("site")
                    or labels.get("site_slug")
                )
                entries.append(
                    {
                        "timestamp": iso_ts,
                        "device": device,
                        "site_id": site_id,
                        "line": line,
                        "labels": labels,
                    }
                )
        entries.sort(key=lambda row: str(row.get("timestamp") or ""))
        return entries[-limit:]

    def _log_filter_match(self, row: dict[str, Any], log_filter: str) -> bool:
        if log_filter == "all":
            return True
        text = f"{row.get('line') or ''} {json.dumps(row.get('labels') or {}, default=str)}".lower()
        if log_filter == "pppoe":
            return any(token in text for token in ("pppoe", "authentication failed", "auth fail", "radius reject", "invalid password"))
        if log_filter == "dhcp":
            return any(token in text for token in ("dhcp:", "dhcp ", "discover", "offer", "request", "ack", "option 82", "lease bound"))
        if log_filter == "interface":
            return any(token in text for token in ("link down", "link up", "flap", "carrier", "ether"))
        if log_filter == "bridge":
            return any(token in text for token in ("bridge", "mac move", "mac moved", "moved from", "host table", "loop"))
        if log_filter == "error":
            return any(token in text for token in ("error", ":critical:", ":warning:", "failed", "panic", "link down"))
        return True

    def _classify_log_events(self, entries: list[dict[str, Any]], window_minutes: int = 15) -> list[dict[str, Any]]:
        text_blob = "\n".join(str(row.get("line") or "").lower() for row in entries)
        classifications: list[dict[str, Any]] = []
        lines = [str(row.get("line") or "").lower() for row in entries]
        pppoe_lines = [line for line in lines if "pppoe" in line]
        dhcp_lines = [line for line in lines if "dhcp:" in line or line.startswith("dhcp ")]
        interface_lines = [line for line in lines if "link down" in line or "link up" in line]
        api_login_lines = [line for line in lines if "mktxp_user" in line and "via api" in line and ("logged in" in line or "logged out" in line)]
        safe_window_minutes = max(int(window_minutes or 15), 1)
        dhcp_per_hour = len(dhcp_lines) / (safe_window_minutes / 60)
        device_count = len({str(row.get("device") or "").strip() for row in entries if str(row.get("device") or "").strip()})

        if api_login_lines and len(api_login_lines) >= max(3, len(lines) // 2):
            classifications.append(
                {
                    "kind": "routine_management_api_activity",
                    "summary": "Most of the recent log volume is routine management API login/logout activity from mktxp_user, not subscriber-impacting failures.",
                    "confidence": "medium",
                }
            )

        if (
            pppoe_lines
            and any(token in text_blob for token in ("auth fail", "authentication failed", "radius reject", "invalid password"))
        ):
            classifications.append(
                {
                    "kind": "credentials_or_radius_issue",
                    "summary": "PPPoE authentication failures are present. The session is reaching auth, so layer 2 looks intact and the likely issue is credentials or RADIUS.",
                    "confidence": "medium",
                }
            )

        if any("discover" in line for line in dhcp_lines) and not any("offer" in line for line in dhcp_lines):
            classifications.append(
                {
                    "kind": "vlan_mismatch_or_dhcp_path_issue",
                    "summary": "DHCP DISCOVER appears without a matching OFFER, which points more toward VLAN mismatch or relay path trouble than a healthy DHCP server response.",
                    "confidence": "medium",
                }
            )
        elif dhcp_lines and dhcp_per_hour >= DHCP_RATE_ABNORMAL_PER_HOUR:
            classifications.append(
                {
                    "kind": "dhcp_abnormal_rate",
                    "summary": (
                        f"DHCP rate is abnormally high at ~{int(dhcp_per_hour)} events/hour from "
                        f"{device_count} device(s). This level of DHCP churn suggests a loop, rogue client, "
                        "or misconfigured device — investigate."
                    ),
                    "confidence": "high",
                }
            )
        elif dhcp_lines and dhcp_per_hour >= DHCP_RATE_ELEVATED_PER_HOUR:
            classifications.append(
                {
                    "kind": "dhcp_elevated_rate",
                    "summary": (
                        f"DHCP activity is elevated at ~{int(dhcp_per_hour)} events/hour. This could be aggressive "
                        "lease renewal or a chatty client. Worth monitoring but not immediately alarming."
                    ),
                    "confidence": "medium",
                }
            )
        elif dhcp_lines and dhcp_per_hour < DHCP_RATE_ELEVATED_PER_HOUR and any(token in text_blob for token in ("msg-type = ack", "lease bound", "sending ack")):
            classifications.append(
                {
                    "kind": "routine_dhcp_activity",
                    "summary": "The logs show routine DHCP request/ack activity. Addresses are being handed out normally in this window.",
                    "confidence": "medium",
                }
            )

        if interface_lines and any(
            token in text_blob for token in ("session down", "pppoe disconnect", "customer drop", "lease lost")
        ):
            classifications.append(
                {
                    "kind": "physical_layer_instability",
                    "summary": "Interface flap timing overlaps with session drops, which points toward physical-layer instability rather than an auth-only problem.",
                    "confidence": "medium",
                }
            )
        elif any("link down" in line for line in interface_lines) and not any("link up" in line for line in interface_lines):
            classifications.append(
                {
                    "kind": "stuck_port_down",
                    "summary": "An interface went down but did not come back up in this window. That is a stuck-down port, not a flap — worth checking physically or remotely.",
                    "confidence": "high",
                }
            )
        elif len(interface_lines) >= 2 and any("link down" in line for line in interface_lines) and any("link up" in line for line in interface_lines):
            classifications.append(
                {
                    "kind": "interface_flap_activity",
                    "summary": "Interface down/up events are present in the same window. That looks like a local physical flap, even without matching subscriber-drop evidence here.",
                    "confidence": "medium",
                }
            )

        if any(token in text_blob for token in ("mac moved", "host moved", "bridge host moved", "moved from")):
            classifications.append(
                {
                    "kind": "loop_or_mispatch",
                    "summary": "MAC movement between ports was observed. Treat that as a loop or mispatched-cable signal until proven otherwise.",
                    "confidence": "medium",
                }
            )

        if any(token in text_blob for token in ("reboot", "booting", "startup", "system rebooted")) and any(
            token in text_blob for token in ("session down", "pppoe disconnect", "all sessions dropped", "link down")
        ):
            classifications.append(
                {
                    "kind": "power_or_crash_event",
                    "summary": "A reboot/crash-style event lines up with service drops, which makes power or a system crash more likely than a subscriber-specific issue.",
                    "confidence": "medium",
                }
            )

        if not classifications:
            classifications.append(
                {
                    "kind": "no_clear_root_cause",
                    "summary": "Jake found log activity in the requested window but no strong multi-signal root-cause pattern.",
                    "confidence": "low",
                }
            )
        return classifications

    def _loki_build_summary(
        self,
        *,
        scope: str,
        site_id: str | None,
        device_name: str | None,
        window_minutes: int,
        log_filter: str,
        entries: list[dict[str, Any]],
        loki_available: bool,
        error: str | None = None,
    ) -> dict[str, Any]:
        filtered = [row for row in entries if self._log_filter_match(row, log_filter)]
        devices = sorted({str(row.get("device") or "").strip() for row in filtered if str(row.get("device") or "").strip()})
        category_counts = {
            "pppoe": sum(1 for row in filtered if self._log_filter_match(row, "pppoe")),
            "dhcp": sum(1 for row in filtered if self._log_filter_match(row, "dhcp")),
            "interface": sum(1 for row in filtered if self._log_filter_match(row, "interface")),
            "bridge": sum(1 for row in filtered if self._log_filter_match(row, "bridge")),
            "error": sum(1 for row in filtered if self._log_filter_match(row, "error")),
        }
        timeline = [
            {
                "timestamp": row.get("timestamp"),
                "device": row.get("device"),
                "summary": str(row.get("line") or "")[:200],
            }
            for row in filtered[:15]
        ]
        return {
            "scope": scope,
            "site_id": site_id,
            "device_name": device_name,
            "window_minutes": int(window_minutes),
            "filter": log_filter,
            "limit": min(500, len(entries) if entries else 500),
            "loki_available": bool(loki_available),
            "error": error,
            "log_count": len(filtered),
            "devices": devices[:25],
            "category_counts": category_counts,
            "timeline": timeline,
            "classifications": self._classify_log_events(filtered, window_minutes),
        }

    def _site_log_query_candidates(self, site_id: str) -> list[str]:
        escaped = re.escape(site_id)
        base = f'{{host=~"{escaped}.*"}}'
        return [
            f'{base} !~ "mktxp_user"',
            f'{base} |~ "mktxp_user" |~ "failed|error"',
        ]

    def _device_log_query_candidates(self, device_name: str) -> list[str]:
        escaped = re.escape(device_name)
        return [
            f'{{host="{device_name}"}} !~ "mktxp_user"',
            f'{{host="{device_name}"}} |~ "mktxp_user" |~ "failed|error"',
            f'{{host=~"{escaped}.*"}} !~ "mktxp_user"',
        ]

    def get_site_logs(
        self,
        site_id: str,
        window_minutes: int = 15,
        log_filter: str = "all",
        limit: int = 500,
    ) -> dict[str, Any]:
        canonical_site = canonical_scope(site_id)
        window = max(1, min(int(window_minutes or 15), 24 * 60))
        bounded_limit = max(1, min(int(limit or 500), 500))
        if not self._loki_base_url():
            return self._loki_build_summary(
                scope="site",
                site_id=canonical_site or site_id,
                device_name=None,
                window_minutes=window,
                log_filter=log_filter,
                entries=[],
                loki_available=False,
                error="LOKI_URL is not configured",
            )
        end_ns = int(time.time() * 1_000_000_000)
        start_ns = end_ns - window * 60 * 1_000_000_000
        all_streams: list[dict[str, Any]] = []
        last_error: str | None = None
        for query in self._site_log_query_candidates(canonical_site or site_id):
            ok, streams, detail = self._loki_query_range(query, start_ns=start_ns, end_ns=end_ns, limit=bounded_limit)
            if ok and streams:
                all_streams.extend(streams)
            elif not ok:
                last_error = detail
        if not all_streams:
            return self._loki_build_summary(
                scope="site",
                site_id=canonical_site or site_id,
                device_name=None,
                window_minutes=window,
                log_filter=log_filter,
                entries=[],
                loki_available=last_error is None,
                error=last_error,
            )
        entries = self._loki_normalize_entries(all_streams, limit=bounded_limit)
        entries = [row for row in entries if canonical_scope(row.get("site_id")) in {None, canonical_site}]
        return self._loki_build_summary(
            scope="site",
            site_id=canonical_site or site_id,
            device_name=None,
            window_minutes=window,
            log_filter=log_filter,
            entries=entries,
            loki_available=True,
        )

    def get_device_logs(
        self,
        device_name: str,
        window_minutes: int = 15,
        log_filter: str = "all",
        limit: int = 500,
    ) -> dict[str, Any]:
        host = str(device_name or "").strip()
        window = max(1, min(int(window_minutes or 15), 24 * 60))
        bounded_limit = max(1, min(int(limit or 500), 500))
        if not self._loki_base_url():
            return self._loki_build_summary(
                scope="device",
                site_id=canonical_scope(host.split(".", 1)[0]) if "." in host else None,
                device_name=host,
                window_minutes=window,
                log_filter=log_filter,
                entries=[],
                loki_available=False,
                error="LOKI_URL is not configured",
            )
        end_ns = int(time.time() * 1_000_000_000)
        start_ns = end_ns - window * 60 * 1_000_000_000
        all_streams: list[dict[str, Any]] = []
        last_error: str | None = None
        for query in self._device_log_query_candidates(host):
            ok, streams, detail = self._loki_query_range(query, start_ns=start_ns, end_ns=end_ns, limit=bounded_limit)
            if ok and streams:
                all_streams.extend(streams)
            elif not ok:
                last_error = detail
        if not all_streams:
            return self._loki_build_summary(
                scope="device",
                site_id=canonical_scope(host.split(".", 1)[0]) if "." in host else None,
                device_name=host,
                window_minutes=window,
                log_filter=log_filter,
                entries=[],
                loki_available=last_error is None,
                error=last_error,
            )
        entries = self._loki_normalize_entries(all_streams, limit=bounded_limit)
        filtered_entries = []
        host_lower = host.lower()
        for row in entries:
            device = str(row.get("device") or "").strip()
            if not device:
                filtered_entries.append(row)
                continue
            if device.lower() == host_lower or host_lower in device.lower():
                filtered_entries.append(row)
        return self._loki_build_summary(
            scope="device",
            site_id=canonical_scope(host.split(".", 1)[0]) if "." in host else None,
            device_name=host,
            window_minutes=window,
            log_filter=log_filter,
            entries=filtered_entries,
            loki_available=True,
        )

    def correlate_event_window(
        self,
        site_id: str,
        window_minutes: int = 15,
        limit: int = 500,
    ) -> dict[str, Any]:
        summary = self.get_site_logs(site_id, window_minutes=window_minutes, log_filter="all", limit=limit)
        timeline = summary.get("timeline") or []
        ordered = sorted(timeline, key=lambda row: str(row.get("timestamp") or ""))
        return {
            **summary,
            "scope": "correlate",
            "timeline": ordered,
            "ordered_event_count": len(ordered),
            "what_happened": [row.get("summary") for row in ordered[:10] if row.get("summary")],
        }

    def get_site_summary(self, site_id: str, include_alerts: bool) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        scan_id = self.latest_scan_id()
        devices = self._device_rows_for_prefix(scan_id, site_id)
        routers = [d for d in devices if re.search(r"\.R\d{1,2}$", str(d["identity"])) is not None]
        if not routers:
            routers = self._recent_site_router_candidates(site_id)
        switches = [d for d in devices if ".SW" in d["identity"] or ".RFSW" in d["identity"]]
        outliers = self._outlier_rows_for_prefix(scan_id, site_id)
        online = self.get_online_customers(site_id, site_id, None, None)
        if not routers and online.get("matched_routers"):
            routers = online.get("matched_routers") or []
        topology: dict[str, Any] = {"site_id": site_id, "radios": [], "radio_links": [], "buildings": []}
        netbox_inventory: list[dict[str, Any]] = []
        topology_error: str | None = None
        netbox_inventory_error: str | None = None
        try:
            topology = self.get_site_topology(site_id)
        except Exception as exc:
            topology_error = str(exc)
        if self.netbox:
            try:
                netbox_inventory = self._netbox_site_inventory_light(site_id)
            except Exception as exc:
                netbox_inventory_error = str(exc)
        bridge_rows = [
            dict(row)
            for row in self.db.execute(
                """
                select d.identity, bh.on_interface, bh.mac, bh.vid
                from bridge_hosts bh
                left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                where bh.scan_id=? and d.identity like ?
                """,
                (scan_id, f"{site_id}%"),
            ).fetchall()
        ]
        bridge_counts = {"total": len(bridge_rows)}
        for vendor in ("tplink", "vilo"):
            deduped = dedupe_vendor_mac_groups(bridge_rows, vendor)
            bridge_counts[vendor] = deduped["estimated_cpe_count"]
            bridge_counts[f"{vendor}_raw_macs"] = deduped["raw_mac_count"]
            bridge_counts[f"{vendor}_alt_mac_duplicates"] = deduped["duplicate_mac_delta_count"]
        bridge_counts["dedupe_method"] = "same_port_vlan_related_mac_clustering"
        location_groups: list[dict[str, Any]] = []
        by_location: dict[str, list[dict[str, Any]]] = {}
        for row in netbox_inventory:
            location = str(row.get("location") or "").strip() or "Unknown"
            by_location.setdefault(location, []).append(row)
        topology_buildings = {canonical_scope(row.get("building_id")): row for row in (topology.get("buildings") or [])}
        for location, rows in sorted(by_location.items()):
            names = [str(row.get("name") or "") for row in rows]
            building_id = next((canonical_scope(r.get("resolved_building_id")) for r in (topology.get("radios") or []) if str(r.get("location") or "").strip() == location and canonical_scope(r.get("resolved_building_id"))), None)
            location_groups.append(
                {
                    "location": location,
                    "building_id": building_id,
                    "devices": names,
                    "device_count": len(names),
                    "primary_ips": [row.get("primary_ip") for row in rows if row.get("primary_ip")],
                    "building_health_hint": topology_buildings.get(building_id),
                }
            )
        result = {
            "site_id": site_id,
            "scan": self.latest_scan_meta(),
            "devices_total": max(len(devices), len(netbox_inventory)),
            "routers": routers,
            "switches_count": len(switches),
            "online_customers": {"count": online["count"], "counting_method": online["counting_method"], "matched_routers": online["matched_routers"]},
            "outlier_count": len(outliers),
            "bridge_host_summary": bridge_counts,
            "scan_devices": devices,
            "netbox_inventory": netbox_inventory,
            "netbox_device_count": len(netbox_inventory),
            "transport_topology": {
                "radios": topology.get("radios") or [],
                "radio_links": topology.get("radio_links") or [],
                "buildings": topology.get("buildings") or [],
            },
            "location_groups": location_groups,
        }
        if topology_error:
            result["transport_topology_error"] = topology_error
        if netbox_inventory_error:
            result["netbox_inventory_error"] = netbox_inventory_error
        result["cnwave_summary"] = self._cnwave_site_summary(site_id)
        result["tauc_summary"] = self._tauc_summary()
        result["vilo_summary"] = self._vilo_summary()
        if include_alerts and self.alerts:
            result["active_alerts"] = self._alerts_for_site(site_id)
        return result

    def get_site_precheck(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        profile = SITE_SERVICE_PROFILES.get(site_id) or {}
        inventory = self._netbox_site_inventory_light(site_id) if self.netbox else []
        alerts = self._alerts_for_site(site_id) if self.alerts else []
        online = self.get_online_customers(site_id, site_id, None, None)
        role_counts: dict[str, int] = {}
        building_ids: set[str] = set()
        for row in inventory:
            role = str(row.get("role") or "").strip()
            if role:
                role_counts[role] = int(role_counts.get(role, 0) or 0) + 1
            building_id = canonical_scope(row.get("building_id"))
            if building_id:
                building_ids.add(building_id)
        cached_topology = self._site_topology_cache.get(site_id) or {}
        topology_radios = len(cached_topology.get("radios") or [])
        topology_links = len(cached_topology.get("radio_links") or [])
        topology_buildings = len(cached_topology.get("buildings") or []) or len(building_ids)
        tags: list[str] = []
        if role_counts.get("Radio"):
            tags.append("transport_radio_site")
        if role_counts.get("OLT"):
            tags.append("optical_access_site")
        if role_counts.get("Switch", 0) >= 4:
            tags.append("switching_heavy_site")
        if role_counts.get("Patch Panel") or role_counts.get("Power-Distribution") or role_counts.get("Power-backup") or role_counts.get("shelf"):
            tags.append("infrastructure_heavy_site")
        if int(online.get("count") or 0) == 0 and not alerts:
            tags.append("quiet_or_low_signal_site")
        source_status = {
            "customer_counting_method": online.get("counting_method"),
            "has_alerts": bool(alerts),
            "has_topology": bool(role_counts.get("Radio") or role_counts.get("OLT") or inventory),
            "topology_radios": topology_radios or int(role_counts.get("Radio") or 0),
            "topology_links": topology_links,
        }
        return {
            "site_id": site_id,
            "site_name": str(profile.get("name") or site_id),
            "service_profile": profile,
            "role_counts": role_counts,
            "classification_tags": tags,
            "online_customers": online,
            "active_alert_count": len(alerts),
            "topology_summary": {
                "radios": topology_radios or int(role_counts.get("Radio") or 0),
                "links": topology_links,
                "buildings": topology_buildings,
            },
            "source_status": source_status,
        }

    def get_site_live_audit_surface(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        try:
            precheck = self.get_site_precheck(site_id)
        except Exception:
            precheck = {
                "site_id": site_id,
                "site_name": str((SITE_SERVICE_PROFILES.get(site_id) or {}).get("name") or site_id),
                "service_profile": SITE_SERVICE_PROFILES.get(site_id) or {},
                "role_counts": {},
                "classification_tags": [],
                "online_customers": {"count": 0, "counting_method": None},
                "active_alert_count": 0,
                "topology_summary": {"radios": 0, "links": 0, "buildings": 0},
                "source_status": {},
            }
        try:
            raw_devices = self._netbox_site_devices(site_id) if self.netbox else []
            inventory = self._netbox_site_inventory_light(site_id) if self.netbox else []
        except Exception:
            raw_devices = []
            inventory = []

        ssh_devices: set[str] = set()
        ssh_allowlist: set[str] = set()
        if SSH_MCP_ROOT.exists():
            try:
                cfg_path = SSH_MCP_ROOT / "config" / "ssh_mcp.json"
                if cfg_path.exists():
                    cfg = json.loads(cfg_path.read_text())
                    ssh_allowlist = {str(host).strip() for host in (cfg.get("host_allowlist") or []) if str(host).strip()}
                db_path = SSH_MCP_ROOT / "data" / "ssh_mcp.sqlite3"
                if db_path.exists():
                    conn = sqlite3.connect(str(db_path))
                    conn.row_factory = sqlite3.Row
                    ssh_devices = {str(row["name"]).strip() for row in conn.execute("select name from devices")}
                    conn.close()
            except Exception:
                ssh_devices = set()

        dhcp_status = lynxmsp_source_status(site_id)
        cnwave_live = self.get_live_cnwave_rf_summary(site_id=site_id, limit=1)
        readiness = {
            "routeros": {
                "configured": SSH_MCP_ROOT.exists(),
                "available": bool(_ssh_mcp_password()) and bool(ssh_devices),
                "device_count": len(ssh_devices),
            },
            "dhcp": {
                "configured": bool((dhcp_status.get("db") or {}).get("configured")) or bool((dhcp_status.get("api") or {}).get("configured")),
                "available": bool((dhcp_status.get("db") or {}).get("available")) or bool((dhcp_status.get("api") or {}).get("available")),
                "source": "lynxmsp_db" if (dhcp_status.get("db") or {}).get("available") else ("lynxmsp_api" if (dhcp_status.get("api") or {}).get("available") else None),
                "detail": (dhcp_status.get("api") or {}).get("detail") or (dhcp_status.get("db") or {}).get("error"),
            },
            "cnwave": {
                "configured": bool(cnwave_live.get("configured")),
                "available": bool(cnwave_live.get("available")),
                "metric_row_count": int(cnwave_live.get("metric_row_count") or cnwave_live.get("link_count") or 0),
            },
            "olt": {
                "configured": bool(_olt_telnet_password()),
                "available": bool(_olt_telnet_password()) and OLT_TELNET_READ_SCRIPT.exists(),
            },
        }

        role_counts: Counter[str] = Counter(str(row.get("role") or "").strip() or "unknown" for row in inventory)
        routeros_targets: list[dict[str, Any]] = []
        olt_targets: list[dict[str, Any]] = []
        radio_targets: list[dict[str, Any]] = []
        unsupported_targets: list[dict[str, Any]] = []
        ghn_targets: list[dict[str, Any]] = []
        infra_targets: list[dict[str, Any]] = []
        positron_probe_ready = (REPO_ROOT / "scripts" / "positron_ssh_probe.exp").exists() and bool(
            _positron_username() and _positron_password()
        )

        for raw_device in raw_devices:
            name = str(raw_device.get("name") or "").strip()
            role = str(((raw_device.get("role") or {}).get("name")) or "").strip() or None
            manufacturer = str((((raw_device.get("device_type") or {}).get("manufacturer")) or {}).get("name") or "").strip() or None
            model = str(((raw_device.get("device_type") or {}).get("model")) or "").strip() or None
            ip = self._netbox_primary_ip(raw_device)
            location = str(((raw_device.get("location") or {}).get("display")) or ((raw_device.get("location") or {}).get("name")) or "").strip() or None
            row = {
                "name": name,
                "role": role,
                "manufacturer": manufacturer,
                "model": model,
                "ip": ip,
                "location": location,
            }
            if manufacturer == "MikroTik" and role in {"Router", "Switch", "Aggregation switch", "OOB-lte"}:
                row["ssh_enrolled"] = name in ssh_devices
                row["ssh_allowlisted"] = name in ssh_allowlist
                row["live_ready"] = bool(readiness.get("routeros", {}).get("available")) and row["ssh_enrolled"] and row["ssh_allowlisted"]
                routeros_targets.append(row)
            elif role == "OLT":
                row["live_ready"] = bool(readiness.get("olt", {}).get("available")) and bool(ip)
                olt_targets.append(row)
            elif role == "Radio":
                row["live_ready"] = bool(readiness.get("cnwave", {}).get("available")) and int(readiness.get("cnwave", {}).get("metric_row_count") or 0) > 0
                radio_targets.append(row)
            elif role == "G.Hn":
                row["live_ready"] = bool(positron_probe_ready and ip)
                ghn_targets.append(row)
            elif role in {"Patch Panel", "Power-Distribution", "Power-backup", "shelf", "Cable Mgmt"}:
                row["live_ready"] = False
                infra_targets.append(row)
            elif role in {"Digi", "CPE"}:
                row["live_ready"] = False
                unsupported_targets.append(row)

        live_capabilities: list[dict[str, Any]] = []
        if routeros_targets:
            ready = [row for row in routeros_targets if row.get("live_ready")]
            live_capabilities.append(
                {
                    "class": "routeros_live_reads",
                    "status": "ready" if ready else "partial",
                    "count": len(routeros_targets),
                    "ready_count": len(ready),
                    "details": "Read-only ssh_mcp troubleshooting is available for enrolled MikroTik routers/switches/OOB devices.",
                    "sample_targets": ready[:8] or routeros_targets[:8],
                }
            )
        if olt_targets:
            ready = [row for row in olt_targets if row.get("live_ready")]
            live_capabilities.append(
                {
                    "class": "olt_live_reads",
                    "status": "ready" if ready else "partial",
                    "count": len(olt_targets),
                    "ready_count": len(ready),
                    "details": "TP-Link OLT telnet reads can resolve ONU info and OLT logs when OLT IPs are present.",
                    "sample_targets": ready[:8] or olt_targets[:8],
                }
            )
        if radio_targets:
            live_capabilities.append(
                {
                    "class": "transport_radio_live_reads",
                    "status": "ready" if int(readiness.get("cnwave", {}).get("metric_row_count") or 0) > 0 else "inventory_only",
                    "count": len(radio_targets),
                    "ready_count": len([row for row in radio_targets if row.get("live_ready")]),
                    "details": "Jake has NetBox radio inventory and local transport issue correlation; cnWave RF metrics are available when exporter rows exist.",
                    "sample_targets": radio_targets[:8],
                }
            )
        if ghn_targets:
            ready = [row for row in ghn_targets if row.get("live_ready")]
            live_capabilities.append(
                {
                    "class": "ghn_positron_live_reads",
                    "status": "ready" if ready else "inventory_only",
                    "count": len(ghn_targets),
                    "ready_count": len(ready),
                    "details": "Positron G.Hn CLI reads are available when direct SSH credentials and management IP reachability are present.",
                    "sample_targets": ready[:8] or ghn_targets[:8],
                }
            )
        if infra_targets:
            live_capabilities.append(
                {
                    "class": "infrastructure_handoff",
                    "status": "inventory_handoff_only",
                    "count": len(infra_targets),
                    "ready_count": 0,
                    "details": "Infrastructure objects are available for dispatch and physical handoff reasoning, not direct live reads.",
                    "sample_targets": infra_targets[:8],
                }
            )
        if unsupported_targets:
            live_capabilities.append(
                {
                    "class": "unsupported_live_reads",
                    "status": "inventory_only",
                    "count": len(unsupported_targets),
                    "ready_count": 0,
                    "details": "These classes are visible in inventory but do not yet have approved live Jake read adapters on this host.",
                    "sample_targets": unsupported_targets[:8],
                }
            )

        gaps: list[str] = []
        if not readiness.get("dhcp", {}).get("available"):
            gaps.append("Live DHCP / LynxMSP lease correlation is unavailable on this host.")
        if routeros_targets and not any(row.get("live_ready") for row in routeros_targets):
            gaps.append("MikroTik inventory is present but no site devices are both ssh_mcp-enrolled and allowlisted.")
        if radio_targets and not int(readiness.get("cnwave", {}).get("metric_row_count") or 0):
            gaps.append("Radio inventory is present, but cnWave exporter metrics are empty right now.")
        if unsupported_targets:
            role_set = sorted({str(row.get("role") or "") for row in unsupported_targets if row.get("role")})
            gaps.append(f"No direct live read adapters yet for: {', '.join(role_set)}.")

        return {
            "site_id": site_id,
            "site_name": str((precheck.get("service_profile") or {}).get("name") or site_id),
            "precheck": precheck,
            "readiness": readiness,
            "role_counts": dict(sorted(role_counts.items())),
            "routeros_targets": routeros_targets,
            "olt_targets": olt_targets,
            "radio_targets": radio_targets,
            "ghn_targets": ghn_targets,
            "infrastructure_targets": infra_targets,
            "unsupported_targets": unsupported_targets,
            "live_capabilities": live_capabilities,
            "gaps": gaps,
        }

    def correlate_customer_fault_domain(
        self,
        network_name: str | None = None,
        mac: str | None = None,
        serial: str | None = None,
        site_id: str | None = None,
    ) -> dict[str, Any]:
        local_row = find_local_online_cpe_row(network_name, None, mac, serial)
        resolved_network_name = str((local_row or {}).get("networkName") or network_name or "").strip() or None
        resolved_mac = norm_mac(str((local_row or {}).get("mac") or mac or ""))
        resolved_serial = str((local_row or {}).get("sn") or serial or "").strip() or None
        resolved_site_id = canonical_scope(site_id or infer_site_from_network_name(resolved_network_name))

        tauc_row = None
        if resolved_network_name:
            lowered = resolved_network_name.strip().lower()
            tauc_row = next(
                (row for row in load_tauc_nycha_audit_rows() if str(row.get("networkName") or "").strip().lower() == lowered),
                None,
            )
        nycha_row = None
        if resolved_network_name and not tauc_row:
            lowered = resolved_network_name.strip().lower()
            nycha_row = next(
                (row for row in load_nycha_info_rows() if str(row.get("PPPoE") or "").strip().lower() == lowered),
                None,
            )

        building_hint = self._resolve_building_from_network_name(resolved_network_name or "") or {}
        building_id = canonical_scope(
            (tauc_row or {}).get("expected_prefix")
            or building_hint.get("building_id")
        )
        if not building_id and nycha_row:
            resolved = self._resolve_building_from_address(str(nycha_row.get("Address") or ""))
            building_id = canonical_scope(((resolved.get("best_match") or {}).get("prefix")))
        if building_id and not resolved_site_id:
            resolved_site_id = canonical_scope(building_id.split(".")[0])

        unit = parse_unit_token((tauc_row or {}).get("expected_unit") or (nycha_row or {}).get("Unit"))
        if resolved_network_name and resolved_site_id == "000002":
            savoy_match = re.search(r"savoy(\d+)unit([a-z0-9]+)", resolved_network_name, re.I)
            if savoy_match:
                building_num = int(savoy_match.group(1))
                unit = unit or savoy_match.group(2).upper()
                if not building_id:
                    building_id = f"000002.{building_num + 3:03d}"
        if not unit and resolved_network_name:
            resolved = self._resolve_building_from_network_name(resolved_network_name)
            if resolved:
                remainder = compact_free_text(resolved_network_name).split(resolved["stem"], 1)
                suffix = remainder[1] if len(remainder) == 2 else ""
                unit = parse_unit_token(suffix)

        trace = self.trace_mac(resolved_mac, True) if resolved_mac else {"trace_status": "no_mac"}
        local_ont = self.get_local_ont_path(resolved_mac, resolved_serial)
        alerts = self._alerts_for_site(resolved_site_id) if self.alerts and resolved_site_id else []
        building_model = self.get_building_model(building_id) if building_id else None
        ghn_hint = self._get_live_ghn_customer_hint(resolved_site_id, building_id, unit, resolved_network_name)
        if not building_id and ghn_hint.get("building_id"):
            building_id = canonical_scope(ghn_hint.get("building_id"))
            if building_id and not building_model:
                building_model = self.get_building_model(building_id)
        same_floor_units: list[dict[str, Any]] = []
        floor_offline = 0
        floor_online = 0
        if building_model and unit:
            floor_match = re.match(r"(\d+)", unit)
            floor_token = floor_match.group(1) if floor_match else None
            if floor_token:
                for row in (building_model.get("unit_state_decisions") or []):
                    row_unit = str(row.get("unit") or "")
                    if not row_unit.startswith(floor_token):
                        continue
                    same_floor_units.append(row)
                    if str(row.get("state") or "") == "online":
                        floor_online += 1
                    else:
                        floor_offline += 1

        likely_domain = "unknown"
        confidence = "low"
        reason = "Jake does not yet have enough correlated evidence to isolate the break in the chain."
        suggested_fix = "Pull the strongest current live evidence for this subscriber path before assigning ownership."
        affected_scope = "single_subscriber"
        owner = "NOC triage"

        top_cluster = None
        if alerts:
            clusters: dict[tuple[str, str], dict[str, Any]] = {}
            for alert in alerts:
                annotations = alert.get("annotations") or {}
                labels = alert.get("labels") or {}
                summary = str(annotations.get("summary") or labels.get("alertname") or "")
                lowered = summary.lower()
                if not any(token in lowered for token in ("rx power low", "rx power high", "rx power critical")):
                    continue
                olt_name = str(annotations.get("olt_name") or labels.get("olt_name") or "").strip() or "unknown"
                port_id = str(annotations.get("port_id") or labels.get("port_id") or "").strip() or "?"
                key = (olt_name, port_id)
                row = clusters.setdefault(
                    key,
                    {"olt_name": olt_name, "port_id": port_id, "critical_count": 0, "low_count": 0, "worst": None},
                )
                severity = str(labels.get("severity") or "warning").lower()
                if severity == "critical":
                    row["critical_count"] += 1
                else:
                    row["low_count"] += 1
                desc = str(annotations.get("description") or "")
                match = re.search(r"(-?\d+(?:\.\d+)?)dBm", desc, re.I)
                if match:
                    value = float(match.group(1))
                    if row["worst"] is None or value < row["worst"]:
                        row["worst"] = value
            if clusters:
                top_cluster = max(
                    clusters.values(),
                    key=lambda item: (
                        int(item.get("critical_count") or 0),
                        int(item.get("low_count") or 0),
                        -float(item.get("worst") or 0.0),
                    ),
                )

        best_guess = trace.get("best_guess") or {}
        trace_status = str(trace.get("trace_status") or "")
        service_online = bool(local_row and str(local_row.get("status") or "").upper() == "ONLINE")
        physically_seen = bool(trace.get("verified_sightings"))
        related_mac = (self.get_cpe_state(resolved_mac, True).get("related_mac_candidates") or [None])[0] if resolved_mac else None

        if same_floor_units and floor_offline >= 2 and not floor_online and top_cluster:
            likely_domain = "shared_floor_access_path"
            confidence = "medium"
            affected_scope = f"floor_{re.match(r'(\\d+)', unit).group(1) if re.match(r'(\\d+)', unit) else unit}"
            owner = "Fiber/mux team"
            reason = (
                f"Multiple units on the same floor of {building_id} appear offline and the site has an active optical concentration on "
                f"{top_cluster.get('olt_name')} PON {top_cluster.get('port_id')}. That reads more like a shared floor/access path issue than one bad CPE."
            )
            suggested_fix = "Check the shared floor handoff first: mux/drop/splitter/patch path for that branch, then validate the top PON path."
        elif local_ont.get("found") and (local_ont.get("placement") or {}).get("kind") == "gpon-ont" and top_cluster:
            placement = local_ont.get("placement") or {}
            if str(placement.get("olt_name") or "").strip() == str(top_cluster.get("olt_name") or "").strip() and str(placement.get("pon") or "").strip().lstrip("0") == str(top_cluster.get("port_id") or "").strip().lstrip("0"):
                likely_domain = "optical_pon_path"
                confidence = "high"
                owner = "Fiber/OLT team"
                reason = (
                    f"This subscriber resolves to {placement.get('olt_name')} {placement.get('pon')} ONU {placement.get('onu_id')}, "
                    f"and that same PON path is the current strongest optical work item."
                )
                suggested_fix = "Work the OLT/PON optical path first: connectors, attenuation, splitter/drop loss, then the local unit handoff."
        elif service_online and physically_seen:
            likely_domain = "field_side_mismatch_or_downstream_validation"
            confidence = "high"
            owner = "Field tech team"
            reason = (
                "The control plane still sees the subscriber online and the MAC is still being learned at the edge. "
                "That makes wrong unit, wrong patch, local LAN/Wi-Fi/client validation, or downstream field mismatch more likely than a dead upstream path."
            )
            suggested_fix = "Verify you are on the correct unit/path first, then validate local LAN/client behavior before escalating to network core."
        elif ghn_hint.get("matched") and ghn_hint.get("shared_radio_alerts"):
            endpoint = ghn_hint.get("endpoint_match") or {}
            subscriber = ghn_hint.get("subscriber_match") or {}
            port_text = f" port {endpoint.get('port')}" if endpoint.get("port") else ""
            likely_domain = "shared_building_path_or_power"
            confidence = "high"
            owner = "Field tech team"
            reason = (
                f"This unit maps live to {ghn_hint.get('device_name')} endpoint {endpoint.get('endpoint_id') or subscriber.get('endpoint_id') or '?'}"
                f"{port_text}, and the same building also has paired radio fault signals. "
                "That reads more like a shared building path, handoff, or power problem than one bad in-unit device."
            )
            suggested_fix = "Work the building dependency first: power, uplink/handoff, and paired radio path before replacing the in-unit subscriber device."
        elif ghn_hint.get("matched"):
            endpoint = ghn_hint.get("endpoint_match") or {}
            subscriber = ghn_hint.get("subscriber_match") or {}
            port_text = f" port {endpoint.get('port')}" if endpoint.get("port") else ""
            likely_domain = "ghn_local_access_path"
            confidence = "high"
            owner = "Field tech team"
            reason = (
                f"This unit maps live to {ghn_hint.get('device_name')} endpoint {endpoint.get('endpoint_id') or subscriber.get('endpoint_id') or '?'}"
                f"{port_text}. "
                "That gives Jake a concrete G.Hn building-path anchor, so the break is more likely between the Positron/building handoff and the unit than in an unrelated upstream OLT path."
            )
            suggested_fix = "Start at the mapped Positron/building handoff and subscriber drop for this unit before escalating to non-G.Hn architectures."
        elif trace_status == "not_found_in_latest_scan" and building_id:
            likely_domain = "unit_specific_dark_or_unprovisioned"
            confidence = "medium"
            owner = "Provisioning/subscriber-system team"
            reason = (
                f"The subscriber is not visible in the latest edge evidence, while the surrounding building path at {building_id} still has enough evidence to look partially alive. "
                "That points more toward a dark/unpatched/unprovisioned unit-specific path than a whole-building outage."
            )
            suggested_fix = "Check local patching, provisioning visibility, and whether the expected unit port/path is actually live."
        elif (local_ont.get("placement") or {}).get("kind") == "uplink-side":
            likely_domain = "identity_or_uplink_side_visibility_problem"
            confidence = "high"
            owner = "Field tech team"
            reason = (
                str((local_ont.get("placement") or {}).get("summary") or "")
                or "The subscriber MAC is showing up on the OLT uplink side instead of resolving cleanly to one ONU."
            )
            suggested_fix = "Treat this as an identity/path problem first: verify the exact subscriber path, check for wrong patch or bridged WAN/LAN behavior, and avoid assuming one dead ONU."
        elif related_mac:
            likely_domain = "identity_or_wrong_patch_issue"
            confidence = "medium"
            owner = "Field tech team"
            relation = str(related_mac.get("mac_relation") or "").replace("_", " ")
            reason = (
                f"A close MAC variant is showing up on the edge as a {relation}. "
                "That is a strong hint for wrong port, wrong label, dual-patch, or bridged WAN/LAN behavior."
            )
            suggested_fix = "Validate the exact customer port and isolate any bridged or wrong-patched path before blaming upstream service."

        return {
            "query": {
                "network_name": network_name,
                "mac": mac,
                "serial": serial,
                "site_id": site_id,
            },
            "resolved": {
                "network_name": resolved_network_name,
                "mac": resolved_mac,
                "serial": resolved_serial,
                "site_id": resolved_site_id,
                "building_id": building_id,
                "unit": unit,
            },
            "local_row": local_row,
            "trace": trace,
            "local_ont_path": local_ont,
            "ghn_hint": ghn_hint,
            "building_model": {
                "building_id": building_id,
                "known_units": (building_model or {}).get("known_units"),
                "coverage": (building_model or {}).get("coverage"),
            } if building_model else None,
            "same_floor_units": same_floor_units,
            "active_alerts": alerts,
            "fault_domain": {
                "likely_domain": likely_domain,
                "confidence": confidence,
                "owner": owner,
                "reason": reason,
                "suggested_fix": suggested_fix,
                "affected_scope": affected_scope,
            },
        }

    def get_customer_access_trace(
        self,
        network_name: str | None = None,
        mac: str | None = None,
        serial: str | None = None,
        site_id: str | None = None,
    ) -> dict[str, Any]:
        fault = self.correlate_customer_fault_domain(network_name, mac, serial, site_id)
        resolved = dict(fault.get("resolved") or {})
        resolved_network_name = str(resolved.get("network_name") or network_name or "").strip() or None
        resolved_mac = norm_mac(str(resolved.get("mac") or mac or ""))
        resolved_serial = str(resolved.get("serial") or serial or "").strip() or None
        resolved_site_id = canonical_scope(resolved.get("site_id") or site_id)
        building_id = canonical_scope(resolved.get("building_id"))
        unit = str(resolved.get("unit") or "").strip() or None

        cpe_state = self.get_cpe_state(resolved_mac, True) if resolved_mac else {
            "mac": resolved_mac,
            "bridge": {"trace_status": "no_mac", "verified_sightings": []},
            "ppp_sessions": [],
            "arp_entries": [],
            "related_mac_candidates": [],
            "local_ont_path": self.get_local_ont_path(None, resolved_serial),
            "is_physically_seen": False,
            "is_service_online": False,
        }
        trace = cpe_state.get("bridge") or fault.get("trace") or {}
        local_ont_path = cpe_state.get("local_ont_path") or fault.get("local_ont_path") or {}
        building_model = self.get_building_model(building_id) if building_id else None
        block_label = None
        if resolved_network_name:
            block_match = re.search(r"NYCHA(\d{3,4}-\d{3,4}[A-Za-z]+)", resolved_network_name, re.I)
            if block_match:
                raw = block_match.group(1)
                street_match = re.match(r"(\d{3,4}-\d{3,4})([A-Za-z].+)", raw)
                if street_match:
                    block_label = f"{street_match.group(1)} {street_match.group(2)}"
        block_transport_hint = None
        legacy_handoff_hint = None
        if block_label:
            block_transport_query = block_label
            block_query_match = re.match(r"(\d{3,4})-\d{3,4}\s+(.+)", block_label)
            if block_query_match:
                block_transport_query = f"{block_query_match.group(1)} {block_query_match.group(2)}"
            transport = self.get_transport_radio_summary(query=block_transport_query)
            if transport.get("found"):
                radio = transport.get("radio") or {}
                block_transport_hint = {
                    "query": block_transport_query,
                    "name": radio.get("name"),
                    "ip": radio.get("ip"),
                    "status": radio.get("status"),
                    "site_id": transport.get("site_id"),
                }
            # WHY: Per-site legacy handoff hints live in SITE_SERVICE_PROFILES
            # under "legacy_handoff_hints": a list of {block_label_fragment, device_identity,
            # interface, comment, source}. This replaces the hardcoded Fenimore check
            # and allows any site to declare its own router-transport topology shortcuts.
            site_profile = SITE_SERVICE_PROFILES.get(canonical_scope(resolved_site_id) or "", {})
            for hint in (site_profile.get("legacy_handoff_hints") or []):
                if hint.get("block_label_fragment", "") in block_label:
                    legacy_handoff_hint = {
                        "device_identity": hint.get("device_identity"),
                        "interface":       hint.get("interface"),
                        "comment":         hint.get("comment"),
                        "source":          hint.get("source"),
                    }
                    break

        exact_access_match = None
        if building_model and unit:
            exact_access_match = next(
                (
                    row for row in (building_model.get("exact_access_matches") or [])
                    if str(row.get("unit") or "").strip().upper() == unit.upper()
                ),
                None,
            )

        ppp_sessions = cpe_state.get("ppp_sessions") or []
        arp_entries = cpe_state.get("arp_entries") or []
        best_guess = trace.get("best_guess") or {}
        bigmac_edge = trace.get("bigmac_best_edge_guess") or {}

        access_path: list[dict[str, Any]] = []
        if exact_access_match:
            access_path.append(
                {
                    "layer": "expected_access_port",
                    "device_identity": exact_access_match.get("switch_identity"),
                    "interface": exact_access_match.get("interface"),
                    "source": ",".join(exact_access_match.get("evidence_sources") or ["expected_access_port"]),
                }
            )
        if best_guess:
            access_path.append(
                {
                    "layer": "latest_scan_bridge_host",
                    "device_identity": best_guess.get("identity"),
                    "interface": best_guess.get("on_interface"),
                    "vid": best_guess.get("vid"),
                    "source": "bridge_hosts",
                }
            )
        if bigmac_edge:
            access_path.append(
                {
                    "layer": "bigmac_edge_corroboration",
                    "device_identity": bigmac_edge.get("device_name"),
                    "interface": bigmac_edge.get("port_name"),
                    "vid": bigmac_edge.get("vlan_id"),
                    "source": "bigmac",
                }
            )
        for row in ppp_sessions[:3]:
            access_path.append(
                {
                    "layer": "ppp_session",
                    "device_identity": canonical_identity(row.get("identity")) or row.get("router_ip"),
                    "interface": row.get("name"),
                    "address": row.get("address"),
                    "source": "router_ppp_active",
                }
            )
        for row in arp_entries[:3]:
            access_path.append(
                {
                    "layer": "arp_entry",
                    "device_identity": row.get("router_ip"),
                    "interface": row.get("interface"),
                    "address": row.get("address"),
                    "source": "router_arp",
                }
            )

        inferred_break = "unknown"
        building_device_count = int(((building_model or {}).get("device_count")) or 0)
        if exact_access_match and not best_guess and not ppp_sessions and not arp_entries:
            inferred_break = "expected_access_port_not_live"
        elif building_id and building_device_count == 0:
            inferred_break = "building_access_unmapped"
        elif trace.get("trace_status") == "latest_scan_uplink_only":
            inferred_break = "visible_upstream_not_pinned_to_edge"
        elif trace.get("trace_status") == "edge_trace_found" and not ppp_sessions and not arp_entries:
            inferred_break = "edge_seen_without_service_session"
        elif ppp_sessions or arp_entries:
            inferred_break = "service_plane_present_check_field_side"
        elif local_ont_path.get("found"):
            inferred_break = "olt_or_optical_path_present"

        return {
            "resolved": resolved,
            "fault_domain": fault.get("fault_domain") or {},
            "trace": trace,
            "cpe_state": cpe_state,
            "local_ont_path": local_ont_path,
            "building_model_summary": {
                "building_id": building_id,
                "address": (building_model or {}).get("address"),
                "address_block": block_label,
                "block_transport_hint": block_transport_hint,
                "legacy_handoff_hint": legacy_handoff_hint,
                "device_count": (building_model or {}).get("device_count"),
                "probable_cpe_count": (building_model or {}).get("probable_cpe_count"),
            } if building_model else None,
            "exact_access_match": exact_access_match,
            "ppp_sessions": ppp_sessions,
            "arp_entries": arp_entries,
            "access_path": access_path,
            "inferred_break": inferred_break,
            "available": True,
            "query": {
                "network_name": resolved_network_name,
                "mac": resolved_mac,
                "serial": resolved_serial,
                "site_id": resolved_site_id,
            },
        }

    def get_building_fault_domain(self, building_id: str) -> dict[str, Any]:
        building_id = canonical_scope(building_id)
        if not building_id:
            raise ValueError("building_id is required")
        building_model = self.get_building_model(building_id)
        site_id = canonical_scope(building_id.split(".")[0])
        alerts = self._alerts_for_site(site_id) if self.alerts and site_id else []
        units = list(building_model.get("unit_state_decisions") or [])

        floor_clusters: list[dict[str, Any]] = []
        by_floor: dict[str, list[dict[str, Any]]] = {}
        for row in units:
            unit = str(row.get("unit") or "")
            match = re.match(r"(\d+)", unit)
            floor = match.group(1) if match else "unknown"
            by_floor.setdefault(floor, []).append(row)

        for floor, rows in by_floor.items():
            offline = [row for row in rows if str(row.get("state") or "") != "online"]
            online = [row for row in rows if str(row.get("state") or "") == "online"]
            switch_counts: dict[str, int] = {}
            for row in offline:
                identity = canonical_identity(row.get("switch_identity"))
                if identity:
                    switch_counts[identity] = switch_counts.get(identity, 0) + 1
            dominant_switch = None
            if switch_counts:
                dominant_switch = max(switch_counts.items(), key=lambda item: item[1])[0]
            floor_clusters.append(
                {
                    "floor": floor,
                    "offline_count": len(offline),
                    "online_count": len(online),
                    "offline_units": [str(row.get("unit") or "") for row in offline],
                    "online_units": [str(row.get("unit") or "") for row in online],
                    "dominant_switch": dominant_switch,
                }
            )
        floor_clusters.sort(
            key=lambda row: (
                -int(row.get("offline_count") or 0),
                int(row.get("online_count") or 0),
                str(row.get("floor") or ""),
            )
        )

        top_cluster = None
        if alerts:
            clusters: dict[tuple[str, str], dict[str, Any]] = {}
            for alert in alerts:
                annotations = alert.get("annotations") or {}
                labels = alert.get("labels") or {}
                summary = str(annotations.get("summary") or labels.get("alertname") or "")
                lowered = summary.lower()
                if not any(token in lowered for token in ("rx power low", "rx power high", "rx power critical")):
                    continue
                olt_name = str(annotations.get("olt_name") or labels.get("olt_name") or "").strip() or "unknown"
                port_id = str(annotations.get("port_id") or labels.get("port_id") or "").strip() or "?"
                key = (olt_name, port_id)
                row = clusters.setdefault(
                    key,
                    {"olt_name": olt_name, "port_id": port_id, "critical_count": 0, "low_count": 0, "worst": None},
                )
                severity = str(labels.get("severity") or "warning").lower()
                if severity == "critical":
                    row["critical_count"] += 1
                else:
                    row["low_count"] += 1
                desc = str(annotations.get("description") or "")
                match = re.search(r"(-?\d+(?:\.\d+)?)dBm", desc, re.I)
                if match:
                    value = float(match.group(1))
                    if row["worst"] is None or value < row["worst"]:
                        row["worst"] = value
            if clusters:
                top_cluster = max(
                    clusters.values(),
                    key=lambda item: (
                        int(item.get("critical_count") or 0),
                        int(item.get("low_count") or 0),
                        -float(item.get("worst") or 0.0),
                    ),
                )

        likely_domain = "unknown"
        confidence = "low"
        reason = "Jake does not yet have enough shared-path evidence to isolate this building."
        suggested_fix = "Start with the sharpest current shared-path clue before dispatching multiple teams."
        affected_scope = "building"
        owner = "NOC triage"

        top_floor = floor_clusters[0] if floor_clusters else None
        if top_floor and int(top_floor.get("offline_count") or 0) >= 2 and int(top_floor.get("online_count") or 0) == 0:
            likely_domain = "shared_floor_access_path"
            confidence = "high" if top_cluster else "medium"
            affected_scope = f"floor_{top_floor.get('floor')}"
            owner = "Fiber/mux team" if top_cluster else "Field tech team"
            if top_cluster:
                reason = (
                    f"Multiple units on floor {top_floor.get('floor')} of {building_id} are offline, and the site's strongest active optical issue is "
                    f"{top_cluster.get('olt_name')} PON {top_cluster.get('port_id')}. That reads more like a shared floor path, mux, splitter, or drop-side handoff problem than isolated bad CPEs."
                )
                suggested_fix = (
                    f"Work the shared floor path first for floor {top_floor.get('floor')}: mux/drop/splitter/patch path, then validate "
                    f"{top_cluster.get('olt_name')} PON {top_cluster.get('port_id')}."
                )
            elif top_floor.get("dominant_switch"):
                reason = (
                    f"Multiple units on floor {top_floor.get('floor')} of {building_id} are offline and the offline units cluster on "
                    f"{top_floor.get('dominant_switch')}. That points to a shared floor/access switch path instead of one bad subscriber."
                )
                suggested_fix = f"Check the shared floor path and switch-side handoff around {top_floor.get('dominant_switch')} before treating units individually."
            else:
                reason = (
                    f"Multiple units on floor {top_floor.get('floor')} of {building_id} are offline together, with no same-floor online units in the current model. "
                    "That suggests a shared floor path or mux/drop issue."
                )
                suggested_fix = f"Check the floor {top_floor.get('floor')} shared handoff path first: mux, drop, patch, and any shared edge switch."
        elif top_cluster:
            likely_domain = "shared_optical_plant_noise"
            confidence = "medium"
            owner = "Fiber/OLT team"
            reason = (
                f"The building does not show a clean same-floor outage cluster, but the site's strongest active shared-path issue is "
                f"{top_cluster.get('olt_name')} PON {top_cluster.get('port_id')}."
            )
            suggested_fix = f"Prioritize {top_cluster.get('olt_name')} PON {top_cluster.get('port_id')} before assuming each subscriber is independently broken."
        elif top_floor and int(top_floor.get("offline_count") or 0) == 1:
            likely_domain = "localized_unit_or_access_port"
            confidence = "medium"
            affected_scope = "single_unit"
            owner = "Field tech team"
            offline_units = ", ".join((top_floor.get("offline_units") or [])[:4]) or "the affected unit"
            if top_floor.get("dominant_switch"):
                reason = (
                    f"The building does not show a clean shared floor outage. The strongest current signal is a localized unit problem on "
                    f"{top_floor.get('dominant_switch')} affecting {offline_units}."
                )
                suggested_fix = f"Check the exact customer port and local patch path on {top_floor.get('dominant_switch')} before escalating to a shared-building theory."
            else:
                reason = (
                    f"The building does not show a clean shared floor outage. The strongest current signal is a localized unit problem affecting {offline_units}."
                )
                suggested_fix = "Check the exact unit path, patching, and local handoff before treating this as a building-wide issue."

        return {
            "building_id": building_id,
            "site_id": site_id,
            "address": building_model.get("address"),
            "floor_clusters": floor_clusters,
            "top_optical_cluster": top_cluster,
            "fault_domain": {
                "likely_domain": likely_domain,
                "confidence": confidence,
                "owner": owner,
                "reason": reason,
                "suggested_fix": suggested_fix,
                "affected_scope": affected_scope,
            },
        }

    def get_site_historical_evidence(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        alerts = self._alerts_for_site(site_id) if self.alerts else []
        site_flaps = self.get_site_flap_history(site_id)
        radio_inventory = self.get_site_radio_inventory(site_id)
        syslog_summary = self.get_site_syslog_summary(site_id)
        radio_rows = radio_inventory.get("radios") or []
        building_flap_counts = site_flaps.get("counts_by_building") or {}

        optical_alerts: list[dict[str, Any]] = []
        radio_alerts: list[dict[str, Any]] = []
        for alert in alerts:
            labels = alert.get("labels") or {}
            annotations = alert.get("annotations") or {}
            summary = str(annotations.get("summary") or "")
            if str(labels.get("device_role") or "").lower() == "onu" or "onu" in summary.lower():
                optical_alerts.append(alert)
            if "cambium" in str(labels.get("alertname") or "").lower() or "cambium" in summary.lower():
                radio_alerts.append(alert)

        optical_by_olt: dict[str, int] = {}
        for alert in optical_alerts:
            olt_name = str((alert.get("labels") or {}).get("olt_name") or "").strip() or "unknown"
            optical_by_olt[olt_name] = optical_by_olt.get(olt_name, 0) + 1

        radio_status_counts: dict[str, int] = {}
        radio_without_ip: list[str] = []
        transport_history: list[dict[str, Any]] = []
        for row in radio_rows:
            status = str(row.get("status") or "unknown")
            radio_status_counts[status] = radio_status_counts.get(status, 0) + 1
            if not row.get("primary_ip"):
                radio_without_ip.append(str(row.get("name") or ""))
            if "transport_scan" not in (row.get("sources") or []):
                continue
            summary = self.get_transport_radio_summary(name=str(row.get("name") or ""))
            radio = summary.get("radio") or {}
            history_row = {
                "name": radio.get("name") or row.get("name"),
                "vendor": summary.get("vendor"),
                "status": radio.get("status") or row.get("status"),
                "likely_issue": summary.get("likely_issue"),
                "likely_reason": summary.get("likely_reason"),
            }
            if summary.get("vendor") == "siklu":
                history_row["log_flags"] = ((radio.get("log_analysis") or {}).get("flags")) or {}
            transport_history.append(history_row)

        field_evidence: list[dict[str, Any]] = []
        candidate_paths = [
            REPO_ROOT / "docs" / "NYCHA_NETWORK_TOPOLOGY_2026-03-13.md",
            REPO_ROOT / "docs" / "SAVOY_OLT_FIELD_NOTES_2026-04-02.md",
            REPO_ROOT / "artifacts" / "transport_radio_scan" / "transport_radio_scan.json",
            REPO_ROOT / "artifacts" / "customer_port_map" / "customer_port_map.json",
            REPO_ROOT / "artifacts" / "crs_44_audit" / "crs_44_audit.json",
        ]
        site_token = site_id
        for path in candidate_paths:
            if not path.exists():
                continue
            note = {"path": str(path), "kind": "artifact" if path.suffix == ".json" else "doc"}
            if path.suffix == ".md":
                try:
                    text = path.read_text(errors="ignore")
                    if site_token in text or (site_id == "000021" and "Girard" in text):
                        note["matched"] = True
                        note["reason"] = "site-specific notes present"
                    else:
                        note["matched"] = False
                except Exception:
                    note["matched"] = False
            else:
                note["matched"] = True
                note["reason"] = "local archived artifact available"
            field_evidence.append(note)

        netbox_change_status = {"configured": bool(self.netbox), "available": False}
        try:
            if self.netbox:
                payload = self.netbox.request("/api/core/object-changes/", {"limit": 10, "q": site_id})
                rows = payload.get("results") or []
                netbox_change_status = {
                    "configured": True,
                    "available": True,
                    "count": len(rows),
                    "sample": rows[:5],
                }
        except Exception as exc:
            netbox_change_status = {
                "configured": bool(self.netbox),
                "available": False,
                "error": str(exc),
            }

        by_building_radios: dict[str, list[str]] = {}
        for row in radio_rows:
            building_id = canonical_scope(row.get("building_id")) or "unknown"
            by_building_radios.setdefault(building_id, []).append(str(row.get("name") or ""))

        return {
            "site_id": site_id,
            "optical_alert_count": len(optical_alerts),
            "optical_alerts_by_olt": dict(sorted(optical_by_olt.items())),
            "radio_alert_count": len(radio_alerts),
            "radio_status_counts": dict(sorted(radio_status_counts.items())),
            "radios_without_management_ip": sorted(set(radio_without_ip)),
            "shared_building_v2000_pairs": radio_inventory.get("shared_building_v2000_pairs") or [],
            "dn_radios": radio_inventory.get("dn_radios") or [],
            "cn_radio_count": int(radio_inventory.get("cn_radio_count") or 0),
            "flap_port_count": int(site_flaps.get("count") or 0),
            "flap_counts_by_building": building_flap_counts,
            "radio_buildings": {k: sorted(v) for k, v in sorted(by_building_radios.items())},
            "transport_history": transport_history[:20],
            "syslog_summary": syslog_summary,
            "field_evidence": field_evidence,
            "netbox_changelogs": netbox_change_status,
        }

    def get_site_syslog_summary(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        all_events = load_syslog_events()
        events = [row for row in all_events if canonical_scope(row.get("site_id")) == site_id]
        by_vendor: dict[str, int] = {}
        by_device: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for row in events:
            vendor = str(row.get("vendor") or "unknown")
            by_vendor[vendor] = by_vendor.get(vendor, 0) + 1
            device = str(row.get("device_hint") or row.get("host") or "unknown")
            by_device[device] = by_device.get(device, 0) + 1
            severity = str(row.get("severity") or "unknown")
            by_severity[severity] = by_severity.get(severity, 0) + 1
        sample = []
        for row in events[:20]:
            sample.append(
                {
                    "timestamp": row.get("timestamp"),
                    "host": row.get("host"),
                    "device_hint": row.get("device_hint"),
                    "vendor": row.get("vendor"),
                    "severity": row.get("severity"),
                    "message": row.get("message"),
                    "source_path": row.get("source_path"),
                }
            )
        return {
            "site_id": site_id,
            "configured_dir": str(ARTIFACT_SYSLOG_DIR),
            "available": ARTIFACT_SYSLOG_DIR.exists(),
            "event_count": len(events),
            "total_event_count": len(all_events),
            "by_vendor": dict(sorted(by_vendor.items())),
            "by_device": dict(sorted(by_device.items(), key=lambda item: (-item[1], item[0]))[:10]),
            "by_severity": dict(sorted(by_severity.items())),
            "sample": sample,
        }

    def _lynxdhcp_snapshot(self) -> dict[str, Any]:
        state = load_lynxdhcp_state()
        return {
            "available": bool(state),
            "source_path": state.get("_source_path"),
            "summary": state.get("summary") or {},
            "subscribers": list(state.get("subscribers") or []),
            "relays": list(((state.get("network") or {}).get("relays") or [])),
            "links": list(((state.get("network") or {}).get("links") or [])),
            "findings": list(state.get("findings") or []),
            "events": list(state.get("events") or []),
        }

    def get_dhcp_findings_summary(self) -> dict[str, Any]:
        snap = self._lynxdhcp_snapshot()
        findings = snap.get("findings") or []
        by_severity: dict[str, int] = {}
        for row in findings:
            severity = str(row.get("severity") or "unknown").lower()
            by_severity[severity] = by_severity.get(severity, 0) + 1
        lynxmsp = lynxmsp_source_status()
        return {
            "available": bool(snap.get("available")),
            "source_path": snap.get("source_path"),
            "provider_summary": snap.get("summary") or {},
            "finding_count": len(findings),
            "by_severity": dict(sorted(by_severity.items())),
            "findings": findings[:20],
            "relay_count": len(snap.get("relays") or []),
            "subscriber_count": len(snap.get("subscribers") or []),
            "lynxmsp_status": lynxmsp,
        }

    def get_dhcp_relay_summary(self, relay_name: str) -> dict[str, Any]:
        snap = self._lynxdhcp_snapshot()
        relay_name_norm = str(relay_name or "").strip()
        relay_name_key = relay_name_norm.lower()
        relays = snap.get("relays") or []
        relay = next((row for row in relays if str(row.get("name") or "").lower() == relay_name_key), None)
        subscribers = [
            row
            for row in (snap.get("subscribers") or [])
            if str(row.get("relay") or "").lower() == relay_name_key
        ]
        findings = [
            row
            for row in (snap.get("findings") or [])
            if relay_name_key in str(row.get("device") or "").lower()
            or relay_name_key in str(row.get("title") or "").lower()
            or relay_name_key in str(row.get("evidence") or "").lower()
        ]
        status = lynxmsp_source_status()
        return {
            "query": relay_name_norm,
            "available": bool(snap.get("available")),
            "source_path": snap.get("source_path"),
            "relay": relay,
            "subscriber_count": len(subscribers),
            "subscribers": subscribers[:10],
            "findings": findings[:10],
            "provider_summary": snap.get("summary") or {},
            "lynxmsp_status": status,
        }

    def get_dhcp_circuit_summary(self, circuit_id: str) -> dict[str, Any]:
        snap = self._lynxdhcp_snapshot()
        circuit_norm = str(circuit_id or "").strip()
        circuit_key = circuit_norm.lower()
        subscriber = next(
            (
                row
                for row in (snap.get("subscribers") or [])
                if str(row.get("circuitId") or "").lower() == circuit_key
            ),
            None,
        )
        relay = None
        if subscriber:
            relay = next(
                (
                    row
                    for row in (snap.get("relays") or [])
                    if str(row.get("name") or "").lower() == str(subscriber.get("relay") or "").lower()
                ),
                None,
            )
        parts = [part for part in circuit_norm.split("/") if part]
        tail = parts[-1] if parts else ""
        interface = "/".join(parts[1:-1]) if len(parts) >= 3 else (parts[-2] if len(parts) >= 2 else None)
        port_suffix = tail.split(":", 1)[0] if ":" in tail else tail or None
        subscriber_hint = tail.split(":", 1)[1] if ":" in tail else None
        return {
            "query": circuit_norm,
            "available": bool(snap.get("available")),
            "source_path": snap.get("source_path"),
            "subscriber": subscriber,
            "relay": relay,
            "decoded_path": {
                "site_token": parts[0] if parts else None,
                "interface_scope": interface,
                "port_token": port_suffix,
                "subscriber_token": subscriber_hint,
            },
            "lynxmsp_status": lynxmsp_source_status(),
        }

    def get_dhcp_subscriber_summary(
        self,
        mac: str | None = None,
        ip: str | None = None,
        circuit_id: str | None = None,
        remote_id: str | None = None,
        subscriber_id: str | None = None,
        relay_name: str | None = None,
    ) -> dict[str, Any]:
        snap = self._lynxdhcp_snapshot()
        subscribers = snap.get("subscribers") or []
        relay_rows = snap.get("relays") or []
        query = {
            "mac": norm_mac(mac) if mac else None,
            "ip": str(ip or "").strip() or None,
            "circuit_id": str(circuit_id or "").strip() or None,
            "remote_id": str(remote_id or "").strip() or None,
            "subscriber_id": str(subscriber_id or "").strip() or None,
            "relay_name": str(relay_name or "").strip() or None,
        }

        def matches(row: dict[str, Any]) -> bool:
            if query["mac"] and norm_mac(str(row.get("cpeMac") or "")) != query["mac"]:
                return False
            if query["ip"] and str(row.get("ipv4") or "").strip() != query["ip"]:
                return False
            if query["circuit_id"] and str(row.get("circuitId") or "").strip().lower() != str(query["circuit_id"]).lower():
                return False
            if query["remote_id"] and str(row.get("remoteId") or "").strip().lower() != str(query["remote_id"]).lower():
                return False
            if query["subscriber_id"] and str(row.get("id") or "").strip().lower() != str(query["subscriber_id"]).lower():
                return False
            if query["relay_name"] and str(row.get("relay") or "").strip().lower() != str(query["relay_name"]).lower():
                return False
            return any(value for value in query.values())

        matched = [row for row in subscribers if matches(row)]
        relay = None
        if matched:
            relay_name_value = str(matched[0].get("relay") or "").strip().lower()
            relay = next((row for row in relay_rows if str(row.get("name") or "").strip().lower() == relay_name_value), None)
        related_findings: list[dict[str, Any]] = []
        if matched:
            keys = {
                str(matched[0].get("relay") or "").lower(),
                str(matched[0].get("remoteId") or "").lower(),
                str(matched[0].get("circuitId") or "").lower(),
            }
            for finding in snap.get("findings") or []:
                haystack = " ".join(
                    [
                        str(finding.get("title") or ""),
                        str(finding.get("device") or ""),
                        str(finding.get("evidence") or ""),
                    ]
                ).lower()
                if any(key and key in haystack for key in keys):
                    related_findings.append(finding)
        return {
            "query": query,
            "available": bool(snap.get("available")),
            "source_path": snap.get("source_path"),
            "match_count": len(matched),
            "subscribers": matched[:10],
            "relay": relay,
            "related_findings": related_findings[:10],
            "provider_summary": snap.get("summary") or {},
            "lynxmsp_status": lynxmsp_source_status(),
        }

    def get_live_dhcp_lease_summary(self, site_id: str | None = None, mac: str | None = None, ip: str | None = None, limit: int = 25) -> dict[str, Any]:
        limit = max(1, min(int(limit or 25), 100))
        canonical_site = canonical_scope(site_id) if site_id else None
        query_mac = norm_mac(mac) if mac else None
        query_ip = str(ip or "").strip() or None
        live_rows: list[dict[str, Any]] = []
        api_detail = "not configured"
        api_ok = False
        for base in LYNXMSP_API_CANDIDATES:
            if not base:
                continue
            params = {"active_only": "true"}
            ok, payload, detail = _http_json_request(f"{base}/dhcp/leases?" + urllib.parse.urlencode(params), timeout=8.0)
            api_detail = detail
            if not ok:
                continue
            if isinstance(payload, list):
                live_rows = [row for row in payload if isinstance(row, dict)]
                api_ok = True
                break

        def row_matches(row: dict[str, Any]) -> bool:
            if query_mac:
                row_mac = norm_mac(str(row.get("mac_address") or row.get("macAddress") or row.get("active_mac_address") or row.get("activeMacAddress") or ""))
                if row_mac != query_mac:
                    return False
            if query_ip:
                row_ip = str(row.get("address") or row.get("ip_address") or row.get("active_address") or row.get("activeAddress") or "").strip()
                if row_ip != query_ip:
                    return False
            if canonical_site:
                haystack = json.dumps(row, sort_keys=True).lower()
                if canonical_site.lower() not in haystack:
                    return False
            return True

        filtered_live = [row for row in live_rows if row_matches(row)]
        if filtered_live or api_ok:
            return {
                "available": api_ok,
                "source": "lynxmsp_api",
                "base_detail": api_detail,
                "site_id": canonical_site,
                "query": {"mac": query_mac, "ip": query_ip},
                "lease_count": len(filtered_live),
                "leases": filtered_live[:limit],
            }

        status = lynxmsp_source_status(canonical_site)
        db_rows: list[dict[str, Any]] = []
        db_path = find_lynxmsp_db_path()
        if db_path:
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                clauses = ["1=1"]
                params: list[Any] = []
                if query_mac:
                    clauses.append("(lower(mac_address)=lower(?) or lower(active_mac_address)=lower(?))")
                    params.extend([query_mac, query_mac])
                if query_ip:
                    clauses.append("(address=? or active_address=?)")
                    params.extend([query_ip, query_ip])
                sql = f"select * from dhcp_leases where {' and '.join(clauses)} order by lease_time desc limit ?"
                params.append(limit)
                db_rows = [dict(r) for r in cur.execute(sql, params).fetchall()]
                conn.close()
            except Exception:
                db_rows = []
        filtered_db = []
        for row in db_rows:
            if not canonical_site:
                filtered_db.append(row)
                continue
            haystack = json.dumps(row, sort_keys=True).lower()
            if canonical_site.lower() in haystack:
                filtered_db.append(row)
        if filtered_db:
            return {
                "available": True,
                "source": "lynxmsp_db_fallback",
                "site_id": canonical_site,
                "query": {"mac": query_mac, "ip": query_ip},
                "lease_count": len(filtered_db),
                "leases": filtered_db[:limit],
                "lynxmsp_status": status,
                "api_detail": api_detail,
            }

        snap = self._lynxdhcp_snapshot()
        snapshot_rows = list(snap.get("subscribers") or [])
        filtered_snapshot: list[dict[str, Any]] = []
        for row in snapshot_rows:
            row_mac = norm_mac(str(row.get("cpeMac") or ""))
            row_ip = str(row.get("ipv4") or "").strip()
            haystack = json.dumps(row, sort_keys=True).lower()
            if query_mac and row_mac != query_mac:
                continue
            if query_ip and row_ip != query_ip:
                continue
            if canonical_site and canonical_site.lower() not in haystack:
                continue
            filtered_snapshot.append(row)
        return {
            "available": bool(filtered_snapshot),
            "source": "lynxdhcp_state_fallback",
            "site_id": canonical_site,
            "query": {"mac": query_mac, "ip": query_ip},
            "lease_count": len(filtered_snapshot),
            "leases": filtered_snapshot[:limit],
            "source_path": snap.get("source_path"),
            "provider_summary": snap.get("summary") or {},
            "lynxmsp_status": status,
            "api_detail": api_detail,
        }

    def get_live_splynx_online_summary(self, site_id: str | None = None, search: str | None = None, limit: int = 25) -> dict[str, Any]:
        limit = max(1, min(int(limit or 25), 100))
        canonical_site = canonical_scope(site_id) if site_id else None
        ok, payload, detail = _splynx_request("admin/customers/customers-online")
        rows: list[dict[str, Any]] = []
        if ok:
            if isinstance(payload, list):
                rows = [row for row in payload if isinstance(row, dict)]
            elif isinstance(payload, dict):
                candidate = payload.get("data")
                if isinstance(candidate, list):
                    rows = [row for row in candidate if isinstance(row, dict)]

        needle = str(search or "").strip().lower()
        filtered: list[dict[str, Any]] = []
        for row in rows:
            haystack = json.dumps(row, sort_keys=True).lower()
            if canonical_site and canonical_site.lower() not in haystack:
                continue
            if needle and needle not in haystack:
                continue
            filtered.append(row)
        return {
            "available": ok,
            "source": "splynx_api",
            "detail": detail,
            "site_id": canonical_site,
            "search": search,
            "online_count": len(filtered),
            "rows": filtered[:limit],
            "configured": bool(_splynx_credentials()["base_url"]),
        }

    def get_live_cnwave_rf_summary(self, site_id: str | None = None, name: str | None = None, limit: int = 20) -> dict[str, Any]:
        import urllib.request, urllib.parse, json as _json
        limit = max(1, min(int(limit or 20), 100))
        base = os.environ.get("CNWAVE_EXPORTER_URL", "").rstrip("/")
        prometheus_mode = bool(os.environ.get("CNWAVE_PROMETHEUS_MODE", ""))
        if not base or not prometheus_mode:
            # Fall back to old path
            rows = self._cnwave_metrics()
            if not rows:
                return {"configured": self.cnwave is not None, "available": False, "site_id": site_id, "name": name}
            return {"configured": True, "available": True, "site_id": site_id, "links": [], "name": name}

        def pquery(metric):
            try:
                url = f"{base}/api/v1/query?query={urllib.parse.quote(metric)}"
                req = urllib.request.Request(url, headers={"User-Agent": "jake/1.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = _json.loads(resp.read())
                return data.get("data", {}).get("result", [])
            except Exception:
                return []

        def node_match(labels, site_id, name):
            a = (labels.get("a_node") or "").lower()
            z = (labels.get("z_node") or "").lower()
            ln = (labels.get("link_name") or "").lower()
            nd = (labels.get("name") or labels.get("node") or "").lower()
            if site_id:
                s = site_id.lower()
                if not (s in a or s in z or s in ln or s in nd):
                    return False
            if name:
                n = name.lower()
                if not (n in a or n in z or n in ln or n in nd):
                    return False
            return True

        # Fetch all needed metrics
        rssi_data = {r["metric"].get("link_name"): float(r["value"][1]) for r in pquery("cnwave_link_rssi") if node_match(r["metric"], site_id, name) and r.get("value")}
        snr_data = {r["metric"].get("link_name"): float(r["value"][1]) for r in pquery("cnwave_link_snr") if node_match(r["metric"], site_id, name) and r.get("value")}
        mcs_data = {r["metric"].get("link_name"): float(r["value"][1]) for r in pquery("cnwave_link_mcs") if node_match(r["metric"], site_id, name) and r.get("value")}
        status_data = {r["metric"].get("link_name"): float(r["value"][1]) for r in pquery("cnwave_link_status") if node_match(r["metric"], site_id, name) and r.get("value")}

        # Get node labels for a_node/z_node
        link_nodes: dict[str, dict] = {}
        for r in pquery("cnwave_link_rssi"):
            m = r["metric"]
            ln = m.get("link_name")
            if ln and node_match(m, site_id, name):
                link_nodes[ln] = {"a_node": m.get("a_node"), "z_node": m.get("z_node")}

        all_links = set(rssi_data) | set(snr_data) | set(mcs_data) | set(status_data)
        # Deduplicate bidirectional links
        seen: set[str] = set()
        unique_links = []
        for ln in all_links:
            parts = ln.replace("link-", "").split("-", 1) if ln else [ln]
            key = "link-" + "-".join(sorted(parts))
            if key in seen:
                continue
            seen.add(key)
            unique_links.append(ln)

        links = []
        for ln in sorted(unique_links)[:limit]:
            rssi = rssi_data.get(ln)
            snr = snr_data.get(ln)
            mcs = mcs_data.get(ln)
            status_val = status_data.get(ln)
            nodes = link_nodes.get(ln, {})
            links.append({
                "link_name": ln,
                "a_node": nodes.get("a_node"),
                "z_node": nodes.get("z_node"),
                "rssi_dbm": rssi,
                "snr_db": snr,
                "mcs": mcs,
                "status": "up" if status_val == 1.0 else ("down" if status_val == 0.0 else "unknown"),
            })

        return {
            "configured": True,
            "available": True,
            "site_id": site_id,
            "name": name,
            "link_count": len(links),
            "links": links,
        }

    def get_live_cnwave_radio_neighbors(
        self,
        site_id: str | None = None,
        name: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        radio_lookup = self.get_transport_radio_summary(query=query, name=name)
        if not radio_lookup.get("found") and query:
            cleaned = normalize_free_text(str(query or ""))
            for noise in (
                "show ipv4 neighbors for",
                "show ipv4 neighbors on",
                "ipv4 neighbors for",
                "ipv4 neighbors on",
                "what devices are behind",
                "what is behind this radio",
                "what is behind that radio",
                "devices behind this radio",
                "devices behind that radio",
                "neighbors on this radio",
                "neighbors on that radio",
            ):
                cleaned = cleaned.replace(noise, " ")
            cleaned = " ".join(cleaned.split()).strip()
            if cleaned:
                radio_lookup = self.get_transport_radio_summary(query=cleaned)
        controller = self.cnwave_controller.diagnostics() if self.cnwave_controller else {"configured": False}
        if not radio_lookup.get("found"):
            return {
                "configured": bool(controller.get("configured")),
                "available": False,
                "error": "radio_not_found",
                "query": {"site_id": site_id, "name": name, "query": query},
                "controller": controller,
            }

        radio = dict(radio_lookup.get("radio") or {})
        resolved_site_id = canonical_scope(site_id) or canonical_scope(radio_lookup.get("site_id"))
        if resolved_site_id and canonical_scope(radio_lookup.get("site_id")) not in {None, "", resolved_site_id}:
            return {
                "configured": bool(controller.get("configured")),
                "available": False,
                "error": "radio_scope_mismatch",
                "site_id": resolved_site_id,
                "radio_site_id": radio_lookup.get("site_id"),
                "radio": radio,
                "controller": controller,
            }

        peer_names = radio_lookup.get("peer_names") or []
        fallback_partial = {
            "radio_name": radio.get("name"),
            "radio_ip": radio.get("ip"),
            "site_id": radio_lookup.get("site_id"),
            "status": radio.get("status"),
            "vendor": radio_lookup.get("vendor"),
            "transport_scan_peers": peer_names,
            "neighbor_macs": list(radio.get("neighbor_macs") or []),
            "initiator_macs": list(radio.get("initiator_macs") or []),
        }
        if not controller.get("remote_neighbors_ready"):
            return {
                "configured": bool(controller.get("configured")),
                "available": False,
                "error": "cnwave_remote_neighbors_not_ready",
                "detail": "Jake has cnWave exporter metrics and direct radio inventory, but the controller remote-command path for Show IPv4 Neighbors is not fully configured.",
                "query": query,
                "site_id": radio_lookup.get("site_id"),
                "radio": radio,
                "partial_evidence": fallback_partial,
                "controller": controller,
            }

        controller_result = self.cnwave_controller.get_ipv4_neighbors(str(radio.get("name") or name or query or ""), str(radio.get("ip") or ""))
        return {
            "configured": bool(controller_result.get("configured")),
            "available": bool(controller_result.get("available")),
            "query": query,
            "site_id": radio_lookup.get("site_id"),
            "radio": radio,
            "partial_evidence": fallback_partial,
            "controller": controller_result.get("controller") or controller,
            "controller_result": controller_result,
        }

    def get_cnwave_controller_capabilities(self, query: str | None = None, site_id: str | None = None) -> dict[str, Any]:
        controller = self.cnwave_controller.diagnostics() if self.cnwave_controller else {"configured": False}
        exporter_configured = bool(os.environ.get("CNWAVE_EXPORTER_URL", "").strip()) and bool(os.environ.get("CNWAVE_PROMETHEUS_MODE", "").strip())
        lower = normalize_free_text(str(query or ""))
        asks_neighbors = "ipv4 neighbors" in lower or "neighbors" in lower
        asks_mac_table = "mac address table" in lower or "bridge table" in lower or "mac table" in lower
        asks_devices_behind = "devices behind" in lower or "behind this radio" in lower or "downstream device identities" in lower

        supported_commands: list[str] = []
        if controller.get("remote_neighbors_ready"):
            supported_commands.append("Show IPv4 Neighbors")
        unverified_commands: list[str] = []
        if asks_mac_table:
            unverified_commands.append("Show MAC address table")

        explanation = []
        if exporter_configured:
            explanation.append("Jake has cnWave exporter metrics for RF/link health.")
        else:
            explanation.append("Jake does not currently have cnWave exporter metrics configured.")
        if controller.get("configured"):
            explanation.append("Jake has some cnWave controller wiring configured.")
        else:
            explanation.append("Jake does not currently have cnWave controller wiring configured.")
        if controller.get("remote_neighbors_ready"):
            explanation.append("The controller-side IPv4 neighbors path is considered ready.")
        else:
            explanation.append("The controller-side IPv4 neighbors path is not fully wired yet.")

        if asks_neighbors:
            operator_read = (
                "Use the controller remote-command path first for IPv4 neighbor visibility. "
                "If that path is not wired, fall back to radio inventory plus handoff-switch SFP/MAC evidence."
            )
        elif asks_mac_table:
            operator_read = (
                "Do not claim controller-side MAC-table visibility as proven here. "
                "Treat it as an unverified community-reported capability until the exact command path is confirmed."
            )
        elif asks_devices_behind or "rf health" in lower:
            operator_read = (
                "RF health comes from exporter metrics, but downstream identities require either a controller-side neighbor/table command "
                "or building-side switch/MAC evidence."
            )
        else:
            operator_read = (
                "Jake should distinguish exporter metrics, controller remote commands, and handoff-switch evidence instead of treating them as the same visibility layer."
            )

        return {
            "configured": bool(controller.get("configured") or exporter_configured),
            "available": True,
            "site_id": canonical_scope(site_id) if site_id else None,
            "query": query,
            "exporter": {
                "configured": exporter_configured,
                "url": os.environ.get("CNWAVE_EXPORTER_URL", "").strip() or None,
            },
            "controller": controller,
            "supported_commands": supported_commands,
            "unverified_commands": unverified_commands,
            "asks_neighbors": asks_neighbors,
            "asks_mac_table": asks_mac_table,
            "asks_devices_behind": asks_devices_behind,
            "operator_read": operator_read,
            "explanation": explanation,
        }


    def run_live_routeros_read(self, device_name: str, intent: str, params: dict[str, Any] | None = None, reason: str | None = None) -> dict[str, Any]:
        if not SSH_MCP_ROOT.exists():
            return {"available": False, "error": "ssh_mcp repo is not present on this host"}
        try:
            ServerConfig, Store, SSHExecutor = _load_ssh_mcp_runtime()
        except Exception as exc:
            return {"available": False, "error": f"ssh_mcp import failed: {exc}"}

        os.environ.setdefault("SSH_MCP_ROOT", str(SSH_MCP_ROOT))
        os.environ.setdefault("SSH_MCP_CONFIG", str(SSH_MCP_ROOT / "config" / "ssh_mcp.json"))
        os.environ.setdefault("SSH_MCP_DB_PATH", str(SSH_MCP_ROOT / "data" / "ssh_mcp.sqlite3"))
        config = ServerConfig.load()
        store = Store(config.db_path)
        executor = SSHExecutor(store, config)
        if not _ssh_mcp_password():
            return {
                "available": False,
                "configured": True,
                "error": "SSH_MCP_PASSWORD is not set for password_env devices",
            }
        try:
            cmd_def = store.resolve_command_template(device_name, intent, params or {})
            proposal = store.create_proposal(
                proposal_type="show_command",
                device_name=device_name,
                session_id=None,
                intent=intent,
                mode="read",
                risk=str(cmd_def.get("risk") or "low"),
                reason=reason or "Jake live read-only execution from chat.",
                rendered_commands=[cmd_def["rendered_command"]],
                requested_by="jake-chat",
            )
            final = executor.run_proposal(proposal["id"], approved_by="jake-chat", approval_note="User requested live read-only execution in Jake chat.")
            return {
                "available": True,
                "device_name": device_name,
                "intent": intent,
                "proposal_id": proposal["id"],
                "rendered_command": cmd_def["rendered_command"],
                "result_count": len(final.get("results") or []),
                "results": final.get("results") or [],
                "execution_summary": final.get("execution_summary"),
                "status": final.get("status"),
            }
        except Exception as exc:
            return {
                "available": False,
                "configured": True,
                "device_name": device_name,
                "intent": intent,
                "error": str(exc),
            }

    def _run_live_routeros_show_command(self, device_name: str, command: str, reason: str, risk: str = "medium") -> dict[str, Any]:
        if not SSH_MCP_ROOT.exists():
            return {"available": False, "error": "ssh_mcp repo is not present on this host"}
        try:
            ServerConfig, Store, SSHExecutor = _load_ssh_mcp_runtime()
        except Exception as exc:
            return {"available": False, "error": f"ssh_mcp import failed: {exc}"}

        os.environ.setdefault("SSH_MCP_ROOT", str(SSH_MCP_ROOT))
        os.environ.setdefault("SSH_MCP_CONFIG", str(SSH_MCP_ROOT / "config" / "ssh_mcp.json"))
        os.environ.setdefault("SSH_MCP_DB_PATH", str(SSH_MCP_ROOT / "data" / "ssh_mcp.sqlite3"))
        config = ServerConfig.load()
        store = Store(config.db_path)
        executor = SSHExecutor(store, config)
        if not _ssh_mcp_password():
            return {
                "available": False,
                "configured": True,
                "error": "SSH_MCP_PASSWORD is not set for password_env devices",
            }
        try:
            proposal = store.create_proposal(
                proposal_type="show_command",
                device_name=device_name,
                session_id=None,
                intent="ad_hoc",
                mode="read",
                risk=risk,
                reason=reason,
                rendered_commands=[command],
                requested_by="jake-chat",
            )
            final = executor.run_proposal(proposal["id"], approved_by="jake-chat", approval_note="User requested live read-only execution in Jake chat.")
            return {
                "available": True,
                "device_name": device_name,
                "intent": "ad_hoc",
                "proposal_id": proposal["id"],
                "rendered_command": command,
                "result_count": len(final.get("results") or []),
                "results": final.get("results") or [],
                "execution_summary": final.get("execution_summary"),
                "status": final.get("status"),
            }
        except Exception as exc:
            return {
                "available": False,
                "configured": True,
                "device_name": device_name,
                "intent": "ad_hoc",
                "error": str(exc),
            }

    @staticmethod
    def _version_tuple(version: str | None) -> tuple[int, ...] | None:
        if not version:
            return None
        match = re.search(r"(\d+(?:\.\d+)+)", str(version))
        if not match:
            return None
        try:
            return tuple(int(part) for part in match.group(1).split("."))
        except ValueError:
            return None

    @staticmethod
    def _version_less_than(current: str | None, target: str | None) -> bool | None:
        current_parts = JakeOps._version_tuple(current)
        target_parts = JakeOps._version_tuple(target)
        if not current_parts or not target_parts:
            return None
        return current_parts < target_parts

    @staticmethod
    def _site_id_from_device_name(device_name: str | None) -> str | None:
        if not device_name:
            return None
        match = re.search(r"\b(\d{6})\b", str(device_name))
        return match.group(1) if match else None

    def _load_local_routeros_export(self, site_id: str | None = None, device_name: str | None = None) -> dict[str, Any]:
        resolved_site = canonical_scope(site_id) if site_id else self._site_id_from_device_name(device_name)
        candidates: list[Path] = []
        if device_name:
            candidates.append(REPO_ROOT / "references" / "tikbreak" / f"{canonical_identity(device_name)}.rsc")
        if resolved_site:
            candidates.append(REPO_ROOT / "references" / "tikbreak" / f"{resolved_site}.R1.rsc")
        for path in candidates:
            if path.exists():
                text = path.read_text(errors="ignore")
                model = None
                for line in text.splitlines()[:8]:
                    if line.startswith("# model = "):
                        model = line.split("=", 1)[1].strip()
                        break
                return {
                    "available": True,
                    "site_id": resolved_site,
                    "device_name": canonical_identity(device_name) if device_name else (f"{resolved_site}.R1" if resolved_site else None),
                    "path": str(path),
                    "text": text,
                    "line_count": len(text.splitlines()),
                    "model": model,
                    "source": "local_export",
                }
        return {"available": False, "site_id": resolved_site, "device_name": canonical_identity(device_name) if device_name else None}

    def _live_routeros_baseline(self, site_id: str | None = None, device_name: str | None = None) -> dict[str, Any]:
        api, target = self._connect_live_routeros_api(site_id=site_id, device_name=device_name)
        baseline = {"target": target}
        if api is None:
            return baseline
        resource: dict[str, Any] = {}
        routerboard: dict[str, Any] = {}
        try:
            rows = [self._routeros_api_row_to_text(row) for row in api.path("system", "resource").select()]
            if rows:
                resource = rows[0]
        except Exception:
            pass
        try:
            rows = [self._routeros_api_row_to_text(row) for row in api.path("system", "routerboard").select()]
            if rows:
                routerboard = rows[0]
        except Exception:
            pass
        baseline["resource"] = resource
        baseline["routerboard"] = routerboard
        return baseline

    def get_live_routeros_export(self, site_id: str | None = None, device_name: str | None = None, show_sensitive: bool = True, terse: bool = True) -> dict[str, Any]:
        target = self._resolve_live_routeros_api_target(site_id=site_id, device_name=device_name)
        resolved_device = target.get("device_name")
        if not resolved_device and device_name:
            resolved_device = canonical_identity(device_name)
        if not resolved_device and site_id:
            resolved_device = f"{canonical_scope(site_id)}.R1"
        export_bits = ["/export"]
        if show_sensitive:
            export_bits.append("show-sensitive")
        if terse:
            export_bits.append("terse")
        export_bits.append("without-paging")
        command = " ".join(export_bits)

        live: dict[str, Any] | None = None
        if resolved_device:
            live = self._run_live_routeros_show_command(
                resolved_device,
                command,
                reason="Pull fresh read-only RouterOS export for upgrade audit.",
                risk="medium",
            )
        if live and live.get("available"):
            stdout_parts = [str(item.get("stdout") or "").strip() for item in (live.get("results") or []) if str(item.get("stdout") or "").strip()]
            export_text = "\n".join(part for part in stdout_parts if part).strip()
            if export_text:
                baseline = self._live_routeros_baseline(site_id=site_id, device_name=resolved_device)
                return {
                    "available": True,
                    "site_id": canonical_scope(site_id) if site_id else self._site_id_from_device_name(resolved_device),
                    "device_name": resolved_device,
                    "source": "live_routeros_export",
                    "command": command,
                    "text": export_text,
                    "line_count": len(export_text.splitlines()),
                    "baseline": baseline,
                    "live_read": live,
                }

        local_export = self._load_local_routeros_export(site_id=site_id, device_name=resolved_device or device_name)
        if local_export.get("available"):
            local_export["fallback_from_live"] = bool(live)
            local_export["live_read"] = live
            return local_export
        return {
            "available": False,
            "site_id": canonical_scope(site_id) if site_id else self._site_id_from_device_name(device_name),
            "device_name": resolved_device,
            "command": command,
            "live_read": live,
            "error": "Could not pull a live RouterOS export and no local export fallback was found.",
        }

    def _audit_upgrade_risk(self, export_text: str, *, target_version: str, model: str | None = None, current_version: str | None = None) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        preflight_steps: list[str] = []
        proposed_changes: list[dict[str, Any]] = []

        upper_model = str(model or "").upper()

        if "CCR2004" in upper_model:
            findings.append({
                "severity": "high",
                "title": "CCR2004 staged-upgrade risk",
                "detail": "CCR2004 boxes can hit the staged-upgrade/NAND trap when jumping from older versions to newer stable builds.",
            })
            older_than_staging = self._version_less_than(current_version, "7.16.2")
            if older_than_staging is True or current_version is None:
                preflight_steps.append("If the current version is older than 7.16.2, use the staged path: 7.16.2 -> /system/routerboard/upgrade -> reboot -> 7.18.2 -> target.")

        if '#error exporting "/interface/bridge/calea"' in export_text or '#error exporting "/ip/firewall/calea"' in export_text:
            findings.append({
                "severity": "high",
                "title": "Existing export is incomplete",
                "detail": "The current export already shows failed sections, so it is not a safe restore artifact by itself.",
            })
            proposed_changes.append({
                "kind": "preflight_only",
                "change": "Take a fresh live `/export show-sensitive` and a binary backup before the upgrade.",
                "why": "The older export is incomplete and should not be the only rollback artifact.",
            })

        if "/system routerboard settings" in export_text:
            findings.append({
                "severity": "medium",
                "title": "RouterBOARD firmware step still required",
                "detail": "Package upgrades do not complete the RouterBOARD firmware step automatically.",
            })
            preflight_steps.append("After the RouterOS package upgrade, run `/system/routerboard/print` and `/system/routerboard/upgrade`, then schedule the extra reboot deliberately.")

        if "/interface pppoe-server server" in export_text and "/ppp aaa" in export_text and "use-radius=yes" in export_text:
            findings.append({
                "severity": "high",
                "title": "Subscriber-impacting headend role",
                "detail": "This box is handling PPPoE and RADIUS, so reboot and recovery behavior directly affect subscribers.",
            })
            preflight_steps.append("Treat the upgrade as a maintenance window and verify PPPoE and RADIUS recovery immediately after reboot.")

        if "/snmp" in export_text:
            findings.append({
                "severity": "medium",
                "title": "Monitoring behavior should be re-checked",
                "detail": "SNMP and monitoring-side parsing can shift across RouterOS 7 releases.",
            })
            preflight_steps.append("Verify SNMP polling and any sysDescr or interface-speed parsing in the monitoring stack after the upgrade.")

        if "/user group" in export_text and ("sensitive" in export_text or "password" in export_text or "api" in export_text):
            findings.append({
                "severity": "medium",
                "title": "Sensitive-field handling matters",
                "detail": "Backup and API workflows that expect secrets to appear automatically can break on RouterOS v7.",
            })
            proposed_changes.append({
                "kind": "preflight_only",
                "change": "Verify Oxidized, Unimus, Ansible, Terraform, or custom API reads against the post-upgrade device.",
                "why": "v7 export and API reads hide sensitive fields by default unless the workflow accounts for it.",
            })

        if "/interface bridge" in export_text and "vlan-filtering=yes" in export_text:
            findings.append({
                "severity": "low",
                "title": "No obvious bridge/VLAN syntax blocker",
                "detail": "The bridge and VLAN layout looks normal for a RouterOS 7 CCR2004 upgrade and does not suggest a mandatory config rewrite.",
            })

        if not proposed_changes:
            proposed_changes.append({
                "kind": "no_config_delta",
                "change": "No mandatory config rewrite is apparent from the current export.",
                "why": "The main work here is upgrade preflight and post-upgrade verification, not a config conversion.",
            })

        if not preflight_steps:
            preflight_steps.extend(
                [
                    "Take a fresh `/export show-sensitive` and a binary backup.",
                    "Verify the current ROS version and RouterBOARD firmware state.",
                    f"Validate one controlled reboot path before committing to the {target_version} maintenance window.",
                ]
            )

        return {
            "target_version": target_version,
            "current_version": current_version,
            "model": model,
            "findings": findings,
            "proposed_changes": proposed_changes,
            "preflight_steps": preflight_steps,
        }

    def review_live_upgrade_risk(self, site_id: str | None = None, device_name: str | None = None, target_version: str = "7.22.1") -> dict[str, Any]:
        export_payload = self.get_live_routeros_export(site_id=site_id, device_name=device_name, show_sensitive=True, terse=True)
        baseline = export_payload.get("baseline") or self._live_routeros_baseline(site_id=site_id, device_name=device_name)
        resource = (baseline or {}).get("resource") or {}
        routerboard = (baseline or {}).get("routerboard") or {}
        model = export_payload.get("model") or resource.get("board-name") or resource.get("platform")
        current_version = resource.get("version") or resource.get("build-time") or None
        audit = self._audit_upgrade_risk(
            str(export_payload.get("text") or ""),
            target_version=target_version,
            model=str(model or ""),
            current_version=current_version,
        )
        return {
            "available": bool(export_payload.get("available")),
            "site_id": export_payload.get("site_id") or (canonical_scope(site_id) if site_id else None),
            "device_name": export_payload.get("device_name") or (canonical_identity(device_name) if device_name else (f"{canonical_scope(site_id)}.R1" if site_id else None)),
            "target_version": target_version,
            "current_version": current_version,
            "model": model,
            "routerboard": routerboard,
            "export_source": export_payload.get("source"),
            "export_path": export_payload.get("path"),
            "live_read": export_payload.get("live_read"),
            "audit": audit,
        }

    def generate_upgrade_preflight_plan(self, site_id: str | None = None, device_name: str | None = None, target_version: str = "7.22.1") -> dict[str, Any]:
        review = self.review_live_upgrade_risk(site_id=site_id, device_name=device_name, target_version=target_version)
        audit = review.get("audit") or {}
        plan_steps: list[dict[str, Any]] = []
        for idx, step in enumerate(audit.get("preflight_steps") or [], start=1):
            plan_steps.append({"step": idx, "action": step})
        config_rewrites = [item for item in (audit.get("proposed_changes") or []) if item.get("kind") not in {"no_config_delta", "preflight_only"}]
        return {
            "available": bool(review.get("available")),
            "site_id": review.get("site_id"),
            "device_name": review.get("device_name"),
            "target_version": target_version,
            "current_version": review.get("current_version"),
            "model": review.get("model"),
            "required_config_changes": config_rewrites,
            "preflight_only_changes": [item for item in (audit.get("proposed_changes") or []) if item.get("kind") == "preflight_only"],
            "no_config_delta": not config_rewrites,
            "plan_steps": plan_steps,
            "findings": audit.get("findings") or [],
        }

    def render_upgrade_change_explanation(self, site_id: str | None = None, device_name: str | None = None, target_version: str = "7.22.1") -> dict[str, Any]:
        review = self.review_live_upgrade_risk(site_id=site_id, device_name=device_name, target_version=target_version)
        audit = review.get("audit") or {}
        lines = []
        lines.append(f"Upgrade review for {review.get('device_name') or review.get('site_id') or 'target device'} -> {target_version}.")
        if review.get("model"):
            lines.append(f"Model: {review.get('model')}.")
        if review.get("current_version"):
            lines.append(f"Current version: {review.get('current_version')}.")
        source = review.get("export_source")
        if source == "live_routeros_export":
            lines.append("Source: fresh live RouterOS export.")
        elif source == "local_export":
            lines.append(f"Source: local export fallback ({review.get('export_path')}).")
        changes = audit.get("proposed_changes") or []
        config_rewrites = [item for item in changes if item.get("kind") not in {"no_config_delta", "preflight_only"}]
        preflight_only = [item for item in changes if item.get("kind") == "preflight_only"]
        if config_rewrites:
            lines.append("")
            lines.append("Changes to make before the upgrade:")
            for idx, item in enumerate(config_rewrites[:5], start=1):
                lines.append(f"{idx}. {item.get('change')}")
                if item.get("why"):
                    lines.append(f"Why: {item.get('why')}")
        else:
            lines.append("")
            lines.append("No mandatory config changes are apparent from the current export.")
        if preflight_only:
            lines.append("")
            lines.append("Preflight-only changes:")
            for idx, item in enumerate(preflight_only[:5], start=1):
                lines.append(f"{idx}. {item.get('change')}")
                if item.get("why"):
                    lines.append(f"Why: {item.get('why')}")
        preflight = audit.get("preflight_steps") or []
        if preflight:
            lines.append("")
            lines.append("Preflight steps:")
            for idx, item in enumerate(preflight[:5], start=1):
                lines.append(f"{idx}. {item}")
        findings = audit.get("findings") or []
        if findings:
            lines.append("")
            lines.append("What to watch:")
            for item in findings[:5]:
                lines.append(f"- {item.get('title')}: {item.get('detail')}")
        return {
            "available": bool(review.get("available")),
            "site_id": review.get("site_id"),
            "device_name": review.get("device_name"),
            "target_version": target_version,
            "current_version": review.get("current_version"),
            "model": review.get("model"),
            "text": "\n".join(lines),
            "review": review,
        }

    def get_live_source_readiness(self) -> dict[str, Any]:
        readiness: dict[str, Any] = {
            "routeros": {"configured": False, "available": False},
            "dhcp": {"configured": False, "available": False},
            "splynx": {"configured": False, "available": False},
            "cnwave": {"configured": False, "available": False},
            "cnwave_controller": {"configured": False, "available": False},
            "olt": {"configured": False, "available": False},
            "syslog": {"configured": True, "available": False},
        }

        try:
            if SSH_MCP_ROOT.exists():
                import sqlite3

                db_path = SSH_MCP_ROOT / "data" / "ssh_mcp.sqlite3"
                device_count = 0
                mikrotik_count = 0
                if db_path.exists():
                    with sqlite3.connect(db_path) as conn:
                        cur = conn.cursor()
                        device_count = int(cur.execute("select count(*) from devices").fetchone()[0] or 0)
                        mikrotik_count = int(cur.execute("select count(*) from devices where vendor='MikroTik'").fetchone()[0] or 0)
                readiness["routeros"] = {
                    "configured": True,
                    "available": bool(_ssh_mcp_password()) and mikrotik_count > 0,
                    "device_count": device_count,
                    "mikrotik_count": mikrotik_count,
                    "password_present": bool(_ssh_mcp_password()),
                    "db_path": str(db_path),
                }
        except Exception as exc:
            readiness["routeros"] = {"configured": True, "available": False, "error": str(exc)}

        dhcp = self.get_live_dhcp_lease_summary(limit=1)
        readiness["dhcp"] = {
            "configured": bool((dhcp.get("lynxmsp_status") or {}).get("db", {}).get("configured")) or bool((dhcp.get("lynxmsp_status") or {}).get("api", {}).get("configured")),
            "available": bool(dhcp.get("available")),
            "source": dhcp.get("source"),
            "api_detail": dhcp.get("api_detail"),
            "db_path": ((dhcp.get("lynxmsp_status") or {}).get("db") or {}).get("path"),
        }

        splynx = self.get_live_splynx_online_summary(limit=1)
        readiness["splynx"] = {
            "configured": bool(splynx.get("configured")),
            "available": bool(splynx.get("available")),
            "source": splynx.get("source"),
            "detail": splynx.get("detail"),
        }

        cnwave = self.get_live_cnwave_rf_summary(limit=1)
        cnwave_metric_rows = cnwave.get("metric_row_count")
        if cnwave_metric_rows is None:
            cnwave_metric_rows = cnwave.get("link_count", 0)
        readiness["cnwave"] = {
            "configured": bool(cnwave.get("configured")),
            "available": bool(cnwave.get("available")),
            "metric_row_count": cnwave_metric_rows,
        }
        controller = self.cnwave_controller.diagnostics() if self.cnwave_controller else {"configured": False}
        readiness["cnwave_controller"] = {
            "configured": bool(controller.get("configured")),
            "available": bool(controller.get("remote_neighbors_ready")),
            "base_url": controller.get("base_url"),
            "missing": controller.get("missing") or [],
        }

        readiness["olt"] = {
            "configured": bool(_olt_telnet_password()),
            "available": bool(_olt_telnet_password()) and OLT_TELNET_READ_SCRIPT.exists(),
            "script_present": OLT_TELNET_READ_SCRIPT.exists(),
        }

        syslog_events = load_syslog_events()
        site_counts: dict[str, int] = {}
        for row in syslog_events:
            site = canonical_scope(row.get("site_id"))
            if site:
                site_counts[site] = site_counts.get(site, 0) + 1
        readiness["syslog"] = {
            "configured": True,
            "available": bool(syslog_events),
            "event_count": len(syslog_events),
            "site_scoped_sites": len(site_counts),
            "top_sites": sorted(site_counts.items(), key=lambda item: (-item[1], item[0]))[:10],
            "path": str(ARTIFACT_SYSLOG_DIR),
        }
        return readiness

    def diagnose_lynxmsp_wiring(self) -> dict[str, Any]:
        db_candidates = [str(path) for path in LYNXMSP_DB_CANDIDATES if path]
        api_candidates = [str(url) for url in LYNXMSP_API_CANDIDATES if url]
        state_candidates = [str(path) for path in LYNXDHCP_STATE_CANDIDATES if path]
        status = lynxmsp_source_status()
        db_path = find_lynxmsp_db_path()
        state_path = find_lynxdhcp_state_path()

        blockers: list[str] = []
        recommended_actions: list[str] = []
        if not db_path:
            blockers.append("No local LynxMSP database path is available on this host.")
            recommended_actions.append("Set LYNXMSP_DB_PATH to a real lynxcrm.db if you want local DB-backed DHCP/customer joins.")
        elif not bool(((status.get("db") or {}).get("table_counts") or {}).get("dhcp_leases")):
            blockers.append("Resolved LynxMSP database is present but the DHCP/customer tables are empty.")
            recommended_actions.append("Refresh or repoint the LynxMSP database if you want DB-backed live DHCP correlation.")
        if not state_path:
            blockers.append("No local lynxdhcp state.json snapshot is available on this host.")
            recommended_actions.append("Set LYNXDHCP_STATE_PATH to a real lynxdhcp state.json if you want snapshot-based relay and subscriber evidence.")
        if not os.environ.get("LYNXMSP_API_URL"):
            blockers.append("LYNXMSP_API_URL is not explicitly set, so Jake falls back to generic localhost candidates.")
            recommended_actions.append("Set LYNXMSP_API_URL to the real LynxMSP backend base URL to avoid dead localhost fallback.")
        api = status.get("api") or {}
        if api.get("configured") and not api.get("available"):
            blockers.append(f"LynxMSP API probe failed at {api.get('base_url')}: {api.get('detail')}.")
            recommended_actions.append("Start the LynxMSP backend on the configured base URL or point LYNXMSP_API_URL at the reachable backend.")

        return {
            "db_candidates": db_candidates,
            "api_candidates": api_candidates,
            "state_candidates": state_candidates,
            "resolved_db_path": str(db_path) if db_path else None,
            "resolved_state_path": str(state_path) if state_path else None,
            "status": status,
            "env": {
                "LYNXMSP_API_URL": os.environ.get("LYNXMSP_API_URL"),
                "LYNXMSP_DB_PATH": os.environ.get("LYNXMSP_DB_PATH"),
                "LYNXDHCP_STATE_PATH": os.environ.get("LYNXDHCP_STATE_PATH"),
            },
            "blockers": blockers,
            "recommended_actions": recommended_actions,
        }

    def _resolve_live_routeros_api_target(self, site_id: str | None = None, device_name: str | None = None) -> dict[str, Any]:
        target_identity = canonical_identity(device_name) if device_name else None
        target_site = canonical_scope(site_id) if site_id else None
        target_ip = None

        if not target_identity and target_site:
            candidates = self._recent_site_router_candidates(target_site)
            if candidates:
                target_identity = candidates[0]["identity"]
                target_ip = candidates[0]["ip"]

        if target_identity and not target_ip:
            scan_id = self.latest_scan_id()
            row = self.db.execute(
                "select ip from devices where scan_id=? and identity=? order by ip limit 1",
                (scan_id, target_identity),
            ).fetchone()
            if row and row[0]:
                target_ip = str(row[0])

        return {
            "site_id": target_site,
            "device_name": target_identity,
            "target_ip": target_ip,
            "available": bool(target_identity and target_ip),
        }

    @staticmethod
    def _routeros_api_row_to_text(row: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for key, value in row.items():
            clean[key] = value.decode(errors="ignore") if isinstance(value, bytes) else value
        return clean

    def _connect_live_routeros_api(self, site_id: str | None = None, device_name: str | None = None) -> tuple[Any | None, dict[str, Any]]:
        try:
            from librouteros import connect
        except Exception as exc:
            return None, {"available": False, "configured": False, "error": f"librouteros import failed: {exc}"}

        user = _ssh_mcp_username()
        password = _ssh_mcp_password()
        if not user or not password:
            return None, {"available": False, "configured": False, "error": "RouterOS API username/password are not configured in env."}

        target = self._resolve_live_routeros_api_target(site_id, device_name)
        if not target.get("available"):
            target["configured"] = True
            target["error"] = "Could not resolve a live RouterOS target for this read."
            return None, target

        try:
            api = connect(host=target["target_ip"], username=user, password=password, port=8728, timeout=8)
        except Exception as exc:
            target["configured"] = True
            target["available"] = False
            target["error"] = str(exc)
            return None, target

        try:
            for row in api.path("system", "identity").select("name"):
                clean = self._routeros_api_row_to_text(row)
                if clean.get("name"):
                    target["device_name"] = clean["name"]
                    break
        except Exception:
            pass
        target["configured"] = True
        target["available"] = True
        return api, target

    def get_live_rogue_dhcp_scan(self, site_id: str | None = None, device_name: str | None = None, interface: str | None = None, seconds: int = 5, mac: str | None = None) -> dict[str, Any]:
        try:
            from librouteros import connect
        except Exception as exc:
            return {"available": False, "configured": False, "error": f"librouteros import failed: {exc}"}

        user = _ssh_mcp_username()
        password = _ssh_mcp_password()
        if not user or not password:
            return {"available": False, "configured": False, "error": "RouterOS API username/password are not configured in env."}

        target_identity = canonical_identity(device_name) if device_name else None
        target_site = canonical_scope(site_id) if site_id else None
        target_ip = None

        if not target_identity and target_site:
            candidates = self._recent_site_router_candidates(target_site)
            if len(candidates) == 1:
                target_identity = candidates[0]["identity"]
                target_ip = candidates[0]["ip"]
            elif len(candidates) > 1:
                target_identity = candidates[0]["identity"]
                target_ip = candidates[0]["ip"]

        if target_identity and not target_ip:
            scan_id = self.latest_scan_id()
            row = self.db.execute(
                "select ip from devices where scan_id=? and identity=? order by ip limit 1",
                (scan_id, target_identity),
            ).fetchone()
            if row and row[0]:
                target_ip = str(row[0])

        if not target_identity or not target_ip:
            return {
                "available": False,
                "configured": True,
                "site_id": target_site,
                "device_name": target_identity,
                "error": "Could not resolve a live RouterOS target for this rogue-DHCP scan.",
            }

        interface_name = str(interface or "all").strip()
        duration = max(2, min(int(seconds or 5), 10))
        mac_filter = norm_mac(mac) if mac else None
        try:
            api = connect(host=target_ip, username=user, password=password, port=8728, timeout=8)
            identity = target_identity
            try:
                for row in api.path("system", "identity").select("name"):
                    identity = row.get("name")
                    if isinstance(identity, bytes):
                        identity = identity.decode(errors="ignore")
                    break
            except Exception:
                pass

            try:
                list(api.rawCmd("/tool/sniffer/stop"))
            except Exception:
                pass

            set_args = ["/tool/sniffer/set", "=filter-direction=any"]
            if interface_name.lower() not in {"", "all", "*", "any"}:
                set_args.append(f"=filter-interface={interface_name}")
            if mac_filter:
                set_args.append(f"=filter-mac-address={mac_filter}")
            list(api.rawCmd(*set_args))

            rows: list[dict[str, Any]] = []
            for i, raw in enumerate(api.rawCmd("/tool/sniffer/quick", f"=duration={duration}s")):
                item = {
                    "interface": raw.get("interface"),
                    "dir": raw.get("dir"),
                    "src-mac": raw.get("src-mac"),
                    "dst-mac": raw.get("dst-mac"),
                    "protocol": raw.get("protocol"),
                    "src-address": raw.get("src-address"),
                    "dst-address": raw.get("dst-address"),
                    "src-port": raw.get("src-port"),
                    "dst-port": raw.get("dst-port"),
                    "ip-protocol": raw.get("ip-protocol"),
                }
                clean = {}
                for key, value in item.items():
                    if isinstance(value, bytes):
                        clean[key] = value.decode(errors="ignore")
                    else:
                        clean[key] = value
                rows.append(clean)
                if i >= 500:
                    break
            try:
                list(api.rawCmd("/tool/sniffer/stop"))
            except Exception:
                pass
        except Exception as exc:
            return {
                "available": False,
                "configured": True,
                "site_id": target_site,
                "device_name": target_identity,
                "device_ip": target_ip,
                "error": str(exc),
            }

        dhcp_rows = [
            row for row in rows
            if str(row.get("src-port") or "") in {"67", "68"}
            or str(row.get("dst-port") or "") in {"67", "68"}
            or "bootp" in str(row.get("protocol") or "").lower()
            or "dhcp" in str(row.get("protocol") or "").lower()
        ]
        talkers = Counter()
        offers = []
        broadcasts = 0
        for row in dhcp_rows:
            src_mac = norm_mac(str(row.get("src-mac") or "")) or str(row.get("src-mac") or "").lower()
            dst_mac = norm_mac(str(row.get("dst-mac") or "")) or str(row.get("dst-mac") or "").lower()
            if src_mac:
                talkers[src_mac] += 1
            if dst_mac == "ff:ff:ff:ff:ff:ff":
                broadcasts += 1
            if str(row.get("src-port") or "") == "67":
                offers.append(row)

        return {
            "available": True,
            "configured": True,
            "site_id": target_site,
            "device_name": target_identity,
            "device_ip": target_ip,
            "interface": interface_name,
            "seconds": duration,
            "mac_filter": mac_filter,
            "packet_count": len(rows),
            "dhcp_packet_count": len(dhcp_rows),
            "broadcast_count": broadcasts,
            "dhcp_talkers": [{"mac": mac_addr, "packets": count} for mac_addr, count in talkers.most_common(10)],
            "offer_like_packet_count": len(offers),
            "sample": dhcp_rows[:50],
        }

    @staticmethod
    def _joined_routeros_stdout(payload: dict[str, Any] | None) -> str:
        parts = [str(item.get("stdout") or "").strip() for item in list((payload or {}).get("results") or []) if str(item.get("stdout") or "").strip()]
        return "\n".join(part for part in parts if part).strip()

    @staticmethod
    def _parse_routeros_kv_text(text: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            normalized = re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")
            if normalized:
                out[normalized] = value.strip()
        return out

    @staticmethod
    def _normalize_routeros_speed(value: str | None) -> str | None:
        text = str(value or "").strip().lower()
        if not text:
            return None
        if "10g" in text or "10000" in text:
            return "10G"
        if "1g" in text or "1000" in text:
            return "1G"
        if "100m" in text or text == "100" or "100base" in text:
            return "100M"
        if "10m" in text or text == "10":
            return "10M"
        return str(value or "").strip() or None

    @staticmethod
    def _parse_intish(value: Any) -> int | None:
        text = str(value or "").strip()
        if not text:
            return None
        match = re.search(r"-?\d+", text.replace(",", ""))
        if not match:
            return None
        try:
            return int(match.group(0))
        except ValueError:
            return None

    @classmethod
    def _parse_port_physical_state_outputs(cls, monitor_text: str, stats_text: str) -> dict[str, Any]:
        monitor = cls._parse_routeros_kv_text(monitor_text)
        stats = cls._parse_routeros_kv_text(stats_text)
        rx_errors = cls._parse_intish(stats.get("rx_error") or stats.get("rx_errors"))
        tx_errors = cls._parse_intish(stats.get("tx_error") or stats.get("tx_errors"))
        fcs_errors = cls._parse_intish(stats.get("fcs_error") or stats.get("fcs_errors"))
        crc_errors = cls._parse_intish(stats.get("rx_fcs_error") or stats.get("crc_error") or stats.get("crc_errors"))
        link_flaps = cls._parse_intish(
            monitor.get("link_downs")
            or monitor.get("link_ups")
            or stats.get("link_downs")
            or stats.get("link_flaps")
        )
        running = str(monitor.get("status") or monitor.get("running") or "").strip().lower()
        rate = monitor.get("rate") or monitor.get("speed")
        if not rate:
            rate = monitor.get("sfp_rate")
        return {
            "port_speed": cls._normalize_routeros_speed(rate),
            "link_partner_speed": cls._normalize_routeros_speed(
                monitor.get("link_partner_advertising")
                or monitor.get("link_partner_speed")
                or monitor.get("advertised_speed")
            ),
            "port_duplex": (
                "full"
                if any(token in str(monitor.get("full_duplex") or monitor.get("duplex") or "").lower() for token in ("full", "yes", "true"))
                else "half" if "half" in str(monitor.get("full_duplex") or monitor.get("duplex") or "").lower() else None
            ),
            "link_partner_duplex": (
                "full"
                if "full" in str(monitor.get("link_partner_advertising") or monitor.get("link_partner_duplex") or "").lower()
                else "half" if "half" in str(monitor.get("link_partner_advertising") or monitor.get("link_partner_duplex") or "").lower() else None
            ),
            "rx_errors": rx_errors,
            "tx_errors": tx_errors,
            "fcs_errors": fcs_errors,
            "crc_errors": crc_errors,
            "link_flaps": link_flaps,
            "link_flaps_window_seconds": 900 if link_flaps is not None else None,
            "port_up": True if running in {"link-ok", "running", "up"} else False if running in {"no-link", "down", "stopped"} else None,
        }

    def get_port_physical_state(self, interface: str, site_id: str | None = None, device_name: str | None = None) -> dict[str, Any]:
        target = self._resolve_live_routeros_api_target(site_id=site_id, device_name=device_name)
        resolved_device = canonical_identity(target.get("device_name") or device_name)
        result = {
            "available": False,
            "configured": bool(target.get("configured")),
            "site_id": canonical_scope(site_id) if site_id else target.get("site_id"),
            "device_name": resolved_device or None,
            "interface": str(interface or "").strip(),
            "port_speed": None,
            "link_partner_speed": None,
            "port_duplex": None,
            "link_partner_duplex": None,
            "rx_errors": None,
            "tx_errors": None,
            "fcs_errors": None,
            "crc_errors": None,
            "link_flaps": None,
            "link_flaps_window_seconds": None,
            "port_up": None,
        }
        if not resolved_device:
            result["error"] = str(target.get("error") or "No live RouterOS target could be resolved.")
            return result
        iface = str(interface or "").strip()
        monitor_cmd = f'/interface ethernet monitor [find where name="{iface}"] once without-paging'
        stats_cmd = f'/interface ethernet print stats without-paging where name="{iface}"'
        monitor_read = self._run_live_routeros_show_command(resolved_device, monitor_cmd, reason=f"Collect physical state for {iface}.", risk="low")
        stats_read = self._run_live_routeros_show_command(resolved_device, stats_cmd, reason=f"Collect interface counters for {iface}.", risk="low")
        if not monitor_read.get("available") and not stats_read.get("available"):
            result["error"] = str(monitor_read.get("error") or stats_read.get("error") or "Live port physical reads failed.")
            return result
        parsed = self._parse_port_physical_state_outputs(
            self._joined_routeros_stdout(monitor_read),
            self._joined_routeros_stdout(stats_read),
        )
        result.update(parsed)
        result["available"] = True
        result["monitor_read"] = monitor_read
        result["stats_read"] = stats_read
        return result

    def _get_interface_state_via_api(self, interface: str, site_id: str | None = None, device_name: str | None = None) -> dict[str, Any]:
        api, target = self._connect_live_routeros_api(site_id=site_id, device_name=device_name)
        result = {
            "available": False,
            "configured": bool(target.get("configured")),
            "site_id": canonical_scope(site_id) if site_id else target.get("site_id"),
            "device_name": canonical_identity(target.get("device_name") or device_name) or None,
            "interface": str(interface or "").strip(),
            "port_speed": None,
            "link_partner_speed": None,
            "port_duplex": None,
            "link_partner_duplex": None,
            "rx_errors": None,
            "tx_errors": None,
            "fcs_errors": None,
            "crc_errors": None,
            "link_flaps": None,
            "link_flaps_window_seconds": None,
            "port_up": None,
            "source": "routeros_api",
        }
        if api is None:
            result["error"] = str(target.get("error") or "RouterOS API unavailable.")
            return result
        iface = str(interface or "").strip()
        try:
            rows = [self._routeros_api_row_to_text(row) for row in api.path("interface", "ethernet").select()]
        except Exception as exc:
            result["error"] = f"RouterOS API interface read failed: {exc}"
            return result
        row = next((item for item in rows if str(item.get("name") or "").strip() == iface), None)
        if not row:
            result["error"] = f"Interface {iface} was not returned by RouterOS API."
            return result
        running = row.get("running")
        disabled = row.get("disabled")
        result["port_up"] = bool(running) if running is not None else False if disabled else None
        result["port_speed"] = self._normalize_routeros_speed(row.get("rate") or row.get("speed") or row.get("actual-speed"))
        result["link_partner_speed"] = self._normalize_routeros_speed(row.get("link-partner-speed") or row.get("advertising"))
        duplex = str(row.get("duplex") or row.get("full-duplex") or "").lower()
        if duplex:
            result["port_duplex"] = "full" if "full" in duplex or duplex in {"true", "yes"} else "half" if "half" in duplex else None
        result["available"] = True
        result["api_row"] = row
        return result

    def _get_cached_interface_state(self, interface: str, site_id: str | None = None, device_name: str | None = None) -> dict[str, Any]:
        target = self._resolve_live_routeros_api_target(site_id=site_id, device_name=device_name)
        resolved_device = canonical_identity(target.get("device_name") or device_name)
        result = {
            "available": False,
            "configured": True,
            "site_id": canonical_scope(site_id) if site_id else target.get("site_id"),
            "device_name": resolved_device or None,
            "interface": str(interface or "").strip(),
            "port_speed": None,
            "link_partner_speed": None,
            "port_duplex": None,
            "link_partner_duplex": None,
            "rx_errors": None,
            "tx_errors": None,
            "fcs_errors": None,
            "crc_errors": None,
            "link_flaps": None,
            "link_flaps_window_seconds": None,
            "port_up": None,
            "source": "db_cached_interface_state",
        }
        if not resolved_device:
            result["error"] = str(target.get("error") or "No device resolved for cached interface lookup.")
            return result
        scan_id = self.latest_scan_id()
        row = self.db.execute(
            """
            select d.identity, i.name, i.running, i.disabled, i.rx_byte, i.tx_byte, i.rx_packet, i.tx_packet, i.last_link_up_time
            from interfaces i
            left join devices d on d.scan_id=i.scan_id and d.ip=i.ip
            where i.scan_id=? and d.identity=? and i.name=?
            limit 1
            """,
            (scan_id, resolved_device, str(interface or "").strip()),
        ).fetchone()
        if not row:
            result["error"] = f"No cached interface row found for {resolved_device} {interface} in scan {scan_id}."
            return result
        row_dict = dict(row)
        running = row_dict.get("running")
        disabled = row_dict.get("disabled")
        result["port_up"] = bool(running) if running is not None else False if disabled else None
        result["cached_rx_byte"] = row_dict.get("rx_byte")
        result["cached_tx_byte"] = row_dict.get("tx_byte")
        result["cached_rx_packet"] = row_dict.get("rx_packet")
        result["cached_tx_packet"] = row_dict.get("tx_packet")
        result["cached_last_link_up_time"] = row_dict.get("last_link_up_time")
        result["available"] = True
        return result

    def get_interface_state(self, interface: str, site_id: str | None = None, device_name: str | None = None) -> dict[str, Any]:
        ssh_result = self.get_port_physical_state(interface=interface, site_id=site_id, device_name=device_name)
        if ssh_result.get("available"):
            ssh_result["source"] = "routeros_ssh"
            return ssh_result

        api_result = self._get_interface_state_via_api(interface=interface, site_id=site_id, device_name=device_name)
        if api_result.get("available"):
            api_result["fallback_from"] = ssh_result.get("error")
            return api_result

        db_result = self._get_cached_interface_state(interface=interface, site_id=site_id, device_name=device_name)
        if db_result.get("available"):
            db_result["fallback_from"] = {
                "ssh": ssh_result.get("error"),
                "api": api_result.get("error"),
            }
            return db_result

        return {
            "available": False,
            "configured": bool(ssh_result.get("configured") or api_result.get("configured") or db_result.get("configured")),
            "site_id": canonical_scope(site_id) if site_id else ssh_result.get("site_id") or api_result.get("site_id") or db_result.get("site_id"),
            "device_name": canonical_identity(device_name) if device_name else ssh_result.get("device_name") or api_result.get("device_name") or db_result.get("device_name"),
            "interface": str(interface or "").strip(),
            "error": " ; ".join(
                part for part in [
                    str(ssh_result.get("error") or "").strip(),
                    str(api_result.get("error") or "").strip(),
                    str(db_result.get("error") or "").strip(),
                ] if part
            ) or "No L1 source returned interface state.",
            "sources_tried": ["routeros_ssh", "routeros_api", "db_cached_interface_state"],
        }

    @staticmethod
    def _resolve_unit_row(unit: str) -> dict[str, Any] | None:
        target = str(unit or "").strip().upper()
        if not target:
            return None
        canonical_target = re.sub(r"\s+", "", target.replace("UNIT", ""))
        for row in load_nycha_info_rows():
            unit_token = re.sub(r"\s+", "", str(parse_unit_token(row.get("Unit")) or "").upper().replace("UNIT", ""))
            pppoe_token = str(row.get("PPPoE") or "").strip()
            if unit_token and unit_token == canonical_target:
                return row
            if pppoe_token and pppoe_token.upper() == target:
                return row
        return None

    @staticmethod
    def _infer_pppoe_failure_reason(text: str) -> str | None:
        lowered = str(text or "").lower()
        if any(token in lowered for token in ("authentication failed", "auth fail", "radius reject", "invalid password")):
            return "auth_failed"
        if any(token in lowered for token in ("timed out", "timeout", "waiting for pado", "waiting for pads")):
            return "timeout"
        if any(token in lowered for token in ("no response", "no pado", "no pads", "no offer from server")):
            return "no_response"
        return None

    def get_pppoe_diagnostics(self, unit: str, site_id: str | None = None) -> dict[str, Any]:
        unit_row = self._resolve_unit_row(unit)
        network_name = str((unit_row or {}).get("PPPoE") or "").strip()
        effective_site = canonical_scope(site_id) if site_id else None
        if not effective_site and unit_row:
            resolved = self._resolve_building_from_address(str(unit_row.get("Address") or ""))
            best = (resolved or {}).get("best_match") or {}
            effective_site = canonical_scope(best.get("site_code") or str(best.get("prefix") or "").split(".", 1)[0])

        result = {
            "unit": unit,
            "site_id": effective_site,
            "network_name": network_name or None,
            "pppoe_active": False,
            "pppoe_failed_attempts_seen": None,
            "pppoe_failure_reason": None,
            "pppoe_last_attempt_timestamp": None,
            "available": False,
        }
        if network_name:
            active = self.db.execute(
                "select name, caller_id, uptime from router_ppp_active where lower(name)=lower(?) order by uptime desc",
                (network_name,),
            ).fetchall()
            if active:
                result["pppoe_active"] = True
        if not effective_site or not self._loki_base_url():
            result["available"] = bool(network_name)
            return result
        query_terms = [re.escape(network_name)] if network_name else []
        if unit:
            query_terms.append(re.escape(str(unit)))
        if not query_terms:
            return result
        query = f'{{host=~"{effective_site}.*"}} !~ "mktxp_user" |~ "(?i)pppoe|{"|".join(query_terms)}"'
        end_ns = int(time.time() * 1_000_000_000)
        start_ns = end_ns - 60 * 60 * 1_000_000_000
        ok, streams, detail = self._loki_query_range(query, start_ns=start_ns, end_ns=end_ns, limit=200)
        if not ok:
            result["error"] = detail
            return result
        entries = self._loki_normalize_entries(streams, limit=200)
        filtered = []
        for row in entries:
            line = str(row.get("line") or "")
            lowered = line.lower()
            if "pppoe" not in lowered:
                continue
            if network_name and network_name.lower() not in lowered and str(unit).lower() not in lowered:
                continue
            filtered.append(row)
        failures = []
        for row in filtered:
            reason = self._infer_pppoe_failure_reason(str(row.get("line") or ""))
            if reason:
                failures.append((row, reason))
        result["available"] = True
        if failures:
            result["pppoe_failed_attempts_seen"] = True
            result["pppoe_failure_reason"] = failures[-1][1]
            result["pppoe_last_attempt_timestamp"] = str(failures[-1][0].get("timestamp") or "") or None
        elif filtered:
            result["pppoe_failed_attempts_seen"] = False
            result["pppoe_last_attempt_timestamp"] = str(filtered[-1].get("timestamp") or "") or None
        else:
            result["pppoe_failed_attempts_seen"] = False
        return result

    def get_pppoe_logs_for_site(self, site_id: str) -> dict[str, Any]:
        target_site = canonical_scope(site_id)
        result: dict[str, Any] = {
            "site_id": target_site,
            "available": False,
            "searched": False,
            "active_sessions_by_name": {},
            "observations_by_name": {},
        }
        if not target_site:
            result["error"] = "site_id is required"
            return result

        try:
            active_rows = [
                dict(r)
                for r in self.db.execute(
                    """
                    select p.name, p.caller_id, p.address, p.uptime
                    from router_ppp_active p
                    left join devices d on d.scan_id=p.scan_id and d.ip=p.router_ip
                    where p.scan_id=? and d.identity like ?
                    order by p.name
                    """,
                    (self.latest_scan_id(), f"{target_site}%"),
                ).fetchall()
            ]
        except Exception as exc:
            active_rows = []
            result["active_sessions_error"] = str(exc)

        for row in active_rows:
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            result["active_sessions_by_name"][name.lower()] = {
                "pppoe_active": True,
                "pppoe_last_attempt_timestamp": None,
                "pppoe_failure_reason": None,
                "pppoe_failed_attempts_seen": False,
                "pppoe_no_attempt_evidence": False,
                "caller_id": norm_mac(row.get("caller_id") or "") or None,
                "address": str(row.get("address") or "").strip() or None,
                "uptime": str(row.get("uptime") or "").strip() or None,
                "evidence_sources": ["router_pppoe_session"],
            }

        if not self._loki_base_url():
            result["available"] = bool(result["active_sessions_by_name"])
            result["error"] = "Loki base URL is not configured."
            return result

        query = f'{{host=~"{target_site}.*"}} !~ "mktxp_user" |~ "(?i)pppoe"'
        end_ns = int(time.time() * 1_000_000_000)
        start_ns = end_ns - 60 * 60 * 1_000_000_000
        ok, streams, detail = self._loki_query_range(query, start_ns=start_ns, end_ns=end_ns, limit=1000)
        if not ok:
            result["error"] = detail
            return result

        result["searched"] = True
        result["available"] = True
        entries = self._loki_normalize_entries(streams, limit=1000)
        observations_by_name: dict[str, dict[str, Any]] = {}

        inventory_names: set[str] = set()
        for row in load_nycha_info_rows():
            resolved = self._resolve_building_from_address(str(row.get("Address") or ""))
            best = (resolved or {}).get("best_match") or {}
            row_site = canonical_scope(best.get("site_code") or str(best.get("prefix") or "").split(".", 1)[0])
            if row_site != target_site:
                continue
            network_name = str(row.get("PPPoE") or "").strip()
            if network_name:
                inventory_names.add(network_name.lower())

        for row in entries:
            line = str(row.get("line") or "")
            lowered = line.lower()
            if "pppoe" not in lowered:
                continue
            matched_name = next((name for name in inventory_names if name and name in lowered), None)
            if not matched_name:
                continue
            bucket = observations_by_name.setdefault(
                matched_name,
                {
                    "pppoe_active": False,
                    "pppoe_failed_attempts_seen": False,
                    "pppoe_failure_reason": None,
                    "pppoe_last_attempt_timestamp": None,
                    "pppoe_no_attempt_evidence": False,
                    "evidence_sources": ["pppoe_site_logs"],
                },
            )
            bucket["pppoe_last_attempt_timestamp"] = str(row.get("timestamp") or "") or bucket.get("pppoe_last_attempt_timestamp")
            reason = self._infer_pppoe_failure_reason(line)
            if reason:
                bucket["pppoe_failed_attempts_seen"] = True
                bucket["pppoe_failure_reason"] = reason

        for name, active in dict(result["active_sessions_by_name"]).items():
            bucket = observations_by_name.setdefault(
                name,
                {
                    "pppoe_active": False,
                    "pppoe_failed_attempts_seen": False,
                    "pppoe_failure_reason": None,
                    "pppoe_last_attempt_timestamp": None,
                    "pppoe_no_attempt_evidence": False,
                    "evidence_sources": [],
                },
            )
            bucket["pppoe_active"] = True
            for source in list(active.get("evidence_sources") or []):
                if source not in bucket["evidence_sources"]:
                    bucket["evidence_sources"].append(source)

        result["observations_by_name"] = observations_by_name
        return result

    def get_historical_mac_locations(
        self,
        mac: str,
        *,
        building_id: str | None = None,
        site_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        normalized_mac = norm_mac(mac or "")
        result = {
            "mac": normalized_mac or None,
            "checked": False,
            "available": False,
            "locations": [],
        }
        if not normalized_mac:
            result["error"] = "mac is required"
            return result
        prefix = canonical_scope(building_id) if building_id else canonical_scope(site_id)
        query = """
            select bh.scan_id, d.identity, bh.on_interface, bh.vid, bh.mac
            from bridge_hosts bh
            left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
            where lower(bh.mac)=lower(?) and bh.local=0 and bh.on_interface like 'ether%'
        """
        params: list[Any] = [normalized_mac]
        if prefix:
            query += " and d.identity like ?"
            params.append(f"{prefix}%")
        query += " order by bh.scan_id desc, d.identity, bh.on_interface limit ?"
        params.append(int(limit))
        try:
            rows = [dict(r) for r in self.db.execute(query, params).fetchall()]
        except Exception as exc:
            result["checked"] = True
            result["error"] = str(exc)
            return result
        result["checked"] = True
        result["available"] = True
        result["locations"] = [
            {
                "mac": normalized_mac,
                "switch": canonical_identity(row.get("identity")) or None,
                "port": str(row.get("on_interface") or "").strip() or None,
                "vlan": str(row.get("vid") or "").strip() or None,
                "scan_id": int(row.get("scan_id") or 0) or None,
                "source": "historical_bridge_hosts",
            }
            for row in rows
        ]
        return result

    def get_dhcp_behavior(
        self,
        unit: str,
        site_id: str | None = None,
        device_name: str | None = None,
        interface: str | None = None,
        mac: str | None = None,
    ) -> dict[str, Any]:
        unit_row = self._resolve_unit_row(unit)
        effective_site = canonical_scope(site_id) if site_id else None
        if not effective_site and unit_row:
            resolved = self._resolve_building_from_address(str(unit_row.get("Address") or ""))
            best = (resolved or {}).get("best_match") or {}
            effective_site = canonical_scope(best.get("site_code") or str(best.get("prefix") or "").split(".", 1)[0])
        normalized_mac = norm_mac(mac or str((unit_row or {}).get("MAC Address") or ""))
        lease = self.get_live_dhcp_lease_summary(site_id=effective_site, mac=normalized_mac or None, limit=5) if effective_site else {"available": False}
        rogue = self.get_live_rogue_dhcp_scan(site_id=effective_site, device_name=device_name, interface=interface, seconds=5, mac=normalized_mac or None) if (effective_site or device_name) else {"available": False}
        correlation = self._auto_correlate_dhcp_logs(normalized_mac, effective_site, window_minutes=60) if (effective_site and normalized_mac and self._loki_base_url()) else {"found": False, "request_count": 0}
        offer_source = None
        sample = list((rogue.get("sample") or []))
        for row in sample:
            line = str(row.get("line") or row)
            match = re.search(r"(?:server|src(?:-address)?)[= :]+(\d+\.\d+\.\d+\.\d+)", line, re.I)
            if match:
                offer_source = match.group(1)
                break
        result = {
            "unit": unit,
            "site_id": effective_site,
            "mac": normalized_mac or None,
            "dhcp_expected": True if lease.get("available") else None,
            "dhcp_discovers_seen": int(correlation.get("request_count") or 0) if correlation.get("found") else 0,
            "dhcp_offers_seen": int(rogue.get("offer_like_packet_count") or 0) if rogue.get("available") else 0,
            "dhcp_offer_source": offer_source,
            "dhcp_expected_server": None,
            "rogue_dhcp_detected": bool((rogue.get("offer_like_packet_count") or 0) > 0 and offer_source),
            "available": bool(lease.get("available") or rogue.get("available") or correlation.get("found")),
        }
        if lease.get("available") and lease.get("lease_count"):
            leases = list(lease.get("leases") or [])
            if leases:
                result["dhcp_expected_server"] = str(leases[0].get("server") or leases[0].get("relay") or "") or None
        if result["dhcp_expected_server"] and offer_source and result["dhcp_expected_server"] == offer_source:
            result["rogue_dhcp_detected"] = False
        return result

    def get_live_capsman_summary(self, site_id: str | None = None, device_name: str | None = None) -> dict[str, Any]:
        api, target = self._connect_live_routeros_api(site_id, device_name)
        if not api:
            return target

        def read_path(*parts: str) -> list[dict[str, Any]]:
            try:
                return [self._routeros_api_row_to_text(row) for row in api.path(*parts)]
            except Exception:
                return []

        capsman_manager = read_path("caps-man", "manager")
        remote_caps = read_path("caps-man", "remote-cap")
        wifi_cap = read_path("interface", "wifi", "cap")
        wifi_interfaces = read_path("interface", "wifi")
        return {
            "available": True,
            "configured": True,
            "site_id": target.get("site_id"),
            "device_name": target.get("device_name"),
            "target_ip": target.get("target_ip"),
            "capsman_manager": {
                "row_count": len(capsman_manager),
                "sample": [json.dumps(row, sort_keys=True) for row in capsman_manager[:3]],
            },
            "remote_cap_count": len(remote_caps),
            "wifi_cap": {
                "row_count": len(wifi_cap),
                "sample": [json.dumps(row, sort_keys=True) for row in wifi_cap[:3]],
            },
            "wifi_interface_count": len(wifi_interfaces),
        }

    def get_live_wifi_registration_summary(self, site_id: str | None = None, device_name: str | None = None, limit: int = 25) -> dict[str, Any]:
        api, target = self._connect_live_routeros_api(site_id, device_name)
        if not api:
            return target

        def read_path(*parts: str) -> list[dict[str, Any]]:
            try:
                return [self._routeros_api_row_to_text(row) for row in api.path(*parts)]
            except Exception:
                return []

        capsman_regs = read_path("caps-man", "registration-table")
        wifi_regs = read_path("interface", "wifi", "registration-table")
        sample_clients: list[str] = []
        for row in (capsman_regs + wifi_regs)[: max(1, int(limit or 25))]:
            mac = row.get("mac-address") or row.get("mac_address") or row.get("client-mac") or "unknown-mac"
            iface = row.get("interface") or row.get("radio-name") or row.get("name") or "unknown-iface"
            signal = row.get("signal-strength") or row.get("signal") or row.get("rx-signal") or "n/a"
            sample_clients.append(f"{mac} on {iface} signal={signal}")
        return {
            "available": True,
            "configured": True,
            "site_id": target.get("site_id"),
            "device_name": target.get("device_name"),
            "target_ip": target.get("target_ip"),
            "capsman_registration_count": len(capsman_regs),
            "wifi_registration_count": len(wifi_regs),
            "sample_clients": sample_clients[: max(1, int(limit or 25))],
        }

    def get_live_wifi_provisioning_summary(self, site_id: str | None = None, device_name: str | None = None) -> dict[str, Any]:
        api, target = self._connect_live_routeros_api(site_id, device_name)
        if not api:
            return target

        def read_path(*parts: str) -> list[dict[str, Any]]:
            try:
                return [self._routeros_api_row_to_text(row) for row in api.path(*parts)]
            except Exception:
                return []

        capsman_provisioning = read_path("caps-man", "provisioning")
        wifi_provisioning = read_path("interface", "wifi", "provisioning")
        wifi_configuration = read_path("interface", "wifi", "configuration")
        sample_rules = [json.dumps(row, sort_keys=True) for row in (capsman_provisioning[:3] + wifi_provisioning[:3] + wifi_configuration[:3])]
        return {
            "available": True,
            "configured": True,
            "site_id": target.get("site_id"),
            "device_name": target.get("device_name"),
            "target_ip": target.get("target_ip"),
            "capsman_provisioning_count": len(capsman_provisioning),
            "wifi_provisioning_count": len(wifi_provisioning),
            "wifi_configuration_count": len(wifi_configuration),
            "sample_rules": sample_rules[:9],
        }

    def _resolve_positron_target(self, device_name: str | None = None, ip: str | None = None, site_id: str | None = None) -> dict[str, Any]:
        target_name = canonical_identity(device_name) if device_name else None
        target_ip = str(ip or "").strip() or None
        target_site = canonical_scope(site_id) if site_id else None

        if target_name and not target_ip and target_name in POSITRON_IP_OVERRIDES:
            target_ip = POSITRON_IP_OVERRIDES[target_name]
            if target_name.startswith("000004."):
                target_site = target_site or "000004"

        if target_name and not target_ip:
            try:
                netbox = self.get_netbox_device(target_name)
                for row in netbox.get("devices") or []:
                    row_ip = str(row.get("primary_ip") or "").strip()
                    if row_ip:
                        target_ip = row_ip
                        target_site = target_site or canonical_scope((row.get("site") or {}).get("slug") or (row.get("site") or {}).get("name"))
                        break
            except Exception:
                pass

        if target_ip and not target_name:
            try:
                netbox = self.get_netbox_device_by_ip(target_ip)
                for row in netbox.get("devices") or []:
                    name = str(row.get("name") or "").strip()
                    role = str(row.get("role") or "").strip()
                    if name and role == "G.Hn":
                        target_name = name
                        target_site = target_site or canonical_scope((row.get("site") or {}).get("slug") or (row.get("site") or {}).get("name"))
                        break
            except Exception:
                pass

        if target_site and not (target_name and target_ip):
            try:
                for row in self._netbox_site_inventory_light(target_site):
                    if str(row.get("role") or "") != "G.Hn":
                        continue
                    name = str(row.get("name") or "").strip()
                    row_ip = str(row.get("primary_ip") or "").strip()
                    if name and row_ip:
                        target_name = target_name or name
                        target_ip = target_ip or row_ip
                        break
            except Exception:
                pass

        return {
            "site_id": target_site,
            "device_name": target_name,
            "target_ip": target_ip,
            "available": bool(target_name and target_ip),
        }

    def run_live_positron_read(self, device_name: str | None = None, ip: str | None = None, command: str | None = None) -> dict[str, Any]:
        script_path = REPO_ROOT / "scripts" / "positron_ssh_probe.exp"
        if not script_path.exists():
            return {"available": False, "configured": False, "error": "Positron probe script is not present."}

        target = self._resolve_positron_target(device_name, ip, None)
        if not target.get("available"):
            return {
                "available": False,
                "configured": True,
                "device_name": target.get("device_name"),
                "device_ip": target.get("target_ip"),
                "error": "Could not resolve a live Positron target.",
            }

        user = _positron_username()
        password = _positron_password()
        if not user or not password:
            return {"available": False, "configured": False, "error": "Positron credentials are not configured in env."}

        requested = str(command or "show version").strip().lower()
        if requested not in POSITRON_ALLOWED_COMMANDS:
            return {"available": False, "configured": True, "error": f"Disallowed Positron command: {command}"}
        cache_key = (str(target.get("target_ip") or ""), requested)
        cached = self._positron_read_cache.get(cache_key)
        if cached is not None:
            return dict(cached)

        try:
            proc = subprocess.run(
                ["expect", str(script_path), str(target["target_ip"]), user, password, requested],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception as exc:
            return {
                "available": False,
                "configured": True,
                "device_name": target.get("device_name"),
                "device_ip": target.get("target_ip"),
                "command": requested,
                "error": str(exc),
            }

        stdout = (proc.stdout or "").replace("\r", "").strip()
        stderr = (proc.stderr or "").replace("\r", "").strip()
        stdout = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", stdout)
        stdout = re.sub(r"--\s*more\s*--", "", stdout, flags=re.I)
        cleaned_stdout_lines = []
        for line in stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("spawn ssh "):
                continue
            if "password:" in stripped.lower():
                continue
            cleaned_stdout_lines.append(line)
        stdout = "\n".join(cleaned_stdout_lines).strip()
        result = {
            "available": proc.returncode == 0,
            "configured": True,
            "device_name": target.get("device_name"),
            "device_ip": target.get("target_ip"),
            "site_id": target.get("site_id"),
            "command": requested,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
        if result.get("available"):
            self._positron_read_cache[cache_key] = dict(result)
        return result

    def _parse_positron_running_config(self, text: str) -> dict[str, Any]:
        endpoints: list[dict[str, Any]] = []
        subscribers: list[dict[str, Any]] = []
        uplinks: list[dict[str, Any]] = []
        management_vlans: list[str] = []
        subscriber_vlans: set[str] = set()
        ghn_ports: set[str] = set()
        ghn_interfaces: list[str] = []
        interface_ips: list[dict[str, Any]] = []

        endpoint_re = re.compile(r'ghn endpoint\s+(\d+)(?:.*?port\s+(\d+))?(?:.*?description\s+"([^"]+)")?', re.I)
        subscriber_re = re.compile(r'ghn subscriber\s+(\d+).*?name\s+"([^"]+)".*?vid\s+(\d+).*?endpoint\s+(\d+)', re.I)
        uplink_re = re.compile(r'interface\s+10GigabitEthernet\s+([^\s]+)', re.I)
        mgmt_vlan_re = re.compile(r'interface vlan\s+(\d+)', re.I)
        allowed_vlan_re = re.compile(r'allowed vlan[s]?\s+([0-9,\- ]+)', re.I)
        native_vlan_re = re.compile(r'native vlan\s+(\d+)', re.I)
        ghn_port_re = re.compile(r'^\s*ghn port\s+(\d+)\s*$', re.I | re.M)
        ghn_interface_re = re.compile(r'interface\s+g\.?h?n\s+([^\s]+)', re.I)
        interface_ip_re = re.compile(r'interface vlan\s+(\d+).*?ip address\s+([0-9.]+)\s+([0-9.]+)', re.I | re.S)

        for match in endpoint_re.finditer(text):
            endpoints.append({"endpoint_id": match.group(1), "port": match.group(2), "description": match.group(3)})
        for match in subscriber_re.finditer(text):
            subscribers.append(
                {
                    "subscriber_id": match.group(1),
                    "name": match.group(2),
                    "vid": match.group(3),
                    "endpoint_id": match.group(4),
                }
            )
            subscriber_vlans.add(match.group(3))
        for match in uplink_re.finditer(text):
            uplinks.append({"interface": match.group(1)})
        for match in mgmt_vlan_re.finditer(text):
            management_vlans.append(match.group(1))
        for match in ghn_port_re.finditer(text):
            ghn_ports.add(match.group(1))
        for match in ghn_interface_re.finditer(text):
            ghn_interfaces.append(match.group(1))
        for match in interface_ip_re.finditer(text):
            interface_ips.append({"vlan": match.group(1), "ip": match.group(2), "mask": match.group(3)})
        native_vlans = native_vlan_re.findall(text)
        allowed_vlans = allowed_vlan_re.findall(text)

        return {
            "endpoint_count": len(endpoints),
            "subscriber_count": len(subscribers),
            "ghn_port_count": len(ghn_ports),
            "ghn_ports": sorted(ghn_ports, key=lambda value: int(value) if str(value).isdigit() else str(value)),
            "ghn_interfaces": ghn_interfaces[:12],
            "endpoint_sample": endpoints[:12],
            "subscriber_sample": subscribers[:12],
            "uplinks": uplinks[:8],
            "management_vlans": sorted(set(management_vlans)),
            "interface_ips": interface_ips[:8],
            "subscriber_vlans": sorted(subscriber_vlans),
            "native_vlans": native_vlans[:8],
            "allowed_vlan_samples": allowed_vlans[:8],
        }

    def get_live_ghn_summary(self, device_name: str | None = None, ip: str | None = None, site_id: str | None = None) -> dict[str, Any]:
        target = self._resolve_positron_target(device_name, ip, site_id)
        if not target.get("available"):
            return {
                "available": False,
                "configured": False,
                "device_name": target.get("device_name"),
                "device_ip": target.get("target_ip"),
                "site_id": target.get("site_id"),
                "error": "Could not resolve a live Positron target.",
            }

        version = self.run_live_positron_read(target.get("device_name"), target.get("target_ip"), "show version")
        interfaces = self.run_live_positron_read(target.get("device_name"), target.get("target_ip"), "show ip interface brief")
        routes = self.run_live_positron_read(target.get("device_name"), target.get("target_ip"), "show ip route")
        startup = self.run_live_positron_read(target.get("device_name"), target.get("target_ip"), "show startup-config")
        running = self.run_live_positron_read(target.get("device_name"), target.get("target_ip"), "show running-config")
        config_read = startup if (startup.get("available") and startup.get("stdout")) else running
        parsed = self._parse_positron_running_config(config_read.get("stdout") or "") if config_read.get("available") else {}

        return {
            "available": any(call.get("available") for call in (version, interfaces, routes, running)),
            "configured": True,
            "device_name": target.get("device_name"),
            "device_ip": target.get("target_ip"),
            "site_id": target.get("site_id"),
            "version": version,
            "interfaces": interfaces,
            "routes": routes,
            "config_source_command": config_read.get("command"),
            "running_config": running,
            "startup_config": startup,
            "parsed": parsed,
        }

    def get_site_digi_audit(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        try:
            raw_devices = self._netbox_site_devices(site_id) if self.netbox else []
        except Exception:
            raw_devices = []
        try:
            light_inventory = self._netbox_site_inventory_light(site_id) if self.netbox else []
        except Exception:
            light_inventory = []
        digis: list[dict[str, Any]] = []
        for raw_device in raw_devices:
            role = str(((raw_device.get("role") or {}).get("name")) or "").strip()
            if role != "Digi":
                continue
            digis.append(
                {
                    "name": str(raw_device.get("name") or "").strip(),
                    "role": role,
                    "manufacturer": str((((raw_device.get("device_type") or {}).get("manufacturer")) or {}).get("name") or "").strip() or None,
                    "model": str(((raw_device.get("device_type") or {}).get("model")) or "").strip() or None,
                    "ip": self._netbox_primary_ip(raw_device),
                    "location": str(((raw_device.get("location") or {}).get("display")) or ((raw_device.get("location") or {}).get("name")) or "").strip() or None,
                    "status": str(((raw_device.get("status") or {}).get("label")) or ((raw_device.get("status") or {}).get("value")) or "").strip() or None,
                    "live_ready": False,
                }
            )
        if not digis:
            for row in light_inventory:
                role = str(row.get("role") or "").strip()
                if role != "Digi":
                    continue
                digis.append(
                    {
                        "name": str(row.get("name") or "").strip(),
                        "role": role,
                        "manufacturer": str(row.get("manufacturer") or "").strip() or None,
                        "model": str(row.get("device_type") or "").strip() or None,
                        "ip": str(row.get("primary_ip") or "").strip() or None,
                        "location": str(row.get("location") or "").strip() or None,
                        "status": str(row.get("status") or "").strip() or None,
                        "live_ready": False,
                    }
                )
        role_counts = Counter(str(((row.get("role") or {}).get("name")) or "").strip() or "unknown" for row in raw_devices)
        if not role_counts and light_inventory:
            role_counts = Counter(str(row.get("role") or "").strip() or "unknown" for row in light_inventory)
        notes = []
        if digis:
            notes.append("Digi/OOB devices are present as fallback troubleshooting paths if the primary site circuit is down.")
            notes.append("Jake does not yet have an approved direct live Digi read adapter on this host.")
            notes.append("Digi/OOB reachability helps you get into the site when the main path is down, but it does not prove that the subscriber service path is healthy.")
        else:
            notes.append("No Digi/OOB devices are present in current NetBox inventory for this site.")
        if role_counts.get("OLT"):
            notes.append("This site also has OLT infrastructure, so subscriber-impact diagnosis should still bias toward access/OLT evidence before OOB troubleshooting context.")
        return {
            "site_id": site_id,
            "digi_count": len(digis),
            "digis": digis[:12],
            "role_counts": dict(role_counts),
            "notes": notes,
        }

    def _get_live_ghn_customer_hint(
        self,
        site_id: str | None,
        building_id: str | None,
        unit: str | None,
        network_name: str | None,
    ) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        building_id = canonical_scope(building_id)
        unit = parse_unit_token(unit)
        if site_id != "000004":
            return {"available": False}
        def _norm(value: Any) -> str:
            return compact_free_text(str(value or ""))

        inferred_unit = unit
        if not inferred_unit and network_name:
            unit_match = re.search(r"(\d+[A-Za-z])\s*$", str(network_name))
            if unit_match:
                inferred_unit = unit_match.group(1).upper()

        search_terms: list[str] = []
        if inferred_unit:
            search_terms.extend(
                [
                    _norm(inferred_unit),
                    _norm(f"unit{inferred_unit}"),
                    _norm(f"cambridgeunit{inferred_unit}"),
                ]
            )
        if network_name:
            search_terms.append(_norm(network_name))
        search_terms = [term for term in search_terms if term]

        def _score(candidate: str) -> int:
            normalized = _norm(candidate)
            if not normalized:
                return -1
            best = -1
            for term in search_terms:
                if normalized == term:
                    best = max(best, 100)
                elif term.endswith(normalized) or normalized.endswith(term):
                    best = max(best, 85)
                elif term in normalized or normalized in term:
                    best = max(best, 70)
            if inferred_unit:
                inferred_norm = _norm(inferred_unit)
                if inferred_norm and normalized.endswith(inferred_norm):
                    best = max(best, 95)
                elif inferred_norm and inferred_norm in normalized:
                    best = max(best, 80)
            return best
        candidate_buildings: list[int] = []
        if building_id:
            building_tail = str(building_id).split(".")[-1]
            if building_tail.isdigit():
                candidate_buildings.append(int(building_tail))
        else:
            candidate_buildings.extend(range(1, 9))

        best_result: dict[str, Any] | None = None
        for building_num in candidate_buildings:
            positron_name = f"000004.Positron{building_num:02d}"
            startup = self.run_live_positron_read(positron_name, None, "show startup-config")
            if not startup.get("available"):
                continue
            parsed = self._parse_positron_running_config(startup.get("stdout") or "")
            endpoint_by_id = {
                str(row.get("endpoint_id")): row
                for row in (parsed.get("endpoint_sample") or [])
                if row.get("endpoint_id")
            }
            scored_subscribers = sorted(
                (
                    (_score(str(row.get("name") or "")), row)
                    for row in (parsed.get("subscriber_sample") or [])
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            scored_endpoints = sorted(
                (
                    (_score(str(row.get("description") or "")), row)
                    for row in (parsed.get("endpoint_sample") or [])
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            subscriber_match = scored_subscribers[0][1] if scored_subscribers and scored_subscribers[0][0] >= 70 else None
            endpoint_match = scored_endpoints[0][1] if scored_endpoints and scored_endpoints[0][0] >= 70 else None
            if subscriber_match and not endpoint_match:
                endpoint_match = endpoint_by_id.get(str(subscriber_match.get("endpoint_id")))
            if endpoint_match and not subscriber_match:
                endpoint_id = str(endpoint_match.get("endpoint_id") or "")
                subscriber_match = next(
                    (row for row in (parsed.get("subscriber_sample") or []) if str(row.get("endpoint_id") or "") == endpoint_id),
                    None,
                )
            building_alerts: list[str] = []
            shared_radio_alerts: list[str] = []
            for alert in self._alerts_for_site(site_id):
                summary = str(((alert.get("annotations") or {}).get("summary")) or ((alert.get("labels") or {}).get("alertname")) or "").strip()
                lowered = summary.lower()
                if f"positron{building_num:02d}".lower() in lowered or f"building {building_num}" in lowered:
                    building_alerts.append(summary)
                if "cambium" in lowered and f"building {building_num}" in lowered:
                    shared_radio_alerts.append(summary)
            current = {
                "available": True,
                "device_name": positron_name,
                "building_id": f"000004.{building_num:03d}",
                "config_source": startup.get("command"),
                "parsed": parsed,
                "matched": bool(subscriber_match or endpoint_match),
                "subscriber_match": subscriber_match,
                "endpoint_match": endpoint_match,
                "building_alerts": building_alerts[:8],
                "shared_radio_alerts": shared_radio_alerts[:8],
            }
            if current["matched"]:
                return current
            if best_result is None:
                best_result = current
        return best_result or {"available": False}

    def run_live_olt_read(self, olt_ip: str, command: str, olt_name: str | None = None) -> dict[str, Any]:
        if not OLT_TELNET_READ_SCRIPT.exists():
            return {"available": False, "configured": False, "error": "OLT telnet read script is not present"}
        if not _olt_telnet_password():
            return {"available": False, "configured": False, "error": "OLT telnet password is not set"}
        command = str(command or "").strip()
        if not command:
            return {"available": False, "configured": True, "error": "No OLT command was provided"}
        if not re.match(
            r"^(?:\?|configure|exit|show(?:\s+[A-Za-z0-9:/._?-]+)*|interface\s+gpon(?:\s+[A-Za-z0-9:/._?-]+)*|ont(?:\s+[A-Za-z0-9:/._?-]+)*|terminal\s+length\s+0|terminal\s+page-break\s+disable)$",
            command,
            re.I,
        ):
            return {"available": False, "configured": True, "error": f"Disallowed OLT command: {command}"}
        try:
            import os as _os
            _env = _os.environ.copy()
            _env["PYTHONPATH"] = str(REPO_ROOT) + _os.pathsep + _env.get("PYTHONPATH", "")
            # Split multi-line commands into separate args for single telnet session
            cmd_list = [c.strip() for c in command.split("\n") if c.strip()]
            proc = subprocess.run(
                [sys.executable, str(OLT_TELNET_READ_SCRIPT), "--host", str(olt_ip)] + cmd_list,
                capture_output=True,
                text=True,
                timeout=25,
                check=False,
                env=_env,
            )
        except Exception as exc:
            return {"available": False, "configured": True, "error": str(exc), "olt_ip": olt_ip, "olt_name": olt_name}
        payload_text = (proc.stdout or proc.stderr or "").strip()
        try:
            payload = json.loads(payload_text) if payload_text else {"available": False, "error": "Empty OLT response"}
        except Exception:
            payload = {"available": False, "error": payload_text or f"OLT subprocess exited {proc.returncode}"}
        payload.setdefault("olt_ip", olt_ip)
        if olt_name:
            payload.setdefault("olt_name", olt_name)
        return payload

    def _scan_live_olt_for_serial(self, olt_ip: str, serial: str, olt_name: str | None = None, max_pons: int = 8) -> dict[str, Any] | None:
        needle = str(serial or "").strip().upper()
        if not needle:
            return None
        for pon_idx in range(1, max_pons + 1):
            command = f"show ont info gpon 1/0/{pon_idx} detail"
            live = self.run_live_olt_read(olt_ip, command, olt_name)
            if not live.get("available"):
                continue
            outputs = live.get("outputs") or []
            joined = "\n".join(str(row.get("output") or "") for row in outputs)
            for row in parse_olt_ont_rows(joined):
                if str(row.get("serial") or "").upper() != needle:
                    continue
                return {
                    "olt_ip": olt_ip,
                    "olt_name": olt_name,
                    "pon": f"1/0/{row.get('pon')}",
                    "onu_id": row.get("onu_id"),
                    "serial": needle,
                    "row": row,
                    "scan_command": command,
                    "live": live,
                }
        return None

    def get_live_olt_ont_summary(
        self,
        mac: str | None = None,
        serial: str | None = None,
        olt_name: str | None = None,
        olt_ip: str | None = None,
        pon: str | None = None,
        onu_id: str | None = None,
    ) -> dict[str, Any]:
        olt_telnet_configured = bool(_olt_telnet_password())
        local = self.get_local_ont_path(mac, serial)
        local_placement = (local.get("placement") or {}) if isinstance(local, dict) else {}
        resolved_olt_name = olt_name or local.get("olt_name") or local_placement.get("olt_name")
        resolved_olt_ip = olt_ip or local.get("olt_ip") or local_placement.get("olt_ip")
        resolved_pon = pon or local.get("pon") or local_placement.get("pon")
        resolved_onu = onu_id or local.get("onu_id") or local_placement.get("onu_id")
        if isinstance(resolved_pon, str) and resolved_pon.lower().startswith("gpon"):
            resolved_pon = resolved_pon[4:]

        if resolved_olt_name and not resolved_olt_ip:
            netbox = self.get_netbox_device(resolved_olt_name)
            for row in netbox.get("devices") or []:
                ip = str(row.get("primary_ip") or "").strip()
                if ip:
                    resolved_olt_ip = ip
                    break

        live_resolution = None
        if resolved_olt_ip and serial and not resolved_pon:
            live_resolution = self._scan_live_olt_for_serial(resolved_olt_ip, serial, resolved_olt_name)
            if live_resolution:
                resolved_pon = live_resolution.get("pon")
                resolved_onu = resolved_onu or live_resolution.get("onu_id")

        result = {
            "available": False,
            "configured": olt_telnet_configured,
            "query": {"mac": mac, "serial": serial, "olt_name": olt_name, "olt_ip": olt_ip, "pon": pon, "onu_id": onu_id},
            "resolved": {
                "olt_name": resolved_olt_name,
                "olt_ip": resolved_olt_ip,
                "pon": resolved_pon,
                "onu_id": resolved_onu,
            },
            "local_path": local,
            "live_resolution": live_resolution,
        }
        if not resolved_olt_ip or not resolved_pon:
            result["error"] = "Jake could not resolve a live OLT IP and PON path for that ONU."
            return result
        command = f"show ont info gpon {resolved_pon}"
        if resolved_onu:
            command += f" ont {resolved_onu}"
        live = self.run_live_olt_read(resolved_olt_ip, command, resolved_olt_name)
        result["available"] = bool(live.get("available"))
        result["command"] = command
        result["live"] = live
        joined = "\n".join(str(row.get("output") or "") for row in (live.get("outputs") or []))
        parsed_rows = parse_olt_ont_rows(joined)
        detailed_pon = str(resolved_pon or "").strip()
        if detailed_pon and not detailed_pon.lower().startswith("gpon"):
            detailed_pon = f"Gpon{detailed_pon}"
        detailed_rows = self._parse_ont_table(joined, detailed_pon or str(resolved_pon or ""))
        if resolved_onu:
            result["parsed_row"] = next((row for row in detailed_rows if str(row.get("onu_id") or "") == str(resolved_onu)), None) or next(
                (row for row in parsed_rows if str(row.get("onu_id") or "") == str(resolved_onu)),
                None,
            )
        elif detailed_rows:
            result["parsed_row"] = detailed_rows[0]
        elif parsed_rows:
            result["parsed_row"] = parsed_rows[0]
        if not live.get("available") and live.get("error"):
            result["error"] = live.get("error")
        return result

    def get_live_olt_log_summary(
        self,
        site_id: str | None = None,
        olt_name: str | None = None,
        olt_ip: str | None = None,
        mac: str | None = None,
        serial: str | None = None,
        word: str | None = None,
        module: str | None = None,
        level: int | None = None,
    ) -> dict[str, Any]:
        resolved_olt_name = olt_name
        resolved_olt_ip = olt_ip
        local = None
        if mac or serial:
            local = self.get_local_ont_path(mac, serial)
            placement = (local.get("placement") or {}) if isinstance(local, dict) else {}
            resolved_olt_name = resolved_olt_name or local.get("olt_name") or placement.get("olt_name")
            resolved_olt_ip = resolved_olt_ip or local.get("olt_ip") or placement.get("olt_ip")
        if site_id and not (resolved_olt_name or resolved_olt_ip):
            site_topology = self.get_site_topology(site_id)
            candidate_rows = list(site_topology.get("olt_devices") or [])
            if not candidate_rows:
                site_summary = self.get_site_summary(site_id, False)
                candidate_rows = [
                    row
                    for row in (site_summary.get("netbox_inventory") or [])
                    if str(row.get("role") or "").lower() == "olt"
                ]
            for row in candidate_rows:
                ip = str(row.get("primary_ip") or "").strip()
                name = str(row.get("name") or "").strip()
                if name or ip:
                    resolved_olt_name = resolved_olt_name or name
                    resolved_olt_ip = resolved_olt_ip or ip
                    break
        if resolved_olt_name and not resolved_olt_ip:
            netbox = self.get_netbox_device(resolved_olt_name)
            for row in netbox.get("devices") or []:
                ip = str(row.get("primary_ip") or "").strip()
                if ip:
                    resolved_olt_ip = ip
                    break

        result = {
            "available": False,
            "configured": bool(_olt_telnet_password()),
            "query": {
                "site_id": site_id,
                "olt_name": olt_name,
                "olt_ip": olt_ip,
                "mac": mac,
                "serial": serial,
                "word": word,
                "module": module,
                "level": level,
            },
            "resolved": {
                "olt_name": resolved_olt_name,
                "olt_ip": resolved_olt_ip,
            },
            "local_path": local,
        }
        if not resolved_olt_ip:
            result["error"] = "Jake could not resolve a live OLT IP for the requested log query."
            return result

        command = "show logging flash"
        if word:
            command = f"show logging flash word {str(word).strip()}"
        elif module:
            command = f"show logging flash mod {str(module).strip()}"
        elif level is not None:
            command = f"show logging flash level {int(level)}"

        live = self.run_live_olt_read(resolved_olt_ip, command, resolved_olt_name)
        result["available"] = bool(live.get("available"))
        result["command"] = command
        result["live"] = live
        joined = "\n".join(str(row.get("output") or "") for row in (live.get("outputs") or []))
        result["empty"] = "There is no log in flash." in joined
        if not live.get("available") and live.get("error"):
            result["error"] = live.get("error")
        return result

    def _tauc_web_login(self) -> tuple[urllib.request.OpenerDirector, str, str]:
        seed_project_envs()
        email = os.environ.get("TAUC_EMAIL") or os.environ.get("TPLINK_ID_EMAIL")
        password = _tauc_password()
        if not email or not password:
            raise ValueError("Missing TAUC/TP-Link web login credentials.")
        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        login_body = json.dumps(
            {
                "email": email,
                "password": base64.b64encode(password.encode("utf-8")).decode("ascii"),
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://tauc-api.tplinkcloud.com/v1/isp-users/login",
            data=login_body,
            headers={
                "content-type": "application/json;charset=UTF-8",
                "accept": "application/json, text/plain, */*",
                "x-requested-with": "XMLHttpRequest",
                "x-xsrf-token": "",
                "version": "1.9.3",
                "referer": "https://tauc.tplinkcloud.com/",
            },
        )
        with opener.open(req, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("errorCode") != 0:
            raise RuntimeError(f"TAUC web login failed: {payload}")
        result = payload.get("result") or {}
        return opener, str(result.get("csrfToken") or ""), str(result.get("regionUrl") or "")

    def _tauc_web_get(self, opener: urllib.request.OpenerDirector, csrf_token: str, region_url: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        qs = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{region_url}{path}"
        if qs:
            url = f"{url}?{qs}"
        req = urllib.request.Request(
            url,
            headers={
                "accept": "application/json, text/plain, */*",
                "x-requested-with": "XMLHttpRequest",
                "x-xsrf-token": csrf_token,
                "version": "1.9.3",
                "referer": "https://tauc.tplinkcloud.com/",
            },
        )
        with opener.open(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw)

    def _site_olt_inventory(self, site_id: str | None) -> list[dict[str, str]]:
        if not site_id:
            return []
        canonical_site = canonical_scope(site_id) or site_id
        profile = SITE_SERVICE_PROFILES.get(canonical_site) or {}
        olts = profile.get("olts") or []
        if olts:
            return [
                {
                    "olt_name": str(olt.get("olt_name") or "").strip(),
                    "olt_ip": str(olt.get("olt_ip") or "").strip(),
                }
                for olt in olts
                if str(olt.get("olt_ip") or "").strip()
            ]
        return self._netbox_olt_inventory(canonical_site)

    def _netbox_olt_inventory(self, site_id: str | None) -> list[dict[str, str]]:
        if not site_id:
            return []
        summary = self.get_site_summary(site_id, True)
        inventory = []
        for row in summary.get("netbox_inventory") or []:
            name = str(row.get("name") or "").strip()
            ip = str(row.get("primary_ip") or "").strip()
            if ".OLT" not in name or not ip:
                continue
            inventory.append({"olt_name": name, "olt_ip": ip, "location": str(row.get("location") or "").strip()})
        return inventory

    def _run_olt_command(
        self,
        olt_ip: str,
        command: str,
        timeout: float = 8.0,
    ) -> dict[str, Any]:
        script = str(OLT_TELNET_READ_SCRIPT)
        password = _olt_telnet_password()
        username = str(
            os.environ.get("OLT_TELNET_USER")
            or os.environ.get("olt_user")
            or os.environ.get("olt_telnet_user")
            or "admin"
        ).strip()
        if not OLT_TELNET_READ_SCRIPT.exists():
            return {"available": False, "error": "OLT telnet read script is not present"}
        if not password:
            return {"available": False, "error": "OLT telnet password is not set"}
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
            result = subprocess.run(
                [
                    sys.executable,
                    script,
                    "--host",
                    str(olt_ip),
                    "--username",
                    username,
                    "--password",
                    password,
                    "--timeout",
                    str(timeout),
                    "terminal length 0",
                    command,
                ],
                capture_output=True,
                text=True,
                timeout=timeout + 5,
                cwd=str(REPO_ROOT),
                env=env,
            )
            if result.returncode != 0:
                return {"available": False, "error": (result.stderr or result.stdout or "").strip() or f"exit {result.returncode}"}
            return json.loads((result.stdout or "").strip() or "{}")
        except subprocess.TimeoutExpired:
            return {"available": False, "error": "timeout"}
        except Exception as exc:
            return {"available": False, "error": str(exc)}

    def _parse_ont_table(
        self,
        output: str,
        pon: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_line in str(output or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            if not parts[0].isdigit():
                continue
            try:
                onu_id = int(parts[2])
                serial = parts[3]
                online_status = parts[4].lower()
                admin_status = parts[5].lower() if len(parts) > 5 else ""
                active_status = parts[6].lower() if len(parts) > 6 else ""
                config_status = parts[7].lower() if len(parts) > 7 else ""
                match_status = parts[8].lower() if len(parts) > 8 else ""
                description = parts[-1] if len(parts) >= 10 else ""
                if description and (description[0].isdigit() or re.fullmatch(r"\d+", description)):
                    description = ""
                rows.append(
                    {
                        "pon": pon,
                        "onu_id": str(onu_id),
                        "serial": serial,
                        "online_status": online_status,
                        "admin_status": admin_status,
                        "active_status": active_status,
                        "config_status": config_status,
                        "match_status": match_status,
                        "description": description,
                        "raw_line": line,
                    }
                )
            except (ValueError, IndexError):
                continue
        return rows

    def _probe_olt_mac_variants(self, site_id: str | None, macs: list[str]) -> dict[str, Any]:
        probes: list[dict[str, Any]] = []
        hits: list[dict[str, Any]] = []
        for olt in self._site_olt_inventory(site_id):
            for mac in macs:
                live = self.run_live_olt_read(olt["olt_ip"], f"show mac address-table address {mac}", olt["olt_name"])
                joined = "\n".join(str(item.get("output") or "") for item in (live.get("outputs") or []))
                probe_row = {
                    "olt_name": olt["olt_name"],
                    "olt_ip": olt["olt_ip"],
                    "location": olt.get("location"),
                    "mac": mac,
                    "available": bool(live.get("available")),
                    "text": joined.strip(),
                }
                probes.append(probe_row)
                if joined.strip() and "Specified entry is NULL" not in joined:
                    hits.append(probe_row)
        return {"probes": probes, "hits": hits}

    def _extract_olt_signal_dbm(self, row: dict[str, Any] | None) -> float | None:
        if not isinstance(row, dict):
            return None
        for key in ("rx_power", "rx_power_dbm", "signal_dbm", "optical_power", "rx"):
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except Exception:
                continue
        return None

    def _extract_olt_status(self, row: dict[str, Any] | None) -> str | None:
        if not isinstance(row, dict):
            return None
        for key in ("onu_status", "online_status", "status"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        status_bits = [
            str(row.get("online_status") or "").strip(),
            str(row.get("admin_status") or "").strip(),
            str(row.get("active_status") or "").strip(),
        ]
        status_bits = [bit for bit in status_bits if bit]
        if status_bits:
            return "/".join(status_bits)
        return None

    def _extract_olt_correlation_result(
        self,
        candidate: dict[str, Any] | None,
        *,
        matched_by: str,
    ) -> dict[str, Any]:
        base = {
            "found": False,
            "onu_id": None,
            "pon": None,
            "olt_name": None,
            "olt_ip": None,
            "signal_dbm": None,
            "onu_status": None,
            "matched_by": matched_by,
            "raw": candidate or {},
        }
        if not isinstance(candidate, dict):
            return base
        resolved = candidate.get("resolved") or {}
        parsed_row = candidate.get("parsed_row") or {}
        live_resolution = candidate.get("live_resolution") or {}
        local_path = (candidate.get("local_path") or {}).get("placement") or {}
        olt_name = (
            str(parsed_row.get("olt_name") or "").strip()
            or str(resolved.get("olt_name") or "").strip()
            or str(local_path.get("olt_name") or "").strip()
        )
        olt_ip = (
            str(parsed_row.get("olt_ip") or "").strip()
            or str(resolved.get("olt_ip") or "").strip()
            or str(local_path.get("olt_ip") or "").strip()
        )
        pon = (
            str(parsed_row.get("pon") or "").strip()
            or str(live_resolution.get("pon") or "").strip()
            or str(resolved.get("pon") or "").strip()
            or str(local_path.get("pon") or "").strip()
        )
        onu_id = (
            str(parsed_row.get("onu_id") or "").strip()
            or str(live_resolution.get("onu_id") or "").strip()
            or str(resolved.get("onu_id") or "").strip()
            or str(local_path.get("onu_id") or "").strip()
        )
        signal_dbm = self._extract_olt_signal_dbm(parsed_row) or self._extract_olt_signal_dbm(local_path)
        onu_status = self._extract_olt_status(parsed_row) or self._extract_olt_status(local_path)
        if not (olt_name or olt_ip or pon or onu_id):
            return base
        return {
            "found": True,
            "onu_id": onu_id or None,
            "pon": pon or None,
            "olt_name": olt_name or None,
            "olt_ip": olt_ip or None,
            "signal_dbm": signal_dbm,
            "onu_status": onu_status,
            "matched_by": matched_by,
            "raw": candidate,
        }

    def _auto_correlate_olt(
        self,
        mac: str,
        client_ip: str | None,
        site_id: str | None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "found": False,
            "onu_id": None,
            "pon": None,
            "olt_name": None,
            "olt_ip": None,
            "signal_dbm": None,
            "onu_status": None,
            "matched_by": "none",
            "raw": {},
        }
        canonical_site = canonical_scope(site_id) if site_id else None
        if not canonical_site:
            result["error"] = "site_id unavailable"
            return result
        profile = SITE_SERVICE_PROFILES.get(canonical_site) or {}
        if not profile.get("uses_olt"):
            result["error"] = "site does not use OLT correlation"
            return result
        inventory = self._site_olt_inventory(canonical_site)
        result["site_id"] = canonical_site
        result["olt_candidates"] = inventory
        if not inventory:
            result["error"] = "no OLT inventory found for site"
            return result
        if not _olt_telnet_password():
            result["error"] = "OLT live reads are not configured"
            return result
        for olt in inventory:
            olt_name = str(olt.get("olt_name") or "").strip() or None
            olt_ip = str(olt.get("olt_ip") or "").strip() or None
            if not olt_ip:
                continue
            all_rows: list[dict[str, Any]] = []
            for pon_index in range(1, 9):
                command = f"show ont info gpon 1/0/{pon_index} detail"
                probe = self._run_olt_command(olt_ip, command, timeout=8.0)
                if not probe.get("available"):
                    if pon_index == 1:
                        result.setdefault("errors", []).append(
                            {"olt_name": olt_name, "olt_ip": olt_ip, "pon": pon_index, "error": probe.get("error")}
                        )
                    break
                output = "\n".join(str(item.get("output") or "") for item in (probe.get("outputs") or []))
                rows = self._parse_ont_table(output, f"Gpon1/0/{pon_index}")
                if not rows:
                    break
                for row in rows:
                    enriched = dict(row)
                    enriched["olt_name"] = olt_name
                    enriched["olt_ip"] = olt_ip
                    all_rows.append(enriched)
                    description = normalize_subscriber_label(row.get("description") or "")
                    if not description:
                        continue
                    mac_from_label = SUBSCRIBER_NAME_TO_MAC.get(description)
                    if not mac_from_label:
                        continue
                    colonized = ":".join(mac_from_label[i:i + 2] for i in range(0, 12, 2))
                    if norm_mac(colonized) != mac:
                        continue
                    return {
                        "found": True,
                        "onu_id": row.get("onu_id"),
                        "pon": row.get("pon"),
                        "olt_name": olt_name,
                        "olt_ip": olt_ip,
                        "signal_dbm": None,
                        "onu_status": row.get("online_status"),
                        "matched_by": "description",
                        "description": row.get("description"),
                        "serial": row.get("serial"),
                        "raw": row,
                    }
            if all_rows:
                result.setdefault("candidates", []).extend(all_rows[:32])

        if client_ip:
            lease = self.get_live_dhcp_lease_summary(site_id=canonical_site, mac=mac, ip=client_ip, limit=5)
            result["raw"] = {"lease_probe": lease}
            result["matched_by"] = "ip"
            if lease.get("lease_count"):
                result["error"] = "lease matched but no OLT/ONU path could be derived from current live data"
            else:
                result["error"] = "no OLT/ONU match from MAC probe and no DHCP lease clue from IP"
            return result

        result["error"] = "no OLT/ONU match found for MAC"
        return result

    def _auto_correlate_dhcp_logs(
        self,
        mac: str,
        site_id: str | None,
        window_minutes: int = 60,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "found": False,
            "request_count": 0,
            "requests_per_hour": 0.0,
            "verdict": "normal",
            "sample_lines": [],
        }
        canonical_site = canonical_scope(site_id) if site_id else None
        if not canonical_site:
            result["error"] = "site_id unavailable"
            return result
        if not self._loki_base_url():
            result["error"] = "LOKI_URL is not configured"
            return result
        normalized_mac = norm_mac(mac)
        compact_mac = normalized_mac.replace(":", "")
        mac_forms = sorted(
            {
                normalized_mac.lower(),
                normalized_mac.upper(),
                compact_mac.lower(),
                compact_mac.upper(),
            }
        )
        escaped_site = re.escape(canonical_site)
        escaped_forms = "|".join(re.escape(form) for form in mac_forms if form)
        if not escaped_forms:
            result["error"] = "invalid MAC"
            return result
        query = f'{{host=~"{escaped_site}.*"}} !~ "mktxp_user" |~ "{escaped_forms}"'
        window = max(1, min(int(window_minutes or 60), 24 * 60))
        end_ns = int(time.time() * 1_000_000_000)
        start_ns = end_ns - window * 60 * 1_000_000_000
        ok, streams, detail = self._loki_query_range(query, start_ns=start_ns, end_ns=end_ns, limit=500)
        if not ok:
            result["error"] = detail
            return result
        entries = self._loki_normalize_entries(streams, limit=500)
        matches: list[dict[str, Any]] = []
        for row in entries:
            text = str(row.get("line") or "")
            lowered = text.lower()
            if not any(form.lower() in lowered for form in mac_forms):
                continue
            if "dhcp" not in lowered and "chaddr" not in lowered:
                continue
            matches.append(row)
        requests_per_hour = len(matches) / (window / 60)
        verdict = "normal"
        if requests_per_hour >= DHCP_RATE_ABNORMAL_PER_HOUR:
            verdict = "abnormal"
        elif requests_per_hour >= DHCP_RATE_ELEVATED_PER_HOUR:
            verdict = "elevated"
        return {
            "found": bool(matches),
            "request_count": len(matches),
            "requests_per_hour": requests_per_hour,
            "verdict": verdict,
            "sample_lines": [str(row.get("line") or "")[:200] for row in matches[:5]],
            "window_minutes": window,
            "query": query,
        }

    def resolve_cpe_mac_from_clue(
        self,
        *,
        cpe_hostname: str | None = None,
        port_name: str | None = None,
        window_minutes: int = 60,
        limit: int = 500,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "found": False,
            "mac": None,
            "cpe_hostname": cpe_hostname,
            "port_name": port_name,
            "site_id": None,
            "query": None,
        }
        if not self._loki_base_url():
            result["error"] = "LOKI_URL is not configured"
            return result
        hostname = str(cpe_hostname or "").strip()
        if not hostname:
            result["error"] = "cpe_hostname is required"
            return result
        host_pattern = re.escape(hostname)
        query = f'{{job="syslog"}} !~ "mktxp_user" |~ "Host-Name = \\"{host_pattern}\\"|chaddr ="'
        result["query"] = query
        window = max(1, min(int(window_minutes or 60), 24 * 60))
        bounded_limit = max(1, min(int(limit or 500), 500))
        end_ns = int(time.time() * 1_000_000_000)
        start_ns = end_ns - window * 60 * 1_000_000_000
        ok, streams, detail = self._loki_query_range(query, start_ns=start_ns, end_ns=end_ns, limit=bounded_limit)
        if not ok:
            result["error"] = detail
            return result
        entries = self._loki_normalize_entries(streams, limit=bounded_limit)
        mac_re = re.compile(r"chaddr\s*=\s*([0-9a-f:]{17}|[0-9a-f]{12})", re.I)
        candidate_macs: list[str] = []
        for row in entries:
            line = str(row.get("line") or "")
            match = mac_re.search(line)
            if not match:
                continue
            mac = norm_mac(match.group(1))
            if mac and mac not in candidate_macs:
                candidate_macs.append(mac)
        result["candidate_macs"] = candidate_macs[:20]
        target_port = str(port_name or "").strip().lower()
        for mac in candidate_macs[:20]:
            cpe = self.get_cpe_state(mac, include_bigmac=True)
            primary = (cpe.get("bridge") or {}).get("primary_sighting") or {}
            seen_port = str(primary.get("port_name") or primary.get("on_interface") or "").strip().lower()
            seen_hostname = str(cpe.get("cpe_hostname") or primary.get("hostname") or "").strip().lower()
            if hostname.lower() not in seen_hostname:
                continue
            if target_port and seen_port != target_port:
                continue
            result.update(
                {
                    "found": True,
                    "mac": mac,
                    "site_id": cpe.get("site_id") or primary.get("device_site"),
                    "raw_cpe_state": cpe,
                }
            )
            return result
        result["error"] = "no matching MAC found from DHCP clue search"
        return result

    def get_tp_link_subscriber_join(
        self,
        network_name: str | None = None,
        network_id: str | None = None,
        mac: str | None = None,
        serial: str | None = None,
        site_id: str | None = None,
    ) -> dict[str, Any]:
        local_row = find_local_online_cpe_row(network_name, network_id, mac, serial)
        resolved_network_name = str((local_row or {}).get("networkName") or network_name or "").strip() or None
        resolved_network_id = str((local_row or {}).get("networkId") or network_id or "").strip() or None
        resolved_serial = str((local_row or {}).get("sn") or serial or "").strip() or None
        resolved_mac = norm_mac(str((local_row or {}).get("mac") or mac or ""))
        resolved_site_id = canonical_scope(site_id or infer_site_from_network_name(resolved_network_name))
        result: dict[str, Any] = {
            "query": {
                "network_name": network_name,
                "network_id": network_id,
                "mac": mac,
                "serial": serial,
                "site_id": site_id,
            },
            "resolved": {
                "network_name": resolved_network_name,
                "network_id": resolved_network_id,
                "mac": resolved_mac,
                "serial": resolved_serial,
                "site_id": resolved_site_id,
            },
            "local_row": local_row,
            "mac_variants": tp_link_mac_variants(resolved_mac),
        }

        if resolved_network_id and resolved_serial and str(resolved_serial).upper().startswith("TPLG-") and resolved_site_id:
            live_onu = None
            for olt in self._site_olt_inventory(resolved_site_id):
                candidate = self.get_live_olt_ont_summary(serial=resolved_serial, olt_name=olt["olt_name"], olt_ip=olt["olt_ip"])
                if candidate.get("available") and (candidate.get("parsed_row") or candidate.get("live_resolution")):
                    live_onu = candidate
                    break
            result["live_onu"] = live_onu

        # Try TAUC API network details if we have a network_id
        if resolved_network_id and not resolved_network_id and self.tauc and self.tauc.cloud and self.tauc.cloud.configured():
            pass  # placeholder

        # If no network_id yet, try TAUC API to find it by name
        if not resolved_network_id and resolved_network_name and self.tauc and self.tauc.cloud and self.tauc.cloud.configured():
            try:
                id_resp = self.tauc.cloud.request('GET', '/v1/openapi/network-system-management/id',
                                                   query={'networkName': resolved_network_name})
                id_list = (id_resp.get('result') or [])
                if isinstance(id_list, list) and id_list:
                    resolved_network_id = str(id_list[0].get('id', ''))
                    result['resolved']['network_id'] = resolved_network_id
            except Exception:
                pass

        # Get network details from TAUC API
        if resolved_network_id and self.tauc and self.tauc.cloud and self.tauc.cloud.configured():
            try:
                det = self.tauc.cloud.request('GET', f'/v1/openapi/network-system-management/details/{resolved_network_id}')
                network_info = (det.get('result') or {}).get('network') or {}
                if network_info:
                    mesh_units = network_info.get('meshUnitList') or []
                    if mesh_units and not resolved_mac:
                        resolved_mac = norm_mac(mesh_units[0].get('mac', ''))
                        result['resolved']['mac'] = resolved_mac
                    if mesh_units and not resolved_serial:
                        resolved_serial = mesh_units[0].get('sn', '')
                        result['resolved']['serial'] = resolved_serial
                    # Get status
                    try:
                        st = self.tauc.cloud.request('GET', f'/v1/openapi/network-system-management/status/{resolved_network_id}')
                        status = (st.get('result') or {}).get('status', '')
                    except Exception:
                        status = ''
                    result['tauc_device'] = {
                        'networkName': network_info.get('networkName'),
                        'networkId': resolved_network_id,
                        'online': status == 'ONLINE',
                        'status': status,
                        'mac': resolved_mac,
                        'sn': resolved_serial,
                        'apNum': network_info.get('apNum'),
                        'site_id': network_info.get('userNetworkProfileCity') or resolved_site_id,
                    }
            except Exception as exc:
                result['tauc_device_error'] = str(exc)

        if resolved_network_id and str((local_row or {}).get("deviceId") or "").strip() and str((local_row or {}).get("topoId") or "").strip():
            try:
                opener, csrf, region = self._tauc_web_login()
                device_id = str((local_row or {}).get("deviceId") or "").strip()
                topo_id = str((local_row or {}).get("topoId") or "").strip()
                result["tauc_runtime"] = {
                    "devices_tr": self._tauc_web_get(opener, csrf, region, f"/v1/remote/networks/{device_id}/devices/tr", {"supportThirdParty": "true", "topoId": topo_id}),
                    "devices_tr_clients": self._tauc_web_get(opener, csrf, region, f"/v1/remote/networks/{device_id}/devices/tr/clients", {"supportThirdParty": "true", "topoId": topo_id}),
                    "network_map_devices": self._tauc_web_get(opener, csrf, region, f"/v1/network-map/remote/networks/{device_id}/devices", {"topoId": topo_id}),
                    "network_map_clients": self._tauc_web_get(opener, csrf, region, f"/v1/network-map/remote/networks/{device_id}/clients/tr/v3"),
                    "waninfo": self._tauc_web_get(opener, csrf, region, f"/v1/remote/networks/{device_id}/internet/waninfo"),
                }
            except Exception as exc:
                result["tauc_runtime_error"] = str(exc)

        if resolved_site_id and resolved_mac:
            result["olt_mac_probe"] = self._probe_olt_mac_variants(resolved_site_id, result["mac_variants"])

        return result

    def get_cpe_management_surface(
        self,
        network_name: str | None = None,
        network_id: str | None = None,
        mac: str | None = None,
        serial: str | None = None,
        site_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_mac = norm_mac(mac or "")
        serial_text = str(serial or "").strip()
        network_text = str(network_name or "").strip()
        vendor_hint = infer_cpe_vendor_hint(network_text or None, normalized_mac or None, serial_text or None)
        hinted_vendor = str(vendor_hint.get("vendor") or "unknown")
        hinted_row = vendor_hint.get("row") or {}
        hinted_mac = norm_mac(str(hinted_row.get("mac") or hinted_row.get("MAC Address") or ""))
        hinted_serial = str(hinted_row.get("AP Serial Number") or "").strip()
        effective_mac = normalized_mac or hinted_mac
        effective_serial = serial_text or hinted_serial

        tplink = None
        should_try_tplink = hinted_vendor in {"unknown", "tplink_hc220"}
        if should_try_tplink and (network_text or network_id or effective_serial or effective_mac):
            try:
                tplink = self.get_tp_link_subscriber_join(network_text or None, network_id, effective_mac or None, effective_serial or None, site_id)
            except Exception as exc:
                tplink = {"error": str(exc)}

        vilo = None
        vilo_mac_hint = effective_mac if effective_mac.startswith("e8:da:00:") else None
        should_try_vilo = hinted_vendor in {"unknown", "vilo"} or bool(vilo_mac_hint)
        if should_try_vilo and (network_text or network_id or vilo_mac_hint):
            try:
                vilo = self.get_vilo_target_summary(vilo_mac_hint, network_id, network_text or None)
            except Exception as exc:
                vilo = {"error": str(exc)}

        vendor = hinted_vendor if hinted_vendor != "unknown" else "unknown"
        if tplink and (tplink.get("local_row") or tplink.get("tauc_device") or tplink.get("tauc_runtime")):
            vendor = "tplink_hc220"
        if vilo and vilo.get("found"):
            if vendor == "unknown" or vilo_mac_hint:
                vendor = "vilo"

        local_management: list[str] = []
        controller_management: list[str] = []
        blind_spots: list[str] = []
        evidence: dict[str, Any] = {"tplink": tplink, "vilo": vilo}

        if vendor == "tplink_hc220":
            resolved = (tplink or {}).get("resolved") or {}
            local_row = (tplink or {}).get("local_row") or {}
            runtime = (tplink or {}).get("tauc_runtime") or {}
            tauc_device = (tplink or {}).get("tauc_device") or {}
            wan_rows = ((runtime.get("waninfo") or {}).get("result") or {}).get("wanList") or []
            live_onu = (tplink or {}).get("live_onu") or {}
            if vendor_hint.get("source") == "nycha_ap_make":
                local_management.append("NYCHA reference sheet tags this unit as TP-Link.")
            elif vendor_hint.get("source") == "nycha_scan":
                local_management.append("NYCHA reference scan string identifies this unit as HC220/TP-Link.")
            if local_row.get("wanIp"):
                local_management.append(f"Local export has WAN IP {local_row.get('wanIp')}.")
            if local_row.get("deviceId") and local_row.get("topoId"):
                local_management.append(f"TAUC web runtime can read this device via deviceId={local_row.get('deviceId')} topoId={local_row.get('topoId')}.")
            if wan_rows:
                local_management.append("TAUC web runtime exposes current WAN info for this HC220.")
            if live_onu.get("available"):
                local_management.append("Live OLT path reads are available for the serving ONU/ONT side.")
            controller_management.append("TAUC cloud/service-provider management is the primary controller surface for HC220 builds.")
            if tauc_device.get("networkId"):
                controller_management.append(f"TAUC knows subscriber network {tauc_device.get('networkName') or resolved.get('network_name')} ({tauc_device.get('networkId')}).")
            if resolved.get("serial"):
                controller_management.append(f"HC220 serial in scope: {resolved.get('serial')}.")
            blind_spots.append("Jake does not yet have a direct local HC220 web UI or SSH/CLI adapter on this host.")
            blind_spots.append("Some HC220 service-provider features may exist only in TAUC tasks and not in the local GUI.")
            if not wan_rows and not local_row.get("wanIp"):
                blind_spots.append("Current local management path does not yet prove live WAN state beyond export/runtime hints.")
        elif vendor == "vilo":
            target = vilo or {}
            trace = target.get("trace") or {}
            best = ((trace.get("bridge_hosts") or trace).get("best_hit") or (trace.get("bridge_hosts") or trace).get("best_guess") or {})
            if vendor_hint.get("source") == "nycha_ap_make":
                local_management.append("NYCHA reference sheet tags this unit as Vilo.")
            elif vendor_hint.get("source") in {"nycha_scan", "mac_oui"}:
                local_management.append("Current local identifiers line up with the Vilo device family.")
            if target.get("device_rows"):
                local_management.append("Vilo cloud device list exposes per-node local control IPs for this network.")
            device_local_ip = str(target.get("device_local_ip") or "").strip()
            if device_local_ip:
                local_management.append(f"Current Vilo local control IP evidence: {device_local_ip}.")
            if best.get("identity"):
                local_management.append(f"Latest physical sighting: {best.get('identity')} {best.get('on_interface')} VLAN {best.get('vid')}.")
            controller_management.append("Vilo ISP API is the primary controller surface for inventory, subscribers, networks, and per-network device state.")
            if target.get("effective_network_id"):
                controller_management.append(f"Vilo network in scope: {target.get('effective_network_id')}.")
            blind_spots.append("Jake does not yet have a direct local Vilo web UI or shell adapter on this host.")
            blind_spots.append("Current Vilo management is controller/API-first plus local L2 corroboration, not direct local-device login.")
        else:
            blind_spots.append("Jake could not yet prove whether this CPE is Vilo or TP-Link HC220 from the current identifiers.")

        return {
            "query": {
                "network_name": network_name,
                "network_id": network_id,
                "mac": normalized_mac or None,
                "serial": serial_text or None,
                "site_id": site_id,
            },
            "vendor_hint": vendor_hint,
            "vendor": vendor,
            "local_management": local_management,
            "controller_management": controller_management,
            "blind_spots": blind_spots,
            "evidence": evidence,
        }

    def get_cpe_management_readiness(self, vendor: str | None = None) -> dict[str, Any]:
        vendor_filter = str(vendor or "").strip().lower().replace("-", "_")
        nycha_rows = load_nycha_info_rows()
        local_rows = load_local_online_cpe_rows()
        tauc_summary = self.tauc.summary() if self.tauc else {}
        vilo_summary = self.vilo_api.summary() if self.vilo_api else {}

        nycha_tplink = [row for row in nycha_rows if "tp-link" in str(row.get("AP Make") or "").strip().lower()]
        nycha_vilo = [row for row in nycha_rows if "vilo" in str(row.get("AP Make") or "").strip().lower()]
        local_tplink = [row for row in local_rows if str(row.get("sn") or "").strip().upper().startswith(("Y", "TPLG-"))]
        local_vilo = [row for row in local_rows if norm_mac(str(row.get("mac") or "")).startswith("e8:da:00:")]

        vendors: dict[str, dict[str, Any]] = {
            "tplink_hc220": {
                "fleet_hints": {
                    "nycha_reference_units": len(nycha_tplink),
                    "local_export_rows": len(local_tplink),
                    "tauc_audit_csv_present": TAUC_NYCHA_AUDIT_CSV.exists(),
                },
                "controller_surfaces": {
                    "tauc_cloud_configured": bool(tauc_summary.get("cloud_configured")),
                    "tauc_acs_configured": bool(tauc_summary.get("acs_configured")),
                    "tauc_olt_configured": bool(tauc_summary.get("olt_configured")),
                },
                "local_evidence": [
                    "Local online subscriber export",
                    "NYCHA reference sheet with AP Make / serial / scan payload",
                    "TAUC web-session runtime paths when deviceId/topoId are present",
                    "Live OLT-side MAC and ONU reads when TAUC OLT is configured",
                ],
                "direct_local_adapter_ready": False,
                "direct_local_adapter_note": "Jake does not yet have a direct local HC220 web UI or SSH/CLI adapter on this host.",
                "recommended_next_tooling": [
                    "Build a read-only HC220 local GUI adapter or ACS-side deep device adapter for LAN/Wi-Fi/DHCP inspection.",
                    "Preserve TAUC runtime joins as the primary service-provider management path.",
                ],
            },
            "vilo": {
                "fleet_hints": {
                    "nycha_reference_units": len(nycha_vilo),
                    "local_export_rows": len(local_vilo),
                },
                "controller_surfaces": {
                    "vilo_api_configured": bool(vilo_summary.get("configured")),
                    "vilo_has_access_token": bool(vilo_summary.get("has_access_token")),
                    "vilo_has_refresh_token": bool(vilo_summary.get("has_refresh_token")),
                },
                "local_evidence": [
                    "NYCHA reference sheet with AP Make / MAC / scan payload",
                    "Vilo ISP API network and device detail",
                    "Latest bridge-host physical sightings and local control IP corroboration when available",
                ],
                "direct_local_adapter_ready": False,
                "direct_local_adapter_note": "Jake does not yet have a direct local Vilo web UI or shell adapter on this host.",
                "recommended_next_tooling": [
                    "Build a read-only Vilo local web UI/session adapter for local-device status and LAN-side inspection.",
                    "Keep the Vilo ISP API as the primary controller path and enrich it with local-device access when reachable.",
                ],
            },
        }

        if vendor_filter in {"tplink", "tp_link", "hc220"}:
            vendor_filter = "tplink_hc220"
        if vendor_filter and vendor_filter in vendors:
            vendors = {vendor_filter: vendors[vendor_filter]}

        overall_gaps = [
            "Neither HC220 nor Vilo currently has a first-class direct local device adapter on this host.",
            "Jake is stronger on controller-side truth than on-box local management for both CPE families.",
        ]
        if not tauc_summary.get("cloud_configured"):
            overall_gaps.append("TAUC cloud is not fully configured for HC220 management on this host.")
        if not vilo_summary.get("configured"):
            overall_gaps.append("Vilo API is not fully configured for Vilo management on this host.")

        return {
            "vendor_filter": vendor_filter or None,
            "vendors": vendors,
            "overall_gaps": overall_gaps,
        }

    def get_site_topology(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        radio_scan = load_transport_radio_scan()
        alerts = self._alerts_for_site(site_id) if self.alerts else []
        netbox_inventory = self._netbox_site_inventory_light(site_id) if self.netbox else []
        tauc_rows = load_tauc_nycha_audit_rows()
        nycha_info_rows = load_nycha_info_rows()
        address_units: dict[str, dict[str, Any]] = {}
        building_units: dict[str, set[str]] = {}
        resolved_address_cache: dict[str, str | None] = {}

        def resolve_building_id_for_address(address: str) -> str | None:
            normalized = str(address or "").strip()
            if not normalized:
                return None
            if normalized not in resolved_address_cache:
                resolved = self._resolve_building_from_address(normalized)
                best = (resolved or {}).get("best_match") or {}
                resolved_address_cache[normalized] = canonical_scope(best.get("prefix"))
            return resolved_address_cache[normalized]

        def ensure_address_entry(address: str, building_id: str | None = None) -> dict[str, Any]:
            normalized = str(address or "").strip()
            entry = address_units.setdefault(
                normalized,
                {
                    "address": normalized,
                    "building_id": building_id,
                    "units": set(),
                    "network_names": set(),
                },
            )
            if building_id and not entry.get("building_id"):
                entry["building_id"] = building_id
            return entry

        def add_address_unit(address: str, unit: str | None, network_name: str | None, building_id: str | None = None) -> None:
            normalized_address = str(address or "").strip()
            if not normalized_address:
                return
            resolved_building_id = canonical_scope(building_id) if building_id else resolve_building_id_for_address(normalized_address)
            entry = ensure_address_entry(normalized_address, resolved_building_id)
            if unit:
                entry["units"].add(unit)
                if resolved_building_id:
                    building_units.setdefault(resolved_building_id, set()).add(unit)
            normalized_network_name = str(network_name or "").strip()
            if normalized_network_name:
                entry["network_names"].add(normalized_network_name)

        for row in nycha_info_rows:
            address = str(row.get("Address") or "").strip()
            unit = parse_unit_token(row.get("Unit"))
            network_name = str(row.get("PPPoE") or "").strip()
            if not address:
                continue
            add_address_unit(address, unit, network_name)

        for row in tauc_rows:
            location = str(row.get("expected_location") or "").strip()
            unit = parse_unit_token(row.get("expected_unit"))
            prefix = canonical_scope(row.get("expected_prefix"))
            network_name = str(row.get("networkName") or "").strip()
            if not location:
                continue
            add_address_unit(location, unit, network_name, prefix)

        radios: list[dict[str, Any]] = []
        radio_links: list[dict[str, Any]] = []
        radio_name_to_building_id: dict[str, str] = {}
        seen_radio_names: set[str] = set()
        address_coords: dict[str, tuple[float, float]] = {}
        building_coords: dict[str, tuple[float, float]] = {}
        for row in radio_scan.get("results") or []:
            location = str(row.get("location") or "").strip()
            resolved = self._resolve_building_from_address(location) if location else {"resolved": False, "best_match": None}
            best = resolved.get("best_match") or {}
            building_id = canonical_scope(best.get("prefix"))
            resolved_site = canonical_scope(best.get("site_code")) if best.get("site_code") else (building_id.split(".")[0] if building_id else None)
            if resolved_site != site_id:
                continue
            matching_alerts = [
                alert for alert in alerts
                if normalize_free_text(str(((alert.get("annotations") or {}).get("device_name")) or ((alert.get("labels") or {}).get("name")) or ""))
                == normalize_free_text(str(row.get("name") or ""))
            ]
            name = str(row.get("name") or "")
            model = str(row.get("model") or "")
            latitude = row.get("latitude")
            longitude = row.get("longitude")
            try:
                lat_value = float(latitude) if latitude is not None else None
                lon_value = float(longitude) if longitude is not None else None
            except (TypeError, ValueError):
                lat_value = None
                lon_value = None
            if lat_value is not None and lon_value is not None:
                address_coords[location] = (lat_value, lon_value)
                if building_id:
                    building_coords[building_id] = (lat_value, lon_value)
            if row.get("type") == "siklu" and " - " in name:
                left, right = [part.strip() for part in name.split(" - ", 1)]
                radio_links.append(
                    {
                        "name": name,
                        "kind": "siklu",
                        "from_label": left,
                        "to_label": right,
                        "status": row.get("status"),
                        "ip": row.get("ip"),
                        "location": location,
                    }
                )
            if building_id:
                radio_name_to_building_id[name] = building_id
            seen_radio_names.add(normalize_free_text(name))
            radios.append(
                {
                    "name": name,
                    "type": row.get("type"),
                    "model": model,
                    "ip": row.get("ip"),
                    "location": location,
                    "status": row.get("status"),
                    "resolved_building_id": building_id,
                    "resolved_building_match": best,
                    "address_units": sorted((address_units.get(location, {}) or {}).get("units") or []),
                    "network_names": sorted((address_units.get(location, {}) or {}).get("network_names") or []),
                    "latitude": lat_value,
                    "longitude": lon_value,
                    "coordinate_source": row.get("coordinate_source"),
                    "alert_count": len(matching_alerts),
                    "alerts": matching_alerts[:10],
                }
            )

        for row in netbox_inventory:
            role = str(row.get("role") or "").strip()
            name = str(row.get("name") or "").strip()
            if role.lower() != "radio" or not name:
                continue
            normalized_name = normalize_free_text(name)
            if normalized_name in seen_radio_names:
                continue
            location = str(row.get("location") or "").strip()
            best = {}
            building_id = RADIO_BUILDING_ID_OVERRIDES.get(normalized_name)
            label_match = re.search(rf"\b{re.escape(site_id)}-(\d{{3}})-V(?:1000|2000|3000|5000)\b", name, re.I)
            if label_match and not building_id:
                building_id = f"{site_id}.{label_match.group(1)}"
            if not building_id:
                building_match = re.search(r"\bbuilding\s+(\d{1,3})\b", f"{name} {location}", re.I)
                if building_match:
                    building_id = f"{site_id}.{int(building_match.group(1)):03d}"
            if location:
                resolved = self._resolve_building_from_address(location)
                best = resolved.get("best_match") or {}
                address_building_id = canonical_scope(best.get("prefix"))
                if not building_id and canonical_scope(str(address_building_id or "").split(".")[0]) == site_id:
                    building_id = address_building_id
            if location:
                address_entry = address_units.get(location) or ensure_address_entry(location, building_id)
            else:
                address_entry = {"units": set(), "network_names": set()}
            matching_alerts = [
                alert for alert in alerts
                if normalize_free_text(str(((alert.get("annotations") or {}).get("device_name")) or ((alert.get("labels") or {}).get("name")) or ""))
                == normalized_name
            ]
            if building_id:
                radio_name_to_building_id[name] = building_id
            seen_radio_names.add(normalized_name)
            radios.append(
                {
                    "name": name,
                    "type": "cambium",
                    "model": str(row.get("device_type") or "").strip() or None,
                    "ip": row.get("primary_ip"),
                    "location": location,
                    "status": inventory_radio_status(row.get("status")),
                    "netbox_status": row.get("status"),
                    "status_bucket": row.get("status_bucket"),
                    "is_live_expected": bool(row.get("is_live_expected")),
                    "resolved_building_id": building_id,
                    "resolved_building_match": best,
                    "address_units": sorted((address_entry or {}).get("units") or []),
                    "network_names": sorted((address_entry or {}).get("network_names") or []),
                    "latitude": None,
                    "longitude": None,
                    "coordinate_source": "netbox_inventory_only",
                    "alert_count": len(matching_alerts),
                    "alerts": matching_alerts[:10],
                }
            )

        for link in self._cnwave_site_links(site_id):
            radio_links.append(
                {
                    **link,
                    "from_building_id": radio_name_to_building_id.get(str(link.get("from_label") or "")),
                    "to_building_id": radio_name_to_building_id.get(str(link.get("to_label") or "")),
                }
            )

        for override in RADIO_LINK_OVERRIDES:
            radio_links.append(
                {
                    "name": override["name"],
                    "kind": override["kind"],
                    "from_label": override.get("from_name"),
                    "to_label": override.get("to_name"),
                    "from_building_id": radio_name_to_building_id.get(str(override.get("from_name") or "")),
                    "to_building_id": radio_name_to_building_id.get(str(override.get("to_name") or "")),
                    "status": override.get("status"),
                }
            )

        if not radio_links:
            dn_radios = []
            cn_radios = []
            for row in radios:
                joined = f"{row.get('name') or ''} {row.get('model') or ''}".lower()
                if "v5000" in joined:
                    dn_radios.append(row)
                elif any(tag in joined for tag in ("v1000", "v2000", "v3000")):
                    cn_radios.append(row)
            if len(dn_radios) == 1 and cn_radios:
                dn = dn_radios[0]
                for cn in sorted(cn_radios, key=lambda item: str(item.get("name") or "")):
                    radio_links.append(
                        {
                            "name": f"{dn.get('name')} -> {cn.get('name')}",
                            "kind": "inferred_netbox_dn_cn",
                            "from_label": dn.get("name"),
                            "to_label": cn.get("name"),
                            "from_building_id": canonical_scope(dn.get("resolved_building_id")),
                            "to_building_id": canonical_scope(cn.get("resolved_building_id")),
                            "status": "inferred",
                        }
                    )

        buildings: list[dict[str, Any]] = []
        seen_buildings = sorted({r.get("resolved_building_id") for r in radios if r.get("resolved_building_id")})
        for building_id in seen_buildings:
            buildings.append(
                {
                    "building_id": building_id,
                    "customer_count": self.get_building_customer_count(building_id).get("count", 0),
                    "health": self.get_building_health(building_id, include_alerts=False),
                    "known_units": sorted(building_units.get(building_id, set())),
                    "latitude": building_coords.get(building_id, (None, None))[0],
                    "longitude": building_coords.get(building_id, (None, None))[1],
                }
            )

        return {
            "site_id": site_id,
            "scan": self.latest_scan_meta(),
            "radio_scan_summary": radio_scan.get("summary") or {},
            "radios": radios,
            "radio_links": radio_links,
            "addresses": [
                {
                    "address": address,
                    "building_id": entry.get("building_id"),
                    "units": sorted(entry.get("units") or []),
                    "network_names": sorted(entry.get("network_names") or []),
                    "latitude": address_coords.get(address, (None, None))[0],
                    "longitude": address_coords.get(address, (None, None))[1],
                }
                for address, entry in sorted(address_units.items())
            ],
            "buildings": buildings,
        }

    def get_building_health(self, building_id: str, include_alerts: bool) -> dict[str, Any]:
        scan_id = self.latest_scan_id()
        devices = self._device_rows_for_prefix(scan_id, building_id)
        outliers = self._outlier_rows_for_prefix(scan_id, building_id)
        host_rows = self.db.execute(
            """
            select d.identity, bh.ip, bh.on_interface, bh.vid, bh.mac, bh.local, bh.external
            from bridge_hosts bh
            left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
            where bh.scan_id=? and d.identity like ?
            order by d.identity, bh.on_interface
            """,
            (scan_id, f"{building_id}%"),
        ).fetchall()
        probable_cpes = [dict(r) for r in host_rows if is_probable_customer_bridge_host(dict(r))]
        result = {
            "building_id": building_id,
            "scan": self.latest_scan_meta(),
            "device_count": len(devices),
            "devices": devices,
            "outlier_count": len(outliers),
            "outliers": outliers[:100],
            "probable_cpe_count": len(probable_cpes),
            "probable_cpes": probable_cpes[:200],
            "tauc_summary": self._tauc_summary(),
            "vilo_summary": self._vilo_summary(),
        }
        site_id = building_id.split(".")[0]
        if include_alerts and self.alerts and site_id:
            result["active_alerts"] = self._alerts_for_site(site_id)
        return result

    def _building_address_record(self, building_id: str) -> dict[str, Any] | None:
        building_id = canonical_scope(building_id)
        if not building_id:
            return None
        addresses: dict[str, dict[str, Any]] = {}
        for row in load_tauc_nycha_audit_rows():
            expected_prefix = canonical_scope(row.get("expected_prefix"))
            location = str(row.get("expected_location") or "").strip()
            if expected_prefix != building_id or not location:
                continue
            entry = addresses.setdefault(
                location,
                {
                    "address": location,
                    "building_id": building_id,
                    "units": set(),
                    "network_names": set(),
                },
            )
            unit = parse_unit_token(row.get("expected_unit"))
            if unit:
                entry["units"].add(unit)
            network_name = str(row.get("networkName") or "").strip()
            if network_name:
                entry["network_names"].add(network_name)
        if addresses:
            best = max(addresses.values(), key=lambda entry: (len(entry["units"]), len(entry["network_names"]), entry["address"]))
            return {
                "address": best["address"],
                "building_id": best["building_id"],
                "units": sorted(best["units"]),
                "network_names": sorted(best["network_names"]),
            }
        site_id = canonical_scope(building_id.split(".")[0])
        topology = self._site_topology_cache.get(site_id)
        if topology is None:
            topology = self.get_site_topology(site_id)
            self._site_topology_cache[site_id] = topology
        return next((row for row in (topology.get("addresses") or []) if canonical_scope(row.get("building_id")) == canonical_scope(building_id)), None)

    def _exact_unit_port_matches(self, building_id: str) -> list[dict[str, Any]]:
        building_id = canonical_scope(building_id)
        matches: list[dict[str, Any]] = []
        for row in load_tauc_nycha_audit_rows():
            expected_prefix = canonical_scope(row.get("expected_prefix"))
            if expected_prefix != building_id:
                continue
            unit = parse_unit_token(row.get("expected_unit"))
            if not unit:
                continue
            actual_identity = canonical_identity(row.get("actual_identity"))
            actual_interface = str(row.get("actual_interface") or "").strip()
            if not actual_identity or not actual_interface:
                continue
            matches.append(
                {
                    "network_name": str(row.get("networkName") or "").strip(),
                    "unit": unit,
                    "classification": str(row.get("classification") or "").strip(),
                    "switch_identity": actual_identity,
                    "interface": actual_interface,
                    "mac": norm_mac(row.get("tauc_mac") or row.get("mac") or ""),
                    "evidence_sources": ["tauc_audit_exact_access_match"],
                }
            )
        return sorted(matches, key=lambda r: (r["unit"], r["switch_identity"], r["interface"]))

    def _nycha_inventory_rows_for_address(self, address: str) -> list[dict[str, str]]:
        target = normalize_address_text(address)
        rows: list[dict[str, str]] = []
        for row in load_nycha_info_rows():
            if normalize_address_text(row.get("Address")) != target:
                continue
            unit = parse_unit_token(row.get("Unit"))
            if not unit:
                continue
            rows.append(row)
        return rows

    def _direct_neighbor_edges(self, identity: str, ip: str) -> list[dict[str, Any]]:
        scan_id = self.latest_scan_id()
        rows = self.db.execute(
            "select interface, neighbor_identity, neighbor_address, platform, version from neighbors where scan_id=? and ip=? order by interface, neighbor_identity",
            (scan_id, ip),
        ).fetchall()
        edges: list[dict[str, Any]] = []
        for row in rows:
            interface = str(row["interface"] or "")
            if not is_direct_physical_interface(interface):
                continue
            neighbor_identity = canonical_identity(row["neighbor_identity"])
            if not neighbor_identity:
                continue
            edges.append(
                {
                    "from_identity": canonical_identity(identity),
                    "from_interface": interface.split(",", 1)[0],
                    "to_identity": neighbor_identity,
                    "neighbor_address": row["neighbor_address"],
                    "platform": row["platform"],
                    "version": row["version"],
                }
            )
        return edges

    def _address_inventory_online_unit_evidence(self, building_id: str, address: str) -> list[dict[str, Any]]:
        building_id = canonical_scope(building_id)
        if not building_id or not address:
            return []
        scan_id = self.latest_scan_id()
        nycha_rows = self._nycha_inventory_rows_for_address(address)
        if not nycha_rows:
            return []
        site_id = canonical_scope(building_id.split(".")[0])
        ppp_rows = [
            dict(r)
            for r in self.db.execute(
                """
                select p.router_ip, p.name, p.service, p.caller_id, p.address, p.uptime, d.identity
                from router_ppp_active p
                left join devices d on d.scan_id=p.scan_id and d.ip=p.router_ip
                where p.scan_id=? and d.identity like ?
                order by d.identity, p.name
                """,
                (scan_id, f"{site_id}%"),
            ).fetchall()
        ]
        ppp_by_name = {str(row.get("name") or "").strip(): row for row in ppp_rows if str(row.get("name") or "").strip()}
        arp_rows = [
            dict(r)
            for r in self.db.execute(
                """
                select a.router_ip, a.address, a.mac, a.interface, a.dynamic
                from router_arp a
                left join devices d on d.scan_id=a.scan_id and d.ip=a.router_ip
                where a.scan_id=? and d.identity like ?
                """,
                (scan_id, f"{site_id}%"),
            ).fetchall()
        ]
        arp_by_mac = {norm_mac(row.get("mac") or ""): row for row in arp_rows if norm_mac(row.get("mac") or "")}

        online_units: list[dict[str, Any]] = []
        for row in nycha_rows:
            unit = parse_unit_token(row.get("Unit"))
            if not unit:
                continue
            network_name = str(row.get("PPPoE") or "").strip()
            mac = norm_mac(row.get("MAC Address") or row.get("mac") or "")
            sources: list[str] = []
            if network_name and network_name in ppp_by_name:
                sources.append("router_pppoe_session")
            if mac and mac in arp_by_mac:
                sources.append("router_arp")
            if not sources:
                continue
            online_units.append(
                {
                    "unit": unit,
                    "network_name": network_name or None,
                    "mac": mac or None,
                    "sources": sorted(set(sources)),
                }
            )
        return online_units

    def get_building_model(self, building_id: str) -> dict[str, Any]:
        building_id = canonical_scope(building_id)
        if not building_id:
            raise ValueError("building_id is required")
        address_record = self._building_address_record(building_id) or {}
        building_health = self.get_building_health(building_id, include_alerts=False)
        customer_count = self.get_building_customer_count(building_id)
        exact_matches = self._exact_unit_port_matches(building_id)
        ppp_unit_evidence = self._ppp_unit_evidence_for_building(building_id)
        scan_id = self.latest_scan_id()
        nycha_rows = self._nycha_inventory_rows_for_address(str(address_record.get("address") or ""))
        nycha_by_unit: dict[str, dict[str, str]] = {}
        nycha_by_mac: dict[str, dict[str, str]] = {}
        for row in nycha_rows:
            unit = parse_unit_token(row.get("Unit"))
            if not unit:
                continue
            nycha_by_unit.setdefault(unit, row)
            mac = norm_mac(row.get("MAC Address") or row.get("mac") or "")
            if mac:
                nycha_by_mac[mac] = row

        live_bridge_hits = [
            dict(r)
            for r in self.db.execute(
                """
                select d.identity, bh.ip, bh.on_interface, bh.vid, bh.mac, bh.local, bh.external
                from bridge_hosts bh
                left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                where bh.scan_id=? and d.identity like ? and bh.local=0 and bh.on_interface like 'ether%'
                order by d.identity, bh.on_interface, bh.mac
                """,
                (scan_id, f"{building_id}%"),
            ).fetchall()
        ]
        live_bridge_hits = [row for row in live_bridge_hits if is_probable_customer_bridge_host(row)]
        bridge_hit_by_mac = {norm_mac(row.get("mac") or ""): row for row in live_bridge_hits if norm_mac(row.get("mac") or "")}

        exact_keys = {(row["unit"], row["switch_identity"], row["interface"]) for row in exact_matches}
        for mac, row in nycha_by_mac.items():
            hit = bridge_hit_by_mac.get(mac)
            unit = parse_unit_token(row.get("Unit"))
            if not hit or not unit:
                continue
            key = (unit, canonical_identity(hit.get("identity")), str(hit.get("on_interface") or "").strip())
            if key in exact_keys:
                continue
            exact_matches.append(
                {
                    "network_name": str(row.get("PPPoE") or "").strip(),
                    "unit": unit,
                    "classification": "nycha_info_mac_bridge_match",
                    "switch_identity": canonical_identity(hit.get("identity")),
                    "interface": str(hit.get("on_interface") or "").strip(),
                    "mac": mac,
                    "evidence_sources": ["nycha_info_mac", "bridge_host"],
                }
            )
            exact_keys.add(key)

        exact_matches = sorted(exact_matches, key=lambda r: (r["unit"], r["switch_identity"], r["interface"]))
        match_by_switch: dict[str, list[dict[str, Any]]] = {}
        for match in exact_matches:
            match_by_switch.setdefault(match["switch_identity"], []).append(match)

        devices = building_health.get("devices") or []
        switches: list[dict[str, Any]] = []
        direct_edges: list[dict[str, Any]] = []
        for device in devices:
            identity = canonical_identity(device.get("identity"))
            ip = str(device.get("ip") or "")
            if not identity or not ip:
                continue
            served_units = sorted({m["unit"] for m in match_by_switch.get(identity, [])})
            served_floors = sorted({int(re.match(r"(\d+)", unit).group(1)) for unit in served_units if re.match(r"(\d+)", unit)})
            edges = self._direct_neighbor_edges(identity, ip)
            direct_edges.extend(edges)
            switches.append(
                {
                    "identity": identity,
                    "ip": ip,
                    "model": device.get("model"),
                    "version": device.get("version"),
                    "served_units": served_units,
                    "served_floors": served_floors,
                    "exact_match_count": len(match_by_switch.get(identity, [])),
                    "direct_neighbors": edges,
                }
            )

        radios = [
            {
                "name": str(radio.get("name") or ""),
                "type": str(radio.get("type") or ""),
                "model": str(radio.get("model") or ""),
                "status": str(radio.get("status") or ""),
            }
            for radio in (self.get_site_topology(building_id.split(".")[0]).get("radios") or [])
            if canonical_scope(radio.get("resolved_building_id")) == building_id
        ]

        ppp_evidence_by_unit = {str(row.get("unit") or ""): row for row in ppp_unit_evidence if str(row.get("unit") or "")}
        known_units = sorted(set(address_record.get("units") or []) | set(ppp_evidence_by_unit))
        exact_unit_set = {row["unit"] for row in exact_matches}
        ppp_rows = [
            dict(r)
            for r in self.db.execute(
                """
                select p.router_ip, p.name, p.service, p.caller_id, p.address, p.uptime, d.identity
                from router_ppp_active p
                left join devices d on d.scan_id=p.scan_id and d.ip=p.router_ip
                where p.scan_id=?
                order by p.name
                """,
                (scan_id,),
            ).fetchall()
        ]
        ppp_by_name = {str(row.get("name") or "").strip(): row for row in ppp_rows if str(row.get("name") or "").strip()}
        arp_rows = [
            dict(r)
            for r in self.db.execute(
                "select router_ip, address, mac, interface, dynamic from router_arp where scan_id=?",
                (scan_id,),
            ).fetchall()
        ]
        arp_by_mac = {norm_mac(row.get("mac") or ""): row for row in arp_rows if norm_mac(row.get("mac") or "")}
        unit_state_decisions: list[dict[str, Any]] = []
        exact_match_by_unit = {row["unit"]: row for row in exact_matches}
        for unit in known_units:
            inventory = nycha_by_unit.get(unit, {})
            network_name = str(inventory.get("PPPoE") or "").strip()
            mac = norm_mac(inventory.get("MAC Address") or inventory.get("mac") or "")
            sources: list[str] = []
            state = "unknown"
            exact = exact_match_by_unit.get(unit)
            ppp_evidence = ppp_evidence_by_unit.get(unit)
            if exact:
                state = "online"
                sources.extend(exact.get("evidence_sources") or ["bridge_host"])
            if ppp_evidence:
                state = "online"
                sources.extend(ppp_evidence.get("sources") or ["router_pppoe_session"])
                network_name = network_name or str(ppp_evidence.get("network_name") or "").strip()
                mac = mac or norm_mac(ppp_evidence.get("mac") or "")
            if network_name and network_name in ppp_by_name:
                state = "online"
                sources.append("router_pppoe_session")
            if mac and mac in arp_by_mac:
                state = "online"
                sources.append("router_arp")
            unit_state_decisions.append(
                {
                    "unit": unit,
                    "state": state,
                    "network_name": network_name or None,
                    "mac": mac or None,
                    "sources": sorted(set(sources)),
                    "switch_identity": exact.get("switch_identity") if exact else None,
                    "interface": exact.get("interface") if exact else None,
                }
            )

        live_port_pool = [
            {
                "switch_identity": canonical_identity(row.get("identity")),
                "interface": row.get("on_interface"),
                "mac": norm_mac(row.get("mac") or ""),
                "vid": row.get("vid"),
            }
            for row in (customer_count.get("results") or [])
        ]
        coverage = {
            "known_unit_count": len(known_units),
            "exact_unit_port_match_count": len(exact_matches),
            "exact_unit_port_coverage_pct": round((len(exact_unit_set) / len(known_units) * 100.0), 1) if known_units else 0.0,
            "live_port_pool_count": len(live_port_pool),
            "switch_count": len(switches),
            "direct_neighbor_edge_count": len(direct_edges),
        }
        return {
            "building_id": building_id,
            "site_id": building_id.split(".")[0],
            "address": address_record.get("address"),
            "known_units": known_units,
            "floors_inferred_from_units": max((int(re.match(r"(\d+)", unit).group(1)) for unit in known_units if re.match(r"(\d+)", unit)), default=0),
            "exact_unit_port_matches": exact_matches,
            "unit_state_decisions": unit_state_decisions,
            "live_port_pool": live_port_pool,
            "switches": switches,
            "direct_neighbor_edges": direct_edges,
            "radios": radios,
            "coverage": coverage,
            "data_gaps": {
                "building_geometry": "Jake has no authoritative facade/massing dataset for this building.",
                "full_unit_to_port_mapping": "Only TAUC-audited unit labels are exact today; the rest of the live ports are unmatched pool entries.",
                "switch_floor_placement": "Switch floor placement is only exact where unit-port matches exist; otherwise it remains inferred.",
            },
        }

    def get_vilo_server_info(self) -> dict[str, Any]:
        return self.vilo_api.summary() if self.vilo_api else {"configured": False}

    def get_vilo_inventory(self, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        return self.vilo_api.get_inventory(page_index, page_size)

    def audit_vilo_inventory(self, site_id: str | None = None, building_id: str | None = None, limit: int = 500) -> dict[str, Any]:
        return self.get_vilo_inventory_audit(site_id, building_id, limit)

    def search_vilo_inventory(self, filter_group: list[dict[str, Any]] | None = None, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        return self.vilo_api.search_inventory(filter_group or [], page_index, page_size)

    def get_vilo_subscribers(self, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        return self.vilo_api.get_subscribers(page_index, page_size)

    def search_vilo_subscribers(self, filter_group: list[dict[str, Any]] | None = None, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        return self.vilo_api.search_subscribers(filter_group or [], page_index, page_size)

    def get_vilo_networks(self, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        return self.vilo_api.get_networks(page_index, page_size)

    def search_vilo_networks(self, filter_group: list[dict[str, Any]] | None = None, sort_group: list[dict[str, Any]] | None = None, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        return self.vilo_api.search_networks(filter_group or [], sort_group or [], page_index, page_size)

    def get_vilo_devices(self, network_id: str) -> dict[str, Any]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        return self.vilo_api.get_devices(network_id)

    def _nearby_vilo_mac_candidates(self, mac: str | None, limit: int = 5) -> list[dict[str, Any]]:
        needle = norm_mac(mac or "")
        if not needle:
            return []

        candidates: dict[str, dict[str, Any]] = {}
        for row in self._latest_vilo_scan_sightings():
            candidate_mac = norm_mac(row.get("mac") or "")
            relation = related_mac_delta(needle, candidate_mac)
            if not candidate_mac or candidate_mac == needle or not relation:
                continue
            current = candidates.get(candidate_mac) or {}
            if (not current) or int(relation.get("distance") or 999999) < int(current.get("mac_delta") or 999999):
                candidates[candidate_mac] = {
                    "mac": candidate_mac,
                    "mac_delta": int(relation.get("distance") or 0),
                    "mac_relation": relation.get("kind"),
                    "identity": row.get("identity"),
                    "building_id": row.get("building_id"),
                    "on_interface": row.get("on_interface"),
                    "vid": row.get("vid"),
                    "port_comment": row.get("port_comment") or "",
                    "port_status": row.get("port_status"),
                    "source": "latest_vilo_scan",
                }

        network_rows = self._fetch_vilo_network_rows(limit=3000, page_size=50)
        for row in network_rows:
            candidate_mac = norm_mac(row.get("main_vilo_mac") or "")
            relation = related_mac_delta(needle, candidate_mac)
            if not candidate_mac or candidate_mac == needle or not relation:
                continue
            current = candidates.get(candidate_mac) or {}
            if (not current) or int(relation.get("distance") or 999999) < int(current.get("mac_delta") or 999999):
                candidates[candidate_mac] = {
                    "mac": candidate_mac,
                    "mac_delta": int(relation.get("distance") or 0),
                    "mac_relation": relation.get("kind"),
                    "network_id": row.get("network_id"),
                    "network_name": row.get("network_name"),
                    "network_status": row.get("network_status"),
                    "source": "vilo_cloud_network",
                }

        ranked = sorted(
            candidates.values(),
            key=lambda row: (
                int(row.get("mac_delta") or 999999),
                0 if row.get("identity") else 1,
                str(row.get("identity") or row.get("network_name") or ""),
            ),
        )
        return ranked[: max(1, int(limit))]

    def _nearby_vilo_device_candidates(self, mac: str | None, limit: int = 5) -> list[dict[str, Any]]:
        needle = norm_mac(mac or "")
        if not needle or not self.vilo_api:
            return []
        candidates: list[dict[str, Any]] = []
        seen_networks: set[str] = set()
        for row in self._nearby_vilo_mac_candidates(needle, limit=8):
            network_id = str(row.get("network_id") or "").strip()
            if not network_id or network_id in seen_networks:
                continue
            seen_networks.add(network_id)
            try:
                payload = self.get_vilo_devices(network_id)
            except Exception:
                continue
            devices = [dict(item) for item in ((((payload or {}).get("data") or {}).get("vilo_info_list")) or [])]
            for device in devices:
                candidate_mac = norm_mac(device.get("vilo_mac") or "")
                relation = related_mac_delta(needle, candidate_mac)
                if not candidate_mac or candidate_mac == needle or not relation:
                    continue
                candidates.append(
                    {
                        "mac": candidate_mac,
                        "mac_delta": int(relation.get("distance") or 0),
                        "mac_relation": relation.get("kind"),
                        "network_id": network_id,
                        "network_name": row.get("network_name"),
                        "vilo_name": device.get("vilo_name"),
                        "firmware_ver": device.get("firmware_ver"),
                        "ip": device.get("ip"),
                        "is_main": device.get("is_main"),
                        "status": device.get("vilo_status"),
                        "source": "vilo_cloud_device_list",
                    }
                )
        candidates.sort(
            key=lambda item: (
                int(item.get("mac_delta") or 999999),
                0 if item.get("is_main") else 1,
                str(item.get("network_name") or ""),
                str(item.get("mac") or ""),
            )
        )
        return candidates[: max(1, int(limit))]

    def _vilo_cloud_candidates_for_exact_macs(self, macs: list[str], limit: int = 8) -> list[dict[str, Any]]:
        if not self.vilo_api:
            return []
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for mac in macs:
            normalized = norm_mac(mac or "")
            if not normalized:
                continue
            network_payload = self.search_vilo_networks(
                [{"key": "main_vilo_mac", "value": normalized.replace(":", "").upper()}],
                [],
                1,
                10,
            )
            networks = [dict(r) for r in (((network_payload or {}).get("data") or {}).get("network_list") or [])]
            inventory_payload = self.search_vilo_inventory([{"key": "device_mac", "value": normalized.upper()}], 1, 10)
            inventories = [dict(r) for r in (((inventory_payload or {}).get("data") or {}).get("device_list") or [])]
            inventory = inventories[0] if inventories else {}
            for network in networks:
                key = (str(network.get("network_id") or ""), normalized)
                if key in seen:
                    continue
                seen.add(key)
                row = {
                    "mac": normalized,
                    "network_id": network.get("network_id"),
                    "network_name": network.get("network_name"),
                    "network_status": network.get("network_status"),
                    "firmware_version": network.get("firmware_version"),
                    "public_ip_address": network.get("public_ip_address"),
                    "wan_ip_address": network.get("wan_ip_address"),
                    "inventory_status": inventory.get("status"),
                    "device_sn": inventory.get("device_sn"),
                    "source": "vilo_cloud_exact_lookup",
                }
                network_id = str(network.get("network_id") or "").strip()
                if network_id:
                    try:
                        devices_payload = self.get_vilo_devices(network_id)
                        devices = [dict(item) for item in ((((devices_payload or {}).get("data") or {}).get("vilo_info_list")) or [])]
                    except Exception:
                        devices = []
                    for device in devices:
                        if norm_mac(device.get("vilo_mac") or "") == normalized:
                            row["local_ip"] = device.get("ip")
                            row["vilo_name"] = device.get("vilo_name")
                            row["firmware_ver"] = device.get("firmware_ver")
                            row["vilo_status"] = device.get("vilo_status")
                            break
                out.append(row)
        out.sort(key=lambda item: (str(item.get("network_name") or ""), str(item.get("mac") or "")))
        return out[: max(1, int(limit))]

    def _related_cpe_mac_candidates(self, mac: str | None, limit: int = 5) -> list[dict[str, Any]]:
        needle = norm_mac(mac or "")
        if not needle:
            return []
        scan_id = self.latest_scan_id()
        rows = [
            dict(r)
            for r in self.db.execute(
                """
                select d.identity, bh.ip, bh.mac, bh.on_interface, bh.vid, bh.local, bh.external
                from bridge_hosts bh
                left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                where bh.scan_id=? and bh.external=1 and bh.local=0
                order by d.identity, bh.on_interface, bh.mac
                """,
                (scan_id,),
            ).fetchall()
        ]
        out: list[dict[str, Any]] = []
        for row in rows:
            candidate_mac = norm_mac(row.get("mac") or "")
            relation = related_mac_delta(needle, candidate_mac)
            if not candidate_mac or candidate_mac == needle or not relation:
                continue
            out.append(
                {
                    "mac": candidate_mac,
                    "mac_delta": int(relation.get("distance") or 0),
                    "mac_relation": relation.get("kind"),
                    "vendor": relation.get("vendor"),
                    "identity": canonical_identity(row.get("identity")),
                    "on_interface": row.get("on_interface"),
                    "vid": row.get("vid"),
                }
            )
        out.sort(key=lambda row: (int(row.get("mac_delta") or 999999), 0 if row.get("identity") else 1, str(row.get("identity") or ""), str(row.get("on_interface") or "")))
        return out[: max(1, int(limit))]

    def get_vilo_target_summary(self, mac: str | None = None, network_id: str | None = None, network_name: str | None = None) -> dict[str, Any]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")

        normalized_mac = norm_mac(mac or "")
        target_network: dict[str, Any] | None = None
        target_inventory: dict[str, Any] | None = None

        if network_id:
            payload = self.search_vilo_networks([{"key": "network_id", "value": str(network_id).strip()}], [], 1, 10)
            rows = [dict(r) for r in (((payload or {}).get("data") or {}).get("network_list") or [])]
            if rows:
                target_network = rows[0]
        elif normalized_mac:
            payload = self.search_vilo_networks([{"key": "main_vilo_mac", "value": normalized_mac.replace(":", "").upper()}], [], 1, 10)
            rows = [dict(r) for r in (((payload or {}).get("data") or {}).get("network_list") or [])]
            if rows:
                target_network = rows[0]
        elif network_name:
            requested = str(network_name).strip().lower()
            rows = self._fetch_vilo_network_rows(limit=3000, page_size=50)
            exact = [dict(r) for r in rows if str(r.get("network_name") or "").strip().lower() == requested]
            if exact:
                target_network = exact[0]

        inventory_filter: list[dict[str, Any]] = []
        if normalized_mac:
            inventory_filter = [{"key": "device_mac", "value": normalized_mac.upper()}]
        elif target_network and target_network.get("main_vilo_mac"):
            inventory_filter = [{"key": "device_mac", "value": norm_mac(target_network.get("main_vilo_mac")).upper()}]
        if inventory_filter:
            payload = self.search_vilo_inventory(inventory_filter, 1, 10)
            rows = [dict(r) for r in (((payload or {}).get("data") or {}).get("device_list") or [])]
            if rows:
                target_inventory = rows[0]

        if not target_network and not target_inventory:
            return {
                "found": False,
                "query": {
                    "mac": normalized_mac or None,
                    "network_id": network_id or None,
                    "network_name": network_name or None,
                },
                "nearby_mac_candidates": self._nearby_vilo_mac_candidates(normalized_mac, limit=5) if normalized_mac else [],
                "nearby_device_candidates": self._nearby_vilo_device_candidates(normalized_mac, limit=5) if normalized_mac else [],
            }

        effective_network_id = str((target_network or {}).get("network_id") or network_id or "").strip()
        devices_payload = self.get_vilo_devices(effective_network_id) if effective_network_id else {"data": {"vilo_info_list": []}}
        device_rows = [dict(r) for r in ((((devices_payload or {}).get("data") or {}).get("vilo_info_list")) or [])]

        effective_mac = normalized_mac or norm_mac((target_network or {}).get("main_vilo_mac") or (target_inventory or {}).get("device_mac") or "")
        trace = self.trace_mac(effective_mac, include_bigmac=False) if effective_mac else {"mac": None, "trace_status": "not_queried"}
        bridge = trace.get("bridge_hosts") or trace
        best = bridge.get("best_hit") or bridge.get("best_guess") or {}

        network_status = int((target_network or {}).get("network_status") or 0)
        wan_ip = str((target_network or {}).get("wan_ip_address") or "").strip()
        public_ip = str((target_network or {}).get("public_ip_address") or "").strip()
        device_online_num = int((target_network or {}).get("device_online_num") or 0)
        best_identity = str(best.get("identity") or "").strip()
        best_building = str(best.get("building_id") or "").strip()
        best_interface = str(best.get("on_interface") or "").strip()

        likely_issue = "unknown"
        likely_reason = "Jake needs more corroborating evidence to rank the likely failure domain."
        nearby_mac_candidates = self._nearby_vilo_mac_candidates(effective_mac, limit=5) if effective_mac else []
        nearby_device_candidates = self._nearby_vilo_device_candidates(effective_mac, limit=5) if effective_mac else []
        device_local_ip = str((device_rows[0] or {}).get("ip") or "").strip() if device_rows else ""
        local_plane_arp_mac = ""
        shared_local_ip_candidates: list[dict[str, Any]] = []
        if device_local_ip:
            arp_rows = [dict(r) for r in self.db.execute(
                """
                select bh.mac, d.identity, bh.on_interface, bh.vid
                from bridge_hosts bh
                left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                where bh.scan_id=? and bh.ip=?
                order by d.identity, bh.on_interface, bh.mac
                """,
                (self.latest_scan_id(), device_local_ip),
            ).fetchall()]
            for row in arp_rows:
                candidate = norm_mac(row.get("mac") or "")
                if candidate:
                    local_plane_arp_mac = candidate
                    break
            lookup_macs: list[str] = []
            if effective_mac:
                lookup_macs.extend(adjacent_mac_variants(effective_mac))
            if local_plane_arp_mac:
                lookup_macs.extend([local_plane_arp_mac, *adjacent_mac_variants(local_plane_arp_mac)])
            dedup_lookup: list[str] = []
            seen_lookup: set[str] = set()
            for item in lookup_macs:
                normalized = norm_mac(item)
                if not normalized or normalized in seen_lookup or normalized == effective_mac:
                    continue
                seen_lookup.add(normalized)
                dedup_lookup.append(normalized)
            shared_local_ip_candidates = [
                row for row in self._vilo_cloud_candidates_for_exact_macs(dedup_lookup, limit=8)
                if str(row.get("local_ip") or "").strip() == device_local_ip
            ]
        if network_status == 0 and not best_identity and (not wan_ip or wan_ip == "0.0.0.0"):
            likely_issue = "power_or_local_patch"
            likely_reason = "The Vilo cloud object is offline, there is no latest-scan sighting, and WAN addressing is missing. That points first to power, patching, or local CPE failure."
        elif network_status == 0 and best_identity and (not wan_ip or wan_ip == "0.0.0.0"):
            likely_issue = "wan_or_vlan_upstream"
            likely_reason = f"The Vilo MAC is still seen at {best_identity} {best_interface}, but the cloud object is offline and WAN addressing is missing. That points more toward WAN DHCP, VLAN, or upstream path issues than pure power loss."
        elif network_status == 0 and best_identity and public_ip:
            likely_issue = "service_plane_or_stale_cloud_state"
            likely_reason = "The Vilo cloud object reports offline even though the device still has public path evidence and is physically seen. Treat this as likely stale cloud state or a higher-layer service issue."
        elif network_status == 1 and wan_ip and device_online_num == 0:
            likely_issue = "lan_side_or_client_side"
            likely_reason = "The Vilo cloud object is online and has WAN addressing, but it shows no downstream online devices. That points more toward LAN-side or client-side issues than upstream transport."
        elif network_status == 1 and (not wan_ip or wan_ip == "0.0.0.0"):
            likely_issue = "wan_assignment_failure"
            likely_reason = "The Vilo cloud object is online but has no usable WAN IP. Check upstream DHCP, VLAN tagging, and bridge forwarding."
        elif network_status == 1 and wan_ip and public_ip:
            likely_issue = "upstream_likely_healthy"
            likely_reason = "The Vilo cloud object is online with WAN and public IPs. The upstream path is likely present; focus on LAN-side, client-side, or intermittent issues."

        if nearby_mac_candidates and int(nearby_mac_candidates[0].get("mac_delta") or 999999) == 1:
            close = nearby_mac_candidates[0]
            candidate_location = " ".join(
                str(part).strip()
                for part in [close.get("identity"), close.get("on_interface")]
                if str(part or "").strip()
            ).strip()
            likely_reason += (
                f" There is also a Vilo MAC exactly one increment away ({close.get('mac')})"
                f"{' seen at ' + candidate_location if candidate_location else ''}."
                " Treat that as a strong hint that the expected device may be patched into the wrong port,"
                " mislabeled by one MAC value, or leaking WAN/LAN bridging in a way that exposes the adjacent hardware MAC."
            )
        if shared_local_ip_candidates:
            names = ", ".join(
                f"{row.get('network_name') or row.get('network_id')} ({row.get('mac')})"
                for row in shared_local_ip_candidates[:3]
            )
            likely_issue = "stale_duplicate_cloud_state"
            likely_reason += (
                f" The local control IP {device_local_ip} is also tied in Vilo cloud to adjacent offline object(s): {names}."
                " Treat that as strong evidence of stale duplicate onboarding state or alternate-interface MAC drift,"
                " not as proof that each of those MACs is a separate healthy deployed unit."
            )

        return {
            "found": True,
            "query": {
                "mac": normalized_mac or None,
                "network_id": network_id or None,
                "network_name": network_name or None,
            },
            "network": target_network,
            "inventory": target_inventory,
            "devices": device_rows,
            "label_candidates": self._derive_vilo_label_candidates(target_network, target_inventory, device_rows),
            "trace": trace,
            "likely_issue": likely_issue,
            "likely_reason": likely_reason,
            "nearby_mac_candidates": nearby_mac_candidates,
            "nearby_device_candidates": nearby_device_candidates,
            "local_control_plane": {
                "ip": device_local_ip or None,
                "live_arp_mac": local_plane_arp_mac or None,
                "shared_cloud_candidates": shared_local_ip_candidates,
            },
            "placement_hint": {
                "identity": best_identity or None,
                "building_id": best_building or None,
                "on_interface": best_interface or None,
                "vid": best.get("vid"),
            },
        }

    def _transport_radio_rows(self) -> list[dict[str, Any]]:
        return [dict(r) for r in (load_transport_radio_scan().get("results") or [])]

    def _transport_radio_name_index(self) -> dict[str, dict[str, Any]]:
        rows = self._transport_radio_rows()
        index: dict[str, dict[str, Any]] = {}
        for row in rows:
            name = str(row.get("name") or "").strip()
            if name:
                index[normalize_free_text(name)] = row
            for mac in [row.get("device_mac"), *(row.get("wlan_macs") or []), *(row.get("initiator_macs") or [])]:
                norm = norm_mac(str(mac or ""))
                if norm and norm != str(mac or "").lower():
                    index[norm] = row
        return index

    def get_transport_radio_summary(self, query: str | None = None, name: str | None = None, ip: str | None = None, mac: str | None = None) -> dict[str, Any]:
        rows = self._transport_radio_rows()
        needle_name = normalize_free_text(name or query or "")
        needle_ip = str(ip or "").strip()
        needle_mac = norm_mac(mac or "")
        site_hint_match = re.search(r"\b(\d{6})[-.]", str(name or query or ""))
        fallback_site_id = canonical_scope(site_hint_match.group(1)) if site_hint_match else None
        netbox_match = self._match_netbox_radio(query=query, name=name, ip=ip, site_id=fallback_site_id)

        matches: list[dict[str, Any]] = []
        for row in rows:
            row_name = str(row.get("name") or "").strip()
            row_ip = str(row.get("ip") or "").strip()
            candidate_macs = {
                norm_mac(str(value))
                for value in [row.get("device_mac"), *(row.get("wlan_macs") or []), *(row.get("initiator_macs") or []), *(row.get("neighbor_macs") or [])]
                if str(value or "").strip()
            }
            if needle_ip and row_ip == needle_ip:
                matches.append(dict(row))
                continue
            if needle_mac and needle_mac in candidate_macs:
                matches.append(dict(row))
                continue
            if needle_name:
                hay = normalize_free_text(row_name)
                if needle_name == hay or needle_name in hay:
                    matches.append(dict(row))
                    continue

        # Prefer matches where the query matches the START of the link name (local end)
        if len(matches) > 1 and needle_name:
            start_matches = [m for m in matches if normalize_free_text(str(m.get("name",""))).startswith(needle_name)]
            if start_matches:
                matches = start_matches

        if not matches:
            if netbox_match:
                status = str(netbox_match.get("status") or "").strip() or None
                return {
                    "found": True,
                    "vendor": "cambium",
                    "site_id": canonical_scope(netbox_match.get("site_id")) or fallback_site_id,
                    "radio": {
                        "name": netbox_match.get("name"),
                        "model": netbox_match.get("device_type"),
                        "ip": netbox_match.get("primary_ip"),
                        "location": netbox_match.get("location"),
                        "status": inventory_radio_status(status),
                        "netbox_status": status,
                        "serial": netbox_match.get("serial"),
                        "sources": ["netbox"],
                    },
                    "peer_names": [],
                    "likely_issue": inventory_radio_status(status),
                    "likely_reason": (
                        "NetBox source of truth shows this radio as active, but Jake does not have a matching current transport scan row yet."
                        if inventory_is_live_expected(status)
                        else "NetBox source of truth has this radio in non-active inventory state, so it should not be treated as an online production node yet."
                    ),
                    "issue_signals": [inventory_radio_status(status)],
                    "inventory_truth": "netbox",
                }
            fallback_match = None
            if fallback_site_id:
                fallback_inventory = self.get_site_radio_inventory(fallback_site_id)
                for row in fallback_inventory.get("radios") or []:
                    row_name = str(row.get("name") or "").strip()
                    row_ip = str(row.get("primary_ip") or "").strip()
                    if needle_ip and row_ip == needle_ip:
                        fallback_match = row
                        break
                    if needle_name:
                        hay = normalize_free_text(row_name)
                        if needle_name == hay or needle_name in hay:
                            fallback_match = row
                            break
            if fallback_match:
                status = str(fallback_match.get("status") or "inventory_only")
                likely_issue = status if status not in {"ok", "inventory_only"} else "inventory_only_no_live_scan"
                likely_reason = (
                    "Jake found this radio in site inventory and alerts, but it is missing from the current transport scan artifact."
                    if status == "inventory_only"
                    else "Jake found this radio through site inventory and active alerts rather than the transport scan artifact."
                )
                return {
                    "found": True,
                    "vendor": str(fallback_match.get("vendor") or "cambium"),
                    "site_id": fallback_site_id,
                    "radio": fallback_match,
                    "peer_names": [],
                    "likely_issue": likely_issue,
                    "likely_reason": likely_reason,
                    "issue_signals": [status],
                }
            return {
                "found": False,
                "query": {"query": query, "name": name, "ip": ip, "mac": needle_mac or None},
            }

        row = matches[0]
        name_index = self._transport_radio_name_index()
        vendor = str(row.get("type") or "")
        radio_name = str(row.get("name") or "")
        site_id = infer_site_from_network_name(str(row.get("topology_site_name") or "")) or canonical_scope(str(row.get("topology_site_name") or "").split()[-1]) if row.get("topology_site_name") else None
        if not site_id:
            resolved = self._resolve_building_from_address(str(row.get("location") or ""))
            best = resolved.get("best_match") or {}
            prefix = canonical_scope(best.get("prefix"))
            site_id = canonical_scope(best.get("site_code")) if best.get("site_code") else (prefix.split(".")[0] if prefix else None)

        replacement = self._netbox_radio_replacement_for_scan_row(row, site_id)
        if replacement:
            status = str(replacement.get("status") or "").strip() or None
            return {
                "found": True,
                "vendor": "cambium",
                "site_id": canonical_scope(replacement.get("site_id")) or site_id,
                "radio": {
                    "name": replacement.get("name"),
                    "model": replacement.get("device_type"),
                    "ip": replacement.get("primary_ip"),
                    "location": replacement.get("location"),
                    "status": inventory_radio_status(status),
                    "netbox_status": status,
                    "serial": replacement.get("serial"),
                    "sources": ["netbox", "stale_transport_scan_replaced"],
                },
                "peer_names": [],
                "likely_issue": "stale_transport_scan_identity",
                "likely_reason": (
                    f"NetBox source of truth shows active radio `{replacement.get('name')}` at {replacement.get('location') or 'this location'} "
                    f"({replacement.get('primary_ip') or 'no management IP'}), while the current transport scan artifact still reports "
                    f"`{row.get('name')}` ({row.get('ip') or 'no management IP'}). Jake is preferring the NetBox identity."
                ),
                "issue_signals": ["netbox_scan_drift", inventory_radio_status(status)],
                "inventory_truth": "netbox",
                "drift": {
                    "location": replacement.get("location"),
                    "netbox_name": replacement.get("name"),
                    "netbox_ip": replacement.get("primary_ip"),
                    "netbox_status": status,
                    "scan_name": row.get("name"),
                    "scan_ip": row.get("ip"),
                    "scan_status": row.get("status"),
                },
            }

        likely_issue = "unknown"
        likely_reason = "Jake needs more evidence before ranking the most likely failure domain."
        issue_signals: list[str] = []

        if vendor == "cambium":
            device_info = row.get("device_info") or {}
            peer_names: list[str] = []
            for peer_mac in row.get("neighbor_macs") or []:
                peer = name_index.get(norm_mac(str(peer_mac)))
                peer_name = str((peer or {}).get("name") or "").strip()
                if peer_name and peer_name != radio_name and peer_name not in peer_names:
                    peer_names.append(peer_name)
            status = str(row.get("status") or "")
            if status != "ok":
                likely_issue = status
                likely_reason = f"The last transport scan could not complete a clean authenticated read from this Cambium radio. Current status is `{status}`."
                issue_signals.append(status)
            elif not row.get("ip"):
                likely_issue = "missing_management_ip"
                likely_reason = "This radio has no management IP in the current transport inventory, so Jake cannot verify live state or alignment counters from this host."
                issue_signals.append("missing_ip")
            else:
                likely_issue = "no_live_rf_stats"
                likely_reason = "Jake can confirm identity, firmware, uptime, reboot reason, and peer relationships, but the cnWave exporter is not returning live RF metrics on this host. RSSI or alignment cannot be proven from current live data."
            return {
                "found": True,
                "vendor": vendor,
                "site_id": site_id,
                "radio": row,
                "peer_names": peer_names,
                "likely_issue": likely_issue,
                "likely_reason": likely_reason,
                "issue_signals": issue_signals,
            }

        if vendor == "siklu":
            flags = ((row.get("log_analysis") or {}).get("flags")) or {}
            modulation_changes = int(flags.get("modulation_change") or 0)
            if str(row.get("status") or "") != "ok":
                likely_issue = str(row.get("status") or "unhealthy")
                likely_reason = f"The last Siklu scan did not complete cleanly. Current status is `{row.get('status')}`."
                issue_signals.append(likely_issue)
            elif modulation_changes >= 500:
                likely_issue = "rf_instability_or_alignment"
                likely_reason = f"This Siklu link shows heavy modulation churn ({modulation_changes} changes) with link/reset history. That is consistent with RF instability, alignment drift, weather sensitivity, or a marginal path."
                issue_signals.extend(["high_modulation_churn", "possible_alignment"])
            elif flags.get("eth_link_down") and flags.get("eth_link_up"):
                likely_issue = "ethernet_handoff_instability"
                likely_reason = "The Siklu logs show Ethernet link down/up events. That points more toward the local handoff, power, or cabling side than pure RF."
                issue_signals.append("eth_flap")
            else:
                likely_issue = "no_major_recent_signal"
                likely_reason = "The saved Siklu logs do not show a single dominant failure signal beyond normal historical records."
            return {
                "found": True,
                "vendor": vendor,
                "site_id": site_id,
                "radio": row,
                "likely_issue": likely_issue,
                "likely_reason": likely_reason,
                "issue_signals": issue_signals,
            }

        return {
            "found": True,
            "vendor": vendor,
            "site_id": site_id,
            "radio": row,
            "likely_issue": likely_issue,
            "likely_reason": likely_reason,
            "issue_signals": issue_signals,
        }

    def get_transport_radio_issues(self, vendor: str | None = None, site_id: str | None = None, limit: int = 10) -> dict[str, Any]:
        rows = self._transport_radio_rows()
        limit = max(1, int(limit))
        filtered: list[dict[str, Any]] = []
        for row in rows:
            if vendor and str(row.get("type") or "") != vendor:
                continue
            if site_id:
                resolved = self.get_transport_radio_summary(name=str(row.get("name") or ""))
                if canonical_scope(resolved.get("site_id")) != canonical_scope(site_id):
                    continue
            filtered.append(dict(row))

        bad_status = [r for r in filtered if str(r.get("status") or "") != "ok"]
        siklu_unstable = []
        for row in filtered:
            if str(row.get("type") or "") != "siklu" or str(row.get("status") or "") != "ok":
                continue
            flags = ((row.get("log_analysis") or {}).get("flags")) or {}
            modulation_changes = int(flags.get("modulation_change") or 0)
            if modulation_changes > 0 or flags.get("eth_link_down") or flags.get("reset_cause"):
                siklu_unstable.append(
                    {
                        "name": row.get("name"),
                        "ip": row.get("ip"),
                        "modulation_changes": modulation_changes,
                        "flags": flags,
                    }
                )
        siklu_unstable.sort(key=lambda r: (int(r.get("modulation_changes") or 0), str(r.get("name") or "")), reverse=True)

        if vendor == "cambium" and site_id and not filtered:
            fallback = self.get_site_radio_inventory(site_id)
            fallback_radios = [row for row in (fallback.get("radios") or []) if str(row.get("vendor") or "") == "cambium"]
            filtered = fallback_radios
            bad_status = [
                {
                    "name": row.get("name"),
                    "type": row.get("vendor"),
                    "status": row.get("status"),
                    "ip": row.get("primary_ip"),
                    "sources": row.get("sources"),
                }
                for row in fallback_radios
                if str(row.get("status") or "") not in {"ok", "inventory_only"}
            ]

        return {
            "vendor": vendor or "all",
            "site_id": canonical_scope(site_id) if site_id else None,
            "radio_count": len(filtered),
            "bad_status": bad_status[:limit],
            "siklu_unstable": siklu_unstable[:limit],
            "summary": load_transport_radio_scan().get("summary") or {},
        }

    def get_radio_handoff_trace(self, query: str | None = None, name: str | None = None) -> dict[str, Any]:
        radio_summary = self.get_transport_radio_summary(query=query, name=name)
        if not radio_summary.get("found") and query:
            cleaned = normalize_free_text(str(query or ""))
            for noise in (
                "what macs are visible on the sfp side of",
                "show the sfp hosts for",
                "show sfp hosts for",
                "sfp hosts for",
                "what macs do you see on the sfp",
                "macs on the sfp side of",
                "radio handoff for",
                "radio handoff trace for",
            ):
                cleaned = cleaned.replace(noise, " ")
            cleaned = " ".join(cleaned.split()).strip()
            if cleaned:
                radio_summary = self.get_transport_radio_summary(query=cleaned)
        if not radio_summary.get("found"):
            return {"found": False, "query": {"query": query, "name": name}}

        radio = dict(radio_summary.get("radio") or {})
        site_id = canonical_scope(radio_summary.get("site_id"))
        topology = self.get_site_topology(site_id) if site_id else {"radios": [], "buildings": [], "radio_links": []}
        radio_name = str(radio.get("name") or "")
        normalized_radio_name = normalize_free_text(radio_name)
        topology_radio = next(
            (
                row
                for row in (topology.get("radios") or [])
                if normalize_free_text(str(row.get("name") or "")) == normalized_radio_name
            ),
            None,
        )
        building_id = canonical_scope((topology_radio or {}).get("resolved_building_id"))
        building_health = self.get_building_health(building_id, include_alerts=False) if building_id else {
            "building_id": None,
            "device_count": 0,
            "devices": [],
            "probable_cpe_count": 0,
            "probable_cpes": [],
        }
        device_rows = building_health.get("devices") or []
        switch_candidates = [
            row for row in device_rows
            if any(token in str(row.get("identity") or "") for token in (".SW", ".RFSW", ".R1", ".R01", ".R"))
        ]
        scan_id = self.latest_scan_id()
        sfp_hosts: list[dict[str, Any]] = []
        if switch_candidates:
            identities = [str(row.get("identity") or "") for row in switch_candidates if str(row.get("identity") or "")]
            placeholders = ",".join("?" for _ in identities)
            rows = self.db.execute(
                f"""
                select d.identity, bh.ip, bh.mac, bh.on_interface, bh.vid, bh.local, bh.external
                from bridge_hosts bh
                left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                where bh.scan_id=? and d.identity in ({placeholders})
                order by d.identity, bh.on_interface, bh.mac
                """,
                [scan_id, *identities],
            ).fetchall()
            sfp_hosts = [dict(r) for r in rows if is_uplink_like_port(dict(r).get("on_interface"))]
        sfp_ports = sorted({f"{row.get('identity')} {row.get('on_interface')}" for row in sfp_hosts})[:20]
        vendor_counts: Counter[str] = Counter(mac_vendor_group(row.get("mac")) for row in sfp_hosts)
        link_rows = [
            row for row in (topology.get("radio_links") or [])
            if normalized_radio_name in {
                normalize_free_text(str(row.get("from_label") or "")),
                normalize_free_text(str(row.get("to_label") or "")),
            }
        ]
        return {
            "found": True,
            "site_id": site_id,
            "radio": radio,
            "topology_radio": topology_radio,
            "building_id": building_id,
            "building_health": building_health,
            "switch_candidates": switch_candidates,
            "link_rows": link_rows,
            "sfp_host_count": len(sfp_hosts),
            "sfp_ports": sfp_ports,
            "sfp_vendor_counts": dict(sorted(vendor_counts.items())),
            "sfp_host_sample": sfp_hosts[:30],
        }

    def get_site_radio_inventory(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        topology = self.get_site_topology(site_id)
        alerts = self._alerts_for_site(site_id) if self.alerts else []
        netbox_inventory = self._netbox_site_inventory(site_id) if self.netbox else []

        radios: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        for row in topology.get("radios") or []:
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            seen_names.add(normalize_free_text(name))
            radios.append(
                {
                    "name": name,
                    "vendor": str(row.get("type") or ""),
                    "model": str(row.get("model") or ""),
                    "status": str(row.get("status") or ""),
                    "primary_ip": str(row.get("ip") or "").strip() or None,
                    "location": str(row.get("location") or "").strip() or None,
                    "building_id": canonical_scope(row.get("resolved_building_id")),
                    "sources": ["transport_scan"],
                    "alerts": row.get("alerts") or [],
                }
            )

        for row in netbox_inventory:
            name = str(row.get("name") or "").strip()
            if not re.search(r"\bV(?:1000|2000|3000|5000)\b", name, re.I):
                continue
            normalized_name = normalize_free_text(name)
            if normalized_name in seen_names:
                continue
            location = str(row.get("location") or "").strip()
            building_id = None
            label_match = re.search(r"(\d{6,7})-(\d{3})-V(?:1000|2000|3000|5000)", name, re.I)
            if label_match:
                parsed_site = canonical_scope(label_match.group(1)[-6:])
                if parsed_site == site_id:
                    building_id = f"{site_id}.{label_match.group(2)}"
            if location:
                resolved = self._resolve_building_from_address(location)
                best = resolved.get("best_match") or {}
                address_building_id = canonical_scope(best.get("prefix"))
                if not building_id or canonical_scope(str(address_building_id or "").split(".")[0]) == site_id:
                    building_id = address_building_id or building_id
            radios.append(
                {
                    "name": name,
                    "vendor": "cambium",
                    "model": str(row.get("device_type") or "").strip() or None,
                    "status": inventory_radio_status(row.get("status")),
                    "netbox_status": row.get("status"),
                    "status_bucket": row.get("status_bucket"),
                    "is_live_expected": bool(row.get("is_live_expected")),
                    "primary_ip": str(row.get("primary_ip") or "").strip() or None,
                    "location": location or None,
                    "building_id": building_id,
                    "sources": ["netbox"],
                    "alerts": [],
                }
            )
            seen_names.add(normalized_name)

        for alert in alerts:
            labels = alert.get("labels") or {}
            annotations = alert.get("annotations") or {}
            alert_name = str(labels.get("name") or annotations.get("device_name") or "").strip()
            if not alert_name or not re.search(r"\bV(?:1000|2000|3000|5000)\b", alert_name, re.I):
                summary = str(annotations.get("summary") or labels.get("alertname") or "").strip()
                if not any(token in summary.lower() for token in ("cambium", "radio")):
                    continue
            normalized_name = normalize_free_text(alert_name)
            existing = next((row for row in radios if normalize_free_text(str(row.get("name") or "")) == normalized_name), None)
            if existing is None and normalized_name:
                existing = next(
                    (
                        row for row in radios
                        if normalized_name in normalize_free_text(str(row.get("name") or ""))
                        or normalize_free_text(str(row.get("name") or "")) in normalized_name
                    ),
                    None,
                )
            if existing is None:
                radios.append(
                    {
                        "name": alert_name,
                        "vendor": "cambium",
                        "model": None,
                        "status": str(labels.get("alertname") or "alert_only"),
                        "primary_ip": None,
                        "location": None,
                        "building_id": None,
                        "sources": ["alerts"],
                        "alerts": [alert],
                    }
                )
                continue
            sources = set(existing.get("sources") or [])
            sources.add("alerts")
            existing["sources"] = sorted(sources)
            existing["alerts"] = [*(existing.get("alerts") or []), alert][:10]
            if str(existing.get("status") or "") in {"ok", "inventory_only"} and labels.get("alertname"):
                existing["status"] = str(labels.get("alertname") or existing.get("status"))

        by_building: dict[str, list[dict[str, Any]]] = {}
        for row in radios:
            building_id = canonical_scope(row.get("building_id"))
            if building_id:
                by_building.setdefault(building_id, []).append(row)

        shared_building_v2000_pairs: list[dict[str, Any]] = []
        dn_radios: list[dict[str, Any]] = []
        cn_radios: list[dict[str, Any]] = []
        for building_id, rows in sorted(by_building.items()):
            v2ks = [row for row in rows if "v2000" in str(row.get("name") or "").lower() or "v2000" in str(row.get("model") or "").lower()]
            if len(v2ks) >= 2:
                shared_building_v2000_pairs.append(
                    {
                        "building_id": building_id,
                        "radio_names": [str(row.get("name") or "") for row in sorted(v2ks, key=lambda item: str(item.get("name") or ""))],
                        "radio_ips": [row.get("primary_ip") for row in v2ks if row.get("primary_ip")],
                    }
                )
        for row in radios:
            joined = f"{row.get('name') or ''} {row.get('model') or ''}".lower()
            if "v5000" in joined:
                dn_radios.append(row)
            elif any(tag in joined for tag in ("v1000", "v2000", "v3000")):
                cn_radios.append(row)

        active_radio_alerts: list[dict[str, Any]] = []
        for row in radios:
            for alert in row.get("alerts") or []:
                labels = alert.get("labels") or {}
                annotations = alert.get("annotations") or {}
                active_radio_alerts.append(
                    {
                        "name": row.get("name"),
                        "alertname": labels.get("alertname"),
                        "summary": annotations.get("summary") or labels.get("alertname"),
                        "severity": labels.get("severity"),
                        "device_mac": labels.get("device_mac"),
                        "node_type": labels.get("node_type"),
                    }
                )

        return {
            "site_id": site_id,
            "radios": sorted(radios, key=lambda row: str(row.get("name") or "")),
            "shared_building_v2000_pairs": shared_building_v2000_pairs,
            "dn_radios": [
                {
                    "name": row.get("name"),
                    "building_id": row.get("building_id"),
                    "primary_ip": row.get("primary_ip"),
                }
                for row in dn_radios
            ],
            "cn_radio_count": len(cn_radios),
            "active_radio_alerts": active_radio_alerts[:20],
            "transport_radio_count": len(topology.get("radios") or []),
            "site_summary_hint": {
                "cnwave": self._cnwave_site_summary(site_id),
                "topology_radio_links": len(topology.get("radio_links") or []),
            },
        }

    def search_vilo_devices(self, network_id: str, sort_group: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        return self.vilo_api.search_devices(network_id, sort_group or [])

    def get_tauc_network_name_list(self, status: str, page: int = 0, page_size: int = 100, name_prefix: str | None = None) -> dict[str, Any]:
        if not self.tauc:
            raise ValueError("TAUC cloud is not configured")
        return self.tauc.get_network_name_list(status, page, page_size, name_prefix)

    def get_tauc_network_details(self, network_id: str) -> dict[str, Any]:
        if not self.tauc:
            raise ValueError("TAUC cloud is not configured")
        return self.tauc.get_network_details(network_id)

    def get_tauc_preconfiguration_status(self, network_id: str) -> dict[str, Any]:
        if not self.tauc:
            raise ValueError("TAUC cloud is not configured")
        return self.tauc.get_preconfiguration_status(network_id)

    def get_tauc_pppoe_status(self, network_id: str, refresh: bool = True, include_credentials: bool = False) -> dict[str, Any]:
        if not self.tauc:
            raise ValueError("TAUC cloud is not configured")
        return self.tauc.get_pppoe_status(network_id, refresh, include_credentials)

    def get_tauc_device_id(self, sn: str, mac: str) -> dict[str, Any]:
        if not self.tauc:
            raise ValueError("TAUC cloud or ACS is not configured")
        return self.tauc.get_device_id(sn, mac)

    def get_tauc_device_detail(self, device_id: str) -> dict[str, Any]:
        if not self.tauc:
            raise ValueError("TAUC cloud or ACS is not configured")
        return self.tauc.get_device_detail(device_id)

    def get_tauc_device_internet(self, device_id: str) -> dict[str, Any]:
        if not self.tauc:
            raise ValueError("TAUC ACS is not configured")
        return self.tauc.get_device_internet(device_id)

    def get_tauc_olt_devices(self, mac: str | None, sn: str | None, status: str | None, page: int = 0, page_size: int = 50) -> dict[str, Any]:
        if not self.tauc:
            raise ValueError("TAUC OLT is not configured")
        return self.tauc.get_olt_devices(mac, sn, status, page, page_size)

    def get_building_customer_count(self, building_id: str) -> dict[str, Any]:
        building_id = canonical_scope(building_id)
        scan_id = self.latest_scan_id()
        rows = self.db.execute(
            """
            select d.identity, bh.ip, bh.mac, bh.on_interface, bh.vid, bh.local, bh.external
            from bridge_hosts bh
            left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
            where bh.scan_id=? and d.identity like ? and bh.local=0 and bh.on_interface like 'ether%'
            order by d.identity, bh.on_interface, bh.mac
            """,
            (scan_id, f"{building_id}%"),
        ).fetchall()
        results = [dict(r) for r in rows if is_probable_customer_bridge_host(dict(r))]
        ppp_unit_evidence = self._ppp_unit_evidence_for_building(building_id)
        evidence_online_units = ppp_unit_evidence
        switches = sorted({r['identity'] for r in results if r.get('identity')})
        ports = sorted({(r['identity'], r['on_interface']) for r in results if r.get('identity') and r.get('on_interface')})
        vendor_summary: dict[str, int] = {'vilo': 0, 'tplink': 0, 'unknown': 0}
        for r in results:
            group = mac_vendor_group(r['mac'])
            vendor_summary[group] = vendor_summary.get(group, 0) + 1
        count = max(len(results), len(evidence_online_units))
        counting_method = 'bridge_hosts_external_access_ports'
        if len(evidence_online_units) > len(results):
            counting_method = 'max(bridge_hosts_external_access_ports, inventory_ppp_arp_unit_evidence)'
        return {
            'building_id': building_id,
            'scope_definition': f'all switches with identity prefix {building_id}.',
            'count': count,
            'counting_method': counting_method,
            'switch_count': len(switches),
            'switches': switches,
            'access_port_count': len(ports),
            'vendor_summary': vendor_summary,
            'evidence_backed_online_unit_count': len(evidence_online_units),
            'evidence_online_units': evidence_online_units[:500],
            'results': results[:500],
            'scan': self.latest_scan_meta(),
        }

    def _port_map_scope_rows(self, site_id: str | None = None, building_id: str | None = None) -> list[dict[str, Any]]:
        data = load_customer_port_map()
        rows = data.get("ports", [])
        if building_id:
            rows = [r for r in rows if identity_matches_scope(r.get("identity", ""), building_id)]
        elif site_id:
            rows = [r for r in rows if identity_matches_scope(r.get("identity", ""), site_id)]
        return [self._canonicalize_port_row(r) for r in rows]

    def _canonicalize_port_row(self, row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        ident = canonical_identity(out.get("identity"))
        out["identity"] = ident
        if ident:
            parts = ident.split(".")
            out["site_id"] = parts[0] if len(parts) >= 1 else None
            out["building_id"] = ".".join(parts[:2]) if len(parts) >= 2 else None
        else:
            out["site_id"] = None
            out["building_id"] = None
        return out

    def _fetch_vilo_inventory_rows(self, limit: int = 500, page_size: int = 50) -> dict[str, Any]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        requested_limit = max(1, int(limit))
        page_size = min(50, max(1, int(page_size)))
        rows: list[dict[str, Any]] = []
        total_count = 0
        pages_fetched = 0
        page_index = 1
        while len(rows) < requested_limit:
            payload = self.vilo_api.get_inventory(page_index, page_size)
            pages_fetched += 1
            data = payload.get("data") or {}
            batch = [dict(r) for r in (data.get("device_list") or [])]
            total_count = int(data.get("total_count") or total_count or len(batch))
            if not batch:
                break
            rows.extend(batch)
            if len(rows) >= total_count:
                break
            page_index += 1
        return {
            "rows": rows[:requested_limit],
            "inventory_total_count": total_count,
            "pages_fetched": pages_fetched,
            "limit_applied": total_count > requested_limit,
        }

    def _fetch_vilo_network_rows(self, limit: int = 2000, page_size: int = 50) -> list[dict[str, Any]]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        requested_limit = max(1, int(limit))
        page_size = min(50, max(1, int(page_size)))
        rows: list[dict[str, Any]] = []
        page_index = 1
        total_count = None
        while len(rows) < requested_limit:
            payload = self.vilo_api.get_networks(page_index, page_size)
            data = payload.get("data") or {}
            batch = [dict(r) for r in (data.get("network_list") or [])]
            if total_count is None:
                total_count = int(data.get("total_count") or len(batch))
            if not batch:
                break
            rows.extend(batch)
            if len(rows) >= (total_count or 0):
                break
            page_index += 1
        return rows[:requested_limit]

    def _fetch_vilo_subscriber_rows(self, limit: int = 500, page_size: int = 50) -> list[dict[str, Any]]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        requested_limit = max(1, int(limit))
        page_size = min(50, max(1, int(page_size)))
        rows: list[dict[str, Any]] = []
        page_index = 1
        total_count = None
        while len(rows) < requested_limit:
            payload = self.vilo_api.get_subscribers(page_index, page_size)
            data = payload.get("data") or {}
            batch = [dict(r) for r in (data.get("user_list") or [])]
            if total_count is None:
                total_count = int(data.get("total_count") or len(batch))
            if not batch:
                break
            rows.extend(batch)
            if len(rows) >= (total_count or 0):
                break
            page_index += 1
        return rows[:requested_limit]

    def _latest_vilo_scan_sightings(self, site_id: str | None = None, building_id: str | None = None) -> list[dict[str, Any]]:
        scan_id = self.latest_scan_id()
        raw_rows = [
            dict(r)
            for r in self.db.execute(
                """
                select d.identity, d.ip, bh.mac, bh.on_interface, bh.vid, bh.local, bh.external
                from bridge_hosts bh
                left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                where bh.scan_id=? and lower(bh.mac) like 'e8:da:00:%'
                order by d.identity, bh.on_interface, bh.mac
                """,
                (scan_id,),
            ).fetchall()
        ]
        port_rows = self._port_map_scope_rows(site_id=site_id, building_id=building_id)
        port_index = {(r.get("identity"), r.get("interface")): r for r in port_rows}
        out: list[dict[str, Any]] = []
        for row in raw_rows:
            identity = canonical_identity(row.get("identity"))
            if building_id and not identity_matches_scope(identity, building_id):
                continue
            if not building_id and site_id and not identity_matches_scope(identity, site_id):
                continue
            sighting = dict(row)
            sighting["identity"] = identity
            sighting["mac"] = norm_mac(sighting.get("mac") or "")
            parts = (identity or "").split(".")
            sighting["site_id"] = parts[0] if len(parts) >= 1 else None
            sighting["building_id"] = ".".join(parts[:2]) if len(parts) >= 2 else None
            port = port_index.get((identity, sighting.get("on_interface")))
            sighting["port_status"] = port.get("status") if port else None
            sighting["port_issues"] = (port.get("issues") or []) if port else []
            sighting["port_comment"] = (port.get("comment") or "") if port else ""
            out.append(sighting)
        return out

    def _derive_vilo_subscriber_hint(self, network: dict[str, Any] | None, sighting: dict[str, Any] | None) -> dict[str, Any] | None:
        sighting = sighting or {}
        network = network or {}
        comment = str(sighting.get("port_comment") or "").strip()
        network_name = str(network.get("network_name") or "").strip()
        building_id = str(sighting.get("building_id") or "").strip()
        if comment:
            return {
                "source": "port_comment",
                "label": comment,
                "building_id": building_id or None,
                "display": f"{building_id} {comment}".strip() if building_id else comment,
            }
        if network_name and not re.fullmatch(r"Vilo_[0-9a-fA-F]+", network_name):
            return {
                "source": "network_name",
                "label": network_name,
                "building_id": building_id or None,
                "display": network_name,
            }
        return None

    def _derive_vilo_label_candidates(
        self,
        network: dict[str, Any] | None,
        inventory: dict[str, Any] | None,
        devices: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        network = network or {}
        inventory = inventory or {}
        devices = devices or []
        raw_sources: list[tuple[str, str]] = []

        def add(source: str, value: Any) -> None:
            text = str(value or "").strip()
            if not text:
                return
            raw_sources.append((source, text))

        if not re.fullmatch(r"Vilo_[0-9a-fA-F]+", str(network.get("network_name") or "").strip()):
            add("network_name", network.get("network_name"))

        for key in ("notes", "note", "device_note", "subscriber_note", "pppoe_username", "P2104"):
            add(f"inventory_{key}", inventory.get(key))
            add(f"network_{key}", network.get(key))

        for device in devices:
            for key in ("notes", "note", "pppoe_username", "P2104", "vilo_name"):
                value = device.get(key)
                if key == "vilo_name" and re.fullmatch(r"Vilo_[0-9a-fA-F]+", str(value or "").strip()):
                    continue
                add(f"device_{key}", value)

        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str | None, str | None]] = set()
        for source, raw in raw_sources:
            unit = parse_unit_token(raw)
            address_text = expand_compact_address(raw)
            building_id = None
            score = None
            if address_text:
                resolved = self._resolve_building_from_address(address_text)
                best = (resolved or {}).get("best_match") or {}
                building_id = canonical_scope(best.get("prefix"))
                score = int(best.get("score") or 0) if best.get("score") is not None else None
            key = (raw, building_id, unit)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(
                {
                    "source": source,
                    "raw": raw,
                    "address_text": address_text or None,
                    "building_id": building_id,
                    "unit": unit,
                    "score": score,
                }
            )
        deduped.sort(
            key=lambda row: (
                0 if row.get("source") in {"network_P2104", "inventory_P2104", "device_P2104"} else 1,
                0 if row.get("source") in {"device_notes", "inventory_notes", "network_notes", "device_note", "inventory_note", "network_note"} else 1,
                0 if row.get("unit") else 1,
                -(int(row.get("score") or 0)),
                str(row.get("raw") or ""),
            )
        )
        return deduped

    def _derive_building_from_network_name(self, network: dict[str, Any] | None) -> dict[str, Any] | None:
        network = network or {}
        network_name = str(network.get("network_name") or "").strip()
        if not network_name:
            return None
        explicit = re.search(r"\b(\d{6}\.\d{3})\b", network_name)
        if explicit:
            return {
                "source": "explicit_scope",
                "building_id": canonical_scope(explicit.group(1)),
                "label": network_name,
            }
        if re.fullmatch(r"Vilo_[0-9a-fA-F]+", network_name):
            return None
        resolved = self._resolve_building_from_address(network_name)
        best = resolved.get("best_match") or {}
        score = int(best.get("score") or 0)
        if best.get("prefix") and score >= 90:
            return {
                "source": "location_match",
                "building_id": canonical_scope(best.get("prefix")),
                "label": network_name,
                "score": score,
                "location": best.get("location"),
            }
        return None

    def get_vilo_inventory_audit(self, site_id: str | None = None, building_id: str | None = None, limit: int = 500) -> dict[str, Any]:
        if not self.vilo_api:
            raise ValueError("Vilo API is not configured")
        canonical_site_id = canonical_scope(site_id) if site_id else None
        canonical_building_id = canonical_scope(building_id) if building_id else None
        if canonical_site_id and canonical_building_id and not identity_matches_scope(canonical_building_id, canonical_site_id):
            raise ValueError("building_id must be within site_id when both are provided")

        inventory_info = self._fetch_vilo_inventory_rows(limit=max(2000, int(limit)), page_size=50)
        inventory_rows = inventory_info["rows"]
        inventory_by_mac: dict[str, dict[str, Any]] = {}
        for row in inventory_rows:
            mac = norm_mac(row.get("device_mac") or "")
            if mac and mac not in inventory_by_mac:
                inventory_by_mac[mac] = row
        network_rows = self._fetch_vilo_network_rows(limit=3000, page_size=50)
        subscriber_rows = self._fetch_vilo_subscriber_rows(limit=1000, page_size=50)
        networks_by_main_mac: dict[str, dict[str, Any]] = {}
        subscribers_by_id: dict[str, dict[str, Any]] = {}
        for row in network_rows:
            mac = norm_mac(row.get("main_vilo_mac") or "")
            if mac and mac not in networks_by_main_mac:
                networks_by_main_mac[mac] = row
        for row in subscriber_rows:
            subscriber_id = str(row.get("subscriber_id") or "").strip()
            if subscriber_id and subscriber_id not in subscribers_by_id:
                subscribers_by_id[subscriber_id] = row

        scan_rows = self._latest_vilo_scan_sightings(canonical_site_id, canonical_building_id)
        sightings_by_mac: dict[str, list[dict[str, Any]]] = {}
        for row in scan_rows:
            sightings_by_mac.setdefault(row["mac"], []).append(row)

        scope_active = bool(canonical_site_id or canonical_building_id)
        counts_by_classification: dict[str, int] = {}
        counts_by_inventory_status: dict[str, int] = {}
        counts_by_building: dict[str, int] = {}
        network_name_drift_count = 0
        rows: list[dict[str, Any]] = []
        live_only_rows: list[dict[str, Any]] = []

        def bump(counter: dict[str, int], key: str) -> None:
            counter[key] = counter.get(key, 0) + 1

        if scope_active:
            for mac, hits in sorted(sightings_by_mac.items()):
                best = best_bridge_hit(hits) or hits[0]
                inventory = inventory_by_mac.get(mac)
                network = networks_by_main_mac.get(mac)
                subscriber = subscribers_by_id.get(str((network or inventory or {}).get("subscriber_id") or "").strip())
                subscriber_hint = None if subscriber else self._derive_vilo_subscriber_hint(network, best)
                expected_building = self._derive_building_from_network_name(network)
                network_name_building_drift = bool(expected_building and best.get("building_id") and expected_building.get("building_id") != best.get("building_id"))
                classification = "inventory_matched" if inventory else "seen_not_in_vilo_inventory"
                if best.get("port_status") in {"isolated", "recovery_ready", "recovery_hold", "observe"}:
                    classification = f"{classification}_attention_port"
                row = {
                    "device_mac": mac,
                    "classification": classification,
                    "inventory_status": (inventory or {}).get("status"),
                    "device_sn": (inventory or {}).get("device_sn"),
                    "subscriber_id": (inventory or {}).get("subscriber_id"),
                    "network_id": (network or {}).get("network_id"),
                    "network_name": (network or {}).get("network_name"),
                    "network_status": (network or {}).get("network_status"),
                    "network_name_building_hint": expected_building,
                    "network_name_building_drift": network_name_building_drift,
                    "subscriber": {
                        "subscriber_id": (subscriber or {}).get("subscriber_id"),
                        "first_name": (subscriber or {}).get("first_name"),
                        "last_name": (subscriber or {}).get("last_name"),
                        "email": (subscriber or {}).get("email"),
                    } if subscriber else None,
                    "subscriber_hint": subscriber_hint,
                    "scan_seen": True,
                    "sighting": {
                        "identity": best.get("identity"),
                        "site_id": best.get("site_id"),
                        "building_id": best.get("building_id"),
                        "on_interface": best.get("on_interface"),
                        "vid": best.get("vid"),
                        "port_status": best.get("port_status"),
                        "port_issues": best.get("port_issues") or [],
                        "port_comment": best.get("port_comment") or "",
                    },
                }
                rows.append(row)
                bump(counts_by_classification, classification)
                bump(counts_by_building, best.get("building_id") or "unknown")
                if inventory and inventory.get("status"):
                    bump(counts_by_inventory_status, str(inventory.get("status")))
                if network_name_building_drift:
                    network_name_drift_count += 1
        else:
            for inventory in inventory_rows:
                mac = norm_mac(inventory.get("device_mac") or "")
                hits = sightings_by_mac.get(mac, [])
                best = best_bridge_hit(hits) if hits else None
                network = networks_by_main_mac.get(mac)
                subscriber = subscribers_by_id.get(str((network or inventory or {}).get("subscriber_id") or "").strip())
                subscriber_hint = None if subscriber else self._derive_vilo_subscriber_hint(network, best)
                expected_building = self._derive_building_from_network_name(network)
                network_name_building_drift = bool(expected_building and (best or {}).get("building_id") and expected_building.get("building_id") != (best or {}).get("building_id"))
                classification = "not_seen_in_latest_scan"
                if best:
                    classification = "seen_on_access_port" if is_edge_port(best.get("on_interface")) else "seen_on_non_access_port"
                    if best.get("port_status") in {"isolated", "recovery_ready", "recovery_hold", "observe"}:
                        classification = f"{classification}_attention_port"
                row = {
                    "device_mac": mac,
                    "classification": classification,
                    "inventory_status": inventory.get("status"),
                    "device_sn": inventory.get("device_sn"),
                    "subscriber_id": inventory.get("subscriber_id"),
                    "network_id": (network or {}).get("network_id"),
                    "network_name": (network or {}).get("network_name"),
                    "network_status": (network or {}).get("network_status"),
                    "network_name_building_hint": expected_building,
                    "network_name_building_drift": network_name_building_drift,
                    "subscriber": {
                        "subscriber_id": (subscriber or {}).get("subscriber_id"),
                        "first_name": (subscriber or {}).get("first_name"),
                        "last_name": (subscriber or {}).get("last_name"),
                        "email": (subscriber or {}).get("email"),
                    } if subscriber else None,
                    "subscriber_hint": subscriber_hint,
                    "scan_seen": bool(best),
                    "sighting": {
                        "identity": (best or {}).get("identity"),
                        "site_id": (best or {}).get("site_id"),
                        "building_id": (best or {}).get("building_id"),
                        "on_interface": (best or {}).get("on_interface"),
                        "vid": (best or {}).get("vid"),
                        "port_status": (best or {}).get("port_status"),
                        "port_issues": (best or {}).get("port_issues") or [],
                        "port_comment": (best or {}).get("port_comment") or "",
                    } if best else None,
                }
                rows.append(row)
                bump(counts_by_classification, classification)
                bump(counts_by_inventory_status, str(inventory.get("status") or "unknown"))
                bump(counts_by_building, ((best or {}).get("building_id") or "unresolved"))
                if network_name_building_drift:
                    network_name_drift_count += 1

            for mac, hits in sorted(sightings_by_mac.items()):
                if mac in inventory_by_mac:
                    continue
                best = best_bridge_hit(hits) or hits[0]
                network = networks_by_main_mac.get(mac)
                subscriber = subscribers_by_id.get(str((network or {}).get("subscriber_id") or "").strip())
                subscriber_hint = None if subscriber else self._derive_vilo_subscriber_hint(network, best)
                expected_building = self._derive_building_from_network_name(network)
                network_name_building_drift = bool(expected_building and best.get("building_id") and expected_building.get("building_id") != best.get("building_id"))
                live_only_rows.append(
                    {
                        "device_mac": mac,
                        "classification": "seen_not_in_vilo_inventory",
                        "network_id": (network or {}).get("network_id"),
                        "network_name": (network or {}).get("network_name"),
                        "network_name_building_hint": expected_building,
                        "network_name_building_drift": network_name_building_drift,
                        "subscriber": {
                            "subscriber_id": (subscriber or {}).get("subscriber_id"),
                            "first_name": (subscriber or {}).get("first_name"),
                            "last_name": (subscriber or {}).get("last_name"),
                            "email": (subscriber or {}).get("email"),
                        } if subscriber else None,
                        "subscriber_hint": subscriber_hint,
                        "sighting": {
                            "identity": best.get("identity"),
                            "site_id": best.get("site_id"),
                            "building_id": best.get("building_id"),
                            "on_interface": best.get("on_interface"),
                            "vid": best.get("vid"),
                            "port_status": best.get("port_status"),
                            "port_issues": best.get("port_issues") or [],
                            "port_comment": best.get("port_comment") or "",
                        },
                    }
                )

        return {
            "scan": self.latest_scan_meta(),
            "scope": {
                "site_id": canonical_site_id,
                "building_id": canonical_building_id,
                "scope_active": scope_active,
                "mode": "scope_scan_to_inventory" if scope_active else "inventory_to_scan",
            },
            "inventory_total_count": inventory_info["inventory_total_count"],
            "inventory_rows_examined": len(inventory_rows),
            "inventory_pages_fetched": inventory_info["pages_fetched"],
            "network_rows_examined": len(network_rows),
            "subscriber_rows_examined": len(subscriber_rows),
            "scope_seen_mac_count": len(sightings_by_mac),
            "subscriber_hint_count": sum(1 for row in rows if row.get("subscriber_hint")),
            "network_name_drift_count": network_name_drift_count,
            "counts_by_classification": dict(sorted(counts_by_classification.items())),
            "counts_by_inventory_status": dict(sorted(counts_by_inventory_status.items())),
            "counts_by_building": dict(sorted(counts_by_building.items())),
            "rows": rows,
            "live_only_rows": live_only_rows[:100],
            "limit_applied": inventory_info["limit_applied"],
        }

    def export_vilo_inventory_audit(self, site_id: str | None = None, building_id: str | None = None, limit: int = 500) -> dict[str, Any]:
        payload = self.get_vilo_inventory_audit(site_id, building_id, limit)
        scope = payload.get("scope") or {}
        scope_token = scope.get("building_id") or scope.get("site_id") or "global"
        safe_scope = str(scope_token).replace("/", "_")
        VILO_AUDIT_OUT_DIR.mkdir(parents=True, exist_ok=True)

        json_path = VILO_AUDIT_OUT_DIR / f"vilo_audit_{safe_scope}.json"
        csv_path = VILO_AUDIT_OUT_DIR / f"vilo_audit_{safe_scope}.csv"
        md_path = VILO_AUDIT_OUT_DIR / f"vilo_audit_{safe_scope}.md"

        latest_json = VILO_AUDIT_OUT_DIR / "vilo_audit_latest.json"
        latest_csv = VILO_AUDIT_OUT_DIR / "vilo_audit_latest.csv"
        latest_md = VILO_AUDIT_OUT_DIR / "vilo_audit_latest.md"

        json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        latest_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        rows = payload.get("rows") or []
        csv_rows: list[dict[str, Any]] = []
        for row in rows:
            sighting = row.get("sighting") or {}
            subscriber = row.get("subscriber") or {}
            subscriber_hint = row.get("subscriber_hint") or {}
            network_hint = row.get("network_name_building_hint") or {}
            csv_rows.append(
                {
                    "device_mac": row.get("device_mac"),
                    "classification": row.get("classification"),
                    "inventory_status": row.get("inventory_status"),
                    "device_sn": row.get("device_sn"),
                    "subscriber_id": row.get("subscriber_id"),
                    "network_id": row.get("network_id"),
                    "network_name": row.get("network_name"),
                    "network_status": row.get("network_status"),
                    "subscriber_first_name": subscriber.get("first_name"),
                    "subscriber_last_name": subscriber.get("last_name"),
                    "subscriber_email": subscriber.get("email"),
                    "subscriber_hint_source": subscriber_hint.get("source"),
                    "subscriber_hint_label": subscriber_hint.get("label"),
                    "subscriber_hint_display": subscriber_hint.get("display"),
                    "network_name_hint_source": network_hint.get("source"),
                    "expected_building_from_network_name": network_hint.get("building_id"),
                    "network_name_building_drift": row.get("network_name_building_drift"),
                    "site_id": sighting.get("site_id"),
                    "building_id": sighting.get("building_id"),
                    "identity": sighting.get("identity"),
                    "on_interface": sighting.get("on_interface"),
                    "vid": sighting.get("vid"),
                    "port_status": sighting.get("port_status"),
                    "port_issues": ",".join(sighting.get("port_issues") or []),
                    "port_comment": sighting.get("port_comment"),
                }
            )
        fieldnames = list(csv_rows[0].keys()) if csv_rows else [
            "device_mac", "classification", "inventory_status", "device_sn", "subscriber_id",
            "network_id", "network_name", "network_status", "subscriber_first_name",
            "subscriber_last_name", "subscriber_email", "subscriber_hint_source", "subscriber_hint_label", "subscriber_hint_display", "network_name_hint_source", "expected_building_from_network_name", "network_name_building_drift", "site_id", "building_id", "identity",
            "on_interface", "vid", "port_status", "port_issues", "port_comment",
        ]
        for target in (csv_path, latest_csv):
            with target.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(csv_rows)

        counts = payload.get("counts_by_classification") or {}
        buildings = payload.get("counts_by_building") or {}
        matched_with_network = sum(1 for row in rows if row.get("network_id"))
        matched_with_subscriber = sum(1 for row in rows if row.get("subscriber"))
        matched_with_hint = sum(1 for row in rows if row.get("subscriber_hint"))
        network_name_drift = sum(1 for row in rows if row.get("network_name_building_drift"))
        attention = [r for r in rows if "attention_port" in str(r.get("classification") or "")]
        missing_inventory = [r for r in rows if str(r.get("classification") or "").startswith("seen_not_in_vilo_inventory")]
        drift_rows = [r for r in rows if r.get("network_name_building_drift")]

        lines = [
            "# Vilo Inventory Audit",
            "",
            "## Summary",
            "",
            f"- scope: `{scope_token}`",
            f"- scan id: `{(payload.get('scan') or {}).get('id')}`",
            f"- Vilo inventory total: `{payload.get('inventory_total_count', 0)}`",
            f"- inventory rows examined: `{payload.get('inventory_rows_examined', 0)}`",
            f"- live scan sightings in scope: `{payload.get('scope_seen_mac_count', 0)}`",
            f"- matched with Vilo network context: `{matched_with_network}`",
            f"- matched with Vilo subscriber context: `{matched_with_subscriber}`",
            f"- local fallback subscriber hints: `{matched_with_hint}`",
            f"- network-name building drift hits: `{network_name_drift}`",
            "",
            "## Classifications",
            "",
        ]
        if counts:
            for key, value in sorted(counts.items()):
                lines.append(f"- `{key}`: `{value}`")
        else:
            lines.append("- none")
        lines.extend([
            "",
            "## Buildings",
            "",
        ])
        if buildings:
            for key, value in sorted(buildings.items()):
                lines.append(f"- `{key}`: `{value}`")
        else:
            lines.append("- none")
        lines.extend([
            "",
            "## Network Name Building Drift",
            "",
        ])
        if drift_rows:
            for row in drift_rows[:25]:
                sighting = row.get("sighting") or {}
                hint = row.get("network_name_building_hint") or {}
                lines.append(
                    f"- `{row.get('device_mac')}` network `{row.get('network_name')}` implies `{hint.get('building_id')}` "
                    f"but is seen on `{sighting.get('building_id')}` `{sighting.get('identity')}` `{sighting.get('on_interface')}`"
                )
        else:
            lines.append("- none")
        lines.extend([
            "",
            "## Attention Ports",
            "",
        ])
        if attention:
            for row in attention[:25]:
                sighting = row.get("sighting") or {}
                lines.append(
                    f"- `{row.get('device_mac')}` `{row.get('network_name') or ''}` on "
                    f"`{sighting.get('identity')}` `{sighting.get('on_interface')}` "
                    f"status `{sighting.get('port_status')}` issues `{', '.join(sighting.get('port_issues') or []) or 'none'}`"
                )
        else:
            lines.append("- none")
        lines.extend([
            "",
            "## Seen In Scan But Missing From Vilo Inventory",
            "",
        ])
        if missing_inventory:
            for row in missing_inventory[:25]:
                sighting = row.get("sighting") or {}
                who = (row.get("subscriber") or {}).get("email") or row.get("network_name") or ""
                lines.append(
                    f"- `{row.get('device_mac')}` seen on `{sighting.get('identity')}` `{sighting.get('on_interface')}`"
                    + (f" linked to `{who}`" if who else "")
                )
        else:
            lines.append("- none")
        markdown = "\n".join(lines) + "\n"
        md_path.write_text(markdown, encoding="utf-8")
        latest_md.write_text(markdown, encoding="utf-8")

        return {
            "scope": scope,
            "paths": {
                "json": str(json_path),
                "csv": str(csv_path),
                "md": str(md_path),
                "latest_json": str(latest_json),
                "latest_csv": str(latest_csv),
                "latest_md": str(latest_md),
            },
            "summary": {
                "rows": len(rows),
                "matched_with_network": matched_with_network,
                "matched_with_subscriber": matched_with_subscriber,
                "matched_with_hint": matched_with_hint,
                "network_name_drift": network_name_drift,
                "counts_by_classification": counts,
            },
        }

    def get_building_flap_history(self, building_id: str) -> dict[str, Any]:
        rows = self._port_map_scope_rows(building_id=building_id)
        hits = [r for r in rows if "flap_history" in (r.get("issues") or [])]
        return {
            "building_id": building_id,
            "scope_definition": f"all switches with identity prefix {building_id}.",
            "count": len(hits),
            "ports": hits,
        }

    def get_site_flap_history(self, site_id: str) -> dict[str, Any]:
        rows = self._port_map_scope_rows(site_id=site_id)
        hits = [r for r in rows if "flap_history" in (r.get("issues") or [])]
        by_building: dict[str, int] = {}
        for row in hits:
            building_id = row.get("building_id") or "unknown"
            by_building[building_id] = by_building.get(building_id, 0) + 1
        return {
            "site_id": site_id,
            "count": len(hits),
            "building_count": len(by_building),
            "counts_by_building": dict(sorted(by_building.items())),
            "ports": hits,
        }

    def get_site_loop_suspicion(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        summary = self.get_site_summary(site_id, True)
        flap = self.get_site_flap_history(site_id)
        alerts = summary.get("active_alerts") or []
        switch_down_alerts: list[str] = []
        router_down_alerts: list[str] = []
        transport_alerts: list[str] = []
        for alert in alerts:
            labels = alert.get("labels") or {}
            annotations = alert.get("annotations") or {}
            text = str(annotations.get("summary") or labels.get("alertname") or "").strip()
            lower = text.lower()
            if not text:
                continue
            if "switch" in lower:
                switch_down_alerts.append(text)
            elif any(term in lower for term in ("router", ".r1", "udm")):
                router_down_alerts.append(text)
            elif any(term in lower for term in ("radio", "cambium", "siklu")):
                transport_alerts.append(text)

        flap_ports = flap.get("ports") or []
        ranked_flap_ports = sorted(
            flap_ports,
            key=lambda row: int(str(row.get("link_downs") or "0") or "0"),
            reverse=True,
        )
        high_churn_ports = [
            row for row in ranked_flap_ports
            if int(str(row.get("link_downs") or "0") or "0") >= 100
        ]
        outlier_count = int(summary.get("outlier_count") or 0)
        bridge = summary.get("bridge_host_summary") or {}
        bridge_total = int(bridge.get("total") or 0)
        flare_buildings = sorted(
            (flap.get("counts_by_building") or {}).items(),
            key=lambda item: int(item[1] or 0),
            reverse=True,
        )

        suspicion = "no_strong_loop_signal"
        confidence = "medium"
        if outlier_count >= 20 and len(high_churn_ports) >= 5:
            suspicion = "broad_l2_instability"
            confidence = "medium"
        elif len(high_churn_ports) >= 3 or (switch_down_alerts and flap.get("count", 0) >= 40):
            suspicion = "possible_local_loop_or_l2_storm"
            confidence = "low"

        return {
            "site_id": site_id,
            "suspicion": suspicion,
            "confidence": confidence,
            "outlier_count": outlier_count,
            "bridge_host_total": bridge_total,
            "switch_down_alerts": switch_down_alerts,
            "router_down_alerts": router_down_alerts,
            "transport_alerts": transport_alerts,
            "flap_count": int(flap.get("count") or 0),
            "flap_building_count": int(flap.get("building_count") or 0),
            "top_flap_buildings": [
                {"building_id": building_id, "count": int(count or 0)}
                for building_id, count in flare_buildings[:5]
            ],
            "high_churn_ports": ranked_flap_ports[:10],
            "summary": summary,
        }

    def get_site_bridge_host_weirdness(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        scan_id = self.latest_scan_id()
        rows = [
            dict(r)
            for r in self.db.execute(
                """
                select d.identity, d.ip, bh.mac, bh.on_interface, bh.vid, bh.local, bh.external
                from bridge_hosts bh
                left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                where bh.scan_id=? and d.identity like ?
                order by d.identity, bh.on_interface, bh.mac
                """,
                (scan_id, f"{site_id}%"),
            ).fetchall()
        ]
        customer_rows = [row for row in rows if mac_vendor_group(row.get("mac")) in {"tplink", "vilo"}]
        uplink_customer = [row for row in customer_rows if is_uplink_like_port(row.get("on_interface"))]
        access_customer = [row for row in customer_rows if is_edge_port(row.get("on_interface"))]

        by_access_port: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in access_customer:
            key = (str(row.get("identity") or ""), str(row.get("on_interface") or ""))
            by_access_port.setdefault(key, []).append(row)
        crowded_access = [
            {
                "identity": identity,
                "interface": iface,
                "customer_mac_count": len(port_rows),
                "sample_macs": [str(r.get("mac") or "") for r in port_rows[:5]],
            }
            for (identity, iface), port_rows in by_access_port.items()
            if len(port_rows) >= 3
        ]
        crowded_access.sort(key=lambda row: int(row.get("customer_mac_count") or 0), reverse=True)

        sightings_by_mac: dict[str, list[dict[str, Any]]] = {}
        for row in customer_rows:
            mac = norm_mac(row.get("mac") or "")
            if not mac:
                continue
            sightings_by_mac.setdefault(mac, []).append(row)
        sprayed_customer_macs = []
        for mac, mac_rows in sightings_by_mac.items():
            unique_paths = {
                (str(r.get("identity") or ""), str(r.get("on_interface") or ""))
                for r in mac_rows
            }
            if len(unique_paths) >= 4:
                sprayed_customer_macs.append(
                    {
                        "mac": mac,
                        "path_count": len(unique_paths),
                        "sample_paths": [f"{identity} {iface}".strip() for identity, iface in sorted(unique_paths)[:5]],
                    }
                )
        sprayed_customer_macs.sort(key=lambda row: int(row.get("path_count") or 0), reverse=True)

        suspicion = "no_strong_bridge_host_anomaly"
        if crowded_access or sprayed_customer_macs:
            suspicion = "bridge_host_anomalies_present"
        elif uplink_customer and not access_customer:
            suspicion = "customer_macs_uplink_only"

        return {
            "site_id": site_id,
            "suspicion": suspicion,
            "customer_bridge_host_count": len(customer_rows),
            "uplink_customer_count": len(uplink_customer),
            "access_customer_count": len(access_customer),
            "crowded_access_ports": crowded_access[:10],
            "sprayed_customer_macs": sprayed_customer_macs[:10],
            "sample_uplink_customer_hosts": uplink_customer[:10],
        }

    def get_site_edge_evidence_gaps(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        punch = self.get_site_punch_list(site_id)
        building_ids = sorted(
            {
                canonical_scope(row.get("building_id"))
                for key in ("isolated_ports", "recovery_ports", "observe_ports")
                for row in (punch.get(key) or [])
                if canonical_scope(row.get("building_id"))
            }
        )
        gaps: list[dict[str, Any]] = []
        for building_id in building_ids:
            model = self.get_building_model(building_id)
            coverage = model.get("coverage") or {}
            exact_match_count = int(coverage.get("exact_unit_port_match_count") or 0)
            live_pool_count = int(coverage.get("live_port_pool_count") or 0)
            known_unit_count = int(coverage.get("known_unit_count") or 0)
            actionable_rows = [
                row
                for key in ("isolated_ports", "recovery_ports", "observe_ports")
                for row in (punch.get(key) or [])
                if canonical_scope(row.get("building_id")) == building_id
            ]
            if not actionable_rows:
                continue
            if exact_match_count > 0:
                continue
            sample_ports = [
                f"{canonical_identity(row.get('identity'))} {row.get('port') or row.get('interface') or '?'}".strip()
                for row in actionable_rows[:4]
            ]
            gaps.append(
                {
                    "building_id": building_id,
                    "actionable_port_count": len(actionable_rows),
                    "known_unit_count": known_unit_count,
                    "exact_unit_port_match_count": exact_match_count,
                    "live_port_pool_count": live_pool_count,
                    "sample_ports": sample_ports,
                }
            )
        gaps.sort(key=lambda row: (int(row.get("actionable_port_count") or 0), int(row.get("live_port_pool_count") or 0)), reverse=True)
        return {
            "site_id": site_id,
            "building_gap_count": len(gaps),
            "gaps": gaps[:15],
        }

    def get_rogue_dhcp_suspects(self, building_id: str | None = None, site_id: str | None = None) -> dict[str, Any]:
        rows = self._port_map_scope_rows(site_id=site_id, building_id=building_id)
        hits = [
            r for r in rows
            if "rogue_dhcp_source_isolated" in (r.get("issues") or []) or "rogue_dhcp" in " ".join(r.get("issues") or [])
        ]
        return {
            "building_id": building_id,
            "site_id": site_id,
            "count": len(hits),
            "ports": hits,
        }

    def get_site_rogue_dhcp_summary(self, site_id: str) -> dict[str, Any]:
        rows = self._port_map_scope_rows(site_id=site_id)
        hits = [
            r for r in rows
            if "rogue_dhcp_source_isolated" in (r.get("issues") or []) or "rogue_dhcp" in " ".join(r.get("issues") or [])
        ]
        by_building: dict[str, dict[str, Any]] = {}
        for row in hits:
            identity = str(row.get("identity") or "")
            building_id = canonical_scope(".".join(identity.split(".")[:2]) if identity.count(".") >= 2 else identity)
            entry = by_building.setdefault(building_id, {"building_id": building_id, "count": 0, "isolated": 0, "ports": []})
            entry["count"] += 1
            if "rogue_dhcp_source_isolated" in (row.get("issues") or []):
                entry["isolated"] += 1
            entry["ports"].append(row)
        return {
            "site_id": site_id,
            "count": len(hits),
            "building_count": len(by_building),
            "buildings": sorted(by_building.values(), key=lambda x: x["building_id"]),
            "ports": hits,
        }

    def get_recovery_ready_cpes(self, building_id: str | None = None, site_id: str | None = None) -> dict[str, Any]:
        rows = self._port_map_scope_rows(site_id=site_id, building_id=building_id)
        hits = [r for r in rows if r.get("status") in {"recovery_ready", "recovery_hold"}]
        return {
            "building_id": building_id,
            "site_id": site_id,
            "count": len(hits),
            "ports": hits,
        }

    def get_site_punch_list(self, site_id: str) -> dict[str, Any]:
        rows = self._port_map_scope_rows(site_id=site_id)
        isolated = [r for r in rows if r.get("status") == "isolated"]
        recovery = [r for r in rows if r.get("status") in {"recovery_ready", "recovery_hold"}]
        flaps = [r for r in rows if "flap_history" in (r.get("issues") or [])]
        observe = [r for r in rows if r.get("status") == "observe"]
        actionable = [r for r in rows if r.get("status") in {"isolated", "recovery_ready", "recovery_hold", "observe"}]
        return {
            "site_id": site_id,
            "total_actionable_ports": len(actionable),
            "isolated_count": len(isolated),
            "recovery_count": len(recovery),
            "flap_count": len(flaps),
            "observe_count": len(observe),
            "isolated_ports": isolated,
            "recovery_ports": recovery,
            "flap_ports": flaps,
            "observe_ports": observe,
        }

    def get_nycha_port_audit(self, site_id: str | None = None) -> dict[str, Any]:
        """Audit switch uplink port patching for any site.

        WHY: CRS354-48G switches (NYCHA 000007) use ether49 as the uplink port.
        CRS326-24G switches (other sites) use ether25. Some are mispatched.
        This method is site-agnostic — it reads the correct uplink ports from
        SITE_SERVICE_PROFILES via get_site_uplink_ports() and applies them to
        whichever site is requested.

        Defaults to site 000007 when called with no arguments (backward compatible
        with NYCHA operator intent tokens in query_core.py).
        """
        effective_site_id = site_id or "000007"
        site_prefix = effective_site_id + "%"
        site_name = (SITE_SERVICE_PROFILES.get(effective_site_id) or {}).get("name", effective_site_id)

        # WHY: Uplink ports are site-specific; consult the registry rather than hardcoding.
        uplink_ports = get_site_uplink_ports(effective_site_id)
        # The "wrong" port is the one just below the expected uplink on the same switch model.
        # For 48-port (ether49 uplink) -> ether48 is the wrong port.
        # For 24-port (ether25 uplink) -> ether24 is the wrong port.
        # Build a map of expected -> wrong for each uplink candidate.
        wrong_port_map: dict[str, str] = {}
        for port in uplink_ports:
            m = re.match(r"^(ether)(\d+)$", port)
            if m:
                num = int(m.group(2))
                if num > 1:
                    wrong_port_map[port] = f"ether{num - 1}"

        if not wrong_port_map:
            # No ether-style uplink ports configured for this site.
            return {
                "site_id": effective_site_id,
                "site_name": site_name,
                "total_issues": 0,
                "wrong_uplink_port": [],
                "mixed_patch_order": [],
                "summary": f"No ether-port uplink audit configured for site {effective_site_id} ({site_name}).",
            }

        scan_id = self.latest_scan_id()
        all_audit_ports = list(wrong_port_map.keys()) + list(wrong_port_map.values())
        port_placeholders = ",".join("?" * len(all_audit_ports))

        port_rows = self.db.execute(
            f"""
            select d.identity, bp.interface as port_interface
            from bridge_ports bp
            join devices d on d.scan_id=bp.scan_id and d.ip=bp.ip
            where bp.scan_id=?
              and d.identity like ?
              and bp.interface in ({port_placeholders})
            """,
            (scan_id, site_prefix, *all_audit_ports),
        ).fetchall()

        devices_with_expected: dict[str, set[str]] = {}  # expected_port -> set of device identities
        devices_with_wrong: dict[str, set[str]] = {}

        for row in port_rows:
            identity = str(row["identity"] or "").strip()
            iface = str(row["port_interface"] or "").strip()
            for expected, wrong in wrong_port_map.items():
                if iface == expected:
                    devices_with_expected.setdefault(expected, set()).add(identity)
                elif iface == wrong:
                    devices_with_wrong.setdefault(wrong, set()).add(identity)

        # MAC learning evidence for all audit ports
        mac_rows = self.db.execute(
            f"""
            select d.identity, bh.on_interface, count(*) as mac_count,
                   sum(bh.external) as external_count
            from bridge_hosts bh
            join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
            where bh.scan_id=?
              and d.identity like ?
              and bh.on_interface in ({port_placeholders})
            group by d.identity, bh.on_interface
            """,
            (scan_id, site_prefix, *all_audit_ports),
        ).fetchall()

        mac_evidence: dict[str, dict[str, Any]] = {}
        for row in mac_rows:
            identity = str(row["identity"] or "").strip()
            iface = str(row["on_interface"] or "").strip()
            mac_evidence.setdefault(identity, {})[iface] = {
                "mac_count": int(row["mac_count"] or 0),
                "external_count": int(row["external_count"] or 0),
            }

        wrong_uplink: list[dict[str, Any]] = []
        mixed_order: list[dict[str, Any]] = []

        for expected_port, wrong_port in wrong_port_map.items():
            expected_set = devices_with_expected.get(expected_port, set())
            wrong_set = devices_with_wrong.get(wrong_port, set())

            # Devices with wrong port but no expected port
            candidates = wrong_set - expected_set
            for identity in sorted(candidates):
                ev = mac_evidence.get(identity, {}).get(wrong_port, {})
                wrong_uplink.append({
                    "device": identity,
                    "issue": f"{wrong_port}_used_as_uplink",
                    "detail": (
                        f"Switch has {wrong_port} configured but no {expected_port}. "
                        f"{expected_port} is the correct uplink port for this switch model at site {effective_site_id}."
                    ),
                    f"{wrong_port}_mac_count": ev.get("mac_count", 0),
                    f"{wrong_port}_external_mac_count": ev.get("external_count", 0),
                    f"{expected_port}_present": False,
                })

            # Devices with BOTH ports where wrong port carries upstream traffic
            for identity in sorted(wrong_set & expected_set):
                ev_wrong = mac_evidence.get(identity, {}).get(wrong_port, {})
                ev_expected = mac_evidence.get(identity, {}).get(expected_port, {})
                wrong_ext = int(ev_wrong.get("external_count") or 0)
                expected_ext = int(ev_expected.get("external_count") or 0)
                if wrong_ext > 0 and expected_ext == 0:
                    mixed_order.append({
                        "device": identity,
                        "issue": f"{wrong_port}_carrying_upstream_traffic",
                        "detail": (
                            f"Switch has both {wrong_port} and {expected_port} configured. "
                            f"{wrong_port} shows upstream MACs but {expected_port} does not — uplink may be on the wrong port."
                        ),
                        f"{wrong_port}_mac_count": ev_wrong.get("mac_count", 0),
                        f"{wrong_port}_external_mac_count": wrong_ext,
                        f"{expected_port}_mac_count": ev_expected.get("mac_count", 0),
                        f"{expected_port}_external_mac_count": expected_ext,
                    })

        total_issues = len(wrong_uplink) + len(mixed_order)
        return {
            "site_id": effective_site_id,
            "site_name": site_name,
            "scan_id": scan_id,
            "total_issues": total_issues,
            "wrong_uplink_port": wrong_uplink,
            "wrong_uplink_count": len(wrong_uplink),
            "mixed_patch_order": mixed_order,
            "mixed_patch_order_count": len(mixed_order),
            "summary": (
                f"{total_issues} switch port issue(s) found at {site_name}: "
                f"{len(wrong_uplink)} using wrong uplink port, "
                f"{len(mixed_order)} with upstream traffic on wrong port."
            ) if total_issues > 0 else f"No switch uplink port mismatches detected at {site_name} in the latest scan.",
        }

    def _prefix_to_address(self, building_prefix: str) -> str | None:
        """Reverse-look up a building address from a building prefix (e.g. '000007.031' → '184 Tapscott St').

        WHY: NetBox location strings are full addresses ('184 Tapscott St, Brooklyn, NY 11212') but
        nycha_info.csv uses short-form street addresses ('184 Tapscott St'). Strip after the first
        comma so _iter_nycha_rows_for_address can match.
        """
        for row in self._location_prefix_index():
            if row.get("prefix") == building_prefix:
                full = str(row.get("location") or "").strip()
                if not full:
                    return None
                # Trim city/state/zip — keep only "<number> <street>" portion
                return full.split(",", 1)[0].strip() or None
        return None

    def _build_db_live_context(self, address_text: str, building_prefix: str | None) -> Any:
        """Build a LiveContext from local DB plus bounded real-time collectors.

        WHY: The workbook path still needs to finish predictably, but pure DB context leaves
        PPPoE/L1/search-completion evidence unknown in live validation. This method keeps the
        fast DB bridge/TAUC/controller sources, then enriches them with bounded real-time
        observability (site PPPoE logs, per-port L1 reads, and explicit search bookkeeping).
        """
        from audits.jake_audit_workbook import (
            LiveContext,
            _build_controller_verification,
            _canonical_unit_token,
            _iter_nycha_rows_for_address,
            _map_switch_label_prefixes,
            is_probable_customer_bridge_host,
            norm_mac,
        )

        source_rows = _iter_nycha_rows_for_address(address_text)
        live_failures: list[dict[str, str]] = []
        captured_at_timestamp = datetime.now(UTC).isoformat()

        # Resolve building_id and site_id from the prefix we already computed.
        # WHY: _resolve_building_from_address does a fuzzy text match which is slow and can
        # return the wrong prefix when the address text is ambiguous. We already know the
        # correct prefix from the NetBox location index — use it directly.
        building_id = building_prefix or None
        inferred_site_id = building_id.split(".", 1)[0] if building_id else None

        # Enumerate all switches for this building from the NetBox prefix index.
        device_names: list[str] = []
        if building_id:
            for row in self._location_prefix_index():
                if row.get("prefix") == building_id:
                    device_names = row.get("device_names") or []
                    break
        switch_identities_by_label_prefix = _map_switch_label_prefixes(device_names, None)

        # Build per-switch bridge-host port maps from the DB scan — skip SSH.
        scan_id = self.latest_scan_id()
        live_port_macs_by_switch_identity: dict[str, dict[str, list[str]]] = {}
        for sw_identity in sorted(set(switch_identities_by_label_prefix.values())):
            rows = [
                dict(r)
                for r in self.db.execute(
                    """
                    select d.identity, bh.on_interface, bh.vid, bh.mac, bh.local, bh.external
                    from bridge_hosts bh
                    left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                    where bh.scan_id=? and d.identity=? and bh.local=0 and bh.on_interface like 'ether%'
                    order by bh.on_interface, bh.mac
                    """,
                    (scan_id, sw_identity),
                ).fetchall()
            ]
            by_interface: dict[str, list[str]] = {}
            for row in rows:
                if not is_probable_customer_bridge_host(row):
                    continue
                iface = str(row.get("on_interface") or "").strip()
                mac = norm_mac(row.get("mac") or "")
                if iface and mac:
                    bucket = by_interface.setdefault(iface, [])
                    if mac not in bucket:
                        bucket.append(mac)
            live_port_macs_by_switch_identity[sw_identity] = by_interface

        # WHY: If any switch in this building has no bridge-host data in the local DB
        # (not yet polled or offline during last scan), fall back to Bigmac for those
        # specific switches. Bigmac has live RouterOS bridge table data for all reachable
        # switches. We paginate the full site and filter by device_name.
        if self.bigmac and building_id:
            missing_switches = {
                sw for sw in switch_identities_by_label_prefix.values()
                if not live_port_macs_by_switch_identity.get(sw)
            }
            if missing_switches:
                site_id_for_bigmac = building_id.split(".", 1)[0]
                bigmac_by_switch: dict[str, dict[str, list[str]]] = {}
                try:
                    offset = 0
                    while True:
                        page = self.bigmac.request(
                            f"/api/site/{site_id_for_bigmac}/macs",
                            {"limit": 1000, "offset": offset},
                        )
                        page_rows = page.get("results") or []
                        if not page_rows:
                            break
                        for brow in page_rows:
                            dev = str(brow.get("device_name") or "")
                            if dev not in missing_switches:
                                continue
                            port = str(brow.get("port_name") or "").strip()
                            mac = norm_mac(brow.get("mac_address") or "")
                            vid = brow.get("vlan_id")
                            status = str(brow.get("status") or "")
                            if not port.startswith("ether"):
                                continue
                            if vid != 20:
                                continue
                            if "local" in status and "external" not in status:
                                continue
                            if mac:
                                bucket = bigmac_by_switch.setdefault(dev, {}).setdefault(port, [])
                                if mac not in bucket:
                                    bucket.append(mac)
                        if len(page_rows) < 1000:
                            break
                        offset += 1000
                except Exception as exc:
                    live_failures.append({
                        "source": "bigmac_fallback",
                        "classification": "missing_runtime",
                        "detail": f"Bigmac fetch failed for {building_id}: {exc}",
                    })
                for sw_identity, by_interface in bigmac_by_switch.items():
                    if by_interface:
                        live_port_macs_by_switch_identity[sw_identity] = by_interface
                        live_failures.append({
                            "source": "bigmac_fallback",
                            "classification": "missing_runtime",
                            "detail": f"{sw_identity} not in local DB scan; used Bigmac live data ({sum(len(v) for v in by_interface.values())} MACs on {len(by_interface)} ports)",
                        })

        # Use the first switch's port map as the flat fallback.
        first_sw = next(iter(switch_identities_by_label_prefix.values()), None)
        live_port_macs_by_interface = live_port_macs_by_switch_identity.get(first_sw or "", {})
        inferred_switch_identity = first_sw
        online_units_by_token: dict[str, dict[str, Any]] = {}
        port_observations_by_unit: dict[str, dict[str, Any]] = {}
        auth_observations_by_unit: dict[str, dict[str, Any]] = {}
        historical_search_completed: dict[str, bool] = {}
        historical_locations_by_unit: dict[str, list[dict[str, Any]]] = {}
        expected_port_search_completed_by_unit: dict[str, bool] = {}
        switch_scope_search_completed_by_unit: dict[str, bool] = {}
        global_search_completed_by_unit: dict[str, bool] = {}

        # Exact unit-port matches from TAUC CSV (fast, no network I/O).
        exact_matches_by_unit: dict[str, dict[str, Any]] = {}
        if building_id:
            try:
                for row in self._exact_unit_port_matches(building_id):
                    token = _canonical_unit_token(parse_unit_token(row.get("unit")))
                    if token:
                        exact_matches_by_unit[token] = row
            except Exception as exc:
                live_failures.append(
                    {"source": "exact_unit_port_matches", "classification": "code_error", "detail": str(exc)}
                )

        if building_id:
            try:
                for row in self._address_inventory_online_unit_evidence(building_id, address_text):
                    token = _canonical_unit_token(parse_unit_token(row.get("unit")))
                    if token:
                        online_units_by_token[token] = row
            except Exception as exc:
                live_failures.append(
                    {
                        "source": "address_inventory_online_unit_evidence",
                        "classification": "code_error",
                        "detail": str(exc),
                    }
                )

        site_pppoe_logs: dict[str, Any] | None = None
        if inferred_site_id:
            try:
                site_pppoe_logs = self.get_pppoe_logs_for_site(inferred_site_id)
                if site_pppoe_logs.get("error"):
                    live_failures.append(
                        {
                            "source": "get_pppoe_logs_for_site",
                            "classification": "missing_runtime",
                            "detail": str(site_pppoe_logs.get("error") or ""),
                        }
                    )
            except Exception as exc:
                live_failures.append(
                    {"source": "get_pppoe_logs_for_site", "classification": "code_error", "detail": str(exc)}
                )

        for source_row in source_rows:
            token = _canonical_unit_token(parse_unit_token(source_row.get("Unit")) or parse_unit_token(source_row.get("PPPoE")) or "")
            if not token:
                continue
            expected_port_search_completed_by_unit[token] = True
            switch_scope_search_completed_by_unit[token] = True
            global_search_completed_by_unit[token] = True

            expected_mac = norm_mac(source_row.get("MAC Address") or source_row.get("mac") or "")
            if expected_mac:
                historical_search_completed[token] = True
                try:
                    historical = self.get_historical_mac_locations(
                        expected_mac,
                        building_id=building_id,
                        site_id=inferred_site_id,
                    )
                    if historical.get("checked"):
                        historical_locations_by_unit[token] = list(historical.get("locations") or [])
                    elif historical.get("error"):
                        live_failures.append(
                            {
                                "source": "get_historical_mac_locations",
                                "classification": "missing_runtime",
                                "detail": str(historical.get("error") or f"Historical MAC lookup failed for {token}."),
                            }
                        )
                except Exception as exc:
                    live_failures.append(
                        {"source": "get_historical_mac_locations", "classification": "code_error", "detail": str(exc)}
                    )

            exact = exact_matches_by_unit.get(token) or {}
            interface = str(exact.get("interface") or "").strip() or None
            switch_identity = str(exact.get("switch_identity") or inferred_switch_identity or "").strip() or None
            if interface and switch_identity:
                try:
                    port_state = self.get_interface_state(interface, site_id=inferred_site_id, device_name=switch_identity)
                    if port_state.get("available"):
                        port_observations_by_unit[token] = {
                            key: port_state.get(key)
                            for key in (
                                "port_up",
                                "port_speed",
                                "port_duplex",
                                "link_partner_speed",
                                "link_partner_duplex",
                                "rx_errors",
                                "tx_errors",
                                "fcs_errors",
                                "crc_errors",
                                "link_flaps",
                                "link_flaps_window_seconds",
                            )
                        }
                    else:
                        live_failures.append(
                            {
                                "source": "get_interface_state",
                                "classification": "missing_runtime",
                                "detail": str(port_state.get("error") or f"L1 state read failed for {token} on {switch_identity} {interface}."),
                            }
                        )
                except Exception as exc:
                    live_failures.append(
                        {"source": "get_interface_state", "classification": "code_error", "detail": str(exc)}
                    )

            network_name = str(source_row.get("PPPoE") or "").strip().lower()
            active_row = online_units_by_token.get(token) or {}
            active_sources = [str(item) for item in list(active_row.get("sources") or active_row.get("evidence_sources") or [])]
            site_observation = dict((site_pppoe_logs or {}).get("observations_by_name", {}) or {}).get(network_name) or {}
            if site_pppoe_logs and site_pppoe_logs.get("searched"):
                auth_observations_by_unit[token] = {
                    "pppoe_active": bool("router_pppoe_session" in active_sources or site_observation.get("pppoe_active")),
                    "pppoe_failed_attempts_seen": site_observation.get("pppoe_failed_attempts_seen", False),
                    "pppoe_failure_reason": site_observation.get("pppoe_failure_reason"),
                    "pppoe_last_attempt_timestamp": site_observation.get("pppoe_last_attempt_timestamp"),
                    "pppoe_no_attempt_evidence": (
                        not bool("router_pppoe_session" in active_sources or site_observation.get("pppoe_active"))
                        and site_observation.get("pppoe_failed_attempts_seen") is False
                    ),
                    "evidence_sources": sorted(
                        {
                            *list(site_observation.get("evidence_sources") or []),
                            *(["router_pppoe_session"] if "router_pppoe_session" in active_sources else []),
                        }
                    ),
                }
            elif "router_pppoe_session" in active_sources:
                auth_observations_by_unit[token] = {
                    "pppoe_active": True,
                    "pppoe_failed_attempts_seen": False,
                    "pppoe_failure_reason": None,
                    "pppoe_last_attempt_timestamp": None,
                    "pppoe_no_attempt_evidence": False,
                    "evidence_sources": ["router_pppoe_session"],
                }

        # Controller verification from Vilo snapshot + TAUC CSV (file I/O only).
        try:
            controller_verification_by_mac, ctrl_failures = _build_controller_verification(source_rows)
            live_failures.extend(ctrl_failures)
        except Exception as exc:
            controller_verification_by_mac = {}
            live_failures.append(
                {"source": "controller_verification", "classification": "code_error", "detail": str(exc)}
            )

        return LiveContext(
            building_id=building_id,
            site_id=inferred_site_id,
            online_units_by_token=online_units_by_token,
            exact_matches_by_unit=exact_matches_by_unit,
            active_alert_count=0,
            building_device_count=len(device_names),
            site_online_count=None,
            inferred_switch_identity=inferred_switch_identity,
            live_port_macs_by_interface=live_port_macs_by_interface,
            switch_identities_by_label_prefix=switch_identities_by_label_prefix,
            live_port_macs_by_switch_identity=live_port_macs_by_switch_identity,
            controller_verification_by_mac=controller_verification_by_mac,
            live_failures=live_failures,
            port_observations_by_unit=port_observations_by_unit or None,
            auth_observations_by_unit=auth_observations_by_unit or None,
            captured_at_timestamp=captured_at_timestamp,
            historical_search_completed=historical_search_completed or None,
            historical_locations_by_unit=historical_locations_by_unit or None,
            expected_port_search_completed_by_unit=expected_port_search_completed_by_unit or None,
            switch_scope_search_completed_by_unit=switch_scope_search_completed_by_unit or None,
            global_search_completed_by_unit=global_search_completed_by_unit or None,
            building_has_db_bridge_hosts=bool(live_port_macs_by_interface),
        )

    def generate_nycha_audit_workbook(
        self,
        address_text: str | None = None,
        switch_identity: str | None = None,
        site_id: str | None = None,
        out_path: str | None = None,
    ) -> dict[str, Any]:
        from audits.jake_audit_workbook import generate_nycha_audit_workbook as _generate

        # WHY: The audit workbook is keyed by the NYCHA building address string (e.g. "184 Tapscott St").
        # When called with a switch identity, resolve to address via the NetBox location prefix index —
        # this is the authoritative forward-lookup path (prefix → location). The _resolve_building_from_address
        # method goes the other direction (address text → prefix) and is not appropriate here.
        building_prefix: str | None = None
        if not address_text and switch_identity:
            parts = str(switch_identity).split(".")
            if len(parts) >= 2:
                building_prefix = f"{parts[0]}.{parts[1]}"
                resolved_address = self._prefix_to_address(building_prefix)
                if resolved_address:
                    address_text = resolved_address
                else:
                    return {
                        "available": False,
                        "error": f"Jake could not resolve a building address for switch {switch_identity}. The switch may not have a location set in NetBox.",
                        "switch_identity": switch_identity,
                        "classification": "data_dependency",
                    }
            else:
                return {
                    "available": False,
                    "error": f"Switch identity {switch_identity!r} could not be parsed to a building prefix.",
                    "switch_identity": switch_identity,
                    "classification": "code_error",
                }

        if not address_text:
            return {
                "available": False,
                "error": "Jake needs an address or switch identity to generate a NYCHA audit workbook.",
                "classification": "code_error",
            }

        # Resolve building prefix from address if not already known (address-only queries).
        if not building_prefix:
            resolution = self._resolve_building_from_address(address_text)
            best = (resolution or {}).get("best_match") or {}
            building_prefix = str(best.get("prefix") or "").strip() or None

        # WHY: Build live context from DB and CSV only — avoids SSH reads and Loki queries
        # that would push total execution time past the 30s API timeout.
        live_ctx = self._build_db_live_context(address_text, building_prefix)

        try:
            result = _generate(
                address_text=address_text,
                out_path=out_path,
                ops=self,
                _live_context_override=live_ctx,
            )
            result["available"] = True
            return result
        except ValueError as exc:
            # WHY: ValueError from generate_nycha_audit_workbook means no nycha_info rows exist for this address.
            # This is a data_dependency failure — the nycha_info.csv either does not exist or does not cover this address.
            return {
                "available": False,
                "error": str(exc),
                "address": address_text,
                "classification": "data_dependency",
            }
        except Exception as exc:
            return {
                "available": False,
                "error": f"Unexpected error generating audit workbook: {exc}",
                "address": address_text,
                "classification": "code_error",
            }

    def get_site_infrastructure_handoff(self, site_id: str) -> dict[str, Any]:
        site_id = canonical_scope(site_id)
        inventory = self._netbox_site_inventory_light(site_id) if self.netbox else []
        alerts = self._alerts_for_site(site_id) if self.alerts else []
        online = self.get_online_customers(site_id, site_id, None, None)
        infra_roles = {
            "Patch Panel",
            "Power-Distribution",
            "Power-backup",
            "shelf",
            "Cable Mgmt",
            "Digi",
            "OLT",
            "Router",
        }
        role_counts: dict[str, int] = {}
        location_map: dict[str, dict[str, Any]] = {}
        devices: list[dict[str, Any]] = []
        for row in inventory:
            role = str(row.get("role") or "").strip()
            if role not in infra_roles:
                continue
            role_counts[role] = role_counts.get(role, 0) + 1
            location = str(row.get("location") or "").strip() or "Unknown"
            entry = location_map.setdefault(
                location,
                {
                    "location": location,
                    "roles": {},
                    "devices": [],
                },
            )
            entry["roles"][role] = int(entry["roles"].get(role, 0) or 0) + 1
            device_row = {
                "name": str(row.get("name") or "").strip(),
                "role": role,
                "location": location,
                "primary_ip": str(row.get("primary_ip") or "").strip() or None,
                "status": str(row.get("status") or "").strip() or None,
            }
            entry["devices"].append(device_row)
            devices.append(device_row)

        physical_checks: list[str] = []
        if role_counts.get("Power-Distribution") or role_counts.get("Power-backup"):
            physical_checks.append(
                "Verify site power first: check power-distribution, backup power, and whether the OLT/router shelf is actually energized."
            )
        if role_counts.get("Patch Panel"):
            physical_checks.append(
                "Check the fiber patch-panel path for mislabeled, loose, or crossed jumpers before blaming upstream optics."
            )
        if role_counts.get("Cable Mgmt") or role_counts.get("shelf"):
            physical_checks.append(
                "Inspect cable management and shelf layout for disturbed handoffs, over-bent jumpers, or the wrong enclosure path."
            )
        if role_counts.get("Digi"):
            physical_checks.append(
                "Use Digi/OOB as a fallback access path when the main site circuit is down; OOB up helps remote troubleshooting, but it does not prove subscriber service is healthy."
            )
        if role_counts.get("OLT"):
            physical_checks.append(
                "If customer impact is present, check the top OLT/PON optical work item and its local patch path before escalating to site-core."
            )
        if role_counts.get("Router"):
            physical_checks.append(
                "Confirm the router/headend handoff is powered, patched, and present at the intended demarc before treating this as downstream-only."
            )

        return {
            "site_id": site_id,
            "online_customers": {
                "count": online.get("count", 0),
                "counting_method": online.get("counting_method"),
            },
            "active_alerts": alerts,
            "role_counts": role_counts,
            "locations": sorted(location_map.values(), key=lambda row: row["location"]),
            "devices": devices,
            "physical_checks": physical_checks,
        }

    def get_switch_summary(self, switch_identity: str) -> dict[str, Any]:
        scan_id = self.latest_scan_id()
        device = self.db.execute(
            "select identity, ip, model, version from devices where scan_id=? and identity=? limit 1",
            (scan_id, switch_identity),
        ).fetchone()
        if not device:
            return {"switch_identity": switch_identity, "error": "No matching switch found in latest scan"}
        outliers = self.db.execute(
            "select interface, direction, severity, note from one_way_outliers o where o.scan_id=? and o.ip=? order by interface",
            (scan_id, device["ip"]),
        ).fetchall()
        hosts = self.db.execute(
            """
            select mac,on_interface,vid,local,external
            from bridge_hosts
            where scan_id=? and ip=?
            order by on_interface, mac
            """,
            (scan_id, device["ip"]),
        ).fetchall()
        probable_cpes = [
            dict(r)
            for r in hosts
            if r["on_interface"] and str(r["on_interface"]).startswith("ether") and bool(r["external"]) and not bool(r["local"])
        ]
        access_ports = sorted({r["on_interface"] for r in probable_cpes})
        vendor_summary: dict[str, int] = {"vilo": 0, "tplink": 0, "unknown": 0}
        for r in probable_cpes:
            group = mac_vendor_group(r["mac"])
            vendor_summary[group] = vendor_summary.get(group, 0) + 1
        return {
            "switch_identity": switch_identity,
            "scan": self.latest_scan_meta(),
            "device": dict(device),
            "outlier_count": len(outliers),
            "outliers": [dict(r) for r in outliers],
            "probable_cpe_count": len(probable_cpes),
            "access_port_count": len(access_ports),
            "access_ports": access_ports,
            "vendor_summary": vendor_summary,
            "probable_cpes": probable_cpes[:300],
        }

    def find_cpe_candidates(self, site_id: str | None, building_id: str | None, oui: str | None, access_only: bool, limit: int) -> dict[str, Any]:
        scan_id = self.latest_scan_id()
        prefix = building_id or site_id
        query = """
            select d.identity, bh.ip, bh.mac, bh.on_interface, bh.vid, bh.local, bh.external
            from bridge_hosts bh
            left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
            where bh.scan_id=? and bh.external=1 and bh.local=0
        """
        params: list[Any] = [scan_id]
        if prefix:
            query += " and d.identity like ?"
            params.append(f"{prefix}%")
        if oui:
            norm_oui = norm_mac(oui + "000000")[:8]
            query += " and lower(bh.mac) like ?"
            params.append(f"{norm_oui.lower()}%")
        if access_only:
            query += " and bh.on_interface like 'ether%'"
        query += " order by d.identity, bh.on_interface limit ?"
        params.append(int(limit))
        rows = [dict(r) for r in self.db.execute(query, params)]
        return {
            "scan": self.latest_scan_meta(),
            "count": len(rows),
            "requested_limit": int(limit),
            "access_only": access_only,
            "results": rows,
            "limit_reached": len(rows) >= int(limit),
        }

    def get_vendor_site_presence(self, vendor: str, limit: int = 20) -> dict[str, Any]:
        vendor = str(vendor or "").strip().lower()
        if vendor not in {"vilo", "tplink"}:
            raise ValueError("vendor must be one of: vilo, tplink")
        scan_id = self.latest_scan_id()
        rows = [
            dict(r)
            for r in self.db.execute(
                """
                select d.identity, bh.on_interface, bh.mac, bh.vid
                from bridge_hosts bh
                left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                where bh.scan_id=?
                """,
                (scan_id,),
            ).fetchall()
        ]
        filtered = [row for row in rows if mac_vendor_group(row.get("mac")) == vendor]
        site_counts: dict[str, int] = {}
        building_counts: dict[str, int] = {}
        sample_ports: dict[str, list[str]] = {}
        for row in filtered:
            identity = canonical_identity(row.get("identity"))
            if not identity:
                continue
            parts = identity.split(".")
            site_id = parts[0] if len(parts) >= 1 else None
            building_id = ".".join(parts[:2]) if len(parts) >= 2 else None
            if site_id:
                site_counts[site_id] = site_counts.get(site_id, 0) + 1
            if building_id:
                building_counts[building_id] = building_counts.get(building_id, 0) + 1
            if site_id and row.get("on_interface"):
                sample_ports.setdefault(site_id, [])
                rendered = f"{identity} {row.get('on_interface')}"
                if rendered not in sample_ports[site_id] and len(sample_ports[site_id]) < 5:
                    sample_ports[site_id].append(rendered)
        top_sites = [
            {
                "site_id": site_id,
                "count": count,
                "sample_ports": sample_ports.get(site_id, []),
            }
            for site_id, count in sorted(site_counts.items(), key=lambda item: (-item[1], item[0]))[: max(1, int(limit))]
        ]
        deduped_sites: list[dict[str, Any]] = []
        for row in top_sites:
            site_rows = [entry for entry in filtered if canonical_identity(entry.get("identity")).startswith(str(row.get("site_id") or ""))]
            deduped = dedupe_vendor_mac_groups(site_rows, vendor)
            deduped_sites.append(
                {
                    "site_id": row.get("site_id"),
                    "raw_mac_count": row.get("count", 0),
                    "estimated_cpe_count": deduped.get("estimated_cpe_count", 0),
                    "alt_mac_duplicates": deduped.get("duplicate_mac_delta_count", 0),
                    "sample_ports": row.get("sample_ports") or [],
                }
            )
        top_buildings = [
            {"building_id": building_id, "count": count}
            for building_id, count in sorted(building_counts.items(), key=lambda item: (-item[1], item[0]))[: max(1, int(limit))]
        ]
        return {
            "vendor": vendor,
            "scan": self.latest_scan_meta(),
            "count": len(filtered),
            "sites": deduped_sites,
            "buildings": top_buildings,
        }

    def get_vendor_alt_mac_clusters(self, vendor: str, site_id: str | None = None, building_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        vendor = str(vendor or "").strip().lower()
        if vendor not in {"vilo", "tplink"}:
            raise ValueError("vendor must be one of: vilo, tplink")
        scan_id = self.latest_scan_id()
        rows = [
            dict(r)
            for r in self.db.execute(
                """
                select d.identity, bh.on_interface, bh.mac, bh.vid
                from bridge_hosts bh
                left join devices d on d.scan_id=bh.scan_id and d.ip=bh.ip
                where bh.scan_id=?
                """,
                (scan_id,),
            ).fetchall()
        ]
        if building_id:
            prefix = f"{canonical_scope(building_id)}%"
            rows = [row for row in rows if canonical_identity(row.get("identity")).startswith(prefix[:-1])]
        elif site_id:
            prefix = canonical_scope(site_id)
            rows = [row for row in rows if canonical_identity(row.get("identity")).startswith(prefix)]
        deduped = dedupe_vendor_mac_groups(rows, vendor)
        clusters = [row for row in (deduped.get("clusters") or []) if int(row.get("alternate_mac_count") or 0) > 0]
        rollups: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in clusters:
            key = (
                tuple(sorted(str(mac or "") for mac in (row.get("macs") or []))),
                str(((row.get("relation") or {}).get("kind") or "")),
            )
            current = rollups.setdefault(
                key,
                {
                    "macs": sorted(str(mac or "") for mac in (row.get("macs") or [])),
                    "relation": row.get("relation") or {},
                    "edge_sightings": [],
                    "uplink_sightings": [],
                    "identities": [],
                },
            )
            sighting = {
                "identity": row.get("identity"),
                "on_interface": row.get("on_interface"),
                "vid": row.get("vid"),
            }
            current["identities"].append(str(row.get("identity") or ""))
            bucket = "uplink_sightings" if is_probable_uplink_interface(row.get("on_interface")) else "edge_sightings"
            current[bucket].append(sighting)

        rollup_rows = sorted(
            rollups.values(),
            key=lambda row: (
                0 if row.get("edge_sightings") else 1,
                -len(row.get("edge_sightings") or []),
                -len(row.get("uplink_sightings") or []),
                ",".join(row.get("macs") or []),
            ),
        )

        actionable_candidates: list[dict[str, Any]] = []
        if vendor == "vilo":
            audit = self.get_vilo_inventory_audit(site_id, building_id, max(200, limit * 10))
            seen_actionable: set[str] = set()
            for row in (audit.get("rows") or []):
                mac = norm_mac(row.get("device_mac") or "")
                sighting = row.get("sighting") or {}
                if not mac or mac in seen_actionable:
                    continue
                if not row.get("scan_seen"):
                    continue
                if is_probable_uplink_interface(sighting.get("on_interface")):
                    continue
                seen_actionable.add(mac)
                cpe = self.get_cpe_state(mac, include_bigmac=True)
                nearby = self._nearby_vilo_mac_candidates(mac, limit=5)
                nearby_cloud = [item for item in nearby if item.get("source") == "vilo_cloud_network"]
                related_same_identity = [
                    item
                    for item in (cpe.get("related_mac_candidates") or [])
                    if canonical_identity(item.get("identity")) == canonical_identity(sighting.get("identity"))
                ]
                if row.get("classification") == "inventory_matched":
                    candidate_type = "cloud_known_edge_vilo"
                    next_step = "Use Vilo cloud detail for this edge port first. If service is still bad, validate WAN/DHCP locally before replacing or adopting anything."
                elif nearby_cloud and related_same_identity:
                    candidate_type = "likely_bridged_or_dual_patched"
                    next_step = "Do not onboard this MAC first. Check whether WAN and LAN are both patched into the switch or bridged through the unit. Keep only the intended WAN/access side."
                elif cpe.get("is_service_online"):
                    candidate_type = "edge_device_alive_but_untracked"
                    next_step = "This edge MAC is physically present and has live L3 evidence but is missing from Vilo cloud. Treat it as an onboarding/reconciliation candidate."
                else:
                    candidate_type = "untracked_edge_candidate"
                    next_step = "This looks like a real edge-port Vilo candidate with no cloud inventory match. Try local access/adoption before assuming the port is bad."
                actionable_candidates.append(
                    {
                        "mac": mac,
                        "classification": row.get("classification"),
                        "candidate_type": candidate_type,
                        "identity": sighting.get("identity"),
                        "building_id": sighting.get("building_id"),
                        "on_interface": sighting.get("on_interface"),
                        "vid": sighting.get("vid"),
                        "is_service_online": bool(cpe.get("is_service_online")),
                        "has_arp": bool(cpe.get("arp_entries")),
                        "nearby_cloud_matches": nearby_cloud[:3],
                        "related_same_identity": related_same_identity[:3],
                        "next_step": next_step,
                    }
                )
            actionable_candidates.sort(
                key=lambda row: (
                    0 if row.get("candidate_type") in {"likely_bridged_or_dual_patched", "edge_device_alive_but_untracked", "untracked_edge_candidate"} else 1,
                    0 if row.get("has_arp") else 1,
                    str(row.get("identity") or ""),
                    str(row.get("on_interface") or ""),
                )
            )
        else:
            seen_actionable: set[tuple[str, str, str]] = set()
            for row in rollup_rows:
                macs = [norm_mac(mac) for mac in (row.get("macs") or []) if norm_mac(mac)]
                relation = row.get("relation") or {}
                reason = str(relation.get("kind") or "related")
                edges = [dict(item) for item in (row.get("edge_sightings") or [])]
                uplinks = [dict(item) for item in (row.get("uplink_sightings") or [])]
                if not macs or not edges:
                    continue
                primary_mac = macs[0]
                primary_edge = edges[0]
                dedupe_key = (primary_mac, str(primary_edge.get("identity") or ""), str(primary_edge.get("on_interface") or ""))
                if dedupe_key in seen_actionable:
                    continue
                seen_actionable.add(dedupe_key)
                cpe = self.get_cpe_state(primary_mac, include_bigmac=True)
                edge_count = len(edges)
                uplink_count = len(uplinks)
                if edge_count == 1 and reason in {"last_octet_adjacent", "first_octet_adjacent"}:
                    candidate_type = "likely_single_hc220_multi_mac"
                    next_step = "Treat this as one HC220-style CPE first. Do not count each MAC as a separate unit unless DHCP direction or unrelated MACs prove a dirty segment."
                elif edge_count == 1 and uplink_count > 0:
                    candidate_type = "edge_cpe_with_upstream_repeats"
                    next_step = "This looks like one customer-facing TP-Link identity plus expected uplink repeats. Prioritize the edge port and ignore uplink duplicates when counting physical units."
                else:
                    candidate_type = "possible_bridge_or_dirty_segment"
                    next_step = "Multiple edge-port sightings for the same TP-Link MAC cluster suggest a bridge, unmanaged switch, or wrong-port patch. Check DHCP direction and isolate the cleanest edge port before treating these as separate ONUs."
                actionable_candidates.append(
                    {
                        "mac": primary_mac,
                        "macs": macs,
                        "candidate_type": candidate_type,
                        "identity": primary_edge.get("identity"),
                        "building_id": ".".join(str(primary_edge.get("identity") or "").split(".")[:2]) or None,
                        "on_interface": primary_edge.get("on_interface"),
                        "vid": primary_edge.get("vid"),
                        "has_arp": bool(cpe.get("arp_entries")),
                        "is_service_online": bool(cpe.get("is_service_online")),
                        "edge_sighting_count": edge_count,
                        "uplink_sighting_count": uplink_count,
                        "relation_kind": reason,
                        "next_step": next_step,
                    }
                )
            actionable_candidates.sort(
                key=lambda row: (
                    0 if row.get("candidate_type") == "possible_bridge_or_dirty_segment" else 1,
                    0 if row.get("edge_sighting_count", 0) > 1 else 1,
                    0 if row.get("has_arp") else 1,
                    str(row.get("identity") or ""),
                    str(row.get("on_interface") or ""),
                )
            )
        return {
            "vendor": vendor,
            "site_id": canonical_scope(site_id) if site_id else None,
            "building_id": canonical_scope(building_id) if building_id else None,
            "scan": self.latest_scan_meta(),
            "raw_mac_count": deduped.get("raw_mac_count", 0),
            "estimated_cpe_count": deduped.get("estimated_cpe_count", 0),
            "alternate_cluster_count": len(clusters),
            "clusters": clusters[: max(1, int(limit))],
            "rollups": rollup_rows[: max(1, int(limit))],
            "actionable_candidates": actionable_candidates[: max(1, int(limit))],
        }

    def capture_operator_note(self, note: str, site_id: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        note = str(note or "").strip()
        if not note:
            raise ValueError("note is required")
        tags = [str(tag).strip() for tag in (tags or []) if str(tag).strip()]
        site_id = canonical_scope(site_id) if site_id else None
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S %Z")
        if not OPERATOR_NOTES_PATH.exists():
            OPERATOR_NOTES_PATH.write_text("# Jake Operator Learned Notes\n\n")
        with OPERATOR_NOTES_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"## {timestamp}\n")
            if site_id:
                handle.write(f"- site: `{site_id}`\n")
            if tags:
                handle.write(f"- tags: {', '.join(f'`{tag}`' for tag in tags)}\n")
            handle.write(f"- note: {note}\n\n")
        return {
            "saved": True,
            "path": str(OPERATOR_NOTES_PATH),
            "site_id": site_id,
            "tags": tags,
            "note": note,
        }

    def get_local_ont_path(self, mac: str | None, serial: str | None) -> dict[str, Any]:
        mac_norm = norm_mac(mac or "") if mac else None
        serial_norm = str(serial or "").strip().upper() or None
        match: dict[str, Any] | None = None
        source = "none"

        if mac_norm and mac_norm in LOCAL_OLT_EVIDENCE_BY_MAC:
            match = dict(LOCAL_OLT_EVIDENCE_BY_MAC[mac_norm])
            source = "field_notes_by_mac"
            if match.get("serial") and not serial_norm:
                serial_norm = str(match.get("serial") or "").strip().upper() or None
        if not match and serial_norm and serial_norm in LOCAL_OLT_EVIDENCE_BY_SERIAL:
            match = dict(LOCAL_OLT_EVIDENCE_BY_SERIAL[serial_norm])
            source = "field_notes_by_serial"
        if not match and serial_norm and serial_norm in load_local_olt_telemetry():
            rows = load_local_olt_telemetry()[serial_norm]
            first = rows[0]
            unique_paths = sorted(
                {
                    (
                        str(row.get("olt_name") or ""),
                        str(row.get("pon") or ""),
                        str(row.get("onu_id") or ""),
                    )
                    for row in rows
                }
            )
            match = {
                "kind": "local-olt-telemetry-ambiguous" if len(unique_paths) > 1 else "local-olt-telemetry",
                "summary": (
                    "Local TP-Link OLT telemetry matched this serial, but the available files disagree on the exact OLT/ONU placement."
                    if len(unique_paths) > 1
                    else "Local TP-Link OLT telemetry matched this serial in exporter-style ONU status data."
                ),
                "olt_name": first.get("olt_name"),
                "olt_ip": first.get("olt_ip"),
                "pon": first.get("pon"),
                "onu_id": first.get("onu_id"),
                "site_name": first.get("site_name"),
                "serial": serial_norm,
                "path_count": len(unique_paths),
                "unique_paths": [
                    {"olt_name": olt_name or None, "pon": pon or None, "onu_id": onu_id or None}
                    for olt_name, pon, onu_id in unique_paths[:10]
                ],
                "details": rows[:5],
            }
            source = "local_olt_telemetry"

        return {
            "query": {"mac": mac_norm, "serial": serial_norm},
            "found": bool(match),
            "source": source,
            "placement": match,
        }

    def get_cpe_state(self, mac: str, include_bigmac: bool) -> dict[str, Any]:
        mac = norm_mac(mac)
        scan_id = self.latest_scan_id()
        bridge = self.trace_mac(mac, include_bigmac)
        ppp = self.db.execute(
            "select router_ip, name, service, caller_id, address, uptime from router_ppp_active where scan_id=? and lower(caller_id)=lower(?) order by router_ip,name",
            (scan_id, mac),
        ).fetchall()
        arp = self.db.execute(
            "select router_ip, address, mac, interface, dynamic from router_arp where scan_id=? and lower(mac)=lower(?) order by router_ip,address",
            (scan_id, mac),
        ).fetchall()
        local_ont_path = self.get_local_ont_path(mac, None)
        subscriber_name = None
        compact_mac = mac.replace(":", "")
        for candidate_name, candidate_mac in SUBSCRIBER_NAME_TO_MAC.items():
            if candidate_mac == compact_mac:
                subscriber_name = candidate_name
                break
        local_subscriber = (local_ont_path.get("placement") or {}).get("subscriber")
        if local_subscriber and not subscriber_name:
            subscriber_name = str(local_subscriber)
        primary_sighting = bridge.get("primary_sighting") or {}
        primary_port = str(primary_sighting.get("port_name") or primary_sighting.get("on_interface") or "").strip()
        primary_port_role = classify_port_role(primary_port)
        local_placement = (local_ont_path.get("placement") or {}) if local_ont_path.get("found") else {}
        site_id = canonical_scope(
            primary_sighting.get("device_site")
            or str(primary_sighting.get("identity") or "").split(".", 1)[0]
            or str(local_placement.get("olt_name") or "").split(".", 1)[0]
        )
        client_ip = str(primary_sighting.get("client_ip") or "").strip() or None
        should_try_olt_correlation = bool(site_id) and (
            primary_port_role == "uplink"
            or bool(local_placement.get("olt_name") or local_placement.get("olt_ip") or local_placement.get("pon"))
        )
        olt_correlation = (
            self._auto_correlate_olt(mac, client_ip, site_id)
            if should_try_olt_correlation
            else {
                "found": False,
                "onu_id": None,
                "pon": None,
                "olt_name": None,
                "olt_ip": None,
                "signal_dbm": None,
                "onu_status": None,
                "matched_by": "none",
                "raw": {},
            }
        )
        dhcp_correlation = (
            self._auto_correlate_dhcp_logs(mac, site_id, window_minutes=60)
            if primary_port_role == "uplink" and site_id and self._loki_base_url()
            else {
                "found": False,
                "request_count": 0,
                "requests_per_hour": 0.0,
                "verdict": "normal",
                "sample_lines": [],
            }
        )
        return {
            "mac": mac,
            "subscriber_name": subscriber_name,
            "seen_by_device": primary_sighting.get("device_name") or primary_sighting.get("identity"),
            "cpe_hostname": primary_sighting.get("hostname"),
            "site_id": site_id,
            "scan": self.latest_scan_meta(),
            "bridge": bridge,
            "ppp_sessions": [dict(r) for r in ppp],
            "arp_entries": [dict(r) for r in arp],
            "related_mac_candidates": self._related_cpe_mac_candidates(mac, limit=5),
            "local_ont_path": local_ont_path,
            "olt_correlation": olt_correlation,
            "dhcp_correlation": dhcp_correlation,
            "is_physically_seen": bool(bridge.get("primary_sighting") or bridge.get("verified_sightings")),
            "is_service_online": bool(ppp or arp),
        }


class MCPServer:
    def __init__(self) -> None:
        self.ops = JakeOps()

    def run(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                return
            if "method" in message and message.get("id") is None:
                continue
            self._handle_request(message)

    def _handle_request(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = message.get("method")
        try:
            if method == "initialize":
                result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "jake-ops-mcp", "version": "0.1.0"}}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self._call_tool(message.get("params", {}))
            else:
                raise ValueError(f"Unsupported method: {method}")
            self._write_message({"jsonrpc": "2.0", "id": request_id, "result": result})
        except Exception as exc:
            self._write_message({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc), "data": traceback.format_exc()}})

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "get_server_info":
            data = self.ops.get_server_info()
        elif name == "query_summary":
            data = self.ops.query_summary(arguments["query"])
        elif name == "get_outage_context":
            data = self.ops.get_outage_context(arguments["address_text"], arguments["unit"])
        elif name == "audit_device_labels":
            data = self.ops.audit_device_labels(bool(arguments.get("include_valid", False)), int(arguments.get("limit", 500)))
        elif name == "get_subnet_health":
            data = self.ops.get_subnet_health(arguments.get("subnet"), arguments.get("site_id"), bool(arguments.get("include_alerts", True)), bool(arguments.get("include_bigmac", True)))
        elif name == "get_online_customers":
            data = self.ops.get_online_customers(arguments.get("scope"), arguments.get("site_id"), arguments.get("building_id"), arguments.get("router_identity"))
        elif name == "compare_customer_evidence":
            data = self.ops.compare_customer_evidence(arguments["site_id"])
        elif name == "trace_mac":
            data = self.ops.trace_mac(arguments["mac"], bool(arguments.get("include_bigmac", True)))
        elif name == "get_netbox_device":
            data = self.ops.get_netbox_device(arguments["name"])
        elif name == "get_netbox_device_by_ip":
            data = self.ops.get_netbox_device_by_ip(arguments["ip"])
        elif name == "get_site_alerts":
            data = self.ops.get_site_alerts(arguments["site_id"])
        elif name == "get_site_summary":
            data = self.ops.get_site_summary(arguments["site_id"], bool(arguments.get("include_alerts", True)))
        elif name == "get_site_historical_evidence":
            data = self.ops.get_site_historical_evidence(arguments["site_id"])
        elif name == "get_site_syslog_summary":
            data = self.ops.get_site_syslog_summary(arguments["site_id"])
        elif name == "get_dhcp_findings_summary":
            data = self.ops.get_dhcp_findings_summary()
        elif name == "get_dhcp_relay_summary":
            data = self.ops.get_dhcp_relay_summary(arguments["relay_name"])
        elif name == "get_dhcp_circuit_summary":
            data = self.ops.get_dhcp_circuit_summary(arguments["circuit_id"])
        elif name == "get_dhcp_subscriber_summary":
            data = self.ops.get_dhcp_subscriber_summary(
                arguments.get("mac"),
                arguments.get("ip"),
                arguments.get("circuit_id"),
                arguments.get("remote_id"),
                arguments.get("subscriber_id"),
                arguments.get("relay_name"),
            )
        elif name == "get_live_dhcp_lease_summary":
            data = self.ops.get_live_dhcp_lease_summary(arguments.get("site_id"), arguments.get("mac"), arguments.get("ip"), int(arguments.get("limit", 25)))
        elif name == "get_live_splynx_online_summary":
            data = self.ops.get_live_splynx_online_summary(arguments.get("site_id"), arguments.get("search"), int(arguments.get("limit", 25)))
        elif name == "get_live_cnwave_rf_summary":
            data = self.ops.get_live_cnwave_rf_summary(arguments.get("site_id"), arguments.get("name"), int(arguments.get("limit", 20)))
        elif name == "get_live_cnwave_radio_neighbors":
            data = self.ops.get_live_cnwave_radio_neighbors(arguments.get("site_id"), arguments.get("name"), arguments.get("query"))
        elif name == "run_live_routeros_read":
            data = self.ops.run_live_routeros_read(arguments["device_name"], arguments["intent"], arguments.get("params"), arguments.get("reason"))
        elif name == "get_live_source_readiness":
            data = self.ops.get_live_source_readiness()
        elif name == "get_live_rogue_dhcp_scan":
            data = self.ops.get_live_rogue_dhcp_scan(arguments.get("site_id"), arguments.get("device_name"), arguments.get("interface"), int(arguments.get("seconds", 5)), arguments.get("mac"))
        elif name == "get_port_physical_state":
            data = self.ops.get_port_physical_state(arguments["interface"], arguments.get("site_id"), arguments.get("device_name"))
        elif name == "get_pppoe_diagnostics":
            data = self.ops.get_pppoe_diagnostics(arguments["unit"], arguments.get("site_id"))
        elif name == "get_dhcp_behavior":
            data = self.ops.get_dhcp_behavior(arguments["unit"], arguments.get("site_id"), arguments.get("device_name"), arguments.get("interface"), arguments.get("mac"))
        elif name == "get_live_capsman_summary":
            data = self.ops.get_live_capsman_summary(arguments.get("site_id"), arguments.get("device_name"))
        elif name == "get_live_wifi_registration_summary":
            data = self.ops.get_live_wifi_registration_summary(arguments.get("site_id"), arguments.get("device_name"), int(arguments.get("limit", 25)))
        elif name == "get_live_wifi_provisioning_summary":
            data = self.ops.get_live_wifi_provisioning_summary(arguments.get("site_id"), arguments.get("device_name"))
        elif name == "get_live_routeros_export":
            data = self.ops.get_live_routeros_export(arguments.get("site_id"), arguments.get("device_name"), bool(arguments.get("show_sensitive", True)), bool(arguments.get("terse", True)))
        elif name == "review_live_upgrade_risk":
            data = self.ops.review_live_upgrade_risk(arguments.get("site_id"), arguments.get("device_name"), arguments.get("target_version", "7.22.1"))
        elif name == "generate_upgrade_preflight_plan":
            data = self.ops.generate_upgrade_preflight_plan(arguments.get("site_id"), arguments.get("device_name"), arguments.get("target_version", "7.22.1"))
        elif name == "render_upgrade_change_explanation":
            data = self.ops.render_upgrade_change_explanation(arguments.get("site_id"), arguments.get("device_name"), arguments.get("target_version", "7.22.1"))
        elif name == "run_live_olt_read":
            data = self.ops.run_live_olt_read(arguments["olt_ip"], arguments["command"], arguments.get("olt_name"))
        elif name == "get_live_olt_ont_summary":
            data = self.ops.get_live_olt_ont_summary(
                arguments.get("mac"),
                arguments.get("serial"),
                arguments.get("olt_name"),
                arguments.get("olt_ip"),
                arguments.get("pon"),
                arguments.get("onu_id"),
            )
        elif name == "get_live_olt_log_summary":
            data = self.ops.get_live_olt_log_summary(
                arguments.get("site_id"),
                arguments.get("olt_name"),
                arguments.get("olt_ip"),
                arguments.get("mac"),
                arguments.get("serial"),
                arguments.get("word"),
                arguments.get("module"),
                arguments.get("level"),
            )
        elif name == "get_tp_link_subscriber_join":
            data = self.ops.get_tp_link_subscriber_join(
                arguments.get("network_name"),
                arguments.get("network_id"),
                arguments.get("mac"),
                arguments.get("serial"),
                arguments.get("site_id"),
            )
        elif name == "get_cpe_management_surface":
            data = self.ops.get_cpe_management_surface(
                arguments.get("network_name"),
                arguments.get("network_id"),
                arguments.get("mac"),
                arguments.get("serial"),
                arguments.get("site_id"),
            )
        elif name == "get_cpe_management_readiness":
            data = self.ops.get_cpe_management_readiness(arguments.get("vendor"))
        elif name == "list_sites_inventory":
            data = self.ops.list_sites_inventory(int(arguments.get("limit", 200)))
        elif name == "search_sites_inventory":
            data = self.ops.search_sites_inventory(arguments["query"], int(arguments.get("limit", 25)))
        elif name == "get_site_topology":
            data = self.ops.get_site_topology(arguments["site_id"])
        elif name == "get_tauc_network_name_list":
            data = self.ops.get_tauc_network_name_list(arguments["status"], int(arguments.get("page", 0)), int(arguments.get("page_size", 100)), arguments.get("name_prefix"))
        elif name == "get_tauc_network_details":
            data = self.ops.get_tauc_network_details(arguments["network_id"])
        elif name == "get_tauc_preconfiguration_status":
            data = self.ops.get_tauc_preconfiguration_status(arguments["network_id"])
        elif name == "get_tauc_pppoe_status":
            data = self.ops.get_tauc_pppoe_status(arguments["network_id"], bool(arguments.get("refresh", True)), bool(arguments.get("include_credentials", False)))
        elif name == "get_tauc_device_id":
            data = self.ops.get_tauc_device_id(arguments["sn"], arguments["mac"])
        elif name == "get_tauc_device_detail":
            data = self.ops.get_tauc_device_detail(arguments["device_id"])
        elif name == "get_tauc_device_internet":
            data = self.ops.get_tauc_device_internet(arguments["device_id"])
        elif name == "get_tauc_olt_devices":
            data = self.ops.get_tauc_olt_devices(arguments.get("mac"), arguments.get("sn"), arguments.get("status"), int(arguments.get("page", 0)), int(arguments.get("page_size", 50)))
        elif name == "get_vilo_server_info":
            data = self.ops.get_vilo_server_info()
        elif name == "get_vilo_inventory":
            data = self.ops.get_vilo_inventory(int(arguments.get("page_index", 1)), int(arguments.get("page_size", 20)))
        elif name == "get_vilo_inventory_audit":
            data = self.ops.audit_vilo_inventory(arguments.get("site_id"), arguments.get("building_id"), int(arguments.get("limit", 500)))
        elif name == "export_vilo_inventory_audit":
            data = self.ops.export_vilo_inventory_audit(arguments.get("site_id"), arguments.get("building_id"), int(arguments.get("limit", 500)))
        elif name == "search_vilo_inventory":
            data = self.ops.search_vilo_inventory(arguments.get("filter") or [], int(arguments.get("page_index", 1)), int(arguments.get("page_size", 20)))
        elif name == "get_vilo_subscribers":
            data = self.ops.get_vilo_subscribers(int(arguments.get("page_index", 1)), int(arguments.get("page_size", 20)))
        elif name == "search_vilo_subscribers":
            data = self.ops.search_vilo_subscribers(arguments.get("filter") or [], int(arguments.get("page_index", 1)), int(arguments.get("page_size", 20)))
        elif name == "get_vilo_networks":
            data = self.ops.get_vilo_networks(int(arguments.get("page_index", 1)), int(arguments.get("page_size", 20)))
        elif name == "search_vilo_networks":
            data = self.ops.search_vilo_networks(arguments.get("filter") or [], arguments.get("sort") or [], int(arguments.get("page_index", 1)), int(arguments.get("page_size", 20)))
        elif name == "get_vilo_devices":
            data = self.ops.get_vilo_devices(arguments["network_id"])
        elif name == "get_vilo_target_summary":
            data = self.ops.get_vilo_target_summary(arguments.get("mac"), arguments.get("network_id"), arguments.get("network_name"))
        elif name == "get_radio_handoff_trace":
            data = self.ops.get_radio_handoff_trace(arguments.get("query"), arguments.get("name"))
        elif name == "get_site_radio_inventory":
            data = self.ops.get_site_radio_inventory(arguments["site_id"])
        elif name == "search_vilo_devices":
            data = self.ops.search_vilo_devices(arguments["network_id"], arguments.get("sort_group") or [])
        elif name == "get_building_health":
            data = self.ops.get_building_health(arguments["building_id"], bool(arguments.get("include_alerts", True)))
        elif name == "get_building_model":
            data = self.ops.get_building_model(arguments["building_id"])
        elif name == "get_switch_summary":
            data = self.ops.get_switch_summary(arguments["switch_identity"])
        elif name == "get_building_customer_count":
            data = self.ops.get_building_customer_count(arguments["building_id"])
        elif name == "get_building_flap_history":
            data = self.ops.get_building_flap_history(arguments["building_id"])
        elif name == "get_site_flap_history":
            data = self.ops.get_site_flap_history(arguments["site_id"])
        elif name == "get_rogue_dhcp_suspects":
            data = self.ops.get_rogue_dhcp_suspects(arguments.get("building_id"), arguments.get("site_id"))
        elif name == "get_site_rogue_dhcp_summary":
            data = self.ops.get_site_rogue_dhcp_summary(arguments["site_id"])
        elif name == "get_recovery_ready_cpes":
            data = self.ops.get_recovery_ready_cpes(arguments.get("building_id"), arguments.get("site_id"))
        elif name == "get_site_punch_list":
            data = self.ops.get_site_punch_list(arguments["site_id"])
        elif name == "find_cpe_candidates":
            data = self.ops.find_cpe_candidates(arguments.get("site_id"), arguments.get("building_id"), arguments.get("oui"), bool(arguments.get("access_only", True)), int(arguments.get("limit", 100)))
        elif name == "get_cpe_state":
            data = self.ops.get_cpe_state(arguments["mac"], bool(arguments.get("include_bigmac", True)))
        elif name == "get_customer_access_trace":
            data = self.ops.get_customer_access_trace(
                arguments.get("network_name"),
                arguments.get("mac"),
                arguments.get("serial"),
                arguments.get("site_id"),
            )
        elif name == "get_vendor_site_presence":
            data = self.ops.get_vendor_site_presence(arguments["vendor"], int(arguments.get("limit", 20)))
        elif name == "get_vendor_alt_mac_clusters":
            data = self.ops.get_vendor_alt_mac_clusters(arguments["vendor"], arguments.get("site_id"), arguments.get("building_id"), int(arguments.get("limit", 50)))
        elif name == "capture_operator_note":
            data = self.ops.capture_operator_note(arguments["note"], arguments.get("site_id"), arguments.get("tags"))
        elif name == "get_local_ont_path":
            data = self.ops.get_local_ont_path(arguments.get("mac"), arguments.get("serial"))
        else:
            raise ValueError(f"Unknown tool: {name}")
        return {"content": [{"type": "text", "text": json.dumps(data)}]}

    def _read_message(self) -> dict[str, Any] | None:
        try:
            line = input()
        except EOFError:
            return None
        if not line:
            return None
        return json.loads(line)

    def _write_message(self, message: dict[str, Any]) -> None:
        print(json.dumps(message), flush=True)


if __name__ == "__main__":
    MCPServer().run()
