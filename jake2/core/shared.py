from __future__ import annotations

import os
import re
import json
from pathlib import Path
from typing import Any
from functools import lru_cache


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JAKE_HOME = Path(os.environ.get("JAKE_HOME", str(PROJECT_ROOT)))
NYCHA_EXPECTED_UNITS_PATH = PROJECT_ROOT / "data" / "nycha_expected_units.json"


SITE_ALIAS_MAP: dict[str, str] = {
    # WHY: Operators say "Savoy" rather than the canonical six-digit site code.
    "savoy": "000002",
    # WHY: "Park79" appears both compressed and spaced in operator chat and notes.
    "park79": "000003",
    # WHY: Preserve the spaced alias because field phrasing is inconsistent.
    "park 79": "000003",
    # WHY: Cambridge is a common shorthand for the site id.
    "cambridge": "000004",
    # WHY: Essex is used as a direct site-name alias in questions.
    "essex": "000005",
    # WHY: Claiborne is used directly by operators instead of the numeric id.
    "claiborne": "000006",
    # WHY: 000007 is routinely called "NYCHA" or "the big job" in operator language.
    "nycha": "000007",
    # WHY: Operators query NYCHA by street address; "2020 Pacific St" is the primary transport node address for site 000007.
    "2020 pacific": "000007",
    "2020 pacific st": "000007",
    "2020 pacific street": "000007",
    "pacific st": "000007",
    "pacific street": "000007",
    # WHY: Chenoweth is used as the primary site shorthand in ops notes.
    "chenoweth": "000008",
    # WHY: Euclid appears in natural-language operator queries.
    "euclid": "000011",
    # WHY: Longwood appears in natural-language operator queries.
    "longwood": "000012",
    # WHY: Londonderry appears in natural-language operator queries.
    "londonderry": "000014",
    # WHY: Millersville appears in natural-language operator queries.
    "millersville": "000015",
    # WHY: Woodlea appears in natural-language operator queries.
    "woodlea": "000016",
    # WHY: Liberty Terrace is referenced both with and without a space.
    "liberty terrace": "000017",
    # WHY: Preserve the compressed alias because operators use both forms.
    "libertyterrace": "000017",
    # WHY: Festival Field is referenced both with and without a space.
    "festival field": "000021",
    # WHY: Preserve the compressed alias because field phrasing is inconsistent.
    "festivalfield": "000021",
    # WHY: Sweetwater appears in natural-language operator queries.
    "sweetwater": "000022",
}


# WHY: switch_uplink_port is the expected uplink interface on CRS switches at this site.
# Used by get_switch_port_audit to detect mispatched switches universally across all sites,
# not just NYCHA. ether49 is correct for CRS354-48G; ether25 is correct for CRS326-24G.
# A site may list multiple candidates (first match wins in audit logic).
# mgmt_subnet is the management network CIDR used by the network scanner at this site.
SITE_SERVICE_PROFILES: dict[str, dict[str, Any]] = {
    "000002": {
        "name": "Savoy",
        "aliases": ["savoy"],
        "service_mode": "dhcp_tauc_tp_link",
        "uses_olt": True,
        "mgmt_subnet": "192.168.55.0/24",
        "switch_uplink_ports": ["ether49", "ether25", "sfp-sfpplus1"],
        "olts": [
            {"olt_name": "000002.OLT01", "olt_ip": "192.168.55.98"},
            {"olt_name": "000002.OLT02", "olt_ip": "192.168.55.97"},
            {"olt_name": "000002.OLT03", "olt_ip": "192.168.55.99"},
            {"olt_name": "000002.OLT04", "olt_ip": "192.168.55.96"},
            {"olt_name": "000002.OLT05", "olt_ip": "192.168.55.95"},
            {"olt_name": "000002.OLT06", "olt_ip": "192.168.55.94"},
            {"olt_name": "000002.OLT07", "olt_ip": "192.168.55.93"},
        ],
        "summary": "DHCP-first TP-Link/TAUC site with CNWave transport and TP-Link OLTs. Prefer subscriber export and OLT/topology evidence over PPP-only assumptions.",
        "primary_sources": ["local_online_cpe_export", "router_arp", "trace_mac", "local_olt_field_notes", "netbox_site_inventory"],
        "count_preference": ["local_online_cpe_export", "router_arp", "router_ppp_active"],
    },
    "000003": {
        "name": "Park79",
        "aliases": ["park79", "park 79"],
        "service_mode": "routeros_ppp_primary",
        "uses_olt": False,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether49", "ether25", "sfp-sfpplus1"],
        "summary": "Park79 site. Do not assume PPP-only evidence; prefer DHCP and ARP alongside PPP when classifying customer state.",
        "primary_sources": ["live_dhcp_leases", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
    # WHY: Cambridge is G.hn over Positron, not fiber. ONU/OLT reasoning here would be actively wrong.
    "000004": {
        "name": "Cambridge",
        "aliases": ["cambridge"],
        "service_mode": "routeros_ppp_primary",
        "uses_olt": False,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether49", "ether25", "sfp-sfpplus1"],
        "last_mile": "ghn_positron",
        "summary": (
            "Cambridge Square site. Last-mile technology is G.hn over Positron GAM adapters — "
            "NOT fiber, NOT GPON, NOT OLT. Do NOT apply ONU/optical-power reasoning here. "
            "When a Positron device is DOWN, check the G.hn coax path, the GAM adapter itself, "
            "and the building coax wiring — not OLT connectors, splitter loss, or optical power. "
            "Prefer DHCP and ARP alongside PPP when classifying customer state."
        ),
        "primary_sources": ["live_dhcp_leases", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
    "000005": {
        "name": "Essex",
        "aliases": ["essex"],
        "service_mode": "routeros_ppp_primary",
        "uses_olt": False,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether49", "ether25", "sfp-sfpplus1"],
        "summary": "Essex site. Do not assume PPP-only evidence; prefer DHCP and ARP alongside PPP when classifying customer state.",
        "primary_sources": ["live_dhcp_leases", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
    "000006": {
        "name": "Claiborne",
        "aliases": ["claiborne"],
        "service_mode": "routeros_ppp_primary",
        "uses_olt": False,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether49", "ether25", "sfp-sfpplus1"],
        "summary": "Claiborne site. Do not assume PPP-only evidence; prefer DHCP and ARP alongside PPP when classifying customer state.",
        "primary_sources": ["live_dhcp_leases", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
    # WHY: NYCHA is switch-access and Vilo/TP-Link heavy, so switch and export evidence outrank any OLT mental model.
    # WHY: switch_uplink_ports for 000007 CRS354-48G-4S+2Q+RM is ether49. ether48 is a mispatch.
    "000007": {
        "name": "NYCHA Brooklyn",
        "aliases": ["nycha"],
        "service_mode": "dhcp_switch_access_primary",
        "uses_olt": False,
        "mgmt_subnet": "192.168.44.0/24",
        "switch_uplink_ports": ["ether49", "sfp-sfpplus1"],
        "summary": "Switch-access TP-Link and Vilo site. Prefer local subscriber export, switch MAC sightings, bridge evidence, and Vilo audit data over OLT assumptions.",
        "primary_sources": ["local_online_cpe_export", "trace_mac", "switch_mac_evidence", "vilo_inventory_audit", "netbox_site_inventory"],
        "count_preference": ["local_online_cpe_export", "router_arp", "router_ppp_active"],
        # WHY: Known router-to-transport interface topology for this site.
        # Used by get_customer_access_trace to resolve cnWave block labels to
        # physical router interfaces without a live API call.
        "legacy_handoff_hints": [
            {
                "block_label_fragment": "Fenimore",
                "device_identity": "000007.055.R01",
                "interface": "sfp-sfpplus10",
                "comment": "Fenimore V5000",
                "source": "NYCHA_NETWORK_TOPOLOGY_2026-03-13",
            },
        ],
    },
    # WHY: Chenoweth is a TP-Link OLT site, so OLT ONU state and OLT-side MAC evidence are first-class inputs.
    "000008": {
        "name": "Chenoweth",
        "aliases": ["chenoweth"],
        "service_mode": "dhcp_tauc_tp_link_olt",
        "uses_olt": True,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether25", "sfp-sfpplus1"],
        "olts": [],
        "summary": "TP-Link HC220 + TP-Link OLT site. Prefer local subscriber export, TAUC runtime, OLT ONU state, OLT-side MAC evidence, and SwitchOS edge state over PPP-only assumptions.",
        "primary_sources": ["local_online_cpe_export", "tauc_runtime", "live_olt_onu_state", "olt_mac_table", "switchos_edge_state", "netbox_site_inventory"],
        "count_preference": ["local_online_cpe_export", "router_arp", "router_ppp_active"],
    },
    # WHY: Euclid is OLT/ONU optics-sensitive, so optical alerts and TAUC evidence matter more than PPP-only summaries.
    "000011": {
        "name": "Euclid",
        "aliases": ["euclid"],
        "service_mode": "dhcp_tauc_tp_link_olt",
        "uses_olt": True,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether25", "sfp-sfpplus1"],
        "olts": [
            {"olt_name": "000011.OLT01", "olt_ip": "10.64.30.22"},
            {"olt_name": "000011.OLT02", "olt_ip": "10.64.30.23"},
            {"olt_name": "000011.OLT03", "olt_ip": "10.64.31.223"},
            {"olt_name": "000011.OLT04", "olt_ip": "10.64.31.224"},
        ],
        "summary": "Euclid site. TP-Link OLT and ONU optics evidence matter here. Prefer live DHCP leases, TAUC/runtime, OLT ONU state, and optical alert clustering over PPP-only assumptions.",
        "primary_sources": ["live_dhcp_leases", "tauc_runtime", "live_olt_onu_state", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
    "000012": {
        "name": "Longwood",
        "aliases": ["longwood"],
        "service_mode": "dhcp_tauc_tp_link_olt",
        "uses_olt": True,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether25", "sfp-sfpplus1"],
        "olts": [
            {"olt_name": "000012.OLT01", "olt_ip": "100.64.19.224"},
        ],
        "summary": "Longwood site. Treat OLT/PON/ONU optics and live DHCP evidence as first-class sources. Do not collapse this site into a PPP-only summary when optical alarms are active.",
        "primary_sources": ["live_dhcp_leases", "tauc_runtime", "live_olt_onu_state", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
    "000014": {
        "name": "Londonderry",
        "aliases": ["londonderry"],
        "service_mode": "routeros_ppp_primary",
        "uses_olt": False,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether49", "ether25", "sfp-sfpplus1"],
        "summary": "Londonderry site. Do not assume PPP-only evidence; prefer DHCP and ARP alongside PPP when classifying customer state.",
        "primary_sources": ["live_dhcp_leases", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
    "000015": {
        "name": "Millersville",
        "aliases": ["millersville"],
        "service_mode": "routeros_ppp_primary",
        "uses_olt": False,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether49", "ether25", "sfp-sfpplus1"],
        "summary": "Millersville site. Do not assume PPP-only evidence; prefer DHCP and ARP alongside PPP when classifying customer state.",
        "primary_sources": ["live_dhcp_leases", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
    "000016": {
        "name": "Woodlea",
        "aliases": ["woodlea"],
        "service_mode": "routeros_ppp_primary",
        "uses_olt": False,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether49", "ether25", "sfp-sfpplus1"],
        "summary": "Woodlea site. Do not assume PPP-only evidence; prefer DHCP and ARP alongside PPP when classifying customer state.",
        "primary_sources": ["live_dhcp_leases", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
    "000017": {
        "name": "Liberty Terrace",
        "aliases": ["liberty terrace", "libertyterrace"],
        "service_mode": "routeros_ppp_primary",
        "uses_olt": False,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether49", "ether25", "sfp-sfpplus1"],
        "summary": "Liberty Terrace site. Do not assume PPP-only evidence; prefer DHCP and ARP alongside PPP when classifying customer state.",
        "primary_sources": ["live_dhcp_leases", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
    "000021": {
        "name": "Festival Field",
        "aliases": ["festival field", "festivalfield"],
        "service_mode": "routeros_ppp_primary",
        "uses_olt": False,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether49", "ether25", "sfp-sfpplus1"],
        "summary": "Festival Field site. Do not treat this site as Chenoweth. Do not assume PPP-only evidence; prefer DHCP and ARP alongside PPP when classifying customer state.",
        "primary_sources": ["live_dhcp_leases", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
    "000022": {
        "name": "Sweetwater",
        "aliases": ["sweetwater"],
        "service_mode": "routeros_ppp_primary",
        "uses_olt": False,
        "mgmt_subnet": None,
        "switch_uplink_ports": ["ether49", "ether25", "sfp-sfpplus1"],
        "summary": "Sweetwater site. Do not assume PPP-only evidence; prefer DHCP and ARP alongside PPP when classifying customer state.",
        "primary_sources": ["live_dhcp_leases", "router_arp", "router_ppp_active", "netbox_site_inventory"],
        "count_preference": ["live_dhcp_leases", "router_arp", "router_ppp_active"],
    },
}


def get_site_profile(site_id: str) -> dict[str, Any]:
    """Return the service profile for a site, or a safe empty default."""
    return SITE_SERVICE_PROFILES.get(site_id, {})


def get_site_uplink_ports(site_id: str) -> list[str]:
    """Return expected uplink port names for a site. Used by port audit logic."""
    return get_site_profile(site_id).get("switch_uplink_ports", ["ether49", "ether25", "sfp-sfpplus1"])


def get_site_mgmt_subnet(site_id: str) -> str | None:
    """Return the management subnet CIDR for a site, or None if not known."""
    return get_site_profile(site_id).get("mgmt_subnet")



def normalize_address_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = text.replace(".", " ")
    text = re.sub(r"[#,]", " ", text)
    text = re.sub(r"\bst\s+johns\b", "saint johns", text)
    text = re.sub(r"\bst\s+marks\b", "saint marks", text)
    text = re.sub(r"\be\s+new\s+york\b", "east new york", text)
    text = re.sub(r"\beast\s+ny\b", "east new york", text)
    text = re.sub(r"\be\s+ny\b", "east new york", text)
    replacements = {
        "ave": "avenue", "av": "avenue", "st": "street", "rd": "road",
        "pl": "place", "blvd": "boulevard", "dr": "drive", "ln": "lane",
        "ct": "court", "pkwy": "parkway", "ter": "terrace", "terr": "terrace",
    }
    for short, long in replacements.items():
        text = re.sub(rf"\b{short}\b", long, text)
    text = re.sub(r"[^a-z0-9\- ]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_street_number_and_name(value: str | None) -> tuple[str | None, str]:
    normalized = normalize_address_text(value)
    match = re.match(r"^(\d{1,5})(?:-\d{1,5})?\s+(.+)$", normalized)
    if not match:
        return None, normalized
    return match.group(1), match.group(2).strip()


def bare_street_name(value: str | None) -> str:
    street = str(value or "").strip()
    street = re.sub(
        r"\b(street|avenue|road|place|boulevard|drive|lane|court|parkway|terrace)\b$",
        "", street,
    )
    street = re.sub(r"\s+", " ", street).strip()
    return street


@lru_cache(maxsize=1)
def load_address_index() -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = {}
    if NYCHA_EXPECTED_UNITS_PATH.exists():
        payload = json.loads(NYCHA_EXPECTED_UNITS_PATH.read_text(encoding="utf-8"))
        for raw_address in payload.keys():
            normalized = normalize_address_text(raw_address)
            if not normalized:
                continue
            number, street_name = extract_street_number_and_name(raw_address)
            record = {
                "address": str(raw_address),
                "normalized": normalized,
                "site_id": "000007",
                "street_number": number or "",
                "street_name": street_name,
                "street_base": bare_street_name(street_name),
            }
            index.setdefault(normalized, []).append(record)
    return index


def resolve_address_candidates(text: str) -> list[dict[str, str]]:
    normalized_query = normalize_address_text(text)
    if not normalized_query:
        return []
    index = load_address_index()
    explicit_matches: list[dict[str, str]] = []
    for normalized_address, rows in index.items():
        if normalized_address and normalized_address in normalized_query:
            explicit_matches.extend(dict(row) for row in rows)
    if explicit_matches:
        return explicit_matches
    exact = index.get(normalized_query)
    if exact:
        return list(exact)
    for rows in index.values():
        for row in rows:
            number = row.get("street_number") or ""
            street_name = row.get("street_name") or ""
            street_base = row.get("street_base") or ""
            if number and street_name and f"{number} {street_name}" in normalized_query:
                explicit_matches.append(dict(row))
            elif number and street_base and f"{number} {street_base}" in normalized_query:
                explicit_matches.append(dict(row))
    if explicit_matches:
        return explicit_matches
    query_number, query_street = extract_street_number_and_name(text)
    if query_number and query_street:
        query_street_base = bare_street_name(query_street)
        matches: list[dict[str, str]] = []
        for rows in index.values():
            for row in rows:
                if row.get("street_number") == query_number and (
                    row.get("street_name") == query_street or row.get("street_base") == query_street_base
                ):
                    matches.append(dict(row))
        if matches:
            return matches
    if query_street:
        query_street_base = bare_street_name(query_street)
        matches = []
        for rows in index.values():
            for row in rows:
                if row.get("street_name") == query_street or row.get("street_base") == query_street_base:
                    matches.append(dict(row))
        if matches:
            return matches
    for rows in index.values():
        for row in rows:
            if row.get("street_name") and row["street_name"] in normalized_query:
                matches = [dict(c) for cv in index.values() for c in cv if c.get("street_name") == row["street_name"]]
                if matches:
                    return matches
            if row.get("street_base") and row["street_base"] in normalized_query:
                matches = [dict(c) for cv in index.values() for c in cv if c.get("street_base") == row["street_base"]]
                if matches:
                    return matches
    return []


UPLINK_PORT_PREFIXES = ("sfp-sfpplus", "sfp", "ether1", "bond", "bridge")
SUBSCRIBER_PORT_PREFIXES = ("ether2", "ether3", "ether4", "ether5", "ether6", "ether7", "ether8")


def classify_port_role(port_name: str) -> str:
    """Returns 'uplink', 'subscriber', or 'unknown'."""
    if not port_name:
        return "unknown"
    lower = str(port_name).lower().strip()
    for prefix in UPLINK_PORT_PREFIXES:
        if lower.startswith(prefix):
            return "uplink"
    for prefix in SUBSCRIBER_PORT_PREFIXES:
        if lower.startswith(prefix):
            return "subscriber"
    return "unknown"


SUBSCRIBER_NAME_TO_MAC: dict[str, str] = {
    "savoy1unit3f": "6083e7af5fce",
    "savoy1unit3n": "e4fac4b25e92",
}

SUBSCRIBER_NAME_TO_OLT: dict[str, dict[str, str]] = {
    "savoy1unit2n": {"olt": "000002.OLT01", "olt_ip": "192.168.55.98", "pon": "Gpon1/0/1", "onu": "1"},
    "savoy1unit5h": {"olt": "000002.OLT01", "olt_ip": "192.168.55.98", "pon": "Gpon1/0/1", "onu": "4"},
    "savoy1unit10g": {"olt": "000002.OLT01", "olt_ip": "192.168.55.98", "pon": "Gpon1/0/1", "onu": "6"},
    "savoy1unit9k": {"olt": "000002.OLT01", "olt_ip": "192.168.55.98", "pon": "Gpon1/0/1", "onu": "7"},
    "savoy1unit1s": {"olt": "000002.OLT01", "olt_ip": "192.168.55.98", "pon": "Gpon1/0/1", "onu": "12"},
    "savoy1unit16k": {"olt": "000002.OLT01", "olt_ip": "192.168.55.98", "pon": "Gpon1/0/2", "onu": "1"},
    "savoy1unit3n": {"olt": "000002.OLT01", "olt_ip": "192.168.55.98", "pon": "Gpon1/0/2", "onu": "2"},
    "savoy1unit11r": {"olt": "000002.OLT01", "olt_ip": "192.168.55.98", "pon": "Gpon1/0/2", "onu": "5"},
    "savoy1unit17c": {"olt": "000002.OLT01", "olt_ip": "192.168.55.98", "pon": "Gpon1/0/2", "onu": "6"},
    "savoy7unit8c": {"olt": "000002.OLT01", "olt_ip": "192.168.55.98", "pon": "Gpon1/0/2", "onu": "16"},
    "savoy3unit7d": {"olt": "000002.OLT03", "olt_ip": "192.168.55.99", "pon": "Gpon1/0/1", "onu": "2"},
    "savoy4unit10f": {"olt": "000002.OLT04", "olt_ip": "192.168.55.96", "pon": "Gpon1/0/1", "onu": "2"},
    "savoy4unit11n": {"olt": "000002.OLT04", "olt_ip": "192.168.55.96", "pon": "Gpon1/0/1", "onu": "3"},
    "savoy4unit16c": {"olt": "000002.OLT04", "olt_ip": "192.168.55.96", "pon": "Gpon1/0/1", "onu": "5"},
    "savoy4unit6n": {"olt": "000002.OLT04", "olt_ip": "192.168.55.96", "pon": "Gpon1/0/2", "onu": "8"},
    "savoy5unit6h": {"olt": "000002.OLT05", "olt_ip": "192.168.55.95", "pon": "Gpon1/0/1", "onu": "2"},
    "savoy5unit4s": {"olt": "000002.OLT05", "olt_ip": "192.168.55.95", "pon": "Gpon1/0/1", "onu": "11"},
    "savoy7unit4h": {"olt": "000002.OLT07", "olt_ip": "192.168.55.93", "pon": "Gpon1/0/1", "onu": "2"},
    "savoy7unit15j": {"olt": "000002.OLT07", "olt_ip": "192.168.55.93", "pon": "Gpon1/0/2", "onu": "3"},
    "savoy7unit10s": {"olt": "000002.OLT07", "olt_ip": "192.168.55.93", "pon": "Gpon1/0/2", "onu": "4"},
}


def normalize_subscriber_label(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[._,/]+", " ", text)
    text = re.sub(r"[^a-z0-9\-\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace(" ", "")


def extract_subscriber_label(query: str) -> str | None:
    patterns = (
        r"\b(NYCHA[0-9A-Za-z\-]+)\b",
        r"\b(Savoy\d+Unit[0-9A-Za-z]+)\b",
        r"\b(Euclid-\d+-\d+)\b",
        r"\b([A-Za-z]+(?:\d+[A-Za-z]*)*Unit\d+[A-Za-z0-9]*)\b",
        r"\b([A-Za-z]+(?:\d+[A-Za-z]*)*Apt\d+[A-Za-z0-9]*)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, str(query or ""), re.I)
        if match:
            normalized = normalize_subscriber_label(match.group(1))
            if normalized:
                return normalized
    return None


def project_env_candidates(project_root: Path) -> list[Path]:
    root = project_root.resolve()
    candidates = [
        root / ".env",
        root / ".env.networkscan",
        root / "config" / ".env",
        root / "config" / ".env.networkscan",
    ]
    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def _parse_env_assignment(raw_line: str, path: Path, line_number: int) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if "=" not in line:
        raise ValueError(f"Malformed env line in {path}:{line_number}: missing '='")
    key, value = line.split("=", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"Malformed env line in {path}:{line_number}: empty key")
    return key, value.strip().strip('"').strip("'")


def load_env_file(path: Path) -> bool:
    if not path.exists():
        return False
    loaded_any = False
    file_values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        parsed = _parse_env_assignment(raw, path, line_number)
        if parsed is None:
            continue
        key, value = parsed
        prior_file_value = file_values.get(key)
        if prior_file_value is not None and prior_file_value != value:
            raise ValueError(f"Conflicting duplicate env key in {path}:{line_number}: {key}")
        file_values[key] = value
        current = os.environ.get(key)
        if current is None:
            os.environ[key] = value
            loaded_any = True
            continue
        if current != value:
            os.environ.setdefault("JAKE_ENV_CONFLICTS", "")
            conflict = f"{key} from {path}"
            prior = os.environ["JAKE_ENV_CONFLICTS"]
            os.environ["JAKE_ENV_CONFLICTS"] = f"{prior},{conflict}".strip(",")
    return loaded_any


def apply_env_aliases() -> None:
    aliases = [
        ("SSH_MCP_USERNAME", "username"),
        ("SSH_MCP_PASSWORD", "password"),
        ("NETBOX_URL", "NETBOX_BASE_URL"),
        ("TAUC_PASSWORD", "TPLINK_ID_PASSWORD"),
    ]
    for target, source in aliases:
        if not os.environ.get(target) and os.environ.get(source):
            os.environ[target] = os.environ[source]


def seed_project_envs(project_root: Path) -> list[Path]:
    loaded: list[Path] = []
    for path in project_env_candidates(project_root):
        if load_env_file(path):
            loaded.append(path)
    if loaded:
        os.environ.setdefault("JAKE_ROOT", str(project_root.resolve()))
        os.environ.setdefault("JAKE_HOME", str(project_root.resolve()))
    apply_env_aliases()
    return loaded
