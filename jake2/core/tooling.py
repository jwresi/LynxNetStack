from __future__ import annotations

import re
from typing import Any


JAKE_TOOL_REGISTRY: list[dict[str, Any]] = [
    {"name": "get_site_summary", "use_for": ["site health", "site status", "site summary"]},
    {"name": "get_online_customers", "use_for": ["online customer count", "how many users are online"]},
    {"name": "compare_customer_evidence", "use_for": ["discrepancies between sources", "does this match router evidence"]},
    {"name": "trace_mac", "use_for": ["trace a mac", "where does this mac terminate"]},
    {"name": "get_cpe_state", "use_for": ["what is this cpe doing", "is this cpe healthy"]},
    {"name": "get_customer_access_trace", "use_for": ["walk this customer across the network", "full access trace from subscriber to edge evidence"]},
    {"name": "get_local_ont_path", "use_for": ["what PON is this serial or MAC on", "OLT ONU placement from local telemetry"]},
    {"name": "get_vendor_site_presence", "use_for": ["which sites have vilos", "which sites have tplink cpes"]},
    {"name": "get_vendor_alt_mac_clusters", "use_for": ["alternate mac clusters", "mac duplicates on the same port"]},
    {"name": "capture_operator_note", "use_for": ["remember this operator note", "save this learned network pattern"]},
    {"name": "get_vilo_target_summary", "use_for": ["what is going on with this vilo", "look up a vilo network or main mac"]},
    {"name": "get_transport_radio_summary", "use_for": ["what is going on with this cambium or siklu radio", "radio summary by name ip or mac"]},
    {"name": "get_transport_radio_issues", "use_for": ["which cambium radios have issues", "which siklu links look unstable"]},
    {"name": "get_site_radio_inventory", "use_for": ["site radio inventory", "shared-building v2000 aux-port issues"]},
    {"name": "get_radio_handoff_trace", "use_for": ["radio handoff trace", "what macs are visible on the sfp side of this radio path"]},
    {"name": "get_dhcp_findings_summary", "use_for": ["option 82 drift", "dhcp relay findings"]},
    {"name": "get_dhcp_relay_summary", "use_for": ["what do we know about a dhcp relay", "relay status and option 82 policy"]},
    {"name": "get_dhcp_circuit_summary", "use_for": ["break down circuit id", "decode option 82 circuit path"]},
    {"name": "get_dhcp_subscriber_summary", "use_for": ["find subscriber from dhcp lease", "mac or ip to dhcp subscriber snapshot"]},
    {"name": "get_live_dhcp_lease_summary", "use_for": ["live dhcp leases", "current dhcp leases from lynxmsp"]},
    {"name": "get_live_splynx_online_summary", "use_for": ["splynx online users right now", "live splynx joins"]},
    {"name": "get_live_cnwave_rf_summary", "use_for": ["live cambium rssi or snr", "cnwave rf metrics"]},
    {"name": "get_live_cnwave_radio_neighbors", "use_for": ["show ipv4 neighbors on a cnwave radio", "what devices are behind this cambium radio"]},
    {"name": "get_cnwave_controller_capabilities", "use_for": ["what can the cnwave controller show", "why can i see rf health but not downstream identities"]},
    {"name": "run_live_routeros_read", "use_for": ["run approved read-only routeros command from chat", "live mikrotik read"]},
    {"name": "get_live_rogue_dhcp_scan", "use_for": ["scan for rogue dhcp servers", "bounded live dhcp packet capture"]},
    {"name": "get_live_capsman_summary", "use_for": ["live capsman summary", "wifi controller state"]},
    {"name": "get_live_wifi_registration_summary", "use_for": ["live wifi clients", "capsman registration table"]},
    {"name": "get_live_wifi_provisioning_summary", "use_for": ["live capsman provisioning", "wifi provisioning rows"]},
    {"name": "get_live_source_readiness", "use_for": ["which live sources are ready", "live source status on this host"]},
    {"name": "get_site_live_audit_surface", "use_for": ["what can Jake audit live at this site", "what tools do you have here right now"]},
    {"name": "get_site_digi_audit", "use_for": ["what Digi or OOB device is at this site", "Digi audit for this site"]},
    {"name": "run_live_positron_read", "use_for": ["run a read-only Positron command", "live positron cli read"]},
    {"name": "get_live_ghn_summary", "use_for": ["live G.Hn summary", "which units are configured on this Positron"]},
    {"name": "get_live_olt_ont_summary", "use_for": ["show ont info for this subscriber", "live olt onu inspection"]},
    {"name": "get_live_olt_log_summary", "use_for": ["pull olt logs", "live olt flash log query"]},
    {"name": "get_tp_link_subscriber_join", "use_for": ["which subscriber is behind this onu", "tp-link subscriber to olt join"]},
    {"name": "get_site_rogue_dhcp_summary", "use_for": ["rogue dhcp at a site", "rogue dhcp summary"]},
    {"name": "get_rogue_dhcp_suspects", "use_for": ["rogue dhcp suspects in a building", "suspect ports"]},
    {"name": "subscriber_lookup", "use_for": ["unit or cpe summary", "subscriber to cpe/olt path"]},
]


SOURCE_TOOL_HINTS: dict[str, list[str]] = {
    "local_online_cpe_export": ["subscriber_lookup", "get_online_customers", "get_tp_link_subscriber_join"],
    "router_arp": ["compare_customer_evidence", "trace_mac", "get_customer_access_trace", "get_live_rogue_dhcp_scan"],
    "router_ppp_active": ["compare_customer_evidence", "get_customer_access_trace", "subscriber_lookup"],
    "live_dhcp_leases": ["get_live_dhcp_lease_summary", "get_dhcp_subscriber_summary"],
    "tauc_runtime": ["get_tp_link_subscriber_join", "get_cpe_state"],
    "live_olt_onu_state": ["get_live_olt_ont_summary", "get_live_olt_log_summary"],
    "olt_mac_table": ["get_tp_link_subscriber_join", "trace_mac"],
    "switchos_edge_state": ["trace_mac", "get_vendor_alt_mac_clusters"],
    "switch_mac_evidence": ["trace_mac", "get_vendor_alt_mac_clusters"],
    "vilo_inventory_audit": ["get_vilo_target_summary", "get_vendor_alt_mac_clusters"],
    "netbox_site_inventory": ["get_site_summary", "subscriber_lookup"],
    "router_wifi_state": ["get_live_capsman_summary", "get_live_wifi_registration_summary", "get_live_wifi_provisioning_summary"],
}


def _contains_term(text: str, term: str) -> bool:
    lowered = str(text or "").lower()
    needle = str(term or "").strip().lower()
    if not needle:
        return False
    pattern = re.escape(needle)
    pattern = pattern.replace(r"\ ", r"\s+")
    pattern = pattern.replace(r"\-", r"[-\s]+")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", lowered, re.I) is not None


def _contains_any(text: str, terms: list[str] | tuple[str, ...]) -> bool:
    return any(_contains_term(text, term) for term in terms)


TOOL_DOMAIN_GROUPS: dict[str, dict[str, Any]] = {
    "site_observability": {
        "summary": "Cross-site and per-site inventory, alerting, customer counts, and L2/L3 correlation.",
        "tools": [
            "get_site_summary",
            "get_online_customers",
            "compare_customer_evidence",
            "trace_mac",
            "get_live_dhcp_lease_summary",
            "get_live_splynx_online_summary",
            "get_live_source_readiness",
            "subscriber_lookup",
        ],
    },
    "tplink_access": {
        "summary": "TP-Link TAUC, OLT, ONU, and HC220 subscriber correlation.",
        "tools": [
            "get_cpe_state",
            "get_local_ont_path",
            "get_live_olt_ont_summary",
            "get_live_olt_log_summary",
            "get_tp_link_subscriber_join",
            "get_vendor_alt_mac_clusters",
        ],
    },
    "vilo_access": {
        "summary": "Vilo inventory, hidden-controller joins, and Vilo-specific target summaries.",
        "tools": [
            "get_vilo_target_summary",
            "get_vendor_site_presence",
            "get_vendor_alt_mac_clusters",
        ],
    },
    "dhcp_identity": {
        "summary": "DHCP relay, Option 82, rogue DHCP, and subscriber identity correlation.",
        "tools": [
            "get_dhcp_findings_summary",
            "get_dhcp_relay_summary",
            "get_dhcp_circuit_summary",
            "get_dhcp_subscriber_summary",
            "get_site_rogue_dhcp_summary",
            "get_rogue_dhcp_suspects",
        ],
    },
    "wireless_transport": {
        "summary": "Cambium, Siklu, and transport RF / topology issue inspection.",
        "tools": [
            "get_transport_radio_summary",
            "get_transport_radio_issues",
            "get_site_radio_inventory",
            "get_radio_handoff_trace",
            "get_live_cnwave_rf_summary",
            "get_live_cnwave_radio_neighbors",
            "get_cnwave_controller_capabilities",
        ],
    },
    "wireless_live_state": {
        "summary": "Live MikroTik WiFi and CAPsMAN state reads for controller status, registrations, and provisioning.",
        "tools": [
            "get_live_capsman_summary",
            "get_live_wifi_registration_summary",
            "get_live_wifi_provisioning_summary",
        ],
    },
    "routeros_access_troubleshooting": {
        "summary": "RouterOS subscriber-access troubleshooting for PPPoE, DHCP, IPoE, RADIUS, NAT, and IPv6 access-path issues.",
        "tools": ["routeros_access_mcp"],
    },
    "routeros_switching_troubleshooting": {
        "summary": "RouterOS bridge-engine troubleshooting for bridge, VLAN, STP, HW offload, multicast, RA Guard, and MVRP issues.",
        "tools": ["routeros_switching_mcp"],
    },
    "routeros_routing_troubleshooting": {
        "summary": "RouterOS routing-control-plane troubleshooting for BGP, OSPF, VRF, failover, and route lifecycle issues.",
        "tools": ["routeros_routing_mcp"],
    },
    "routeros_platform_troubleshooting": {
        "summary": "RouterOS platform and upgrade-risk troubleshooting for CCR2004, RB5009, L009, RouterBOARD firmware, PoE disruption, and release strategy.",
        "tools": ["routeros_platform_mcp"],
    },
    "routeros_ops_troubleshooting": {
        "summary": "RouterOS operations and scripting troubleshooting for export/API behavior, SNMP, logging, fetch, and automation drift.",
        "tools": ["routeros_ops_mcp"],
    },
    "routeros_wireless_troubleshooting": {
        "summary": "RouterOS wireless and CAPsMAN troubleshooting for driver-package choices, provisioning, VLAN patterns, roaming, and community WiFi design.",
        "tools": ["routeros_wireless_mcp"],
    },
    "swos_switching_troubleshooting": {
        "summary": "SwOS edge-switch troubleshooting for host-table, wrong-port, dirty-segment, VLAN/PVID, and CSS access-switch issues.",
        "tools": ["swos_switching_mcp"],
    },
}


TROUBLESHOOTING_MCP_REGISTRY: dict[str, dict[str, Any]] = {
    "routeros_access_mcp": {
        "summary": "Prefer for subscriber-session and access-path issues on RouterOS: PPPoE, DHCP, IPoE, RADIUS, conntrack, IPv6 access.",
        "invoke_when": [
            "pppoe",
            "chap",
            "ms-chap",
            "radius",
            "framed-route",
            "interim-update",
            "dhcp option 82",
            "option 82",
            "tr-101",
            "ipoe",
            "lease stuck",
            "masquerade",
            "conntrack",
            "dhcpv6",
            "pmtu",
            "mss",
        ],
        "avoid_when": ["swos", "switchos", "css", "host table", "wrong port", "dirty segment"],
    },
    "routeros_switching_mcp": {
        "summary": "Prefer for RouterOS bridge-engine issues: bridge forwarding, STP, VLAN filtering, PVID/trunk/access, HW offload, IGMP snooping, RA Guard, MVRP.",
        "invoke_when": [
            "bridge",
            "rstp",
            "stp",
            "vlan filtering",
            "pvid",
            "trunk",
            "access port",
            "hw offload",
            "switch-cpu",
            "igmp snooping",
            "multicast",
            "ra guard",
            "mvrp",
            "bridge vlan",
        ],
        "avoid_when": ["swos", "switchos", "css", "host table", "duplicate mac on one port"],
    },
    "routeros_routing_mcp": {
        "summary": "Prefer for RouterOS routing-control-plane issues: BGP session state, route leaks, VRF binding, OSPF behavior, failover, check-gateway, and safe-mode route lifecycle.",
        "invoke_when": [
            "bgp",
            "ospf",
            "vrf",
            "framed-route",
            "route leak",
            "default-prepend",
            "as-path",
            "multipath",
            "ecmp",
            "safe mode",
            "safe-mode",
            "scope 1",
            "scope 2",
            "check-gateway",
            "failover",
            "default route",
            "redistribute",
        ],
        "avoid_when": ["swos", "switchos", "host table", "dirty segment", "pppoe session is up but no traffic"],
    },
    "routeros_platform_mcp": {
        "summary": "Prefer for RouterOS platform and upgrade-risk questions: CCR2004/RB5009/L009 hardware traps, RouterBOARD firmware, PoE disruption, device mode, and release strategy.",
        "invoke_when": [
            "upgrade",
            "7.22.1",
            "7.22",
            "7.21",
            "routerboard",
            "firmware",
            "device mode",
            "nand",
            "poe firmware",
            "power interruption",
            "ccr2004",
            "rb5009",
            "l009",
            "channel strategy",
            "release strategy",
            "headend upgrade",
        ],
        "avoid_when": ["capsman", "swos host table", "rogue dhcp scan", "bgp route leak diagnosis"],
    },
    "routeros_ops_mcp": {
        "summary": "Prefer for RouterOS automation, scripting, API, export, SNMP, logging, and monitoring behavior changes across versions.",
        "invoke_when": [
            "export",
            "show-sensitive",
            "api sensitive",
            "ansible",
            "terraform",
            "oxidized",
            "unimus",
            "snmp",
            "getbulk",
            "sysdescr",
            "ifspeed",
            "script",
            "scheduler",
            "fetch",
            "http/2",
            "date format",
            "file id",
            "netwatch",
            "check-gateway",
            "logging",
            "supout",
        ],
        "avoid_when": ["capsman roaming", "bgp session stuck", "host table wrong port"],
    },
    "routeros_wireless_mcp": {
        "summary": "Prefer for MikroTik wireless and CAPsMAN issues: driver-package limits, provisioning, roaming, VLAN-per-SSID, iOS compatibility, and community WiFi design.",
        "invoke_when": [
            "capsman",
            "wifi-qcom",
            "wifi-qcom-ac",
            "wireless package",
            "wifi registrations",
            "capsman registrations",
            "wifi registration",
            "registration table",
            "wireless clients",
            "wifi provisioning",
            "wifi configuration",
            "cap ax",
            "cap ac",
            "roaming",
            "ft-over-ds",
            "ssid",
            "wpa3",
            "hotspot",
            "mac randomization",
            "community wifi",
            "campus wifi",
            "walk around wifi",
            "mikrotik ap",
        ],
        "avoid_when": ["bgp", "ospf", "wrong port", "dirty segment", "rogue dhcp scan"],
    },
    "swos_switching_mcp": {
        "summary": "Prefer for SwOS/CSS access-switch issues: host table reads, wrong-port cleanup, dirty segments, duplicate MAC patterns, VLAN/PVID edge mistakes.",
        "invoke_when": [
            "swos",
            "switchos",
            "css",
            "host table",
            "dhost",
            "wrong port",
            "dirty segment",
            "duplicate mac",
            "mixed mac",
            "single-cpe port",
            "pause frame",
            "flow control",
        ],
        "avoid_when": ["pppoe chap", "framed-route", "dhcpv6"],
    },
}


def preferred_troubleshooting_mcp(query: str, site_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    lowered = str(query or "").lower()
    primary_sources = list((site_profile or {}).get("primary_sources") or [])
    service_mode = str((site_profile or {}).get("service_mode") or "").lower()

    scored: list[tuple[int, str, list[str]]] = []
    for mcp_name, meta in TROUBLESHOOTING_MCP_REGISTRY.items():
        score = 0
        matched_cues: list[str] = []
        for cue in meta.get("invoke_when", []):
            if _contains_term(lowered, cue):
                score += 2
                matched_cues.append(cue)
        for cue in meta.get("avoid_when", []):
            if _contains_term(lowered, cue):
                score -= 2
        if mcp_name == "swos_switching_mcp":
            if "switchos_edge_state" in primary_sources:
                score += 2
                matched_cues.append("site:switchos_edge_state")
            if _contains_any(lowered, ("port comment", "wrong-port", "wrong port", "host learning", "same port")):
                score += 1
        if mcp_name == "routeros_switching_mcp":
            if any(src in primary_sources for src in ("switch_mac_evidence", "router_bridge_state")):
                score += 1
                matched_cues.append("site:bridge_or_switch_mac")
            if _contains_any(lowered, ("bridge", "vlan")):
                score += 1
        if mcp_name == "routeros_access_mcp":
            if service_mode in {"pppoe", "ipoe", "dhcp"}:
                score += 1
                matched_cues.append(f"site:{service_mode}")
            if any(src in primary_sources for src in ("router_ppp_active", "live_dhcp_leases", "router_arp")):
                score += 1
                matched_cues.append("site:router_access_plane")
        if mcp_name == "routeros_routing_mcp":
            if _contains_any(lowered, ("bgp", "ospf", "vrf", "route", "check-gateway", "failover")):
                score += 1
            if service_mode in {"routeros_ppp_primary", "routeros_ppp_primary_with_dhcp_evidence", "routeros_ppp_primary_with_local_online_cpe_export"}:
                score += 1
                matched_cues.append("site:router_control_plane")
        if mcp_name == "routeros_platform_mcp":
            if _contains_any(lowered, ("upgrade", "7.22.1", "7.22", "7.21", "routerboard", "firmware", "device mode", "nand", "poe firmware", "power interruption", "ccr2004", "rb5009", "l009", "channel strategy", "release strategy", "headend")):
                score += 2
            if _contains_any(lowered, ("upgrade", "firmware", "headend")):
                matched_cues.append("platform:upgrade_or_hardware")
        if mcp_name == "routeros_ops_mcp":
            if _contains_any(lowered, ("export", "show-sensitive", "api sensitive", "ansible", "terraform", "oxidized", "unimus", "snmp", "getbulk", "sysdescr", "ifspeed", "script", "scheduler", "fetch", "http/2", "date format", "file id", "netwatch", "check-gateway", "logging", "supout")):
                score += 2
            if _contains_any(lowered, ("script", "api", "snmp", "export", "logging", "netwatch")):
                matched_cues.append("ops:automation_or_monitoring")
        if mcp_name == "routeros_wireless_mcp":
            if _contains_any(lowered, ("capsman", "wifi-qcom", "wifi-qcom-ac", "roaming", "ssid", "community wifi", "campus wifi", "mikrotik ap", "cap ax", "cap ac", "wifi registrations", "capsman registrations", "wifi registration", "registration table", "wireless clients", "wifi provisioning", "wifi configuration")):
                score += 2
            if _contains_any(lowered, ("community wifi", "campus wifi", "walk around", "roaming domain", "capsman", "wifi registrations", "capsman registrations", "wifi registration", "wifi provisioning")):
                matched_cues.append("wireless:campus_or_capsman")
        scored.append((score, mcp_name, matched_cues))

    scored.sort(key=lambda row: row[0], reverse=True)
    best_score, best_name, matched_cues = scored[0]
    if best_score <= 0:
        return {
            "preferred_mcp": None,
            "reason": "No strong troubleshooting-MCP signal was found from the current question.",
            "matched_cues": [],
        }
    return {
        "preferred_mcp": best_name,
        "reason": TROUBLESHOOTING_MCP_REGISTRY[best_name]["summary"],
        "matched_cues": matched_cues,
    }


def _scenario_catalog_for_mcp(mcp_name: str) -> dict[str, dict[str, Any]]:
    if mcp_name == "routeros_access_mcp":
        from mcp.routeros_access_catalog import ROUTEROS_ACCESS_SCENARIOS

        return ROUTEROS_ACCESS_SCENARIOS
    if mcp_name == "routeros_switching_mcp":
        from mcp.routeros_switching_catalog import ROUTEROS_SWITCHING_SCENARIOS

        return ROUTEROS_SWITCHING_SCENARIOS
    if mcp_name == "routeros_routing_mcp":
        from mcp.routeros_routing_catalog import ROUTEROS_ROUTING_SCENARIOS

        return ROUTEROS_ROUTING_SCENARIOS
    if mcp_name == "routeros_platform_mcp":
        from mcp.routeros_platform_catalog import ROUTEROS_PLATFORM_SCENARIOS

        return ROUTEROS_PLATFORM_SCENARIOS
    if mcp_name == "routeros_ops_mcp":
        from mcp.routeros_ops_catalog import ROUTEROS_OPS_SCENARIOS

        return ROUTEROS_OPS_SCENARIOS
    if mcp_name == "routeros_wireless_mcp":
        from mcp.routeros_wireless_catalog import ROUTEROS_WIRELESS_SCENARIOS

        return ROUTEROS_WIRELESS_SCENARIOS
    if mcp_name == "swos_switching_mcp":
        from mcp.swos_switching_catalog import SWOS_SWITCHING_SCENARIOS

        return SWOS_SWITCHING_SCENARIOS
    return {}


def dispatch_troubleshooting_scenarios(query: str, site_profile: dict[str, Any] | None = None, limit: int = 3) -> dict[str, Any]:
    preferred = preferred_troubleshooting_mcp(query, site_profile)
    preferred_mcp = preferred.get("preferred_mcp")
    if not preferred_mcp:
        return {
            "preferred_mcp": None,
            "reason": preferred.get("reason"),
            "matched_cues": preferred.get("matched_cues") or [],
            "scenarios": [],
        }

    lowered = str(query or "").lower()
    catalog = _scenario_catalog_for_mcp(preferred_mcp)
    ranked: list[tuple[int, dict[str, Any]]] = []
    for tool_name, scenario in catalog.items():
        score = 0
        for phrase in scenario.get("invoke_when") or []:
            phrase_lower = str(phrase).lower()
            if phrase_lower and _contains_term(lowered, phrase_lower):
                score += 4
                continue
            tokens = [token for token in phrase_lower.replace("/", " ").replace("-", " ").split() if len(token) >= 3]
            overlap = sum(1 for token in tokens if _contains_term(lowered, token))
            score += overlap
        summary_tokens = [token for token in str(scenario.get("summary") or "").lower().replace("/", " ").replace("-", " ").split() if len(token) >= 4]
        score += sum(1 for token in summary_tokens[:12] if _contains_term(lowered, token))
        if preferred_mcp == "routeros_wireless_mcp" and tool_name == "design_capsman_community_wifi_roaming_domain":
            if _contains_any(lowered, ("community wifi", "campus wifi", "walk around", "roaming domain", "capsman")):
                score += 8
        if score > 0:
            ranked.append((score, {"tool_name": tool_name, **scenario}))

    ranked.sort(key=lambda row: (-row[0], row[1]["tool_name"]))
    scenarios = []
    for score, scenario in ranked[: max(1, limit)]:
        entry = dict(scenario)
        entry["match_score"] = score
        scenarios.append(entry)
    return {
        "preferred_mcp": preferred_mcp,
        "reason": preferred.get("reason"),
        "matched_cues": preferred.get("matched_cues") or [],
        "scenarios": scenarios,
    }


def recommend_tools_for_query(query: str, site_profile: dict[str, Any] | None = None, limit: int = 8) -> dict[str, Any]:
    lowered = str(query or "").lower()
    primary_sources = list((site_profile or {}).get("primary_sources") or [])
    service_mode = str((site_profile or {}).get("service_mode") or "").lower()
    site_name = str((site_profile or {}).get("name") or "").strip() or None

    ranked: list[tuple[int, dict[str, Any]]] = []
    for tool in JAKE_TOOL_REGISTRY:
        score = 0
        reasons: list[str] = []
        name = str(tool.get("name") or "")
        for phrase in tool.get("use_for", []) or []:
            phrase_lower = str(phrase).lower()
            if _contains_term(lowered, phrase_lower):
                score += 4
                reasons.append(f"query:{phrase_lower}")
                continue
            tokens = [token for token in phrase_lower.replace("/", " ").replace("-", " ").split() if len(token) >= 4]
            overlap = sum(1 for token in tokens if _contains_term(lowered, token))
            if overlap >= 2:
                score += overlap
                reasons.append(f"query_tokens:{phrase_lower}")
        for source in primary_sources:
            hinted_tools = SOURCE_TOOL_HINTS.get(source, [])
            if name in hinted_tools:
                score += 3
                reasons.append(f"site_source:{source}")
        if service_mode:
            if service_mode in {"pppoe", "ipoe", "dhcp"} and name in {"compare_customer_evidence", "get_live_dhcp_lease_summary", "subscriber_lookup"}:
                score += 2
                reasons.append(f"site_mode:{service_mode}")
            if "wireless" in service_mode and name in {"get_live_capsman_summary", "get_live_wifi_registration_summary", "get_live_wifi_provisioning_summary"}:
                score += 2
                reasons.append(f"site_mode:{service_mode}")
            if any(token in service_mode for token in ("optical", "olt", "gpon")) and name in {"get_live_olt_ont_summary", "get_live_olt_log_summary", "get_tp_link_subscriber_join", "get_site_alerts"}:
                score += 2
                reasons.append(f"site_mode:{service_mode}")
            if any(token in service_mode for token in ("transport", "radio")) and name in {"get_transport_radio_summary", "get_transport_radio_issues", "get_site_radio_inventory", "get_live_cnwave_rf_summary", "get_live_cnwave_radio_neighbors", "get_radio_handoff_trace"}:
                score += 2
                reasons.append(f"site_mode:{service_mode}")
        if _contains_any(lowered, ("which customers are affected", "what customers are affected", "which customers would be affected", "what customers would be affected")):
            if name in {"get_site_alerts", "get_tp_link_subscriber_join", "subscriber_lookup", "get_live_olt_ont_summary"}:
                score += 3
                reasons.append("intent:affected_customers")
        if _contains_any(lowered, ("how is", "how's", "how are things looking", "what can you tell me about", "what is going on at", "what's going on at", "quick read on")):
            if name in {"get_site_summary", "get_site_alerts", "get_site_issue_ledger"}:
                score += 4
                reasons.append("intent:site_summary")
        if _contains_any(lowered, ("what needs to be fixed", "needs to be fixed", "what should we fix", "what should be fixed")):
            if name in {"get_site_summary", "get_site_alerts", "get_site_issue_ledger", "get_site_infrastructure_handoff"}:
                score += 2
                reasons.append("intent:fix_priority")
        if _contains_any(lowered, ("local management", "management do we have", "how much local visibility", "cpe management", "management readiness")):
            if name in {"get_cpe_state", "get_vendor_site_presence", "get_site_live_audit_surface", "subscriber_lookup"}:
                score += 4
                reasons.append("intent:cpe_management")
        if _contains_any(lowered, ("show ipv4 neighbors", "what devices are behind this cambium radio", "behind this radio")):
            if name in {"get_live_cnwave_radio_neighbors", "get_transport_radio_summary", "get_radio_handoff_trace"}:
                score += 5
                reasons.append("intent:radio_neighbors")
        if _contains_any(lowered, ("what tools do you have", "which tools do you have", "what can you audit live", "what can you inspect live")):
            if name in {"get_site_live_audit_surface", "get_live_source_readiness", "get_site_digi_audit"}:
                score += 5
                reasons.append("intent:tool_audit")
        if score and name == "capture_operator_note" and not _contains_any(lowered, ("remember", "save this note", "operator note", "learn this")):
            score = 0
            reasons = []
        if score > 0:
            ranked.append(
                (
                    score,
                    {
                        "name": name,
                        "score": score,
                        "use_for": list(tool.get("use_for") or []),
                        "reasons": reasons[:6],
                    },
                )
            )

    ranked.sort(key=lambda item: (-item[0], item[1]["name"]))
    tools = [tool for _, tool in ranked[: max(1, limit)]]
    preferred = preferred_troubleshooting_mcp(query, site_profile)
    return {
        "site_name": site_name,
        "service_mode": service_mode or None,
        "primary_sources": primary_sources,
        "recommended_tools": tools,
        "preferred_mcp": preferred.get("preferred_mcp"),
        "preferred_mcp_reason": preferred.get("reason"),
        "preferred_mcp_cues": preferred.get("matched_cues") or [],
    }
