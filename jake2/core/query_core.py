#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from typing import Any

from core.shared import (
    SITE_ALIAS_MAP,
    SITE_SERVICE_PROFILES,
    SUBSCRIBER_NAME_TO_MAC,
    SUBSCRIBER_NAME_TO_OLT,
    classify_port_role,
    extract_street_number_and_name,
    extract_subscriber_label,
    resolve_address_candidates,
    normalize_subscriber_label,
)
from core.tooling import dispatch_troubleshooting_scenarios, preferred_troubleshooting_mcp
from mcp.routeros_dispatch_mcp import dispatch_routeros_question

# WHY: These field-note MACs capture OLT-side exceptions that deterministic lookup cannot infer from live tables alone.
# WHY: In particular, some sightings are on uplink-side transport interfaces and must not be misreported as a single subscriber ONU.
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
        "pon": "Gpon1/0/2",
        "onu_id": "2",
    },
    "d8:44:89:a7:05:c8": {
        "kind": "gpon-ont",
        "summary": "Field notes tied this MAC to 000002.OLT05 Gpon1/0/1 ONT 4.",
        "olt_name": "000002.OLT05",
        "pon": "Gpon1/0/1",
        "onu_id": "4",
    },
    "30:68:93:c1:c5:cd": {
        "kind": "gpon-ont",
        "summary": "Field notes tied this MAC to 000002.OLT01 Gpon1/0/2 ONT 4.",
        "olt_name": "000002.OLT01",
        "pon": "Gpon1/0/2",
        "onu_id": "4",
        "serial": "TPLG-31A11BB2",
    },
}

SERIAL_RE = re.compile(r"\b(?:TPLG-[A-Z0-9]+|Y[0-9A-Z]{8,}|(?=[A-Z0-9]{10,}\b)(?=[A-Z0-9]*\d)[A-Z0-9]+)\b", re.I)
RELAY_NAME_RE = re.compile(r"\b(DHCP-RELAY-[A-Z0-9-]+)\b", re.I)
CIRCUIT_ID_RE = re.compile(r"\b([a-z0-9][a-z0-9_-]*(?:/[a-z0-9._:-]+){2,})\b", re.I)
LOG_WINDOW_RE = re.compile(r"\b(?:last|past)\s+(\d+)\s*(minute|minutes|min|hour|hours|hr|hrs)\b", re.I)
DEVICE_HOST_RE = re.compile(r"\b(\d{6}(?:\.\d{3})?\.(?:R\d+|SR\d+|SW\d+|RFSW\d+|OLT\d+))\b", re.I)
LOCAL_OPERATOR_TZ = ZoneInfo("America/New_York")


@dataclass(slots=True, frozen=True)
class BuildingTruth:
    switches_seen: int
    probable_cpes: int
    outliers: int
    active_alerts: int


@dataclass(slots=True, frozen=True)
class ScanContext:
    subnet: str | None
    api_reachable: int | None
    hosts_tested: int | None
    timestamp: str | None
    freshness: str | None
    age_detail: str | None


def _contains_term(text: str, term: str) -> bool:
    lowered = str(text or "").lower()
    needle = str(term or "").strip().lower()
    if not needle:
        return False
    pattern = re.escape(needle)
    pattern = pattern.replace(r"\ ", r"\s+")
    pattern = pattern.replace(r"\-", r"[-\s]+")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", lowered, re.I) is not None


def _contains_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _parse_seen_timestamp(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _describe_seen_recency(value: str | None) -> tuple[str | None, str | None]:
    seen = _parse_seen_timestamp(value)
    if seen is None:
        return None, None
    delta = datetime.now(UTC) - seen
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 3600:
        amount = max(1, round(seconds / 60))
        return "healthy signal", f"about {amount} minutes ago"
    if seconds < 86400:
        amount = max(1, round(seconds / 3600))
        unit = "hour" if amount == 1 else "hours"
        return "stale but present", f"about {amount} {unit} ago"
    amount = max(1, round(seconds / 86400))
    unit = "day" if amount == 1 else "days"
    return "possibly offline", f"about {amount} {unit} ago"


def _append_primary_sighting(lines: list[str], sighting: dict[str, Any] | None, prefix: str = "Last seen location") -> None:
    row = sighting or {}
    device = str(row.get("device_name") or row.get("identity") or "").strip()
    port = str(row.get("port_name") or row.get("on_interface") or "").strip()
    vlan = row.get("vlan_id") if row.get("vlan_id") is not None else row.get("vid")
    location = " ".join(part for part in (device, port) if part).strip()
    if location:
        if vlan not in (None, ""):
            lines.append(f"{prefix}: {location} VLAN {vlan}.")
        else:
            lines.append(f"{prefix}: {location}.")
    if row.get("hostname"):
        lines.append(f"Hostname: {row.get('hostname')}.")
    if row.get("client_ip"):
        lines.append(f"Observed client IP: {row.get('client_ip')}.")
    freshness, age = _describe_seen_recency(row.get("last_seen"))
    if row.get("last_seen"):
        lines.append(f"Last seen timestamp: {row.get('last_seen')}.")
    if freshness and age:
        lines.append(f"Freshness: {freshness} ({age}).")


def infer_site_alias(lowered_query: str) -> str | None:
    for alias, site_id in SITE_ALIAS_MAP.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered_query, re.I):
            return site_id
    # WHY: Operators prefix addresses with a street number ("audit 2020 Pacific St").
    # Strip a leading number so the word-only alias ("pacific st") can match.
    stripped = re.sub(r"^\d+\s+", "", lowered_query).strip()
    if stripped != lowered_query:
        for alias, site_id in SITE_ALIAS_MAP.items():
            if re.search(rf"\b{re.escape(alias)}\b", stripped, re.I):
                return site_id
    return None


def infer_site_from_subscriber_label(label: str | None) -> str | None:
    lowered = str(label or "").lower().strip()
    if not lowered:
        return None
    direct = infer_site_alias(lowered)
    if direct:
        return direct
    for alias, site_id in SITE_ALIAS_MAP.items():
        if lowered.startswith(alias):
            return site_id
    if lowered.startswith("nycha"):
        return "000007"
    return None


def _colonize_compact_mac(value: str | None) -> str | None:
    clean = "".join(ch for ch in str(value or "").lower() if ch in "0123456789abcdef")
    if len(clean) != 12:
        return None
    return ":".join(clean[i : i + 2] for i in range(0, 12, 2))


def _subscriber_name_for_mac(mac: str | None) -> str | None:
    colonized = _colonize_compact_mac(mac)
    if not colonized:
        return None
    compact = colonized.replace(":", "")
    for subscriber_name, subscriber_mac in SUBSCRIBER_NAME_TO_MAC.items():
        if subscriber_mac == compact:
            return subscriber_name
    evidence = LOCAL_OLT_EVIDENCE_BY_MAC.get(colonized) or {}
    raw_name = str(evidence.get("subscriber") or "").strip()
    if raw_name:
        return raw_name
    return None


def norm_scope(text: str) -> str:
    return text.strip().rstrip('?.!,')


def normalize_query(query: str) -> str:
    q = query.strip()
    q = re.sub(r'^\s*(hey|hi|hello)\s+jake[\s,:\-]*', '', q, flags=re.I)
    q = re.sub(r'^\s*jake[\s,:\-]*', '', q, flags=re.I)
    q = re.sub(r'^\s*(let\'?s|lets)\s+', '', q, flags=re.I)
    q = re.sub(r"\b(what can you tell me about|what do you know about|give me the rundown on|give me a summary of|summary of)\b", ' ', q, flags=re.I)
    q = re.sub(r"\b(what's going on with|whats going on with|what is going on with|look at|check on|check|take a look at|how is|how's|what about)\b", ' ', q, flags=re.I)
    q = re.sub(r"\b(can you|could you|would you|please|i need you to|i need to know|tell me|show me|give me|let me know)\b", ' ', q, flags=re.I)
    q = re.sub(r'\s+', ' ', q).strip()
    return q


def _extract_log_window_minutes(text: str) -> int:
    match = LOG_WINDOW_RE.search(text)
    if not match:
        lowered = text.lower()
        if re.search(r"\b(?:last|past)\s+hour\b", lowered):
            return 60
        if re.search(r"\b(?:last|past)\s+minute\b", lowered):
            return 1
        return 15
    amount = max(int(match.group(1)), 1)
    unit = match.group(2).lower()
    if unit.startswith("hour") or unit.startswith("hr"):
        return min(amount * 60, 24 * 60)
    return min(amount, 24 * 60)


def _extract_log_filter(text: str) -> str:
    lowered = text.lower()
    if "pppoe" in lowered:
        return "pppoe"
    if "dhcp" in lowered:
        return "dhcp"
    if "interface" in lowered or "flap" in lowered or "link" in lowered:
        return "interface"
    if "bridge" in lowered or "mac moved" in lowered or "mac move" in lowered:
        return "bridge"
    if "error" in lowered or "errors" in lowered:
        return "error"
    return "all"


def _extract_device_hostname(text: str) -> str | None:
    match = DEVICE_HOST_RE.search(text)
    if match:
        return match.group(1)
    return None


def _parse_log_timestamp(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.isdigit():
            return datetime.fromtimestamp(int(raw) / 1_000_000_000, tz=UTC)
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return None


def _format_log_time(value: str | None) -> str:
    parsed = _parse_log_timestamp(value)
    if parsed is None:
        return str(value or "").strip()
    return parsed.strftime("%H:%M:%S")


def _format_operator_timestamp(value: str | None) -> str | None:
    parsed = _parse_log_timestamp(value)
    if parsed is None:
        return None
    local = parsed.astimezone(LOCAL_OPERATOR_TZ)
    return local.strftime("%b %-d, %Y at %-I:%M:%S %p %Z")


def _describe_scan_freshness(value: str | None) -> tuple[str | None, str | None]:
    parsed = _parse_log_timestamp(value)
    if parsed is None:
        return None, None
    delta = datetime.now(UTC) - parsed
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 86400:
        hours = max(1, round(seconds / 3600))
        unit = "hour" if hours == 1 else "hours"
        return "current", f"about {hours} {unit} old"
    if seconds < 7 * 86400:
        days = max(1, round(seconds / 86400))
        unit = "day" if days == 1 else "days"
        return "aging", f"about {days} {unit} old"
    days = max(1, round(seconds / 86400))
    unit = "day" if days == 1 else "days"
    return "stale", f"about {days} {unit} old"


def _building_truth(result: dict[str, Any]) -> BuildingTruth:
    return BuildingTruth(
        switches_seen=int(result.get("device_count") or 0),
        probable_cpes=int(result.get("probable_cpe_count") or 0),
        outliers=int(result.get("outlier_count") or 0),
        active_alerts=len(result.get("active_alerts") or []),
    )


def _building_scan_context(result: dict[str, Any]) -> ScanContext:
    scan = result.get("scan") or {}
    reachable = scan.get("api_reachable")
    tested = scan.get("hosts_tested")
    freshness, age_detail = _describe_scan_freshness(scan.get("started_at"))
    return ScanContext(
        subnet=str(scan.get("subnet") or "").strip() or None,
        api_reachable=int(reachable) if isinstance(reachable, (int, float)) else None,
        hosts_tested=int(tested) if isinstance(tested, (int, float)) else None,
        timestamp=_format_operator_timestamp(scan.get("started_at")),
        freshness=freshness,
        age_detail=age_detail,
    )


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return singular
    return plural or f"{singular}s"


def _canonical_scope_token(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    return text


def _extract_street_name_phrase(raw: str) -> str | None:
    match = re.search(
        r"\b([A-Za-z][A-Za-z\s]{2,40}?\s+(?:St|Ave|Rd|Pl|Blvd|Dr|Ln|Way|Ct|Pkwy|Terrace|Place|Street|Avenue|Road|Boulevard|Drive|Lane|Court|Parkway))\b",
        raw,
        re.I,
    )
    if not match:
        return None
    phrase = match.group(1).strip()
    if re.search(r"\d", phrase):
        return None
    return phrase


def _extract_numbered_street_phrase(raw: str) -> str | None:
    match = re.search(r"\b(\d{1,5}\s+[A-Za-z][A-Za-z\s]{2,40})\b", raw, re.I)
    if not match:
        return None
    phrase = re.sub(r"\s+", " ", match.group(1).strip())
    if re.fullmatch(r"\d+", phrase):
        return None
    return phrase


def _clean_log_message(message: str | None) -> str:
    text = str(message or "").strip()
    text = re.sub(r"^:(?:info|critical|warning|error|account):\s*", "", text, flags=re.I)
    text = re.sub(r"^DHCP:\s*", "DHCP ", text, flags=re.I)
    return text.strip()


def _describe_signal_mix(counts: dict[str, Any]) -> str:
    phrases: list[str] = []
    mapping = {
        "pppoe": "PPPoE",
        "dhcp": "DHCP",
        "interface": "interface",
        "bridge": "bridge",
        "error": "error",
    }
    for key in ("pppoe", "dhcp", "interface", "bridge", "error"):
        value = int(counts.get(key) or 0)
        if value > 0:
            label = mapping[key]
            phrases.append(f"{value} {label} event{'s' if value != 1 else ''}")
    if not phrases:
        return ""
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + f", and {phrases[-1]}"


def parse_operator_query(query: str) -> dict:
    q = normalize_query(query)
    lower = q.lower()
    asks_about_pon = " pon" in f" {lower}" or "which pon" in lower or "what pon" in lower

    mac_match = re.search(r'((?:[0-9a-f]{2}[:\-]){5}[0-9a-f]{2}|[0-9a-f]{12})', lower, re.I)
    mac_norm = ""
    if mac_match:
        raw_mac = mac_match.group(1).lower().replace("-", ":")
        mac_norm = raw_mac if ":" in raw_mac else ":".join(raw_mac[i:i + 2] for i in range(0, len(raw_mac), 2))
    serial_match = SERIAL_RE.search(q)
    ip_match = re.search(r'\b(\d{1,3}(?:\.\d{1,3}){3})\b', q)
    relay_match = RELAY_NAME_RE.search(q)
    circuit_match = CIRCUIT_ID_RE.search(q)
    subnet_match = re.search(r'(\d+\.\d+\.\d+\.\d+/\d+)', q)
    switch_match = re.search(r'\b(\d{6}\.\d{3}\.(?:SW\d+|RFSW\d+))\b', q)
    building_match = re.search(r'\b(\d{6}\.\d{3})\b', q)
    site_match = re.search(r'\b(\d{6})\b(?!\.\d{3})', q)
    site_alias = infer_site_alias(lower)
    identifier_site_id = site_match.group(1) if site_match else site_alias
    addr_match = re.search(
        r'\b(\d{1,5}(?:-\d{1,5})?\s+[A-Za-z][A-Za-z\s]{2,40}?\s*(?:St|Ave|Rd|Pl|Blvd|Dr|Ln|Way|Ct|Pkwy|Terr?|Place|Street|Avenue|Road|Boulevard|Drive|Lane|Court|Parkway)\b)',
        q, re.I,
    )
    address_text = addr_match.group(1).strip() if addr_match else None
    address_candidates = resolve_address_candidates(q)
    exact_address = address_candidates[0]["address"] if len(address_candidates) == 1 else None
    address_site_id = address_candidates[0]["site_id"] if len(address_candidates) == 1 else None
    effective_site_id = identifier_site_id or address_site_id
    wireless_dispatch_tokens = ("capsman", "wifi-qcom", "wifi-qcom-ac", "community wifi", "campus wifi", "roaming domain", "mikrotik ap", "cap ax", "cap ac")
    switching_dispatch_tokens = ("bridge", "vlan filtering", "bridge vlan", "stp", "rstp", "hw offload", "pvid", "mvrp", "ra guard", "igmp snooping")
    routing_dispatch_tokens = ("bgp", "ospf", "vrf", "route leak", "default-prepend", "as-path", "multipath", "ecmp", "safe mode", "safe-mode", "check-gateway", "failover", "redistribute")
    access_dispatch_tokens = ("pppoe", "chap", "ms-chap", "ipoe", "option 82", "tr-101", "dhcpv6", "framed-route", "masquerade", "conntrack", "pmtu", "mss")
    swos_dispatch_tokens = ("swos", "switchos", "css", "host table", "wrong port", "dirty segment", "duplicate mac", "mixed mac")
    platform_dispatch_tokens = ("upgrade", "7.22.1", "7.22", "7.21", "routerboard", "firmware", "device mode", "nand", "poe firmware", "power interruption", "ccr2004", "rb5009", "l009", "channel strategy", "release strategy", "headend")
    upgrade_review_tokens = ("configuration file", "config file", "review the config", "review this config", "review the export", "review the configuration", "export diff")
    asks_for_summary = _contains_any(lower, ("summary", "status", "health", "alerts", "customers online", "how many customers", "site summary"))
    log_window_minutes = _extract_log_window_minutes(q)
    log_filter = _extract_log_filter(q)
    device_hostname = _extract_device_hostname(q)
    rerun_scan_tokens = (
        "rerun the scan",
        "re-run the scan",
        "run the scan again",
        "scan again",
        "rerun scan",
        "rescan",
    )

    if any(token in lower for token in rerun_scan_tokens):
        if building_match:
            return {"action": "rerun_latest_scan", "params": {"building_id": building_match.group(1)}}
        if exact_address:
            return {"action": "rerun_latest_scan", "params": {"address_text": exact_address, "site_id": address_site_id}}
        if effective_site_id:
            return {"action": "rerun_latest_scan", "params": {"site_id": effective_site_id}}
        return {"action": "rerun_latest_scan", "params": {}}

    # WHY: Only treat multiple address candidates as an ambiguous address query
    # when no site alias was already resolved. If site_alias is set (e.g. "park79" -> 000003),
    # the address matches are false positives from partial street-name fragments
    # ("park" matching NYCHA "Park Place" addresses). The alias takes precedence.
    if len(address_candidates) > 1 and not building_match and not switch_match and not site_alias:
        rendered = " or ".join(row.get("address") or "" for row in address_candidates[:2] if row.get("address"))
        return {'action': 'clarify_target', 'params': {'reason': f"Do you mean {rendered}?"}}

    if exact_address and site_alias is None and not building_match and not switch_match and not mac_match and not ip_match and not lower.startswith('audit '):
        return {'action': 'get_building_health', 'params': {'address_text': exact_address, 'site_id': address_site_id, 'include_alerts': True}}

    if device_hostname and _contains_any(lower, ("check logs for", "logs for", "what happened on", "errors on", "any errors on")):
        return {
            "action": "get_device_logs",
            "params": {
                "device_name": device_hostname,
                "window_minutes": log_window_minutes,
                "log_filter": log_filter,
                "limit": 500,
            },
        }
    if _contains_any(lower, ("why did customers drop", "why did subs drop", "why did subscribers drop", "customers dropped")):
        if effective_site_id:
            return {
                "action": "correlate_event_window",
                "params": {"site_id": effective_site_id, "window_minutes": log_window_minutes, "limit": 500},
            }
    if effective_site_id and _contains_any(lower, ("what happened at", "what happened on", "site logs", "any errors on", "errors on", "show me logs for", "pppoe errors", "dhcp errors", "interface errors", "bridge errors")):
        return {
            "action": "get_site_logs",
            "params": {
                "site_id": effective_site_id,
                "window_minutes": log_window_minutes,
                "log_filter": log_filter,
                "limit": 500,
            },
        }

    if effective_site_id and _contains_any(lower, ("what site is", "which site is", "what is site", "what site does")):
        return {"action": "get_site_summary", "params": {"site_id": effective_site_id, "include_alerts": True}}
    if effective_site_id and _contains_any(lower, ("what are the alarms", "what are the alarms at", "what alarms are active", "what alerts are active", "show active alerts", "what are the active alerts")):
        return {"action": "get_site_alerts", "params": {"site_id": effective_site_id}}
    if effective_site_id and _contains_any(lower, ("how many alternate mac cpes", "alternate mac cpes", "alternate macs", "alt mac cpes", "alternate mac clusters")):
        vendor = "vilo" if _contains_any(lower, ("vilo",)) else "tplink"
        return {"action": "get_vendor_alt_mac_clusters", "params": {"vendor": vendor, "site_id": effective_site_id, "limit": 50}}
    if effective_site_id and _contains_any(lower, ("how many customers", "how many subscribers", "how many users")):
        return {"action": "get_online_customers", "params": {"scope": effective_site_id, "site_id": effective_site_id}}
    if effective_site_id and _contains_any(lower, ("what outliers", "which outliers", "show outliers", "outliers do you see")):
        return {"action": "get_site_summary", "params": {"site_id": effective_site_id, "include_alerts": True}}
    if effective_site_id and _contains_any(lower, ("what are the devices", "what are the 4 devices", "list the devices", "devices at", "devices from netbox", "list the devices from netbox")):
        return {"action": "get_site_summary", "params": {"site_id": effective_site_id, "include_alerts": True}}
    if effective_site_id and _contains_any(lower, ("loss on the network", "packet loss", "seeing loss", "any loss", "leakage on", "any leakage", "seeing leakage")):
        return {"action": "get_site_summary", "params": {"site_id": effective_site_id, "include_alerts": True}}
    if effective_site_id and _contains_any(lower, ("same pons", "same pon", "same pons are", "high or low light", "mux and the unit", "between the mux and the unit")):
        return {"action": "get_site_alerts", "params": {"site_id": effective_site_id}}
    if effective_site_id and _contains_any(lower, ("precheck", "quick check", "before i go", "before touching", "before answering", "site classification", "classify this site")):
        return {"action": "get_site_precheck", "params": {"site_id": effective_site_id}}
    if effective_site_id and _contains_any(lower, ("loop suspicion", "bridge loop", "loop-ish", "broadcast storm")):
        return {"action": "get_site_loop_suspicion", "params": {"site_id": effective_site_id}}
    if "loop" in lower or "storm" in lower:
        if effective_site_id:
            return {"action": "get_site_loop_suspicion", "params": {"site_id": effective_site_id}}
        # WHY: "nycha" is already resolved to effective_site_id via SITE_ALIAS_MAP
        # before this point. If no site was resolved, return a clarification prompt
        # rather than defaulting to NYCHA — this query could be for any site.
        return {"action": "get_site_loop_suspicion", "params": {"site_id": None, "clarify": True}}
    if _contains_any(lower, ("bridge host weirdness", "bridge hosts weird", "bridge host weird", "bridge host odd", "bridge host off", "mikrotik bridge host", "bridge host")) and _contains_any(lower, ("weird", "off", "odd", "wrong", "looks off")):
        if effective_site_id:
            return {"action": "get_site_bridge_host_weirdness", "params": {"site_id": effective_site_id}}
        if "nycha" in lower or "mikrotik" in lower or "mikrotiks" in lower:
            # WHY: "mikrotik" alone does not identify a site — all sites use MikroTik.
            # Return clarification rather than defaulting to NYCHA.
            return {"action": "get_site_bridge_host_weirdness", "params": {"site_id": None, "clarify": True}}
    if _contains_any(lower, ("mac learning", "learned mac", "learned macs", "too broad", "too many paths", "upstream and not at the edge", "upstream but not at the edge", "only showing upstream", "not at the edge")):
        if effective_site_id:
            return {"action": "get_site_bridge_host_weirdness", "params": {"site_id": effective_site_id}}
        # WHY: ambiguous — ask for a site rather than defaulting to NYCHA.
        return {"action": "get_site_bridge_host_weirdness", "params": {"site_id": None, "clarify": True}}
    if _contains_any(lower, ("cnwave neighbors", "radio neighbors", "live neighbors", "ipv4 neighbors", "what devices are behind", "what is behind this radio", "what is behind that radio", "neighbors on this radio", "neighbors on that radio")):
        params: dict[str, Any] = {"query": q}
        if effective_site_id:
            params["site_id"] = effective_site_id
        return {"action": "get_live_cnwave_radio_neighbors", "params": params}
    if _contains_any(lower, ("radio handoff", "handoff trace", "handoff path", "sfp side", "sfp port", "sfp hosts", "macs on the sfp", "mac addresses via the sfp", "what macs are visible", "what macs do you see on the sfp")):
        return {"action": "get_radio_handoff_trace", "params": {"query": q}}
    if building_match and _contains_any(lower, ("floor issue", "one unit or floor", "shared path", "entire floor", "whole floor", "shared mux", "mux is bad", "building fault domain", "what shared path", "is this a floor issue", "fault domain", "building path issue")):
        return {"action": "get_building_fault_domain", "params": {"building_id": building_match.group(1)}}
    if effective_site_id and _contains_any(lower, ("topology", "site layout", "laid out", "how is the network laid out", "transport topology", "backhaul path", "backhaul links", "transport links", "radio links")):
        return {"action": "get_site_topology", "params": {"site_id": effective_site_id}}

    if _contains_any(lower, upgrade_review_tokens) and _contains_any(lower, ("upgrade", "7.22.1", "7.22", "firmware", "this upgrade")):
        params: dict[str, Any] = {"target_version": "7.22.1"}
        if effective_site_id:
            params["site_id"] = effective_site_id
        if switch_match:
            params["device_name"] = switch_match.group(1)
        return {"action": "review_live_upgrade_risk", "params": params}
    if _contains_any(lower, ("preflight plan", "upgrade preflight", "preflight steps")) and _contains_any(lower, ("upgrade", "7.22.1", "7.22", "firmware")):
        params = {"target_version": "7.22.1"}
        if effective_site_id:
            params["site_id"] = effective_site_id
        return {"action": "generate_upgrade_preflight_plan", "params": params}

    if _contains_any(lower, wireless_dispatch_tokens):
        if not asks_for_summary or _contains_any(lower, ("design", "build", "plan", "topology", "package", "fix", "pilot")):
            return {"action": "dispatch_troubleshooting_scenarios", "params": {"query": q}}
    if _contains_any(lower, routing_dispatch_tokens):
        return {"action": "dispatch_troubleshooting_scenarios", "params": {"query": q}}
    if _contains_any(lower, platform_dispatch_tokens) and (
        effective_site_id
        or _contains_any(lower, ("headend", "router", "switch", "ap", "cpe"))
        or re.search(r"\b(ccr2004|rb5009|l009|crs3\d{2}|hap ax2|routerboard)\b", lower)
    ):
        return {"action": "dispatch_troubleshooting_scenarios", "params": {"query": q}}
    if _contains_any(lower, switching_dispatch_tokens):
        if not _contains_any(lower, ("site summary", "show active alerts")):
            return {"action": "dispatch_troubleshooting_scenarios", "params": {"query": q}}
    if _contains_any(lower, access_dispatch_tokens):
        if not _contains_any(lower, ("how many", "count", "online customers")):
            return {"action": "dispatch_troubleshooting_scenarios", "params": {"query": q}}
    if _contains_any(lower, swos_dispatch_tokens):
        return {"action": "dispatch_troubleshooting_scenarios", "params": {"query": q}}
    outage_match = re.search(r'\b(?:reported\s+outage|outage|issue|problem)\s+at\s+(.+?)\s+(?:unit|apt|apartment)\s+([0-9a-z\-]+)\b', q, re.I)
    if not outage_match:
        outage_match = re.search(r'\bat\s+(.+?)\s+(?:unit|apt|apartment)\s+([0-9a-z\-]+)\b', q, re.I)
    if not outage_match and any(word in lower for word in ('outage', 'issue', 'problem', 'down')):
        outage_match = re.search(r'^\s*(\d+.*?\b[a-z]+(?:\s+[a-z]+)*)\s+([0-9]+[a-z])\s+(?:outage|issue|problem|down)\b', q, re.I)

    if outage_match:
        return {
            'action': 'get_outage_context',
            'params': {
                'address_text': norm_scope(outage_match.group(1)),
                'unit': norm_scope(outage_match.group(2)),
            },
        }
    if ip_match and any(token in lower for token in ('tell me about', 'know about', 'what can you', 'what is', 'about', 'how is', "how's")):
        return {'action': 'get_netbox_device_by_ip', 'params': {'ip': ip_match.group(1)}}
    if 'server info' in lower or 'server status' in lower:
        return {'action': 'get_server_info', 'params': {}}
    if 'vilo api' in lower and ('status' in lower or 'server info' in lower or 'configured' in lower):
        return {'action': 'get_vilo_server_info', 'params': {}}
    if 'vilo' in lower and any(token in lower for token in ('audit', 'reconcile', 'reconciliation')):
        params: dict[str, Any] = {'limit': 500}
        if building_match:
            params['building_id'] = building_match.group(1)
        elif effective_site_id:
            params['site_id'] = effective_site_id
        if 'export' in lower or 'csv' in lower or 'markdown' in lower or 'report' in lower:
            return {'action': 'export_vilo_inventory_audit', 'params': params}
        return {'action': 'get_vilo_inventory_audit', 'params': params}
    if 'vilo inventory' in lower:
        return {'action': 'get_vilo_inventory', 'params': {'page_index': 1, 'page_size': 20}}
    if ('which site has vilo' in lower or 'which sites have vilo' in lower or 'where are the vilos' in lower or 'which site has vilos' in lower or 'which sites have vilos' in lower):
        return {'action': 'get_vendor_site_presence', 'params': {'vendor': 'vilo', 'limit': 20}}
    if ('which site has tp-link' in lower or 'which sites have tp-link' in lower or 'which site has tplink' in lower or 'which sites have tplink' in lower or 'where are the tplink cpes' in lower or 'where are the tp-link cpes' in lower):
        return {'action': 'get_vendor_site_presence', 'params': {'vendor': 'tplink', 'limit': 20}}
    if any(token in lower for token in ('cpe management readiness', 'management readiness', 'local management readiness', 'hc220 readiness', 'vilo readiness', 'cpe tooling readiness', 'cpe management audit', 'what can jake manage right now')):
        params: dict[str, Any] = {}
        if 'vilo' in lower:
            params['vendor'] = 'vilo'
        elif any(token in lower for token in ('hc220', 'tp-link', 'tplink')):
            params['vendor'] = 'tplink_hc220'
        return {'action': 'get_cpe_management_readiness', 'params': params}
    cpe_label_match = re.search(r'\b([A-Z][A-Za-z0-9_]{6,})\b', q)
    if any(token in lower for token in ('local management', 'management surface', 'manage locally', 'local gui', 'what management do we have', 'what local control do we have')) and (cpe_label_match or mac_match or serial_match):
        params: dict[str, Any] = {}
        cpe_label = cpe_label_match.group(1) if cpe_label_match else None
        if cpe_label:
            params['network_name'] = cpe_label
        if mac_match:
            params['mac'] = mac_match.group(1)
        serial_value = serial_match.group(0) if serial_match else None
        if serial_value and cpe_label and serial_value.lower() == cpe_label.lower():
            serial_value = None
        if serial_value:
            params['serial'] = serial_value
        inferred_surface_site = effective_site_id or infer_site_from_subscriber_label(cpe_label)
        if inferred_surface_site:
            params['site_id'] = inferred_surface_site
        return {'action': 'get_cpe_management_surface', 'params': params}
    if any(token in lower for token in ('alternate mac', 'alt mac', 'mac duplicates', 'duplicate macs', 'related macs')):
        vendor = 'vilo' if 'vilo' in lower else 'tplink' if ('tplink' in lower or 'tp-link' in lower) else None
        if vendor:
            params: dict[str, Any] = {'vendor': vendor, 'limit': 50}
            if building_match:
                params['building_id'] = building_match.group(1)
            elif effective_site_id:
                params['site_id'] = effective_site_id
            return {'action': 'get_vendor_alt_mac_clusters', 'params': params}
    if any(token in lower for token in ('remember this', 'note this', 'save this note', 'learn this', 'remember that')) and len(q.split()) > 3:
        params: dict[str, Any] = {'note': q}
        if effective_site_id:
            params['site_id'] = effective_site_id
        tags = []
        if 'vilo' in lower:
            tags.append('vilo')
        if 'tplink' in lower or 'tp-link' in lower:
            tags.append('tplink')
        if 'mac' in lower:
            tags.append('mac')
        if tags:
            params['tags'] = tags
        return {'action': 'capture_operator_note', 'params': params}
    network_name_match = re.search(r'\b(vilo_[0-9a-f]{3,})\b', lower, re.I)
    if ('vilo' in lower or mac_norm.startswith("e8:da:00:")) and (mac_match or network_name_match):
        if mac_match:
            return {'action': 'get_vilo_target_summary', 'params': {'mac': mac_match.group(1)}}
        if network_name_match:
            return {'action': 'get_vilo_target_summary', 'params': {'network_name': network_name_match.group(1)}}
    if 'vilo subscribers' in lower:
        return {'action': 'get_vilo_subscribers', 'params': {'page_index': 1, 'page_size': 20}}
    if 'vilo networks' in lower:
        return {'action': 'get_vilo_networks', 'params': {'page_index': 1, 'page_size': 20}}
    if 'vilo devices' in lower or 'vilos for network' in lower:
        network_match = re.search(r'network(?:_id)?\s+([a-z0-9\-]{6,})', lower, re.I)
        if network_match:
            return {'action': 'get_vilo_devices', 'params': {'network_id': network_match.group(1)}}
    if ('which siklu' in lower and any(token in lower for token in ('issue', 'issues', 'unstable', 'bad'))) or ('which cambium' in lower and any(token in lower for token in ('issue', 'issues', 'down', 'bad'))):
        vendor = 'siklu' if 'siklu' in lower else 'cambium'
        return {'action': 'get_transport_radio_issues', 'params': {'vendor': vendor, 'site_id': effective_site_id, 'limit': 10}}
    if effective_site_id and any(token in lower for token in ('likely failure domain', 'failure domains', 'unrelated noise', 'check first', 'what is probably unrelated', 'work out the most likely')):
        return {'action': 'assess_site_incident', 'params': {'site_id': effective_site_id}}
    if effective_site_id and any(token in lower for token in ('pull the logs', 'historical', 'historically', 'what happened', 'can no longer get to', 'archived evidence', 'history for this site')):
        return {'action': 'get_site_historical_evidence', 'params': {'site_id': effective_site_id}}
    if effective_site_id and any(token in lower for token in ('syslog', 'logs from the hardware', 'hardware logs', 'pull syslog', 'site logs')):
        return {'action': 'get_site_syslog_summary', 'params': {'site_id': effective_site_id}}
    if any(token in lower for token in ('option 82 drift', 'remote-id drift', 'relay findings', 'dhcp findings', 'option 82 findings')):
        return {'action': 'get_dhcp_findings_summary', 'params': {}}
    if relay_match and any(token in lower for token in ('relay', 'option 82', 'dhcp', 'drift', 'what do we know', 'tell me about', 'what is going on with', 'about')):
        return {'action': 'get_dhcp_relay_summary', 'params': {'relay_name': relay_match.group(1)}}
    if circuit_match and any(token in lower for token in ('circuit', 'option 82', 'dhcp', 'what do we know', 'tell me about', 'break down', 'subscriber')):
        return {'action': 'get_dhcp_circuit_summary', 'params': {'circuit_id': circuit_match.group(1)}}
    if any(token in lower for token in ('dhcp lease', 'option 82', 'remote-id', 'circuit-id', 'relay info', 'relay path', 'subscriber from lease', 'dhcp snapshot', 'relay snapshot')):
        params: dict[str, Any] = {}
        if mac_match:
            params['mac'] = mac_match.group(1)
        if ip_match:
            params['ip'] = ip_match.group(1)
        if circuit_match:
            params['circuit_id'] = circuit_match.group(1)
        remote_match = re.search(r'\bremote-id\s+([a-z0-9._:-]+)\b', lower, re.I)
        if remote_match:
            params['remote_id'] = remote_match.group(1)
        if relay_match:
            params['relay_name'] = relay_match.group(1)
        sub_id_match = re.search(r'\b(sub-\d+)\b', lower, re.I)
        if sub_id_match:
            params['subscriber_id'] = sub_id_match.group(1)
        if params:
            return {'action': 'get_dhcp_subscriber_summary', 'params': params}
    if any(token in lower for token in ('live dhcp', 'dhcp leases right now', 'live leases', 'current leases')):
        params: dict[str, Any] = {'limit': 25}
        if effective_site_id:
            params['site_id'] = effective_site_id
        if mac_match:
            params['mac'] = mac_match.group(1)
        if ip_match:
            params['ip'] = ip_match.group(1)
        return {'action': 'get_live_dhcp_lease_summary', 'params': params}
    if any(token in lower for token in ('splynx online', 'online in splynx', 'live splynx', 'splynx customers online')):
        params: dict[str, Any] = {'limit': 25}
        if effective_site_id:
            params['site_id'] = effective_site_id
        return {'action': 'get_live_splynx_online_summary', 'params': params}
    if any(token in lower for token in ('live capsman', 'capsman summary', 'wifi controller summary', 'capsman manager')):
        params: dict[str, Any] = {}
        if effective_site_id:
            params['site_id'] = effective_site_id
        return {'action': 'get_live_capsman_summary', 'params': params}
    if any(token in lower for token in ('wifi registrations', 'registration table', 'wireless clients right now', 'live wifi clients', 'capsman registrations')):
        params: dict[str, Any] = {'limit': 25}
        if effective_site_id:
            params['site_id'] = effective_site_id
        return {'action': 'get_live_wifi_registration_summary', 'params': params}
    if any(token in lower for token in ('wifi provisioning', 'capsman provisioning', 'wifi config rows', 'capsman config rows')):
        params: dict[str, Any] = {}
        if effective_site_id:
            params['site_id'] = effective_site_id
        return {'action': 'get_live_wifi_provisioning_summary', 'params': params}
    if any(token in lower for token in ('live source readiness', 'source readiness', 'what live sources are ready', 'which live sources are ready', 'live source status')):
        return {'action': 'get_live_source_readiness', 'params': {}}
    if any(token in lower for token in ('olt log', 'olt logs', 'show logging flash', 'olt event log', 'olt flash log')):
        params: dict[str, Any] = {}
        if effective_site_id:
            params['site_id'] = effective_site_id
        if mac_match:
            params['mac'] = mac_match.group(1)
        if serial_match:
            params['serial'] = serial_match.group(0)
        olt_match = re.search(r'\b(\d{6}\.OLT\d+)\b', q, re.I)
        if olt_match:
            params['olt_name'] = olt_match.group(1)
        olt_ip_match = re.search(r'\b(?:192\.168\.55\.\d{1,3})\b', q)
        if olt_ip_match:
            params['olt_ip'] = olt_ip_match.group(0)
        level_match = re.search(r'\blevel\s+([0-7])\b', lower)
        if level_match:
            params['level'] = int(level_match.group(1))
        mod_match = re.search(r'\bmod(?:ule)?\s+([a-z0-9._-]+)\b', lower, re.I)
        if mod_match:
            params['module'] = mod_match.group(1)
        word_match = re.search(r'\bword\s+([a-z0-9._:-]+)\b', q, re.I)
        if word_match:
            params['word'] = word_match.group(1)
        elif mac_match:
            params['word'] = mac_match.group(1).replace(':', '').lower()
        elif serial_match:
            params['word'] = serial_match.group(0)
        return {'action': 'get_live_olt_log_summary', 'params': params}
    if any(token in lower for token in ('tp-link join', 'tplink join', 'subscriber join', 'which subscriber is behind this onu', 'which subscriber is behind this tplg', 'show tp-link subscriber join')):
        params: dict[str, Any] = {}
        if serial_match:
            params['serial'] = serial_match.group(0)
        if mac_match:
            params['mac'] = mac_match.group(1)
        network_name_match = re.search(r'\b([A-Za-z]+(?:\d+[A-Za-z]*)*Unit\d+[A-Za-z0-9]*)\b', q, re.I)
        if network_name_match:
            params['network_name'] = network_name_match.group(1)
        if network_id_match:
            params['network_id'] = network_id_match.group(0)
        if effective_site_id:
            params['site_id'] = effective_site_id
        return {'action': 'get_tp_link_subscriber_join', 'params': params}
    if any(token in lower for token in ('live olt', 'olt cli', 'olt telnet', 'show ont info')):
        params: dict[str, Any] = {}
        if mac_match:
            params['mac'] = mac_match.group(1)
        if serial_match:
            params['serial'] = serial_match.group(0)
        olt_match = re.search(r'\b(\d{6}\.OLT\d+)\b', q, re.I)
        if olt_match:
            params['olt_name'] = olt_match.group(1)
        olt_ip_match = re.search(r'\b(?:192\.168\.55\.\d{1,3})\b', q)
        if olt_ip_match:
            params['olt_ip'] = olt_ip_match.group(0)
        gpon_match = re.search(r'\b(?:gpon|Gpon)\s*([0-9]+/[0-9]+/[0-9]+)\b', q)
        if gpon_match:
            params['pon'] = gpon_match.group(1)
        onu_match = re.search(r'\b(?:onu|ont)\s+(\d+)\b', q, re.I)
        if onu_match:
            params['onu_id'] = onu_match.group(1)
        if any(key in params for key in ('mac', 'serial', 'olt_name', 'olt_ip', 'pon', 'onu_id')):
            return {'action': 'get_live_olt_ont_summary', 'params': params}
    radio_name_pattern = bool(re.search(r'\bv(?:1000|2000|3000|5000)\b', lower)) or bool(re.search(r'\beh-\d', lower)) or (' - ' in q and bool(re.search(r'\d', q)))
    if any(token in lower for token in ('rf metrics', 'rssi', 'snr', 'alignment', 'signal quality', 'cnwave metrics')):
        params: dict[str, Any] = {'limit': 20}
        if effective_site_id:
            params['site_id'] = effective_site_id
        if radio_name_pattern:
            params['name'] = q
        return {'action': 'get_live_cnwave_rf_summary', 'params': params}
    if any(token in lower for token in ('run live routeros', 'live routeros', 'live mikrotik', 'check live ppp', 'check live arp', 'check live bridge hosts', 'live interfaces', 'live resource')):
        device_match = re.search(r'\b(\d{6}(?:\.\d{3})?\.(?:R\d+|SW\d+|RFSW\d+|AG\d+))\b', q, re.I)
        if device_match:
            intent = 'interfaces_read'
            if 'ppp' in lower:
                intent = 'ppp_active_read'
            elif 'arp' in lower:
                intent = 'arp_read'
            elif 'bridge host' in lower:
                intent = 'bridge_hosts_read'
            elif 'bridge vlan' in lower:
                intent = 'bridge_vlans_read'
            elif 'bridge port' in lower:
                intent = 'bridge_ports_read'
            elif 'resource' in lower or 'uptime' in lower:
                intent = 'resource_read'
            elif 'neighbor' in lower:
                intent = 'neighbors_read'
            return {'action': 'run_live_routeros_read', 'params': {'device_name': device_match.group(1), 'intent': intent, 'reason': q}}
    if effective_site_id and 'optical alerts' in lower and any(token in lower for token in ('aux port', 'aux ports', 'v2000', 'cambium')):
        return {'action': 'assess_site_incident', 'params': {'site_id': effective_site_id}}
    if effective_site_id and any(token in lower for token in ('radio topology', 'which building is the dn', 'which buildings appear to be cns', 'fed from building', 'radio pair in the same building', 'local handoff problem or a site-wide outage')):
        return {'action': 'get_site_radio_inventory', 'params': {'site_id': effective_site_id}}
    if effective_site_id and any(token in lower for token in ('aux port', 'aux ports', 'share a building', 'share building')) and any(token in lower for token in ('v2000', 'cambium', 'cnwave', 'radio')):
        return {'action': 'get_site_radio_inventory', 'params': {'site_id': effective_site_id}}
    if any(token in lower for token in ('siklu unstable', 'siklu links look unstable', 'siklu links are unstable')):
        return {'action': 'get_transport_radio_issues', 'params': {'vendor': 'siklu', 'site_id': effective_site_id, 'limit': 10}}
    if any(token in lower for token in ('cambium radios have issues', 'cambium radios are down', 'cambium issues')):
        return {'action': 'get_transport_radio_issues', 'params': {'vendor': 'cambium', 'site_id': effective_site_id, 'limit': 10}}
    if radio_name_pattern or any(token in lower for token in ('cambium', 'cnwave', 'siklu')):
        if ip_match:
            return {'action': 'get_transport_radio_summary', 'params': {'ip': ip_match.group(1)}}
        if mac_match:
            return {'action': 'get_transport_radio_summary', 'params': {'mac': mac_match.group(1)}}
        return {'action': 'get_transport_radio_summary', 'params': {'query': q}}

    nycha_port_audit_tokens = (
        'audit nycha ports', 'nycha port audit', 'which nycha switches',
        'nycha switches have wrong', 'nycha switches using ether48',
        'ether48 instead of ether49', 'wrong patching at nycha',
        'wrong patch', 'wrong uplink at nycha', 'nycha uplink',
        'nycha port issues', 'nycha switch uplink',
    )
    if any(token in lower for token in nycha_port_audit_tokens):
        return {'action': 'get_nycha_port_audit', 'params': {'site_id': effective_site_id or '000007'}}

    nycha_audit_workbook_tokens = (
        'audit workbook', 'generate audit workbook',
        'audit all switches at nycha', 'audit all nycha switches',
        'nycha switch audit workbook', 'nycha unit audit',
    )
    sw_match = re.search(r'\b(\d{6}\.\d{3}\.SW\d+)\b', q, re.I)
    # WHY: addr_match guard requires no site alias resolved — "audit 2020 Pacific St" resolves to
    # effective_site_id=000007 (NYCHA alias) and must stay as get_site_summary, not audit workbook.
    if any(token in lower for token in nycha_audit_workbook_tokens) or (
        sw_match and any(token in lower for token in ('audit', 'generate'))
    ) or ((addr_match or exact_address) and not identifier_site_id and lower.startswith('audit ')):
        switch_identity = sw_match.group(1) if sw_match else None
        street_address = (addr_match.group(1).strip() if addr_match else exact_address) if not switch_identity else None
        params: dict[str, Any] = {}
        if switch_identity:
            params['switch_identity'] = switch_identity
        elif street_address:
            params['address_text'] = street_address
        elif effective_site_id:
            params['site_id'] = effective_site_id
        return {'action': 'generate_nycha_audit_workbook', 'params': params}

    wants_audit = any(token in lower for token in ('audit', 'review', 'assess'))
    wants_handoff = any(token in lower for token in ('handoff', 'hand off', 'field team', 'fixes', 'action items', 'what needs to be fixed'))
    if (wants_audit or wants_handoff) and ('nycha' in lower or site_match or building_match):
        if building_match:
            return {'action': 'get_building_health', 'params': {'building_id': building_match.group(1), 'include_alerts': True}}
        if effective_site_id:
            return {'action': 'get_site_punch_list', 'params': {'site_id': effective_site_id}}
        if 'nycha' in lower:
            return {'action': 'get_site_punch_list', 'params': {'site_id': '000007'}}

    if mac_match and any(token in lower for token in ('trace', 'where does', 'where is', 'where did', 'where does this mac', 'land on', 'lands on', 'terminate on')):
        return {'action': 'trace_mac', 'params': {'mac': mac_match.group(1), 'include_bigmac': True}}
    subscriber_candidate = extract_subscriber_label(q)
    if subscriber_candidate:
        normalized_subscriber = normalize_subscriber_label(subscriber_candidate)
        inferred_site_id = effective_site_id or infer_site_from_subscriber_label(normalized_subscriber)
        subscriber_mac = SUBSCRIBER_NAME_TO_MAC.get(normalized_subscriber)
        if subscriber_mac:
            return {
                'action': 'get_cpe_state',
                'params': {'mac': _colonize_compact_mac(subscriber_mac), 'include_bigmac': True},
            }
        subscriber_olt = SUBSCRIBER_NAME_TO_OLT.get(normalized_subscriber)
        if subscriber_olt:
            return {
                'action': 'get_live_olt_ont_summary',
                'params': {
                    'mac': None,
                    'serial': None,
                    'olt_name': subscriber_olt.get('olt'),
                    'olt_ip': subscriber_olt.get('olt_ip'),
                    'pon': subscriber_olt.get('pon'),
                    'onu_id': subscriber_olt.get('onu'),
                },
            }
        if inferred_site_id and any(token in lower for token in ('how is', 'doing', 'status', 'what is wrong with', 'check on', 'tell me about')):
            return {'action': 'get_site_summary', 'params': {'site_id': inferred_site_id, 'include_alerts': True}}
    if ip_match and (lower.rstrip('?.!, ') == ip_match.group(1) or any(token in lower for token in ('tell me about', 'know about', 'what can you', 'what is', 'what is going on with', 'about'))):
        return {'action': 'get_netbox_device_by_ip', 'params': {'ip': ip_match.group(1)}}
    generic_network_name_match = re.search(r'\b([A-Za-z]+(?:\d+[A-Za-z]*)*Unit\d+[A-Za-z0-9]*)\b', q, re.I)
    if generic_network_name_match and any(token in lower for token in ('tell me about', 'know about', 'what can you', 'what is going on with', 'going on with', 'check on', 'about')):
        params = {'network_name': generic_network_name_match.group(1)}
        if effective_site_id:
            params['site_id'] = effective_site_id
        return {'action': 'subscriber_lookup', 'params': params}
    if any(token in lower for token in ('access trace', 'customer trace', 'subscriber trace', 'full access trace', 'trace this subscriber', 'show the full access trace')) and generic_network_name_match:
        inferred_site_id = effective_site_id or infer_site_from_subscriber_label(generic_network_name_match.group(1))
        return {
            'action': 'get_customer_access_trace',
            'params': {
                'network_name': generic_network_name_match.group(1),
                'mac': mac_match.group(1) if mac_match else None,
                'serial': serial_match.group(0) if serial_match else None,
                'site_id': inferred_site_id,
            },
        }
    if asks_about_pon and serial_match and not generic_network_name_match:
        return {'action': 'get_local_ont_path', 'params': {'serial': serial_match.group(0)}}
    if asks_about_pon and mac_match:
        return {'action': 'get_cpe_state', 'params': {'mac': mac_match.group(1), 'include_bigmac': True}}
    if serial_match and not generic_network_name_match and any(token in lower for token in ('tell me about', 'know about', 'what can you', 'what is', 'what is going on with', 'about', 'serial')):
        return {'action': 'get_local_ont_path', 'params': {'serial': serial_match.group(0)}}
    if mac_match and any(token in lower for token in ('tell me about', 'know about', 'what can you', 'what is this', 'what is going on with', 'going on with')):
        return {'action': 'get_cpe_state', 'params': {'mac': mac_match.group(1), 'include_bigmac': True}}
    if ('cpe state' in lower or 'device state' in lower or 'what is this device doing' in lower or 'what is this mac doing' in lower) and mac_match:
        return {'action': 'get_cpe_state', 'params': {'mac': mac_match.group(1), 'include_bigmac': True}}
    if effective_site_id and any(
        token in lower
        for token in (
            'discrepanc',
            'match what we see',
            'match the routers',
            'customer evidence',
            'compare evidence',
            'what evidence do we have',
            'besides subscriber export',
            'dhcp or ppp',
        )
    ):
        return {'action': 'compare_customer_evidence', 'params': {'site_id': effective_site_id}}
    if ('site alerts' in lower or ('alerts' in lower and effective_site_id)) and effective_site_id:
        return {'action': 'get_site_alerts', 'params': {'site_id': effective_site_id}}
    if (
        'list all sites' in lower
        or 'list all of the sites' in lower
        or 'list sites' in lower
        or 'site list' in lower
        or 'list of sites' in lower
        or 'sites in netbox' in lower
        or ('netbox' in lower and 'sites' in lower)
    ):
        return {'action': 'list_sites_inventory', 'params': {'limit': 300}}
    if any(token in lower for token in ('real addresses', '172 ip', '172 ips', 'which sites have which real addresses', 'site addresses')):
        return {'action': 'list_sites_inventory', 'params': {'limit': 300}}
    generic_network_name_match = re.search(r'\b([A-Za-z]+(?:\d+[A-Za-z]*)*Unit\d+[A-Za-z0-9]*)\b', q, re.I)
    if generic_network_name_match and any(token in lower for token in ('tell me about', 'know about', 'what can you', 'what is going on with', 'going on with', 'check on', 'about')):
        params = {'network_name': generic_network_name_match.group(1)}
        if effective_site_id:
            params['site_id'] = effective_site_id
        return {'action': 'subscriber_lookup', 'params': params}
    if not effective_site_id and not building_match and not switch_match and not mac_match and not ip_match:
        plain_name = re.sub(r'[^a-z0-9\s\-]', ' ', lower)
        plain_name = re.sub(r'\s+', ' ', plain_name).strip()
        if plain_name and len(plain_name) >= 3 and len(plain_name.split()) <= 4 and plain_name not in {'status', 'today', 'health', 'alerts', 'customers'}:
            return {'action': 'search_sites_inventory', 'params': {'query': norm_scope(q), 'limit': 25}}
    if ('from netbox' in lower or 'netbox' in lower) and switch_match:
        return {'action': 'get_netbox_device', 'params': {'name': switch_match.group(1)}}
    if (
        building_match
        and (
            lower.strip() == building_match.group(1).lower()
            or 'building health' in lower
            or ('how does' in lower and building_match)
            or ('how is' in lower and building_match)
            or ('status' in lower and building_match and not switch_match)
            or ('tell me about' in lower)
            or ('know about' in lower)
        )
    ):
        return {'action': 'get_building_health', 'params': {'building_id': building_match.group(1), 'include_alerts': True}}
    if ('switch summary' in lower or ('how is' in lower and switch_match) or ('status' in lower and switch_match)) and switch_match:
        return {'action': 'get_switch_summary', 'params': {'switch_identity': switch_match.group(1)}}
    if (
        'site summary' in lower
        or ('how is' in lower and effective_site_id and not building_match)
        or ('status' in lower and effective_site_id and not building_match)
        or ('summary' in lower and effective_site_id and not building_match)
        or ('tell me about' in lower and effective_site_id and not building_match)
        or ('know about' in lower and effective_site_id and not building_match)
    ) and effective_site_id:
        return {'action': 'get_site_summary', 'params': {'site_id': effective_site_id, 'include_alerts': True}}
    if 'nycha' in lower and any(token in lower for token in ('look today', 'look like today', 'today', 'status', 'health', 'how does', 'how is', 'looking', 'right now')):
        return {'action': 'get_subnet_health', 'params': {'subnet': '192.168.44.0/24', 'include_alerts': True, 'include_bigmac': False}}
    if 'odd behavior' in lower or 'health' in lower or ('look today' in lower and subnet_match) or ('looking today' in lower and ('nycha' in lower or subnet_match)):
        if subnet_match:
            return {'action': 'get_subnet_health', 'params': {'subnet': subnet_match.group(1), 'include_alerts': True, 'include_bigmac': False}}
        if switch_match:
            return {'action': 'get_switch_summary', 'params': {'switch_identity': switch_match.group(1)}}
        if building_match:
            return {'action': 'get_building_customer_count', 'params': {'building_id': building_match.group(1)}}
        if effective_site_id:
            return {'action': 'get_site_summary', 'params': {'site_id': effective_site_id, 'include_alerts': True}}
    if (('how many' in lower or 'count' in lower) and ('customer' in lower or 'subs' in lower or 'subscribers' in lower or 'users' in lower) and ('online' in lower or 'up' in lower or 'active' in lower)) or ('how many are up' in lower and (effective_site_id or building_match or switch_match)):
        if switch_match:
            return {'action': 'get_switch_summary', 'params': {'switch_identity': switch_match.group(1)}}
        if building_match:
            return {'action': 'get_building_customer_count', 'params': {'building_id': building_match.group(1)}}
        if effective_site_id:
            return {'action': 'get_online_customers', 'params': {'scope': effective_site_id}}
    if ('rogue dhcp' in lower or ('dhcp server' in lower and ('rogue' in lower or 'wrong' in lower))) and any(token in lower for token in ('scan', 'sniff', 'capture', 'packet')):
        params: dict[str, Any] = {}
        if effective_site_id:
            params['site_id'] = effective_site_id
        if switch_match:
            params['device_name'] = switch_match.group(1)
        duration_match = re.search(r'\b(\d+)\s*s(?:ec(?:ond)?s?)?\b', lower)
        if duration_match:
            params['seconds'] = int(duration_match.group(1))
        iface_match = re.search(r'\b(?:on|interface)\s+([a-z0-9._/-]+)\b', lower, re.I)
        if iface_match:
            params['interface'] = iface_match.group(1)
        if mac_match:
            params['mac'] = mac_match.group(1)
        return {'action': 'get_live_rogue_dhcp_scan', 'params': params}
    if 'rogue dhcp' in lower or ('wrong dhcp' in lower) or ('bad dhcp' in lower) or ('dhcp server' in lower and ('rogue' in lower or 'wrong' in lower)):
        if building_match:
            return {'action': 'get_rogue_dhcp_suspects', 'params': {'building_id': building_match.group(1)}}
        if effective_site_id:
            return {'action': 'get_site_rogue_dhcp_summary', 'params': {'site_id': effective_site_id}}
    if ('punch list' in lower or 'action items' in lower or 'what needs to be fixed' in lower) and effective_site_id:
        return {'action': 'get_site_punch_list', 'params': {'site_id': effective_site_id}}
    if 'recovery ready' in lower or 'recovery-ready' in lower or 'ready for reboot' in lower or 'recovery hold' in lower or 'recovery-hold' in lower:
        if building_match:
            return {'action': 'get_recovery_ready_cpes', 'params': {'building_id': building_match.group(1)}}
        if effective_site_id:
            return {'action': 'get_recovery_ready_cpes', 'params': {'site_id': effective_site_id}}
    if 'flap' in lower or 'flapping' in lower or 'bouncing' in lower or 'unstable ports' in lower:
        if building_match:
            return {'action': 'get_building_flap_history', 'params': {'building_id': building_match.group(1)}}
        if effective_site_id:
            return {'action': 'get_site_flap_history', 'params': {'site_id': effective_site_id}}
    if (('find probable' in lower) or ('find all probable' in lower) or ('find cpe' in lower) or ('probable' in lower and ('tplink' in lower or 'vilo' in lower or 'cpe' in lower))) and ('tplink' in lower or 'vilo' in lower or 'cpe' in lower):
        oui = None
        if 'tplink' in lower:
            oui = '30:68:93'
        elif 'vilo' in lower:
            oui = 'E8:DA:00'
        limit = 100
        if ' all ' in f' {lower} ' or 'full' in lower or 'entire' in lower:
            limit = 1000
        elif building_match:
            limit = 300
        params = {'site_id': effective_site_id, 'building_id': building_match.group(1) if building_match else None, 'oui': oui, 'access_only': True, 'limit': limit}
        return {'action': 'find_cpe_candidates', 'params': params}
    generic_health_words = ('doing', 'look', 'looking', 'going on', 'status', 'today', 'right now')
    if building_match and not switch_match and any(word in lower for word in generic_health_words):
        return {'action': 'get_building_health', 'params': {'building_id': building_match.group(1), 'include_alerts': True}}
    if switch_match and any(word in lower for word in generic_health_words):
        return {'action': 'get_switch_summary', 'params': {'switch_identity': switch_match.group(1)}}
    if effective_site_id and not building_match and any(word in lower for word in generic_health_words):
        return {'action': 'get_site_summary', 'params': {'site_id': effective_site_id, 'include_alerts': True}}
    compact = re.sub(r'[^a-z0-9\.\s]', ' ', lower)
    compact = re.sub(r'\s+', ' ', compact).strip()
    if switch_match and compact == switch_match.group(1).lower():
        return {'action': 'get_switch_summary', 'params': {'switch_identity': switch_match.group(1)}}
    if building_match and compact == building_match.group(1).lower():
        return {'action': 'get_building_health', 'params': {'building_id': building_match.group(1), 'include_alerts': True}}
    if site_match and compact == site_match.group(1).lower():
        return {'action': 'get_site_summary', 'params': {'site_id': site_match.group(1), 'include_alerts': True}}
    if site_alias and compact == site_alias.lower():
        return {'action': 'get_site_summary', 'params': {'site_id': site_alias, 'include_alerts': True}}
    if mac_match and mac_norm.startswith("e8:da:00:") and compact in {
        mac_match.group(1).lower(),
        mac_match.group(1).lower().replace(':', ''),
        mac_match.group(1).lower().replace('-', ''),
    }:
        return {'action': 'get_vilo_target_summary', 'params': {'mac': mac_match.group(1)}}
    if mac_match and compact in {
        mac_match.group(1).lower(),
        mac_match.group(1).lower().replace(':', ''),
        mac_match.group(1).lower().replace('-', ''),
    }:
        return {'action': 'get_cpe_state', 'params': {'mac': mac_match.group(1), 'include_bigmac': True}}
    if mac_match and mac_norm.startswith("e8:da:00:") and not switch_match and not building_match:
        return {'action': 'get_vilo_target_summary', 'params': {'mac': mac_match.group(1)}}
    if mac_match and not switch_match and not building_match:
        return {'action': 'get_cpe_state', 'params': {'mac': mac_match.group(1), 'include_bigmac': True}}
    if effective_site_id and not building_match and not switch_match:
        return {'action': 'get_site_summary', 'params': {'site_id': effective_site_id, 'include_alerts': True}}
    raise ValueError('Could not map query to a deterministic Jake action')


def format_operator_response(action: str, result: dict, query: str | None = None) -> str:
    query_lower = (query or "").lower()
    if action in {"get_site_logs", "get_device_logs", "correlate_event_window"}:
        subject = result.get("device_name") if action == "get_device_logs" else result.get("site_id")
        label = "device" if action == "get_device_logs" else "site"
        if action == "correlate_event_window":
            label = "site"
        lines = []
        if not result.get("loki_available"):
            lines.append(f"Loki is unavailable for {label} {subject}: {result.get('error') or 'unknown error'}.")
            return "\n".join(lines)
        if result.get("error") and int(result.get("log_count") or 0) == 0:
            lines.append(f"Jake could not pull matching logs for {label} {subject}: {result.get('error')}.")
            return "\n".join(lines)
        window = int(result.get("window_minutes") or 15)
        log_count = int(result.get("log_count") or 0)
        device_count = len(result.get("devices") or [])
        if log_count == 0:
            lines.append(f"No log events in the last {window} minutes for this {label}.")
            lines.append("Follow-up: try a longer window, like the last hour, if you expected more activity.")
            return "\n".join(lines)
        lines.append(f"{subject} had {log_count} log events in the last {window} minutes across {device_count} device{'s' if device_count != 1 else ''}.")
        counts = result.get("category_counts") or {}
        signal_mix = _describe_signal_mix(counts)
        if signal_mix:
            lines.append(f"Signal mix: mostly {signal_mix}.")
        classifications = result.get("classifications") or []
        medium_or_higher = [row for row in classifications if str(row.get("confidence") or "").lower() != "low"]
        if medium_or_higher:
            summary = str(medium_or_higher[0].get("summary") or "")
            if medium_or_higher[0].get("kind") in {"stuck_port_down", "dhcp_abnormal_rate"} and str(medium_or_higher[0].get("confidence") or "").lower() == "high":
                summary = f"⚠ {summary}"
            lines.append(summary)
        elif log_count > 0:
            lines.append("No failure pattern stands out — routine activity.")
        timeline = result.get("timeline") or []
        if timeline:
            lines.append("")
            lines.append("Most recent events:")
            for row in timeline[:5]:
                device = row.get("device") or "unknown-device"
                lines.append(f"- {_format_log_time(row.get('timestamp'))} {device}: {_clean_log_message(row.get('summary'))}")
        lines.append("")
        if action == "get_device_logs":
            lines.append("Follow-up: do you want the last hour filtered to DHCP, PPPoE, or interface events only?")
        elif action == "correlate_event_window":
            lines.append(f"Follow-up: do you want me to narrow this to one device at {subject} or expand the time window?")
        else:
            lines.append(f"Follow-up: do you want the last hour, or should I narrow this to one device at {subject}?")
        return "\n".join(lines)

    if action == 'dispatch_troubleshooting_scenarios':
        dispatched = dispatch_routeros_question(query or "", None, limit=3)
        rendered = str(dispatched.get("rendered_answer") or "").strip()
        if rendered:
            return rendered
        preferred_mcp = result.get('preferred_mcp')
        scenarios = result.get('scenarios') or []
        if not preferred_mcp or not scenarios:
            return "I do not have a sharp troubleshooting scenario match for that yet."
        return str((scenarios[0].get('summary') or "")).strip() or "I do not have a sharp troubleshooting scenario match for that yet."

    if action == 'get_outage_context':
        summary = result.get('plain_english_summary', 'No outage summary available.')
        summary = summary.split('Likely causes:')[0].strip()
        lines = [summary]
        inferred = result.get('inferred_unit_port_candidates') or []
        if inferred:
            top = inferred[0]
            lines.append(f"Most likely port: {top.get('identity')} {top.get('on_interface')} ({top.get('confidence')} confidence).")
        nearby = result.get('neighboring_unit_port_hints') or []
        if nearby:
            hints = ", ".join(f"{r.get('unit_token')} -> {(r.get('best_bridge_hit') or {}).get('identity')} {(r.get('best_bridge_hit') or {}).get('on_interface')}" for r in nearby[:3])
            lines.append(f"Nearby same-address online units: {hints}.")
        causes = result.get('likely_causes') or []
        if causes:
            lines.append("Likely causes:")
            lines.extend(f"- {c.get('reason')}" for c in causes[:4])
        checks = result.get('suggested_checks') or []
        if checks:
            lines.append("Suggested checks:")
            lines.extend(f"- {c.get('check')}" for c in checks[:5])
        alerts = result.get('active_alerts') or []
        if alerts:
            alert = alerts[0]
            labels = alert.get('labels', {})
            annotations = alert.get('annotations', {})
            lines.append(f"Active site alert present but separate from this unit: {labels.get('alertname')} - {annotations.get('summary') or labels.get('name')}.")
        return "\n".join(lines)

    if action == 'get_site_precheck':
        lines = [f"Site precheck for {result.get('site_id')}: {result.get('site_name') or result.get('site_id')}."]
        profile = result.get('service_profile') or {}
        if profile.get('summary'):
            lines.append(str(profile.get('summary')))
        tags = result.get('classification_tags') or []
        if tags:
            lines.append(f"Classification: {', '.join(tags)}.")
        online = (result.get('online_customers') or {}).get('count', 0)
        method = (result.get('online_customers') or {}).get('counting_method')
        topo = result.get('topology_summary') or {}
        lines.append(
            f"Quick read: online_customers={online} via {method or 'unknown'}, active_alerts={result.get('active_alert_count', 0)}, "
            f"topology(radios={topo.get('radios', 0)}, links={topo.get('links', 0)}, buildings={topo.get('buildings', 0)})."
        )
        role_counts = result.get('role_counts') or {}
        if role_counts:
            lines.append("NetBox role inventory:")
            lines.append("- " + ", ".join(f"{role}={count}" for role, count in sorted(role_counts.items())))
        lines.append("Next useful questions:")
        lines.append(f"- what can you tell me about {result.get('site_id')}?")
        lines.append(f"- give me the current issue ledger for {result.get('site_id')}")
        return "\n".join(lines)

    if action == 'get_site_loop_suspicion':
        site_id = result.get('site_id')
        suspicion = str(result.get('suspicion') or 'unknown')
        confidence = str(result.get('confidence') or 'low')
        flap_count = int(result.get('flap_count') or 0)
        outlier_count = int(result.get('outlier_count') or 0)
        switch_down = result.get('switch_down_alerts') or []
        top_buildings = result.get('top_flap_buildings') or []
        high_churn = result.get('high_churn_ports') or []
        lines = [f"Loop suspicion read for {site_id}: {suspicion} ({confidence} confidence)."]
        if suspicion == 'no_strong_loop_signal':
            lines.append("Operator read: I do not see strong proof of a broad L2 loop or bridge storm right now.")
        elif suspicion == 'possible_local_loop_or_l2_storm':
            lines.append("Operator read: there are enough switching-side symptoms to keep a local loop or L2 storm on the table, but not enough to call it proven.")
        else:
            lines.append("Operator read: there is enough concurrent L2 churn here to treat broad L2 instability as plausible, not just isolated edge noise.")
        lines.append(f"Current evidence: {flap_count} flap-marked ports, {outlier_count} scan outliers, {len(switch_down)} switch-down alerts.")
        if switch_down:
            lines.append("Switch-down alarms in scope:")
            lines.extend(f"- {item}" for item in switch_down[:3])
        if top_buildings:
            lines.append("Worst flap concentrations:")
            lines.extend(f"- {row.get('building_id')}: {row.get('count')} flap-marked ports" for row in top_buildings[:3])
        if high_churn:
            lines.append("Noisiest ports:")
            for row in high_churn[:5]:
                lines.append(
                    f"- {render_access_target(row)} | link_downs={row.get('link_downs') or '?'} | last_up={row.get('last_link_up_time') or 'unknown'}"
                )
        lines.append("What this does not prove:")
        lines.append("- Jake does not yet have direct STP topology-change counters or broadcast-rate telemetry here, so he should not bluff a confirmed loop.")
        lines.append("Next useful questions:")
        lines.append("- are any of the nycha switches flapping or acting weird?")
        lines.append(f"- what needs to be fixed at {site_id}?")
        return "\n".join(lines)

    if action == 'get_site_bridge_host_weirdness':
        site_id = result.get('site_id')
        suspicion = str(result.get('suspicion') or 'unknown')
        customer_total = int(result.get('customer_bridge_host_count') or 0)
        uplink_total = int(result.get('uplink_customer_count') or 0)
        access_total = int(result.get('access_customer_count') or 0)
        crowded = result.get('crowded_access_ports') or []
        sprayed = result.get('sprayed_customer_macs') or []
        uplink_sample = result.get('sample_uplink_customer_hosts') or []
        lines = [f"Bridge-host weirdness read for {site_id}: {suspicion}."]
        uplink_only_style = any(token in query_lower for token in (
            'upstream and not at the edge',
            'upstream but not at the edge',
            'only showing upstream',
            'not at the edge',
        ))
        if uplink_only_style:
            if uplink_sample:
                lines.append("Operator read: yes, there are customer MACs that Jake is only seeing on uplink-like interfaces right now.")
            else:
                lines.append("Operator read: I do not have clear uplink-only customer-MAC examples in the current bridge-host view.")
        elif suspicion == 'no_strong_bridge_host_anomaly':
            lines.append("Operator read: nothing obviously weird jumps out from the current MikroTik bridge-host view.")
        elif suspicion == 'customer_macs_uplink_only':
            lines.append("Operator read: customer MACs are skewing uplink-only right now, which is suspicious because Jake is not anchoring them cleanly to access edges.")
        else:
            lines.append("Operator read: yes, there is bridge-host evidence that looks off enough to investigate.")
        lines.append(f"Current evidence: {customer_total} customer-class bridge-host sightings, {access_total} on access ports, {uplink_total} on uplink-like ports.")
        if crowded:
            lines.append("Crowded access ports:")
            for row in crowded[:5]:
                lines.append(f"- {row.get('identity')} {row.get('interface')} has {row.get('customer_mac_count')} customer MACs")
        if sprayed:
            lines.append("Customer MACs seen on too many paths:")
            for row in sprayed[:5]:
                sample_paths = ", ".join(row.get('sample_paths') or [])
                lines.append(f"- {row.get('mac')} across {row.get('path_count')} paths: {sample_paths}")
        if uplink_sample:
            lines.append("Sample uplink-only customer MAC sightings:")
            for row in uplink_sample[:5]:
                lines.append(f"- {row.get('identity')} {row.get('on_interface')} mac={row.get('mac')}")
        lines.append("Next useful questions:")
        lines.append(f"- do we have any obvious layer2 mess at {site_id} right now?")
        lines.append(f"- what needs to be fixed at {site_id}?")
        return "\n".join(lines)

    if action == 'get_live_cnwave_radio_neighbors':
        radio = result.get('radio') or {}
        controller = result.get('controller') or {}
        if result.get('error') == 'radio_not_found':
            return "Jake could not match that query to a known cnWave radio in the current transport inventory."
        if not result.get('available'):
            lines = [f"Jake could not run a controller-side `Show IPv4 Neighbors` read for {radio.get('name') or 'that radio'}."]
            requested = str(result.get('query') or '').strip()
            if requested:
                lines.append(f"Requested radio query: {requested}.")
            detail = result.get('detail') or (result.get('controller_result') or {}).get('detail')
            if detail:
                lines.append(f"Reason: {detail}")
            missing = controller.get('missing') or []
            if missing:
                lines.append(f"Missing controller wiring: {', '.join(missing)}.")
            partial = result.get('partial_evidence') or {}
            peers = partial.get('transport_scan_peers') or []
            if peers:
                lines.append(f"Current transport-scan peer radios: {', '.join(peers[:6])}.")
            neighbor_macs = partial.get('neighbor_macs') or []
            if neighbor_macs:
                lines.append(f"Current radio-side neighbor MAC hints: {', '.join(neighbor_macs[:8])}.")
            return "\n".join(lines)
        controller_result = result.get('controller_result') or {}
        parsed = controller_result.get('parsed')
        lines = [f"Controller-side IPv4 neighbors for {radio.get('name')} ({radio.get('ip') or '?'})"]
        if isinstance(parsed, dict):
            neighbors = parsed.get('neighbors') or parsed.get('rows') or parsed.get('data') or []
            if isinstance(neighbors, list) and neighbors:
                for row in neighbors[:20]:
                    if isinstance(row, dict):
                        compact = ", ".join(f"{k}={v}" for k, v in row.items() if v not in (None, "", []))
                        lines.append(f"- {compact}")
                    else:
                        lines.append(f"- {row}")
            else:
                lines.append(json.dumps(parsed)[:1200])
        elif isinstance(parsed, list):
            for row in parsed[:20]:
                if isinstance(row, dict):
                    compact = ", ".join(f"{k}={v}" for k, v in row.items() if v not in (None, "", []))
                    lines.append(f"- {compact}")
                else:
                    lines.append(f"- {row}")
        else:
            lines.append(str(controller_result.get('raw') or parsed or '')[:1200])
        return "\n".join(lines)

    if action == 'get_radio_handoff_trace':
        if not result.get('found'):
            return "Jake could not match that handoff trace request to a known radio."
        radio = result.get('radio') or {}
        switch_candidates = result.get('switch_candidates') or []
        lines = [f"Radio handoff trace for {radio.get('name')}."]
        if result.get('site_id'):
            lines.append(f"- site: {result.get('site_id')}")
        if result.get('building_id'):
            lines.append(f"- building handoff target: {result.get('building_id')}")
        else:
            lines.append("- building handoff target: unresolved from current topology/inventory")
        if switch_candidates:
            lines.append(f"- building-side device candidates: {', '.join(str(row.get('identity')) for row in switch_candidates[:6])}.")
        else:
            lines.append("- building-side device candidates: none mapped in current inventory.")
        lines.append(f"- current SFP/uplink host count on mapped building devices: {result.get('sfp_host_count', 0)}")
        sfp_ports = result.get('sfp_ports') or []
        if sfp_ports:
            lines.append(f"- SFP/uplink ports with learned MACs: {', '.join(sfp_ports[:8])}.")
        vendor_counts = result.get('sfp_vendor_counts') or {}
        if vendor_counts:
            compact_counts = ", ".join(f"{k}={v}" for k, v in sorted(vendor_counts.items()) if v)
            lines.append(f"- SFP-side MAC vendor mix: {compact_counts}.")
        sample = result.get('sfp_host_sample') or []
        if sample:
            lines.append("Sample SFP/uplink MAC sightings:")
            for row in sample[:10]:
                lines.append(f"- {row.get('identity')} {row.get('on_interface')} mac={row.get('mac')} vlan={row.get('vid')}")
        if not sample and not switch_candidates:
            lines.append("- Jake cannot yet show SFP-side MACs here because the building switch/handoff device is not mapped.")
        elif not sample:
            lines.append("- Jake has mapped building devices here, but there are no current SFP/uplink MAC learns in the latest bridge-host snapshot.")
        return "\n".join(lines)

    if action == 'get_building_fault_domain':
        domain = result.get('fault_domain') or {}
        domain_name = str(domain.get('likely_domain') or 'unknown').replace('_', ' ')
        confidence = domain.get('confidence') or 'low'
        lines = [f"Customer fault domain for {result.get('building_id')}:"] 
        lines.append(f"- likely fault domain: {domain_name}")
        lines.append(f"- confidence: {confidence}")
        if domain.get('owner'):
            lines.append(f"- operational owner: {domain.get('owner')}")
        if result.get('address'):
            lines.append(f"- address: {result.get('address')}")
        lines.append("")
        lines.append("Operator view:")
        if domain.get('reason'):
            lines.append(f"Likely {domain_name}. {domain.get('reason')}")
        else:
            lines.append(f"Likely {domain_name}.")
        lines.append("")
        lines.append("Evidence:")
        if domain.get('reason'):
            lines.append(f"- reasoning: {domain.get('reason')}")
        top_floor = (result.get('floor_clusters') or [None])[0]
        if top_floor and top_floor.get('offline_count'):
            lines.append(
                f"- strongest floor cluster: floor {top_floor.get('floor')} offline={top_floor.get('offline_count')} online={top_floor.get('online_count')} "
                f"units={', '.join((top_floor.get('offline_units') or [])[:8]) or 'none'}."
            )
        top_optical = result.get('top_optical_cluster') or {}
        if top_optical.get('olt_name'):
            worst = top_optical.get('worst')
            worst_text = f"{worst:.2f}dBm" if isinstance(worst, (int, float)) else "unknown dBm"
            lines.append(
                f"- top optical cluster: {top_optical.get('olt_name')} PON {top_optical.get('port_id')} "
                f"(critical={top_optical.get('critical_count', 0)}, low={top_optical.get('low_count', 0)}, worst={worst_text})."
            )
        if result.get('address'):
            lines.append("")
            lines.append("Context:")
            lines.append(f"- building address: {result.get('address')}")
        if domain.get('suggested_fix'):
            lines.append("")
            lines.append("Next checks:")
            lines.append(f"- {domain.get('suggested_fix')}")
        else:
            lines.append("")
            lines.append("Next checks:")
        lines.append(f"- what can you tell me about {result.get('site_id')}?")
        lines.append(f"- show active alerts for {result.get('site_id')}")
        lines.append(f"- what needs to be fixed at {result.get('site_id')}?")
        return "\n".join(lines)

    if action == 'get_site_topology':
        site_id = result.get('site_id')
        radios = result.get('radios') or []
        links = result.get('radio_links') or []
        buildings = result.get('buildings') or []
        if not radios:
            return (
                f"Jake does not currently have a populated transport topology for {site_id}. "
                "That means there are no radio objects mapped into the current site topology view."
            )
        lines = [
            f"Transport topology for {site_id}: {len(radios)} radios, {len(links)} mapped links, {len(buildings)} building anchors."
        ]
        dn_radios = [row for row in radios if "v5000" in str(row.get("name") or "").lower()]
        cn_radios = [row for row in radios if any(token in str(row.get("name") or "").lower() for token in ("v1000", "v2000", "v3000"))]
        if dn_radios or cn_radios:
            lines.append(
                f"Topology shape: {len(dn_radios)} DN/backhaul radios, {len(cn_radios)} CN/distribution radios."
            )
        lines.append("Mapped radios:")
        for radio in radios[:10]:
            bits = [str(radio.get("name") or "unknown")]
            if radio.get("resolved_building_id"):
                bits.append(f"building={radio.get('resolved_building_id')}")
            if radio.get("ip"):
                bits.append(f"ip={radio.get('ip')}")
            if radio.get("status"):
                bits.append(f"status={radio.get('status')}")
            lines.append(f"- {' | '.join(bits)}")
        if links:
            inferred_count = sum(1 for row in links if str(row.get("status") or "").lower() == "inferred")
            lines.append("Mapped transport links:")
            for link in links[:10]:
                kind = str(link.get("kind") or "observed")
                status = str(link.get("status") or "observed")
                from_label = link.get("from_label") or link.get("a_label") or "unknown"
                to_label = link.get("to_label") or link.get("z_label") or "unknown"
                lines.append(f"- {from_label} -> {to_label} [{kind}, {status}]")
            if inferred_count:
                lines.append(
                    f"Current read: {inferred_count} link(s) are inferred from NetBox radio inventory rather than live RF adjacency."
                )
        else:
            lines.append(
                "Current read: radio inventory is present, but Jake still does not have mapped radio-to-radio link adjacency for this site."
            )
        lines.append("Next useful questions:")
        lines.append(f"- what can you tell me about {site_id}?")
        lines.append(f"- give me the current issue ledger for {site_id}")
        lines.append(f"- which transport path is most likely to impact customers first at {site_id}?")
        return "\n".join(lines)

    if action == 'get_online_customers':
        count = result.get('count', 0)
        routers = ", ".join(f"{r.get('identity')} ({r.get('ip')})" for r in (result.get('matched_routers') or []))
        method = result.get('counting_method')
        wants_evidence = any(
            token in query_lower
            for token in (
                "evidence",
                "source",
                "counting method",
                "sample",
                "why",
                "how do you know",
                "discrep",
                "dhcp hosts",
            )
        )
        source_status = result.get('source_status') or {}
        db_status = source_status.get('db') or {}
        api_status = source_status.get('api') or {}
        status_bits = []
        db_path = db_status.get('path')
        if db_path:
            if db_status.get('error'):
                status_bits.append(f"LynxMSP DB present but unreadable: {db_status.get('error')}.")
            else:
                table_counts = db_status.get('table_counts') or {}
                if any((table_counts.get(name) or 0) > 0 for name in table_counts):
                    lease_count = db_status.get('site_dhcp_lease_count')
                    if lease_count is not None:
                        status_bits.append(f"LynxMSP DB is available and has {lease_count} DHCP lease rows matching this site.")
                    else:
                        status_bits.append("LynxMSP DB is available but no site-specific DHCP lease rows were matched.")
                else:
                    status_bits.append("LynxMSP DB is present but the useful customer/network tables are empty.")
        elif db_status.get('error'):
            status_bits.append(f"LynxMSP DB probe failed: {db_status.get('error')}.")
        if api_status:
            if api_status.get('available'):
                status_bits.append(
                    f"LynxMSP API reachable at {api_status.get('base_url')} ({api_status.get('detail')})."
                )
            elif api_status.get('configured'):
                status_bits.append(
                    f"LynxMSP API was probed but is not reachable at {api_status.get('base_url')} ({api_status.get('detail')})."
                )
        if method == 'unverified_no_site_specific_customer_source':
            site_mode = result.get('site_service_mode') or 'unknown'
            lines = [
                "I do not have a verified live-customer count source for this site yet.",
                f"Current site service mode hint: {site_mode}.",
                str(result.get('error') or '').strip(),
            ]
            lines.extend(status_bits)
            lines.extend([
                "Next useful questions:",
                "- what evidence do we have on this site besides subscriber export?",
                "- is this a DHCP or PPP site?",
                "- what can you tell me about this site?",
            ])
            return "\n".join(line for line in lines if line)
        if method == 'local_online_cpe_export':
            note = result.get('source_note') or 'Count came from the freshest local online CPE export.'
            samples = result.get('sample_networks') or []
            suffix = f" Sample networks: {', '.join(samples[:5])}." if samples else ""
            lines = [f"{count} customers are currently online right now."]
            if wants_evidence:
                lines.append(f"Source: {note}{suffix}")
                lines.extend(status_bits)
                lines.append("Next useful questions:")
                lines.append("- does this match what we see on the routers dhcp hosts?")
                lines.append("- what evidence do we have on this site besides subscriber export?")
                lines.append("- do you see any discrepancies?")
            else:
                lines.append("That count is coming from the freshest local online CPE export for the site.")
            return "\n".join(lines)
        if wants_evidence:
            return f"{count} customers are currently online. Counting method: {method}. Routers used: {routers}."
        return f"{count} customers are currently online right now."

    if action == 'review_live_upgrade_risk':
        audit = result.get('audit') or {}
        findings = audit.get('findings') or []
        changes = audit.get('proposed_changes') or []
        preflight = audit.get('preflight_steps') or []
        lines = []
        device_name = result.get('device_name') or result.get('site_id') or 'target device'
        target_version = result.get('target_version') or 'target'
        lines.append(f"Upgrade review for {device_name} -> {target_version}.")
        if result.get('model'):
            lines.append(f"Model: {result.get('model')}.")
        if result.get('current_version'):
            lines.append(f"Current version: {result.get('current_version')}.")
        source = result.get('export_source')
        if source == 'live_routeros_export':
            lines.append("Source: fresh live RouterOS export.")
        elif source == 'local_export':
            lines.append(f"Source: local export fallback ({result.get('export_path')}).")
        config_rewrites = [item for item in changes if item.get('kind') not in {'no_config_delta', 'preflight_only'}]
        preflight_only = [item for item in changes if item.get('kind') == 'preflight_only']
        if config_rewrites:
            lines.append("")
            lines.append("Changes to make before the upgrade:")
            for idx, item in enumerate(config_rewrites[:5], start=1):
                lines.append(f"{idx}. {item.get('change')}")
                if item.get('why'):
                    lines.append(f"Why: {item.get('why')}")
        else:
            lines.append("")
            lines.append("No mandatory config changes are apparent from the current export.")
        if preflight_only:
            lines.append("")
            lines.append("Preflight-only changes:")
            for idx, item in enumerate(preflight_only[:5], start=1):
                lines.append(f"{idx}. {item.get('change')}")
                if item.get('why'):
                    lines.append(f"Why: {item.get('why')}")
        if preflight:
            lines.append("")
            lines.append("Preflight steps:")
            for idx, item in enumerate(preflight[:5], start=1):
                lines.append(f"{idx}. {item}")
        if findings:
            lines.append("")
            lines.append("What to watch:")
            for item in findings[:5]:
                lines.append(f"- {item.get('title')}: {item.get('detail')}")
        return "\n".join(lines)

    if action == 'generate_upgrade_preflight_plan':
        lines = []
        device_name = result.get('device_name') or result.get('site_id') or 'target device'
        target_version = result.get('target_version') or 'target'
        lines.append(f"Upgrade preflight for {device_name} -> {target_version}.")
        if result.get('model'):
            lines.append(f"Model: {result.get('model')}.")
        if result.get('current_version'):
            lines.append(f"Current version: {result.get('current_version')}.")
        if result.get('no_config_delta'):
            lines.append("No mandatory config rewrite is apparent.")
        steps = result.get('plan_steps') or []
        if steps:
            lines.append("")
            lines.append("Plan:")
            for step in steps[:6]:
                lines.append(f"{step.get('step')}. {step.get('action')}")
        return "\n".join(lines)

    if action == 'compare_customer_evidence':
        counts = result.get('counts') or {}
        parts = [f"{name}={count}" for name, count in counts.items()]
        source_status = result.get('source_status') or {}
        db_status = source_status.get('db') or {}
        api_status = source_status.get('api') or {}
        lines = [
            f"Customer-count evidence for {result.get('site_id')}: {', '.join(parts) if parts else 'no sources available'}.",
            str(result.get('note') or '').strip(),
        ]
        site_mode = result.get('site_service_mode')
        if site_mode:
            lines.append(f"Current site service mode hint: {site_mode}.")
        if db_status.get('path'):
            table_counts = db_status.get('table_counts') or {}
            if any((table_counts.get(name) or 0) > 0 for name in table_counts):
                lease_count = db_status.get('site_dhcp_lease_count')
                if lease_count is not None:
                    lines.append(f"LynxMSP DB evidence: {lease_count} site-matched DHCP lease rows.")
                else:
                    lines.append("LynxMSP DB is available but no site-matched DHCP lease rows were found.")
            else:
                lines.append("LynxMSP DB is present but the useful customer/network tables are empty.")
        elif db_status.get('error'):
            lines.append(f"LynxMSP DB probe failed: {db_status.get('error')}.")
        if api_status:
            if api_status.get('available'):
                lines.append(f"LynxMSP API status: reachable at {api_status.get('base_url')} ({api_status.get('detail')}).")
            elif api_status.get('configured'):
                lines.append(f"LynxMSP API status: not reachable at {api_status.get('base_url')} ({api_status.get('detail')}).")
        if result.get('has_discrepancy'):
            lines.append(f"Current max gap between sources: {result.get('max_gap', 0)}.")
        sources = result.get('sources') or []
        for source in sources:
            sample = source.get('sample') or []
            if sample:
                lines.append(f"- {source.get('source')}: sample {', '.join(sample[:5])}")
        lines.append("Next useful questions:")
        lines.append(f"- how many customers are currently online at {result.get('site_id')}?")
        lines.append(f"- what can you tell me about {result.get('site_id')}?")
        lines.append(f"- show rogue dhcp suspects on {result.get('site_id')}")
        return "\n".join(line for line in lines if line)

    if action == 'get_subnet_health':
        verified = result.get('verified') or {}
        return (
            f"Latest scan {((verified.get('scan') or {}).get('id'))} saw "
            f"{verified.get('device_count', 0)} devices and "
            f"{verified.get('outlier_count', 0)} outliers."
        )

    if action == 'trace_mac':
        trace_status = str(result.get('trace_status') or 'unknown')
        lines = [f"MAC trace for {result.get('mac') or query or ''}:"]
        if trace_status == 'access_port_current':
            lines.append("- state: current edge/access sighting")
        elif trace_status == 'latest_scan_uplink_only':
            lines.append("- state: uplink/trunk only in the latest scan")
        elif trace_status == 'upstream_or_cached_corroboration_only':
            lines.append("- state: upstream or cached corroboration only")
        elif trace_status == 'not_found_in_latest_scan':
            lines.append("- state: not present in the latest local scan")
        else:
            lines.append(f"- state: {trace_status}")
        lines.append("")
        lines.append("Operator view:")
        if trace_status == 'access_port_current':
            lines.append("This MAC is currently on a direct edge/access port.")
        elif trace_status == 'latest_scan_uplink_only':
            lines.append("This MAC is only visible on an uplink path right now, not on a direct subscriber edge port.")
        elif trace_status == 'upstream_or_cached_corroboration_only':
            lines.append("This MAC is not confirmed on a current edge port.")
        elif trace_status == 'not_found_in_latest_scan':
            lines.append("This MAC is absent from the latest local scan.")
        else:
            lines.append(f"Trace state is {trace_status}.")
        if result.get('reason'):
            lines.append("")
            lines.append("Evidence:")
            lines.append(f"- {result.get('reason')}")
        primary = result.get('primary_sighting') or {}
        if primary:
            _append_primary_sighting(lines, primary, prefix="- current best sighting")
        best = result.get('best_guess') or {}
        if best:
            lines.append(f"- best latest-scan sighting: {best.get('identity')} {best.get('on_interface')} VLAN {best.get('vid')}.")
        mac = (result.get('mac') or query or '').strip()
        lines.append("")
        lines.append("Next checks:")
        if mac:
            lines.append(f"- what is this mac doing: {mac}?")
            lines.append(f"- show cpe state for {mac}")
        if best and best.get('identity'):
            lines.append(f"- how is {best.get('identity')}?")
            if best.get('on_interface'):
                lines.append(f"- show rogue dhcp suspects on {best.get('identity')}")
        return "\n".join(lines)

    if action == 'get_customer_access_trace':
        resolved = result.get('resolved') or {}
        domain = result.get('fault_domain') or {}
        label = resolved.get('network_name') or resolved.get('mac') or resolved.get('serial') or 'this subscriber'
        lines = [f"Access trace for {label}:"]
        scope_bits = []
        if resolved.get('site_id'):
            scope_bits.append(f"site {resolved.get('site_id')}")
        if resolved.get('building_id'):
            scope_bits.append(f"building {resolved.get('building_id')}")
        if resolved.get('unit'):
            scope_bits.append(f"unit {resolved.get('unit')}")
        if scope_bits:
            lines.append(f"- Scope: {', '.join(scope_bits)}.")
        inferred_break = str(result.get('inferred_break') or 'unknown').replace('_', ' ')
        lines.append(f"- Inferred access-state read: {inferred_break}.")
        if domain.get('likely_domain'):
            lines.append(f"- Likely domain: {str(domain.get('likely_domain')).replace('_', ' ')} ({domain.get('confidence') or 'low'} confidence).")
        if domain.get('owner'):
            lines.append(f"- Owner focus: {domain.get('owner')}.")
        exact = result.get('exact_access_match') or {}
        if exact.get('switch_identity'):
            lines.append(f"- Expected access port: {exact.get('switch_identity')} {exact.get('interface')}.")
        trace = result.get('trace') or {}
        primary = trace.get('primary_sighting') or {}
        if primary:
            _append_primary_sighting(lines, primary, prefix="- Last seen location")
        best = trace.get('best_guess') or {}
        if best.get('identity'):
            lines.append(f"- Latest bridge-host sighting: {best.get('identity')} {best.get('on_interface')} VLAN {best.get('vid')}.")
        ppp_sessions = result.get('ppp_sessions') or []
        if ppp_sessions:
            session = ppp_sessions[0]
            lines.append(f"- PPP session evidence: {session.get('identity') or session.get('router_ip')} {session.get('name')} {session.get('address') or ''}".rstrip() + ".")
        arp_entries = result.get('arp_entries') or []
        if arp_entries:
            arp = arp_entries[0]
            lines.append(f"- ARP evidence: {arp.get('router_ip')} {arp.get('interface')} {arp.get('address') or ''}".rstrip() + ".")
        local_ont = result.get('local_ont_path') or {}
        placement = local_ont.get('placement') or {}
        if placement.get('kind') == 'gpon-ont':
            lines.append(f"- OLT path: {placement.get('olt_name')} {placement.get('pon')} ONU {placement.get('onu_id')}.")
        building_summary = result.get('building_model_summary') or {}
        if building_summary.get('address_block'):
            lines.append(f"- Address block: {building_summary.get('address_block')} (shared building block / roof-path context).")
        if domain.get('reason'):
            lines.append(f"- Why: {domain.get('reason')}")
        if domain.get('suggested_fix'):
            lines.append(f"- Fastest fix focus: {domain.get('suggested_fix')}")
        lines.append("Next useful questions:")
        if resolved.get('mac'):
            lines.append(f"- trace MAC {resolved.get('mac')}")
            lines.append(f"- what is this mac doing: {resolved.get('mac')}?")
        if resolved.get('building_id'):
            lines.append(f"- is this a floor issue or one unit at {resolved.get('building_id')}?")
        if resolved.get('site_id'):
            lines.append(f"- show active alerts for {resolved.get('site_id')}")
        return "\n".join(lines)

    if action == 'get_cpe_state':
        mac = result.get('mac') or query or ''
        mac_norm = mac.lower().replace('-', ':')
        bridge = result.get('bridge') or {}
        best = bridge.get('best_guess') or {}
        primary = bridge.get('primary_sighting') or {}
        seen_by_device = str(result.get('seen_by_device') or primary.get('device_name') or primary.get('identity') or '').strip()
        cpe_hostname = str(result.get('cpe_hostname') or primary.get('hostname') or '').strip()
        primary_port = str(primary.get('port_name') or primary.get('on_interface') or '').strip()
        primary_vlan = primary.get('vlan_id') if primary.get('vlan_id') is not None else primary.get('vid')
        primary_client_ip = str(primary.get('client_ip') or '').strip()
        primary_port_role = classify_port_role(primary_port)
        local_ont_path = result.get('local_ont_path') or {}
        local_olt = (local_ont_path.get('placement') or {}) if local_ont_path.get('found') else (LOCAL_OLT_EVIDENCE_BY_MAC.get(mac_norm) or {})
        olt_correlation = result.get('olt_correlation') or {}
        dhcp_correlation = result.get('dhcp_correlation') or {}
        subscriber_name = str(result.get('subscriber_name') or _subscriber_name_for_mac(mac_norm) or "").strip()
        asks_about_pon = " pon" in f" {query.lower()}" or "which pon" in query.lower() or "what pon" in query.lower()
        state_bits = []
        if result.get('is_service_online'):
            state_bits.append("service-online evidence present")
        else:
            state_bits.append("no latest-scan PPP/ARP service evidence")
        if bridge.get('verified_sightings'):
            state_bits.append("physically seen in latest local scan")
        elif primary:
            state_bits.append("physically seen via Bigmac")
        elif bridge.get('trace_status') == 'upstream_or_cached_corroboration_only':
            state_bits.append("only upstream/cached corroboration is available")
        else:
            state_bits.append("not physically seen in latest local scan")
        if subscriber_name:
            lines = [f"CPE state for {subscriber_name} ({mac}):"]
        else:
            lines = [f"CPE state for {mac}:"]
        lines.append(f"- state: {'; '.join(state_bits)}")
        lines.append("")
        lines.append("Operator view:")
        lines.append(f"{'; '.join(state_bits).capitalize()}.")
        lines.append("")
        lines.append("Evidence:")
        if primary:
            if primary_port_role == "uplink":
                vlan_text = f" (VLAN {primary_vlan})" if primary_vlan not in (None, "") else ""
                lines.append(
                    f"- physical/L2: last seen on {seen_by_device or 'unknown-device'} {primary_port}{vlan_text}"
                )
                lines.append("- physical/L2 note: this is an uplink/trunk port, not a direct subscriber drop.")
                lines.append("- physical/L2 note: the subscriber CPE is downstream, likely behind an OLT or distribution switch.")
                if cpe_hostname:
                    lines.append(
                        f"- client identity: DHCP client hostname {cpe_hostname}"
                    )
                    lines.append(
                        f"- client identity note: {seen_by_device or 'the reporting device'} is the headend router that logged this MAC, not the subscriber CPE."
                    )
                if primary_client_ip:
                    lines.append(f"- observed client IP: {primary_client_ip}.")
                freshness, age = _describe_seen_recency(primary.get("last_seen"))
                if primary.get("last_seen") or (freshness and age):
                    lines.append("")
                    lines.append("Context:")
                    if primary.get("last_seen"):
                        lines.append(f"- last seen: {primary.get('last_seen')}")
                    if freshness and age:
                        lines.append(f"- freshness: {freshness} ({age})")

                conclusion_bits = []
                if olt_correlation.get("found"):
                    olt_name = olt_correlation.get("olt_name") or "unknown OLT"
                    pon = olt_correlation.get("pon") or "unknown PON"
                    onu_id = olt_correlation.get("onu_id") or "unknown ONU"
                    onu_status = str(olt_correlation.get("onu_status") or "unknown").strip()
                    signal_dbm = olt_correlation.get("signal_dbm")
                    description = str(olt_correlation.get("description") or "").strip()
                    serial = str(olt_correlation.get("serial") or "").strip()
                    label_bits = [f"{olt_name} {pon} ONU {onu_id}"]
                    if description:
                        label_bits.append(f"({description})")
                    correlation_line = f"{' '.join(label_bits)} is {onu_status or 'unknown'}."
                    detail_bits = []
                    if serial:
                        detail_bits.append(f"serial {serial}")
                    if signal_dbm is not None:
                        detail_bits.append(f"signal {signal_dbm} dBm")
                    if detail_bits:
                        correlation_line += f" ({', '.join(detail_bits)})."
                    if onu_status.lower() != "online":
                        correlation_line = "⚠ " + correlation_line + " Endpoint is offline."
                    else:
                        correlation_line += " This is the subscriber endpoint."
                    lines.append(f"- controller/OLT: {correlation_line}")
                    if signal_dbm is not None and signal_dbm < -27:
                        lines.append(f"- optical warning: signal is weak ({signal_dbm} dBm) — check the fiber drop or connector at this ONU location.")
                    if onu_status and onu_status.lower() not in {"online", "online/enable/active", "enable/active"}:
                        lines.append("- optical warning: ONU is not online — this ONU may need to be re-provisioned or the fiber drop checked.")
                    conclusion_bits.append(f"The downstream source is {olt_name} {pon} ONU {onu_id}")
                    if onu_status:
                        conclusion_bits.append(f"it is currently {onu_status}")
                    if signal_dbm is not None:
                        conclusion_bits.append(f"signal is {signal_dbm} dBm")
                else:
                    conclusion_bits.append(
                        f"This MAC is downstream of {seen_by_device or 'the reporting device'} {primary_port}, so the uplink itself is not the subscriber port"
                    )

                if dhcp_correlation.get("found"):
                    lines.append("")
                    requests_per_hour = float(dhcp_correlation.get("requests_per_hour") or 0.0)
                    verdict = str(dhcp_correlation.get("verdict") or "normal")
                    window = int(dhcp_correlation.get("window_minutes") or 60)
                    if verdict == "abnormal":
                        if olt_correlation.get("found") and olt_correlation.get("onu_status"):
                            lines.append(
                                f"- service evidence: ~{requests_per_hour:.0f} DHCP requests/hour in the last {window} minutes."
                            )
                            lines.append(
                                f"- service evidence note: combined with ONU state {olt_correlation.get('onu_status')}, this points to repeated rebooting or loss of sync."
                            )
                        else:
                            lines.append(
                                f"- service evidence: ~{requests_per_hour:.0f} DHCP requests/hour in the last {window} minutes."
                            )
                            lines.append(
                                "- service evidence note: that churn points to a rebooting ONU/CPE, loop, or misconfigured subscriber device."
                            )
                        conclusion_bits.append(f"it is hammering DHCP at about {requests_per_hour:.0f} requests/hour")
                    elif verdict == "elevated":
                        lines.append(
                            f"- service evidence: ~{requests_per_hour:.0f} DHCP requests/hour in the last {window} minutes."
                        )
                        lines.append("- service evidence note: that is elevated and worth monitoring.")
                    elif requests_per_hour > 0:
                        lines.append(
                            f"- service evidence: ~{requests_per_hour:.0f} DHCP requests/hour in the last {window} minutes."
                        )
                        lines.append("- service evidence note: this looks routine.")

                if conclusion_bits:
                    lines.append("")
                    lines.append("Operator view:")
                    lines.append(
                        f"Subscriber path maps to {olt_name if olt_correlation.get('found') else (seen_by_device or 'the reporting device')}."
                    )
                    if olt_correlation.get("found") and olt_correlation.get("onu_status"):
                        bits = [f"ONU is {olt_correlation.get('onu_status')}"]
                        if signal_dbm is not None:
                            bits.append(f"signal is {signal_dbm} dBm")
                        if dhcp_correlation.get("found") and verdict == "abnormal":
                            bits.append(f"DHCP churn is ~{requests_per_hour:.0f}/hour")
                        lines.append("; ".join(bits) + ".")
                    else:
                        lines.append("; ".join(conclusion_bits) + ".")
            else:
                _append_primary_sighting(lines, primary)
                if cpe_hostname and seen_by_device:
                    lines.append(
                        f"DHCP client hostname: {cpe_hostname} (this is the subscriber CPE hostname, not the router — "
                        f"{seen_by_device} is the device that logged this MAC)."
                    )
        if best and best.get('identity'):
            lines.append(f"- best latest-scan sighting: {best.get('identity')} {best.get('on_interface')} VLAN {best.get('vid')}.")
        if bridge.get('reason'):
            lines.append(f"- trace note: {bridge.get('reason')}")
        related = result.get('related_mac_candidates') or []
        if related:
            top_related = related[0]
            location = " ".join(
                part for part in [str(top_related.get('identity') or '').strip(), str(top_related.get('on_interface') or '').strip()] if part
            ).strip()
            relation = str(top_related.get('mac_relation') or '').replace('_', ' ')
            lines.append(
                f"- adjacent-MAC clue: `{top_related.get('mac')}` is a {relation}"
                f"{' at ' + location if location else ''}."
                " Treat that as a likely wrong-port, wrong-label, or WAN/LAN bridging hint."
            )
        if local_olt.get('summary'):
            lines.append(f"- local OLT knowledge: {local_olt.get('summary')}")
        if local_olt.get('kind') == 'gpon-ont':
            lines.append(
                f"- PON answer: {local_olt.get('olt_name') or '?'} {local_olt.get('pon') or '?'} ONU {local_olt.get('onu_id') or '?'}."
            )
        elif asks_about_pon and local_olt.get('kind') == 'uplink-side':
            lines.append("- PON answer: this MAC is not currently tied to a single GPON PON; local field notes place it on the OLT uplink side.")
        if primary and primary_port_role == "uplink" and not result.get("is_service_online"):
            if not olt_correlation.get("found"):
                lines.append("")
                lines.append("Next checks:")
                lines.append(f"- check the OLT ONU table for MAC {mac} or IP {primary_client_ip or '?'}")
                lines.append(f"- on {seen_by_device or 'the headend router'}, inspect the DHCP lease for MAC {mac}")
                lines.append("- if the lease has no circuit-id, check the OLT ONU MAC table directly")
            else:
                lines.append("")
                lines.append("Next checks:")
        else:
            lines.append("")
            lines.append("Next checks:")
        if mac:
            lines.append(f"- trace MAC {mac}")
        if primary.get('device_site'):
            lines.append(f"- what can you tell me about {primary.get('device_site')}?")
        if primary.get('device_name'):
            lines.append(f"- how is {primary.get('device_name')}?")
        elif best and best.get('identity'):
            lines.append(f"- how is {best.get('identity')}?")
        if primary.get('device_name'):
            lines.append(f"- show rogue dhcp suspects on {primary.get('device_name')}")
        elif best and best.get('identity'):
            lines.append(f"- show rogue dhcp suspects on {best.get('identity')}")
        return "\n".join(lines)

    if action == 'get_local_ont_path':
        found = bool(result.get('found'))
        placement = result.get('placement') or {}
        query_bits = result.get('query') or {}
        serial = query_bits.get('serial')
        mac = query_bits.get('mac')
        needle = serial or mac or (query or '').strip()
        if not found:
            lines = [f"I could not tie {needle} to a specific local OLT/ONU/PON placement from the current field notes or TP-Link exporter telemetry."]
            lines.append("Next useful questions:")
            if serial:
                lines.append(f"- what can you tell me about {serial}?")
            if mac:
                lines.append(f"- trace MAC {mac}")
                lines.append(f"- what is this mac doing: {mac}?")
            lines.append("- check netbox for a list of sites")
            return "\n".join(lines)
        lines = [placement.get('summary') or f"Local OLT placement found for {needle}."]
        if placement.get('olt_name') or placement.get('olt_ip'):
            lines.append(f"OLT: {(placement.get('olt_name') or '?')} ({placement.get('olt_ip') or 'no-ip'}).")
        if placement.get('pon') or placement.get('onu_id'):
            lines.append(f"PON answer: {(placement.get('pon') or '?')} ONU {(placement.get('onu_id') or '?')}.")
        if placement.get('site_name'):
            lines.append(f"Site hint: {placement.get('site_name')}.")
        unique_paths = placement.get('unique_paths') or []
        if unique_paths and len(unique_paths) > 1:
            rendered = ", ".join(
                f"{row.get('olt_name') or '?'} {row.get('pon') or '?'} ONU {row.get('onu_id') or '?'}"
                for row in unique_paths[:5]
            )
            lines.append(f"Telemetry ambiguity: multiple local placements were found for this serial: {rendered}.")
        if placement.get('kind') == 'uplink-side':
            lines.append("This looks like uplink-side visibility rather than a single subscriber ONU.")
        lines.append("Next useful questions:")
        if placement.get('olt_name'):
            lines.append(f"- how is {placement.get('olt_name')}?")
        if placement.get('site_name'):
            lines.append(f"- what can you tell me about {placement.get('site_name')}?")
        if serial:
            lines.append(f"- show me the OLT path for {serial}")
        return "\n".join(lines)

    if action == 'get_netbox_device_by_ip':
        ip = result.get('ip') or query
        devices = result.get('devices') or []
        if not devices:
            lines = [f"I could not find a NetBox device with primary IP `{ip}`."]
            site_matches = result.get('site_matches') or []
            if site_matches:
                first = site_matches[0]
                lines.append(
                    f"It does, however, match site {first.get('site_id')} in the site inventory."
                )
            lines.append("Next useful questions:")
            lines.append("- list all of the sites")
            lines.append("- which sites have which real addresses and which 172 IPs?")
            lines.append("- what can you tell me about 000002?")
            return "\n".join(lines)
        first = devices[0]
        lines = [
            f"{ip} is {first.get('name')} at site {first.get('site_id')}.",
            f"Role/model: {first.get('role') or '?'} / {first.get('device_type') or '?'}.",
        ]
        if first.get('location'):
            lines.append(f"Address: {first.get('location')}.")
        if first.get('status'):
            lines.append(f"Status: {first.get('status')}.")
        if first.get('serial'):
            lines.append(f"Serial: {first.get('serial')}.")
        lines.append("Next useful questions:")
        if first.get('site_id'):
            lines.append(f"- what can you tell me about {first.get('site_id')}?")
        if first.get('name'):
            lines.append(f"- how is {first.get('name')}?")
        if first.get('site_id'):
            lines.append(f"- show active alerts for {first.get('site_id')}")
        return "\n".join(lines)

    if action == 'get_site_summary':
        site_name = (SITE_SERVICE_PROFILES.get(str(result.get('site_id') or '')) or {}).get('name')
        alerts = result.get('active_alerts') or []
        location_groups = result.get('location_groups') or []
        if any(token in query_lower for token in (
            'rest of that site compare',
            'other buildings there with issues',
            'building an outlier',
            'isolated or seen elsewhere on the site',
            'issues clustered or random',
            'clustered or random',
            'any outliers',
        )):
            site_id = result.get('site_id')
            zero_visibility: list[str] = []
            flagged: list[str] = []
            for row in location_groups:
                hint = (row.get('building_health_hint') or {}).get('health') or {}
                building_id = str(row.get('building_id') or hint.get('building_id') or '').strip()
                if not building_id:
                    continue
                switches = int(hint.get('device_count') or 0)
                cpes = int(hint.get('probable_cpe_count') or 0)
                outliers = int(hint.get('outlier_count') or 0)
                if switches == 0 and cpes == 0:
                    zero_visibility.append(building_id)
                elif outliers > 0:
                    flagged.append(building_id)
            lines = [f"Site {site_id} comparison:"]
            lines.append(f"- {len(location_groups)} mapped building scopes in current inventory")
            lines.append(f"- {len(flagged)} building scope{'s' if len(flagged) != 1 else ''} with outlier evidence")
            lines.append(f"- {len(zero_visibility)} building scope{'s' if len(zero_visibility) != 1 else ''} with zero switch/CPE visibility")
            lines.append("")
            lines.append("Operator view:")
            if flagged:
                sample = ", ".join(flagged[:4])
                lines.append(f"There is building-specific issue evidence elsewhere on this site, not just one isolated building. Current flagged scopes: {sample}.")
            elif zero_visibility:
                sample = ", ".join(zero_visibility[:4])
                lines.append(f"No broader fault cluster stands out, but some buildings do have visibility gaps. Current zero-visibility scopes: {sample}.")
            else:
                lines.append("No broader building-level issue pattern stands out in the current site data.")
            lines.append("")
            lines.append("Evidence:")
            lines.append(f"- site-level alerts: {len(alerts)}")
            lines.append(f"- site-level outliers: {int(result.get('outlier_count') or 0)}")
            if zero_visibility:
                lines.append(f"- zero-visibility building scopes: {', '.join(zero_visibility[:6])}")
            if flagged:
                lines.append(f"- building scopes with outlier evidence: {', '.join(flagged[:6])}")
            lines.append("")
            lines.append("Next checks:")
            lines.append(f"- show active alerts for {site_id}")
            lines.append(f"- what needs to be fixed at {site_id}?")
            if flagged:
                lines.append(f"- how is {flagged[0]}?")
            elif zero_visibility:
                lines.append(f"- how is {zero_visibility[0]}?")
            return "\n".join(lines)
        if result.get('site_id') and any(token in query_lower for token in ('what site is', 'which site is')):
            if site_name:
                return f"{result.get('site_id')} is {site_name}."
            return f"{result.get('site_id')} is a known site in the current inventory."
        if alerts and any(token in query_lower for token in ('urgent', 'urgent alarms', 'urgent alerts', 'quick sweep', 'sweep over', 'sweep')):
            critical = []
            warnings = []
            for alert in alerts:
                labels = alert.get('labels') or {}
                annotations = alert.get('annotations') or {}
                summary = annotations.get('summary') or labels.get('alertname') or 'Unnamed alert'
                started = str(alert.get('startsAt') or '')[:10]
                line = f"- {summary}"
                if started:
                    line += f" since {started}"
                if str(labels.get('severity') or '').lower() == 'critical':
                    critical.append(line)
                else:
                    warnings.append(line)
            lines = [f"NYCHA has {len(alerts)} active alerts right now."]
            if critical:
                lines.append("Urgent first:")
                lines.extend(critical[:5])
            elif warnings:
                lines.append("No critical alerts right now. The main warnings are:")
                lines.extend(warnings[:5])
            lines.append("Next useful questions:")
            lines.append(f"- show active alerts for {result.get('site_id')}")
            lines.append(f"- what needs to be fixed at {result.get('site_id')}?")
            lines.append(f"- which cambium radios have issues at {result.get('site_id')}?")
            return "\n".join(lines)
        summary_style = any(token in query_lower for token in (
            'how is',
            "how's",
            'looking',
            'look today',
            'today',
            'take a look at',
            'check on',
            'what is going on with',
            'what can you tell me about',
            'let me know how everything is looking',
        ))
        detail_style = any(token in query_lower for token in (
            'site summary',
            'show summary',
            'full summary',
            'detailed summary',
            'details',
            'inventory',
            'hardware by location',
        ))
        if summary_style and not detail_style:
            site_id = result.get('site_id')
            online = int(((result.get('online_customers') or {}).get('count')) or 0)
            outliers = int(result.get('outlier_count') or 0)
            alert_count = len(alerts)
            devices_total = int(result.get('devices_total') or 0)
            lines = [f"Site {site_id}:"]
            lines.append(f"- {online} online {_plural(online, 'subscriber')}")
            lines.append(f"- {devices_total} tracked network {_plural(devices_total, 'device')}")
            lines.append(f"- {alert_count} active {_plural(alert_count, 'alert')}")
            lines.append(f"- {outliers} anomal{'ies' if outliers != 1 else 'y'} in current site data")
            lines.append("")
            lines.append("Operator view:")
            if alert_count == 0 and outliers == 0:
                lines.append("No site-level issues stand out right now.")
            else:
                lines.append("This site has issues worth checking.")
            top_alerts = []
            if alert_count:
                seen = set()
                for alert in alerts:
                    labels = alert.get('labels') or {}
                    annotations = alert.get('annotations') or {}
                    summary = annotations.get('summary') or labels.get('alertname')
                    if not summary or summary in seen:
                        continue
                    seen.add(summary)
                    top_alerts.append(summary)
                    if len(top_alerts) >= 3:
                        break
            routers = result.get('routers') or []
            bridge = result.get('bridge_host_summary') or {}
            if bridge:
                lines.append("")
                lines.append("Evidence:")
                lines.append(
                    f"- bridge-host scan summary: {bridge.get('total', 0)} raw MAC sightings, "
                    f"{bridge.get('tplink', 0)} TP-Link-estimated CPEs, {bridge.get('vilo', 0)} Vilo-estimated CPEs"
                )
                lines.append("- bridge-host counts describe current scan visibility, not expected subscriber totals for the site")
            lines.append("")
            lines.append("Context:")
            if routers:
                router_names = ", ".join(str(row.get('identity')) for row in routers[:3] if row.get('identity'))
                if router_names:
                    lines.append(f"- headend/router devices seen: {router_names}")
            if top_alerts:
                for item in top_alerts:
                    lines.append(f"- current alert: {item}")
            lines.append("")
            lines.append("Next checks:")
            lines.append(f"- show active alerts for {site_id}")
            lines.append(f"- how many customers are online for {site_id}?")
            lines.append(f"- what needs to be fixed at {site_id}?")
            return "\n".join(lines)
        if any(token in query_lower for token in ('what outliers', 'which outliers', 'show outliers', 'outliers do you see')):
            outlier_count = int(result.get('outlier_count') or 0)
            outliers = result.get('outliers') or []
            if outlier_count <= 0 or not outliers:
                return f"{result.get('site_id')} has no current outliers in the latest scan."
            lines = [f"{result.get('site_id')} has {outlier_count} current outliers."]
            for row in outliers[:8]:
                bits = [str(row.get('ip') or '').strip(), str(row.get('interface') or '').strip(), str(row.get('direction') or '').strip(), str(row.get('note') or '').strip()]
                rendered = " | ".join(bit for bit in bits if bit)
                if rendered:
                    lines.append(f"- {rendered}")
            return "\n".join(lines)
        if any(token in query_lower for token in ('what are the devices', 'what are the 4 devices', 'list the devices', 'devices at', 'devices from netbox', 'list the devices from netbox')):
            groups = result.get('location_groups') or []
            if not groups:
                return f"I do not have NetBox device inventory grouped for {result.get('site_id')} right now."
            lines = [f"Devices at {site_name or result.get('site_id')} from NetBox:"]
            seen: list[str] = []
            for row in groups:
                for name in (row.get('devices') or []):
                    if name not in seen:
                        seen.append(name)
            for name in seen[:30]:
                lines.append(f"- {name}")
            return "\n".join(lines)
        if any(token in query_lower for token in ('loss on the network', 'packet loss', 'seeing loss', 'any loss', 'leakage on', 'any leakage', 'seeing leakage')):
            site_id = result.get('site_id')
            online = int(((result.get('online_customers') or {}).get('count')) or 0)
            alert_count = len(alerts)
            lines = [f"I do not have deterministic proof of packet loss or leakage at {site_name or site_id} from this summary alone."]
            lines.append(f"Current site read: {online} online customers, {alert_count} active alerts, {int(result.get('outlier_count') or 0)} outliers.")
            if alerts:
                lines.append("What is actually visible right now:")
                seen = []
                for alert in alerts[:3]:
                    summary = (alert.get('annotations') or {}).get('summary') or (alert.get('labels') or {}).get('alertname')
                    if summary and summary not in seen:
                        seen.append(summary)
                        lines.append(f"- {summary}")
            lines.append("Next useful questions:")
            lines.append(f"- show active alerts for {site_id}")
            lines.append(f"- what evidence do we have on {site_id} besides subscriber export?")
            lines.append(f"- show rogue dhcp suspects on {site_id}")
            return "\n".join(lines)
        lines = [
            (
                f"Site {result.get('site_id')} summary: {result.get('devices_total', 0)} devices, "
                f"{(result.get('online_customers') or {}).get('count', 0)} online customers, "
                f"{result.get('outlier_count', 0)} outliers, "
                f"{len(result.get('active_alerts') or [])} active alerts."
            )
        ]
        routers = result.get('routers') or []
        if routers:
            router_text = ", ".join(
                f"{row.get('identity')} ({row.get('ip')})"
                for row in routers[:4]
                if row.get('identity')
            )
            if router_text:
                lines.append(f"Routers: {router_text}.")
        bridge = result.get('bridge_host_summary') or {}
        if bridge:
            lines.append(
                f"Bridge hosts seen on latest scan: total={bridge.get('total', 0)}, "
                f"tplink_est={bridge.get('tplink', 0)} (raw={bridge.get('tplink_raw_macs', 0)}, alt_dupes={bridge.get('tplink_alt_mac_duplicates', 0)}), "
                f"vilo_est={bridge.get('vilo', 0)} (raw={bridge.get('vilo_raw_macs', 0)}, alt_dupes={bridge.get('vilo_alt_mac_duplicates', 0)})."
            )
        locations = result.get('location_groups') or []
        if locations:
            lines.append("Known site hardware by location:")
            for row in locations[:8]:
                device_names = ", ".join((row.get('devices') or [])[:5])
                building_id = row.get('building_id') or "unmapped"
                lines.append(
                    f"- {row.get('location')}: {row.get('device_count', 0)} devices, "
                    f"building={building_id}, devices={device_names}"
                )
        topo = result.get('transport_topology') or {}
        radios = topo.get('radios') or []
        if radios:
            radio_text = ", ".join(
                f"{row.get('name')} ({row.get('primary_ip') or 'no-ip'})"
                for row in radios[:6]
                if row.get('name')
            )
            if radio_text:
                lines.append(f"Transport radios: {radio_text}.")
        alerts = result.get('active_alerts') or []
        if alerts:
            top_alerts = []
            seen = set()
            for alert in alerts:
                labels = alert.get('labels') or {}
                annotations = alert.get('annotations') or {}
                key = (
                    labels.get('alertname'),
                    annotations.get('olt_name') or labels.get('olt_name'),
                    annotations.get('port_id') or labels.get('port_id'),
                )
                if key in seen:
                    continue
                seen.add(key)
                summary = annotations.get('summary') or labels.get('alertname')
                if summary:
                    top_alerts.append(summary)
                if len(top_alerts) >= 3:
                    break
            if top_alerts:
                lines.append("Top current alerts:")
                lines.extend(f"- {item}" for item in top_alerts)
        lines.append("Next useful questions:")
        lines.append(f"- show active alerts for {result.get('site_id')}")
        lines.append(f"- how many customers are online for {result.get('site_id')}?")
        lines.append(f"- show rogue dhcp suspects on {result.get('site_id')}")
        lines.append(f"- what needs to be fixed at {result.get('site_id')}?")
        return "\n".join(lines)

    if action == 'list_sites_inventory':
        rows = result.get('sites') or []
        lines = [f"Known sites from NetBox: {result.get('count', 0)}."]
        for row in rows[:25]:
            addr = ", ".join(row.get('locations') or []) or "no address"
            ips = ", ".join(row.get('router_172_ips') or []) or "no 172 router IP recorded"
            lines.append(f"- {row.get('site_id')}: {addr} | 172 IPs: {ips}")
        lines.append("Next useful questions:")
        lines.append("- what can you tell me about 000002?")
        lines.append("- what can you tell me about 000021?")
        lines.append("- which sites are missing 172 router IPs?")
        return "\n".join(lines)

    if action == 'get_site_alerts':
        site_id = result.get('site_id')
        alerts = result.get('alerts') or []
        if not alerts:
            return f"Site {site_id} has no active alerts right now."
        if any(token in query_lower for token in ('same pons', 'same pon', 'high or low light', 'mux and the unit', 'between the mux and the unit')):
            optical = []
            for alert in alerts:
                annotations = alert.get('annotations') or {}
                labels = alert.get('labels') or {}
                summary = annotations.get('summary') or labels.get('alertname') or ''
                if any(term in summary.lower() for term in ('rx power low', 'rx power high', 'rx power critical')):
                    optical.append(summary)
            if not optical:
                return (
                    f"I do not see optical light-level alerts clustered on the same PONs at {site_id} from the current alert set. "
                    "That makes a shared PON or mux story weaker from the current evidence."
                )
            deduped = []
            for item in optical:
                if item not in deduped:
                    deduped.append(item)
            lines = [f"I do see {len(deduped)} optical light-level alert(s) at {site_id} in the current alert set."]
            lines.append("Current optical alerts:")
            lines.extend(f"- {item}" for item in deduped[:8])
            lines.append(
                "If multiple units on the same exact PON were all showing high or low light together, shared plant like fiber, splitter, or mux would be stronger. "
                "If the issue is isolated to one unit while nearby ONUs stay clean, the problem is more likely between the mux/drop and that unit."
            )
            return "\n".join(lines)
        if any(token in query_lower for token in ('why are we getting this alert', 'why this alert', 'why are we seeing this alert')):
            lowered = query_lower
            matched = None
            for alert in alerts:
                annotations = alert.get('annotations') or {}
                labels = alert.get('labels') or {}
                summary = (annotations.get('summary') or labels.get('alertname') or '').lower()
                name = str(labels.get('name') or annotations.get('device_name') or labels.get('device_name') or '').lower()
                if summary and summary in lowered:
                    matched = alert
                    break
                if name and name in lowered:
                    matched = alert
                    break
            if matched:
                labels = matched.get('labels') or {}
                annotations = matched.get('annotations') or {}
                summary = annotations.get('summary') or labels.get('alertname') or 'Unnamed alert'
                desc = str(annotations.get('description') or '').strip()
                location = annotations.get('location') or labels.get('location')
                started = str(matched.get('startsAt') or '')[:10]
                lines = [f"That alert is firing because `{summary}` is currently being reported as down or unreachable."]
                if location:
                    lines.append(f"Location: {location}.")
                if started:
                    lines.append(f"It has been active since {started}.")
                if desc:
                    lines.append(desc.splitlines()[0].strip())
                return "\n".join(lines)
        critical = []
        warnings = []
        for alert in alerts:
            labels = alert.get('labels') or {}
            annotations = alert.get('annotations') or {}
            summary = annotations.get('summary') or labels.get('alertname') or 'Unnamed alert'
            severity = str(labels.get('severity') or 'warning').lower()
            location = annotations.get('location') or labels.get('location') or ''
            started = str(alert.get('startsAt') or '')[:10]
            detail = summary
            if location:
                detail += f" at {location}"
            if started:
                detail += f" since {started}"
            if severity == 'critical':
                critical.append(detail)
            else:
                warnings.append(detail)
        lines = [f"Site {site_id} has {len(alerts)} active alerts."]
        if critical:
            lines.append("Critical:")
            lines.extend(f"- {item}" for item in critical[:6])
        if warnings:
            lines.append("Warnings:")
            lines.extend(f"- {item}" for item in warnings[:8])
        lines.append("Next useful questions:")
        lines.append(f"- what needs to be fixed at {site_id}?")
        lines.append(f"- show me the site summary for {site_id}")
        return "\n".join(lines)

    if action == 'search_sites_inventory':
        rows = result.get('sites') or []
        if not rows:
            return (
                f"I could not find a site matching `{result.get('query')}` in the current NetBox-backed site inventory.\n"
                "Next useful questions:\n"
                "- list all of the sites\n"
                "- which sites have which real addresses and which 172 IPs?\n"
                "- what can you tell me about 000002?"
            )
        lines = [f"Site matches for `{result.get('query')}`: {result.get('count', 0)}."]
        for row in rows[:10]:
            addr = ", ".join(row.get('locations') or []) or "no address"
            ips = ", ".join(row.get('router_172_ips') or []) or "no 172 router IP recorded"
            lines.append(f"- {row.get('site_id')}: {addr} | 172 IPs: {ips}")
        lines.append("Next useful questions:")
        first = rows[0]
        lines.append(f"- what can you tell me about {first.get('site_id')}?")
        lines.append(f"- how many customers are online at {first.get('site_id')}?")
        return "\n".join(lines)

    if action == 'get_vilo_inventory_audit':
        scope = result.get('scope') or {}
        scoped_to = scope.get('building_id') or scope.get('site_id') or 'global'
        matched_with_network = sum(1 for row in (result.get('rows') or []) if row.get('network_id'))
        matched_with_subscriber = sum(1 for row in (result.get('rows') or []) if row.get('subscriber'))
        matched_with_hint = sum(1 for row in (result.get('rows') or []) if row.get('subscriber_hint'))
        drift_count = sum(1 for row in (result.get('rows') or []) if row.get('network_name_building_drift'))
        return (
            f"Vilo audit {scoped_to}: {len(result.get('rows') or [])} rows analyzed, "
            f"{result.get('scope_seen_mac_count', 0)} scan sightings, "
            f"{matched_with_network} with network context, {matched_with_subscriber} with subscriber context, {matched_with_hint} with local hints, {drift_count} with network-name drift, "
            f"classifications={result.get('counts_by_classification') or {}}, "
            f"buildings={result.get('counts_by_building') or {}}."
        )

    if action == 'export_vilo_inventory_audit':
        paths = result.get('paths') or {}
        summary = result.get('summary') or {}
        return (
            f"Vilo audit export written. Rows={summary.get('rows', 0)}, "
            f"network_context={summary.get('matched_with_network', 0)}, "
            f"subscriber_context={summary.get('matched_with_subscriber', 0)}, "
            f"local_hints={summary.get('matched_with_hint', 0)}, "
            f"network_name_drift={summary.get('network_name_drift', 0)}. "
            f"CSV={paths.get('csv')} MD={paths.get('md')}."
        )

    if action == 'get_building_health':
        building_id = result.get('building_id')
        truth = _building_truth(result)
        scan_context = _building_scan_context(result)
        zero_visibility = truth.switches_seen == 0 and truth.probable_cpes == 0
        lines = [f"Building {building_id}:"]
        lines.append(f"- {truth.switches_seen} switch{'es' if truth.switches_seen != 1 else ''} detected")
        lines.append(f"- {truth.probable_cpes} probable subscriber devices (CPEs)")
        if zero_visibility:
            lines.append("- no alerts or anomalies tied to this building")
            lines.append("- no switch/CPE telemetry visible")
        elif truth.active_alerts == 0 and truth.outliers == 0:
            lines.append("- no alerts or anomalies")
        else:
            lines.append(f"- {truth.active_alerts} active alert{'s' if truth.active_alerts != 1 else ''}")
            lines.append(f"- {truth.outliers} anomal{'ies' if truth.outliers != 1 else 'y'} flagged in current data")

        if zero_visibility:
            lines.append("")
            lines.append("Operator view:")
            lines.append(
                "No switch or CPE telemetry is visible for this building in the latest scan."
            )
            lines.append(
                "This does not prove the building is healthy; Jake does not currently see building-level network evidence for this prefix."
            )
        elif truth.active_alerts == 0 and truth.outliers == 0:
            if truth.switches_seen > 0 and truth.probable_cpes >= 0:
                lines.append("")
                lines.append("Operator view:")
                if scan_context.freshness == "stale":
                    lines.append("No building-specific issue is visible in the available building data.")
                    lines.append("The latest scan is stale, so this is historical visibility, not live proof that the building is healthy.")
                else:
                    lines.append("This building appears operational. Nothing in the current building-level evidence suggests an active problem.")
        else:
            lines.append("")
            lines.append("Operator view:")
            lines.append("This building has building-level signals worth checking before treating it as healthy.")
        lines.append("")
        lines.append("Evidence:")
        lines.append(f"- switches seen in this building: {truth.switches_seen}")
        lines.append(f"- probable subscriber devices (CPEs): {truth.probable_cpes}")
        lines.append(f"- active alerts: {truth.active_alerts}")
        lines.append(f"- anomalies: {truth.outliers}")

        if (
            scan_context.subnet
            and scan_context.api_reachable is not None
            and scan_context.hosts_tested is not None
            and scan_context.timestamp
        ):
            lines.append("")
            lines.append("Context:")
            lines.append(f"- subnet: {scan_context.subnet}")
            lines.append(f"- API reachability: {scan_context.api_reachable} / {scan_context.hosts_tested} IPs responding via API")
            lines.append(f"- last scan: {scan_context.timestamp}")
            if scan_context.freshness and scan_context.age_detail:
                lines.append(f"- scan freshness: {scan_context.freshness} ({scan_context.age_detail})")
            lines.append("")
            lines.append("- this reachability is subnet-wide context, not a building device count")
            if zero_visibility:
                lines.append("- possible causes: missing building-prefix mapping, unreachable switch, no installed equipment, or no DB evidence yet")
                lines.append("- check the parent site scan before assuming this building is healthy or absent")
            elif truth.active_alerts == 0 and truth.outliers == 0:
                lines.append("- low API reachability here is more likely a subnet visibility limit than a building outage")
                if scan_context.freshness == "stale":
                    lines.append("- this scan is old, so treat the reachability context as historical rather than current")

        lines.append("")
        lines.append("Next checks:")
        if zero_visibility:
            lines.append(f"- verify the building prefix mapping for {building_id}")
            lines.append(f"- check latest scan coverage for site {str(building_id).split('.', 1)[0]}")
            lines.append(f"- search MAC and bridge evidence for {building_id}")
            lines.append(f"- check whether expected switches exist in inventory for {building_id}")
        else:
            lines.append(f"- show rogue dhcp suspects on {building_id}")
            lines.append(f"- which ports are flapping on {building_id}?")
            lines.append(f"- show recovery-ready cpes on {building_id}")
            lines.append(f"- explain the latest scan context for {building_id}")
        return "\n".join(lines)

    if action == 'rerun_latest_scan':
        building_id = result.get('building_id')
        site_id = result.get('site_id')
        before_scan = result.get('before_scan') or result.get('scan') or {}
        after_scan = result.get('after_scan') or before_scan
        started = _format_operator_timestamp(before_scan.get('started_at'))
        freshness, age_detail = _describe_scan_freshness(before_scan.get('started_at'))
        target = building_id or site_id or "that scope"
        age_note = ""
        if freshness and age_detail:
            age_note = f" It is {freshness} ({age_detail})."
        if result.get("available") is False:
            return (
                f"Jake cannot trigger a new network scan for {target} from chat because this Jake instance has no scan trigger backend configured. "
                f"It is currently read-only against the latest recorded scan data. "
                f"The latest available scan context is still from {started or 'an unknown time'}.{age_note}"
            )
        if result.get("triggered") is False and result.get("error"):
            return (
                f"Jake tried to trigger a new network scan for {target}, but the scan runner failed. "
                f"{result.get('error')} The latest available scan context is still from {started or 'an unknown time'}.{age_note}"
            )
        if result.get("triggered") and result.get("scan_changed"):
            new_started = _format_operator_timestamp(after_scan.get("started_at"))
            new_freshness, new_age_detail = _describe_scan_freshness(after_scan.get("started_at"))
            new_age_note = f" It is {new_freshness} ({new_age_detail})." if new_freshness and new_age_detail else ""
            return (
                f"Jake triggered a new network scan for {target}. "
                f"The latest scan context moved from {started or 'an unknown time'} to {new_started or 'an unknown time'}.{new_age_note}"
            )
        if result.get("triggered") and not result.get("scan_changed"):
            return (
                f"Jake triggered the scan runner for {target}, but no new scan record appeared within the wait window. "
                f"The latest available scan context is still from {started or 'an unknown time'}.{age_note}"
            )
        if any(token in query_lower for token in ("what changed",)):
            return (
                f"Nothing changed in Jake's evidence for {target} because no new scan was actually run from chat. "
                f"The latest available scan context is still from {started or 'an unknown time'}.{age_note}"
            )
        if any(token in query_lower for token in ("better or worse", "is it better or worse")):
            return (
                f"Jake cannot say better or worse for {target} yet because no new scan was executed from chat. "
                f"The only available scan context is still from {started or 'an unknown time'}.{age_note}"
            )
        if building_id:
            return (
                f"Jake cannot re-run the underlying network scan from chat yet for {target}. "
                f"The latest available scan context for this building is from {started or 'an unknown time'}.{age_note} "
                f"I can keep analyzing the current scan, but a new scan must be triggered outside this chat path."
            )
        if site_id:
            return (
                f"Jake cannot re-run the underlying network scan from chat yet for site {target}. "
                f"The latest available scan context is from {started or 'an unknown time'}.{age_note} "
                "I can keep analyzing the current scan, but a new scan must be triggered outside this chat path."
            )
        return "Jake cannot re-run the underlying network scan from chat yet. Tell me which site or building you want me to analyze from the latest available scan."

    if action == 'clarify_target':
        reason = str(result.get('reason') or '').strip()
        return reason or "Jake needs a more specific site, building, or address."

    if action == 'get_switch_summary':
        vendor_summary = result.get('vendor_summary') or {}
        vendor_text = ", ".join(f"{k}={v}" for k, v in sorted(vendor_summary.items()) if v)
        switch_identity = result.get('switch_identity')
        access_ports = int(result.get('access_port_count', 0) or 0)
        probable_cpes = int(result.get('probable_cpe_count', 0) or 0)
        lines = [f"Switch {switch_identity}:"]
        lines.append(f"- {access_ports} subscriber-facing {_plural(access_ports, 'port')}")
        lines.append(f"- {probable_cpes} probable subscriber devices (CPEs) seen on those ports")
        if vendor_text:
            lines.append(f"- vendor mix on scan-visible CPEs: {vendor_text}")
        lines.append("")
        lines.append("Operator view:")
        lines.append("No switch fault is implied here by itself. This shows what Jake currently sees on subscriber-facing ports.")
        lines.append("")
        lines.append("Evidence:")
        lines.append("- these counts describe current scan visibility, not expected device totals")
        lines.append("")
        lines.append("Next checks:")
        lines.append(f"- show rogue dhcp suspects on {switch_identity}")
        lines.append(f"- how many customers are online on {switch_identity}?")
        lines.append(f"- find probable tplink cpes on {switch_identity}")
        return "\n".join(lines)

    if action == 'get_nycha_port_audit':
        total = int(result.get('total_issues') or 0)
        wrong = result.get('wrong_uplink_port') or []
        mixed = result.get('mixed_patch_order') or []
        if total == 0:
            return "No NYCHA switch uplink port mismatches detected in the latest scan."
        lines = [result.get('summary') or f"{total} NYCHA switch port issue(s) found."]
        if wrong:
            lines.append(f"\nWrong uplink port ({len(wrong)} devices — using ether48 instead of ether49):")
            for row in wrong[:10]:
                mac_note = f" ({row.get('ether48_mac_count', 0)} MACs on ether48)" if row.get('ether48_mac_count') else ""
                lines.append(f"  - {row.get('device')}: {row.get('detail')}{mac_note}")
        if mixed:
            lines.append(f"\nSuspected reversed patch order ({len(mixed)} devices):")
            for row in mixed[:10]:
                lines.append(f"  - {row.get('device')}: {row.get('detail')}")
        return "\n".join(lines)

    if action == 'generate_nycha_audit_workbook':
        if not result.get('available', True):
            error = result.get('error') or 'Jake could not generate the audit workbook.'
            return f"Jake could not run that audit workbook. {error}"
        rows = result.get('rows') or []
        good = sum(1 for r in rows if r.get('state') == 'green')
        yellow = sum(1 for r in rows if r.get('state') == 'yellow')
        red = sum(1 for r in rows if r.get('state') == 'red')
        ready_pct = int(result.get('weighted_ready_percent') or 0)
        out = str(result.get('output_path') or '')
        address = result.get('address') or result.get('sheet_title') or ''
        lines = [f"NYCHA audit workbook for {address}: {ready_pct}% weighted ready."]
        lines.append(f"Rows: {good} good, {yellow} seen/wrong, {red} no evidence. Total: {len(rows)}.")
        if out:
            lines.append(f"Written to: {out}")
        return "\n".join(lines)

    if action == 'get_site_punch_list':
        lines = [
            f"Site {result.get('site_id')} punch list: {result.get('total_actionable_ports', 0)} actionable ports, "
            f"{result.get('isolated_count', 0)} isolated, {result.get('recovery_count', 0)} recovery, "
            f"{result.get('observe_count', 0)} observe, {result.get('flap_count', 0)} with flap history."
        ]
        isolated = result.get('isolated_ports') or []
        recovery = result.get('recovery_ports') or []
        observe = result.get('observe_ports') or []
        if isolated:
            lines.append("Immediate isolate/investigate:")
            lines.extend(
                f"- {p.get('identity')} {p.get('port')} {('comment ' + p.get('comment')) if p.get('comment') else ''}".rstrip()
                for p in isolated[:5]
            )
        if recovery:
            lines.append("Recovery/reboot candidates:")
            lines.extend(
                f"- {p.get('identity')} {p.get('port')} {('comment ' + p.get('comment')) if p.get('comment') else ''}".rstrip()
                for p in recovery[:8]
            )
        if observe:
            lines.append("Field checks:")
            lines.extend(
                f"- {p.get('identity')} {p.get('port')} {('comment ' + p.get('comment')) if p.get('comment') else ''}".rstrip()
                for p in observe[:8]
            )
        return "\n".join(lines)

    if action == 'get_site_rogue_dhcp_summary':
        return (
            f"Site {result.get('site_id')} has {result.get('count', 0)} artifact-marked rogue DHCP suspect ports "
            f"across {result.get('building_count', 0)} buildings. This summary comes from the customer port map, "
            "not a live packet capture."
        )

    if action == 'get_rogue_dhcp_suspects':
        scope = result.get('building_id') or result.get('site_id') or 'that scope'
        count = int(result.get('count', 0))
        if count <= 0:
            return (
                f"Jake has no artifact-marked rogue DHCP suspect ports for {scope}. "
                "That is not a live negative finding; it only means the current customer port map does not label one there."
            )
        ports = result.get('ports') or []
        lines = [
            f"Jake has {count} artifact-marked rogue DHCP suspect ports for {scope}. "
            "This comes from the customer port map, not a live packet capture."
        ]
        for row in ports[:8]:
            port = row.get('interface') or row.get('port') or row.get('on_interface')
            comment = f" comment {row.get('comment')}" if row.get('comment') else ""
            issues = ", ".join(row.get('issues') or [])
            lines.append(f"- {row.get('identity')} {port}{comment} [{issues}]".rstrip())
        return "\n".join(lines)

    if action == 'find_cpe_candidates':
        count = int(result.get('count', 0))
        rows = result.get('results') or []
        if not rows:
            return "No probable CPEs matched that filter in the latest scan."
        lines = [f"Jake found {count} probable CPE sightings in the latest scan for that scope."]
        lines.append("Sample access ports:")
        for row in rows[:8]:
            lines.append(f"- {row.get('identity')} {row.get('on_interface')} {row.get('mac')}")
        lines.append("Next useful questions:")
        first = rows[0]
        if first.get('mac'):
            lines.append(f"- trace MAC {first.get('mac')}")
            lines.append(f"- what is this mac doing: {first.get('mac')}")
        if first.get('identity'):
            lines.append(f"- how is {first.get('identity')}?")
        return "\n".join(lines)

    if action == 'get_vendor_site_presence':
        vendor = str(result.get('vendor') or '').lower()
        sites = result.get('sites') or []
        if not sites:
            return f"Jake did not find any {vendor} CPE sightings in the latest scan."
        lines = [f"Jake sees {result.get('count', 0)} raw {vendor} bridge-host sightings in the latest scan."]
        lines.append("Top sites:")
        for row in sites[:8]:
            sample = ", ".join(row.get('sample_ports') or [])
            suffix = f" Sample ports: {sample}." if sample else ""
            lines.append(
                f"- {row.get('site_id')}: est={row.get('estimated_cpe_count', 0)} "
                f"(raw={row.get('raw_mac_count', 0)}, alt_dupes={row.get('alt_mac_duplicates', 0)}).{suffix}"
            )
        buildings = result.get('buildings') or []
        if buildings:
            lines.append("Top buildings:")
            for row in buildings[:5]:
                lines.append(f"- {row.get('building_id')}: {row.get('count')} sightings.")
        lines.append("Next useful questions:")
        top_site = sites[0].get('site_id')
        if top_site:
            lines.append(f"- what can you tell me about {top_site}?")
            lines.append(f"- find probable {vendor} cpes on {top_site}")
        return "\n".join(lines)

    if action == 'get_vendor_alt_mac_clusters':
        vendor = str(result.get('vendor') or '').lower()
        clusters = result.get('clusters') or []
        rollups = result.get('rollups') or []
        actionable = result.get('actionable_candidates') or []
        scope = result.get('building_id') or result.get('site_id') or 'this scope'
        if not clusters:
            return (
                f"Jake did not find any {vendor} alternate-MAC clusters at {scope}. "
                f"Raw {vendor} MACs={result.get('raw_mac_count', 0)}, estimated physical CPEs={result.get('estimated_cpe_count', 0)}."
            )
        lines = [
            f"{vendor.title()} alternate-MAC clusters at {scope}: {len(clusters)} clusters.",
            f"Raw {vendor} MACs={result.get('raw_mac_count', 0)}; estimated physical CPEs={result.get('estimated_cpe_count', 0)}.",
        ]
        if rollups:
            lines.append("Rolled-up views:")
            for row in rollups[:8]:
                macs = ", ".join(row.get('macs') or [])
                reason = ((row.get('relation') or {}).get('kind')) or 'related'
                edges = row.get('edge_sightings') or []
                uplinks = row.get('uplink_sightings') or []
                if edges:
                    edge_text = ", ".join(f"{item.get('identity')} {item.get('on_interface')}" for item in edges[:3])
                    lines.append(f"- {macs} ({reason}) edge={edge_text}")
                if uplinks:
                    uplink_text = ", ".join(f"{item.get('identity')} {item.get('on_interface')}" for item in uplinks[:3])
                    lines.append(f"  uplink repeats={uplink_text}")
        else:
            for row in clusters[:12]:
                macs = ", ".join(row.get('macs') or [])
                relation = row.get('relation') or {}
                reason = relation.get('kind') or 'related'
                lines.append(
                    f"- {row.get('identity')} {row.get('on_interface')} vlan {row.get('vid')}: "
                    f"{macs} ({reason})"
                )
        if actionable:
            lines.append("Actionable edge candidates:")
            for row in actionable[:6]:
                base = (
                    f"- {row.get('mac')} on {row.get('identity')} {row.get('on_interface')} vlan {row.get('vid')}: "
                    f"{row.get('candidate_type')}"
                )
                if row.get('has_arp'):
                    base += ", ARP/live L3 seen"
                if row.get('relation_kind'):
                    base += f", relation={row.get('relation_kind')}"
                if row.get('edge_sighting_count') is not None and row.get('uplink_sighting_count') is not None:
                    base += f", edge={row.get('edge_sighting_count')} uplink={row.get('uplink_sighting_count')}"
                lines.append(base)
                nearby = row.get('nearby_cloud_matches') or []
                if nearby:
                    nearby_text = ", ".join(
                        f"{item.get('network_name') or item.get('mac')} ({item.get('mac_relation')})"
                        for item in nearby[:2]
                    )
                    lines.append(f"  nearby cloud-known relation={nearby_text}")
                lines.append(f"  next step: {row.get('next_step')}")
        lines.append("Next useful questions:")
        first = actionable[0] if actionable else clusters[0]
        if first.get('identity'):
            lines.append(f"- how is {first.get('identity')}?")
        first_mac = first.get('mac') or first.get('primary_mac')
        if first_mac:
            lines.append(f"- show cpe state for {first_mac}")
        return "\n".join(lines)

    if action == 'capture_operator_note':
        return f"Saved operator note to {result.get('path')}."

    if action == 'get_vilo_server_info':
        return (
            f"Vilo API configured={result.get('configured')} "
            f"base_url={result.get('base_url')} "
            f"token_cached={result.get('has_access_token')}."
        )

    if action == 'get_vilo_inventory':
        data = result.get('data') or {}
        rows = data.get('device_list') or []
        activated = sum(1 for row in rows if str(row.get('status') or '').lower() == 'activated')
        return f"Vilo inventory returned {len(rows)} devices out of total_count {data.get('total_count', 0)}. This page has {activated} activated and {len(rows) - activated} non-activated devices."

    if action == 'get_vilo_subscribers':
        data = result.get('data') or {}
        rows = data.get('user_list') or data.get('subscriber_list') or []
        return f"Vilo subscribers returned {len(rows)} subscribers out of total_count {data.get('total_count', 0)}."

    if action == 'get_vilo_networks':
        data = result.get('data') or {}
        rows = data.get('network_list') or []
        online = sum(1 for row in rows if int(row.get('network_status') or 0) == 1)
        return f"Vilo networks returned {len(rows)} networks out of total_count {data.get('total_count', 0)}. This page has {online} online-status and {len(rows) - online} offline-status networks."

    if action == 'get_vilo_devices':
        data = result.get('data') or {}
        return f"Vilo device detail returned {len(data.get('vilo_info_list') or [])} devices for network {query or ''}".strip()

    if action == 'get_vilo_target_summary':
        if not result.get('found'):
            needle = (
                (result.get('query') or {}).get('network_name')
                or (result.get('query') or {}).get('network_id')
                or (result.get('query') or {}).get('mac')
                or query
            )
            lines = [f"I could not match `{needle}` to a live Vilo cloud object or inventory device."]
            nearby = result.get('nearby_mac_candidates') or []
            nearby_devices = result.get('nearby_device_candidates') or []
            if nearby:
                close = nearby[0]
                if int(close.get('mac_delta') or 999999) == 1:
                    location = " ".join(
                        part for part in [str(close.get('identity') or '').strip(), str(close.get('on_interface') or '').strip()] if part
                    ).strip()
                    lines.append(
                        f"Strong hint: a Vilo MAC exactly one value away, `{close.get('mac')}`, is still being seen"
                        f"{' at ' + location if location else ''}."
                        " That usually means wrong-port patching, WAN/LAN bridging leakage, or the expected unit being mislabeled by one MAC."
                    )
                else:
                    lines.append(
                        "Nearby Vilo MACs with very small address deltas are still being seen, so do not assume the device is simply gone."
                    )
            if nearby_devices:
                close = nearby_devices[0]
                lines.append(
                    f"Cloud-device hint: adjacent Vilo MAC `{close.get('mac')}` exists on network "
                    f"`{close.get('network_name') or close.get('network_id')}` as "
                    f"`{close.get('vilo_name') or 'unnamed'}`"
                    f"{f' local_ip={close.get('ip')}' if close.get('ip') else ''}"
                    f"{f' fw={close.get('firmware_ver')}' if close.get('firmware_ver') else ''}."
                )
                lines.append(
                    "That usually means this MAC is an alternate interface identity of a known Vilo or a bridged WAN/LAN side, not a brand-new separate unit."
                )
            lines.append("Next useful questions:")
            lines.append("- vilo networks")
            lines.append("- which sites have vilos?")
            lines.append("- find probable vilo cpes on 000007")
            return "\n".join(lines)
        network = result.get('network') or {}
        inventory = result.get('inventory') or {}
        devices = result.get('devices') or []
        placement = result.get('placement_hint') or {}
        status_raw = network.get('network_status')
        status_label = 'online' if int(status_raw or 0) == 1 else 'offline'
        allow_internet = network.get('allow_internet_access')
        allow_label = None
        if allow_internet is not None:
            allow_label = 'yes' if str(allow_internet).strip() in {'1', 'true', 'True'} else 'no'
        lines = [f"Vilo summary: {network.get('network_name') or inventory.get('device_mac') or query}."]
        if network.get('network_id'):
            lines.append(f"Network ID: {network.get('network_id')}.")
        if network.get('main_vilo_mac') or inventory.get('device_mac'):
            lines.append(f"Main MAC: {network.get('main_vilo_mac') or inventory.get('device_mac')}.")
        if inventory.get('device_sn'):
            lines.append(f"Serial: {inventory.get('device_sn')}.")
        if network:
            lines.append(
                f"Cloud state: status={status_label}, WAN={network.get('wan_ip_address') or 'none'}, public={network.get('public_ip_address') or 'none'}."
            )
            extra = []
            if allow_label is not None:
                extra.append(f"internet_access={allow_label}")
            if network.get('installer'):
                extra.append(f"installer={network.get('installer')}")
            if network.get('isp_app_account'):
                extra.append(f"isp_app_account={network.get('isp_app_account')}")
            if network.get('time_created'):
                extra.append(f"created={network.get('time_created')}")
            if network.get('subscriber_id') or network.get('user_email'):
                extra.append(
                    f"subscriber_id={network.get('subscriber_id') or 'none'} user_email={network.get('user_email') or 'none'}"
                )
            else:
                extra.append("subscriber_binding=blank")
            lines.append("Network detail: " + ", ".join(extra) + ".")
        if devices:
            main = devices[0]
            lines.append(
                f"Device detail: model={main.get('vilo_model') or '?'}, fw={main.get('firmware_ver') or '?'}, mgmt_ip={main.get('ip') or 'none'}, signal={main.get('signal')}, online_clients={main.get('device_online_num')}."
            )
            device_extra = []
            if main.get('connection_type') is not None:
                device_extra.append(f"connection_type={main.get('connection_type')}")
            if main.get('vilo_status') is not None:
                device_extra.append(f"vilo_status={main.get('vilo_status')}")
            if main.get('time_created'):
                device_extra.append(f"created={main.get('time_created')}")
            if main.get('is_main') is not None:
                device_extra.append(f"is_main={main.get('is_main')}")
            if device_extra:
                lines.append("Device flags: " + ", ".join(device_extra) + ".")
        label_candidates = result.get('label_candidates') or []
        if label_candidates:
            top = label_candidates[0]
            rendered = []
            if top.get('building_id'):
                rendered.append(f"building={top.get('building_id')}")
            if top.get('unit'):
                rendered.append(f"unit={top.get('unit')}")
            if top.get('address_text'):
                rendered.append(f"address='{top.get('address_text')}'")
            rendered.append(f"source={top.get('source')}")
            lines.append("Best label candidate: " + ", ".join(rendered) + ".")
            if len(label_candidates) > 1:
                lines.append(
                    "Alternate label hints: " +
                    ", ".join(
                        f"{item.get('raw')} ({item.get('source')})"
                        for item in label_candidates[1:4]
                    ) +
                    "."
                )
        local_plane = result.get('local_control_plane') or {}
        if local_plane.get('ip'):
            line = f"Local control plane: ip={local_plane.get('ip')}"
            if local_plane.get('live_arp_mac'):
                line += f", live_arp_mac={local_plane.get('live_arp_mac')}"
            line += "."
            lines.append(line)
        shared = local_plane.get('shared_cloud_candidates') or []
        if shared:
            summary = ", ".join(
                f"{row.get('network_name') or row.get('network_id')} ({row.get('mac')})"
                for row in shared[:3]
            )
            lines.append(
                "Shared-IP cloud residue: the same local control IP is also associated to adjacent offline Vilo cloud objects: "
                f"{summary}."
            )
            lines.append(
                "Jake should read that as stale duplicate onboarding state or alternate-interface MAC drift, not as proof that each MAC is a separate healthy deployed unit."
            )
        if placement.get('identity'):
            lines.append(f"Latest physical hint: {placement.get('identity')} {placement.get('on_interface')} VLAN {placement.get('vid')}.")
        bridge = (result.get('trace') or {}).get('bridge_hosts') or {}
        if bridge.get('reason'):
            lines.append(f"Trace note: {bridge.get('reason')}")
        lines.append(f"Likely failure domain: {result.get('likely_issue')}.")
        lines.append(str(result.get('likely_reason') or '').strip())
        nearby = result.get('nearby_mac_candidates') or []
        if nearby:
            top = nearby[0]
            if int(top.get('mac_delta') or 999999) == 1:
                location = " ".join(
                    part for part in [str(top.get('identity') or '').strip(), str(top.get('on_interface') or '').strip()] if part
                ).strip()
                lines.append(
                    f"Close-MAC check: `{top.get('mac')}` is exactly one MAC away"
                    f"{' and is seen at ' + location if location else ''}."
                    " Jake should treat that as a likely wrong-port, wrong-label, or bridged WAN/LAN clue rather than random noise."
                )
        nearby_devices = result.get('nearby_device_candidates') or []
        if nearby_devices:
            top = nearby_devices[0]
            lines.append(
                f"Cloud-adjacent clue: `{top.get('mac')}` exists in Vilo cloud on "
                f"`{top.get('network_name') or top.get('network_id')}`"
                f"{f' local_ip={top.get('ip')}' if top.get('ip') else ''}"
                f"{f' fw={top.get('firmware_ver')}' if top.get('firmware_ver') else ''}."
            )
        lines.append("Next useful questions:")
        mac = network.get('main_vilo_mac') or inventory.get('device_mac')
        if mac:
            lines.append(f"- trace MAC {mac}")
            lines.append(f"- what is this mac doing: {mac}")
        if placement.get('identity'):
            lines.append(f"- how is {placement.get('identity')}?")
        if placement.get('building_id'):
            lines.append(f"- what can you tell me about {placement.get('building_id')}?")
        else:
            lines.append("- which sites have vilos?")
        return "\n".join(lines)

    if action == 'get_transport_radio_summary':
        if not result.get('found'):
            needle = (
                (result.get('query') or {}).get('name')
                or (result.get('query') or {}).get('ip')
                or (result.get('query') or {}).get('mac')
                or (result.get('query') or {}).get('query')
                or query
            )
            lines = [f"I could not match `{needle}` to a known Cambium or Siklu radio in the local transport scan."]
            lines.append("Next useful questions:")
            lines.append("- which cambium radios have issues?")
            lines.append("- which siklu links look unstable?")
            lines.append("- what can you tell me about 000007?")
            return "\n".join(lines)
        row = result.get('radio') or {}
        vendor = str(result.get('vendor') or row.get('type') or '?')
        lines = [f"Radio summary: {row.get('name')}."]
        lines.append(f"Vendor/model: {vendor} / {row.get('model') or '?'}.")
        if row.get('ip'):
            lines.append(f"Management IP: {row.get('ip')}.")
        if row.get('location'):
            lines.append(f"Location: {row.get('location')}.")
        if result.get('site_id'):
            lines.append(f"Site hint: {result.get('site_id')}.")
        lines.append(f"Scan status: {row.get('status')}.")
        if vendor == 'cambium':
            device = row.get('device_info') or {}
            if device:
                lines.append(
                    f"Cambium role: {device.get('type') or '?'}, fw={device.get('fwVersion') or device.get('swVer') or '?'}, uptime={device.get('uptime')}, reboot_reason={device.get('lastRebootReason') or '?'}, bridge={device.get('l2bridge') or '?' }."
                )
            else:
                source_text = ', '.join(row.get('sources') or []) if isinstance(row.get('sources'), list) else 'site inventory'
                lines.append(f"Cambium evidence source: {source_text}.")
            peers = result.get('peer_names') or []
            if peers:
                lines.append(f"Known radio peers: {', '.join(peers[:6])}.")
            lines.append("Live RF note: cnWave exporter RF metrics are not available on this host right now, so Jake cannot prove RSSI or alignment from live counters.")
        elif vendor == 'siklu':
            flags = ((row.get('log_analysis') or {}).get('flags')) or {}
            lines.append(
                f"Siklu log signals: modulation_changes={flags.get('modulation_change', 0)}, eth_link_down={flags.get('eth_link_down')}, eth_link_up={flags.get('eth_link_up')}, reset_cause={flags.get('reset_cause')}."
            )
        lines.append(f"Likely failure domain: {result.get('likely_issue')}.")
        lines.append(str(result.get('likely_reason') or '').strip())
        lines.append("Next useful questions:")
        if row.get('ip'):
            lines.append(f"- what can you tell me about {row.get('ip')}?")
        if result.get('site_id'):
            lines.append(f"- what can you tell me about {result.get('site_id')}?")
        if vendor == 'cambium':
            lines.append("- which cambium radios have issues?")
        elif vendor == 'siklu':
            lines.append("- which siklu links look unstable?")
        return "\n".join(lines)

    if action == 'get_transport_radio_issues':
        lines = [f"Transport radio issue summary: vendor={result.get('vendor')}, radios_scoped={result.get('radio_count')}."]
        bad = result.get('bad_status') or []
        if bad:
            lines.append("Bad-status radios:")
            for row in bad[:8]:
                lines.append(f"- {row.get('name')} ({row.get('type')}) status={row.get('status')} ip={row.get('ip') or 'no-ip'}")
        siklu = result.get('siklu_unstable') or []
        if siklu:
            lines.append("Most unstable Siklu links:")
            for row in siklu[:5]:
                lines.append(f"- {row.get('name')}: modulation_changes={row.get('modulation_changes')} flags={row.get('flags')}")
        lines.append("Next useful questions:")
        if bad:
            lines.append(f"- what is going on with {bad[0].get('name')}?")
        if siklu:
            lines.append(f"- what is going on with {siklu[0].get('name')}?")
        if result.get('site_id'):
            lines.append(f"- what can you tell me about {result.get('site_id')}?")
        else:
            lines.append("- what can you tell me about 000007?")
        return "\n".join(lines)

    if action == 'get_site_historical_evidence':
        site_id = result.get('site_id') or '?'
        lines = [f"Historical evidence for {site_id}."]
        lines.append(
            f"Current archived signal mix: optical_alerts={result.get('optical_alert_count', 0)}, "
            f"radio_alerts={result.get('radio_alert_count', 0)}, flap_ports={result.get('flap_port_count', 0)}."
        )
        optical_by_olt = result.get('optical_alerts_by_olt') or {}
        if optical_by_olt:
            rendered = ", ".join(f"{olt}={count}" for olt, count in list(optical_by_olt.items())[:8])
            lines.append(f"Optical alert spread by OLT: {rendered}.")
        radio_status = result.get('radio_status_counts') or {}
        if radio_status:
            rendered = ", ".join(f"{status}={count}" for status, count in radio_status.items())
            lines.append(f"Radio status history hints: {rendered}.")
        no_ip = result.get('radios_without_management_ip') or []
        if no_ip:
            lines.append(f"Radios missing management IP in archived inventory: {', '.join(no_ip[:6])}.")
        syslog_summary = result.get('syslog_summary') or {}
        if syslog_summary.get('available'):
            lines.append(
                f"Local syslog ingestion: {syslog_summary.get('event_count', 0)} events from {syslog_summary.get('configured_dir')}."
            )
            by_vendor = syslog_summary.get('by_vendor') or {}
            if by_vendor:
                rendered = ", ".join(f"{vendor}={count}" for vendor, count in by_vendor.items())
                lines.append(f"Syslog vendor spread: {rendered}.")
        flap_counts = result.get('flap_counts_by_building') or {}
        if flap_counts:
            rendered = ", ".join(f"{building}={count}" for building, count in list(flap_counts.items())[:8])
            lines.append(f"Flap-history concentration: {rendered}.")
        notable = [row for row in (result.get('transport_history') or []) if row.get('likely_issue') not in {None, 'unknown', 'no_live_rf_stats', 'no_major_recent_signal'}]
        if notable:
            lines.append("Archived transport clues:")
            for row in notable[:5]:
                lines.append(f"- {row.get('name')}: {row.get('likely_issue')} ({row.get('likely_reason')})")
        field_evidence = [row for row in (result.get('field_evidence') or []) if row.get('matched')]
        if field_evidence:
            lines.append("Relevant saved artifacts:")
            for row in field_evidence[:5]:
                lines.append(f"- {row.get('path')}")
        changelogs = result.get('netbox_changelogs') or {}
        if changelogs.get('configured'):
            if changelogs.get('available'):
                lines.append(f"NetBox changelog sample count: {changelogs.get('count', 0)}.")
            else:
                lines.append(f"NetBox changelog note: {changelogs.get('error') or 'configured but unavailable from this host.'}")
        lines.append("Next useful questions:")
        lines.append(f"- at {site_id} what is probably unrelated noise versus the real issue?")
        lines.append(f"- which cambium radios have issues at {site_id}?")
        lines.append(f"- what can you tell me about {site_id}?")
        return "\n".join(lines)

    if action == 'get_site_syslog_summary':
        site_id = result.get('site_id') or '?'
        if not result.get('available'):
            return f"No local syslog directory is configured yet for {site_id}. Jake is ready to ingest archived logs from {result.get('configured_dir')} once files are placed there."
        lines = [f"Syslog summary for {site_id}: {result.get('event_count', 0)} ingested events."]
        if int(result.get('event_count') or 0) == 0 and int(result.get('total_event_count') or 0) > 0:
            lines.append(
                f"Jake does have {result.get('total_event_count')} ingested archival log events overall, but none are site-scoped to {site_id} yet."
            )
        by_vendor = result.get('by_vendor') or {}
        if by_vendor:
            lines.append("Events by vendor: " + ", ".join(f"{vendor}={count}" for vendor, count in by_vendor.items()) + ".")
        by_device = result.get('by_device') or {}
        if by_device:
            lines.append("Noisiest devices: " + ", ".join(f"{device}={count}" for device, count in list(by_device.items())[:6]) + ".")
        sample = result.get('sample') or []
        if sample:
            lines.append("Recent sample lines:")
            for row in sample[:4]:
                lines.append(f"- {row.get('timestamp') or '?'} {row.get('device_hint') or row.get('host')}: {row.get('message')}")
        lines.append("Next useful questions:")
        lines.append(f"- pull the logs for {site_id}")
        lines.append(f"- what can you tell me about {site_id}?")
        return "\n".join(lines)

    if action == 'get_dhcp_findings_summary':
        if not result.get('available'):
            return "Jake does not have a local DHCP relay-state snapshot loaded yet, so there is no grounded Option 82 finding summary to show."
        lines = [
            f"Local DHCP/Option 82 snapshot: {result.get('subscriber_count', 0)} modeled subscribers, {result.get('relay_count', 0)} relays, {result.get('finding_count', 0)} findings."
        ]
        sev = result.get('by_severity') or {}
        if sev:
            lines.append("Finding severity mix: " + ", ".join(f"{k}={v}" for k, v in sev.items()) + ".")
        for row in (result.get('findings') or [])[:5]:
            lines.append(f"- {row.get('severity')}: {row.get('title')} on {row.get('device')} | {row.get('evidence')}")
        lynxmsp = (result.get('lynxmsp_status') or {}).get('db') or {}
        if lynxmsp.get('configured') and not lynxmsp.get('available'):
            lines.append("Live customer-plan joins are still blocked because the local LynxMSP DB is present but empty.")
        lines.append("Next useful questions:")
        lines.append("- what do we know about DHCP-RELAY-KH-02?")
        lines.append("- break down circuit-id khub/ge-0/0/22:1117")
        lines.append("- find subscriber 84:2A:FD:19:22:11 from the dhcp snapshot")
        return "\n".join(lines)

    if action == 'get_dhcp_relay_summary':
        relay = result.get('relay') or {}
        query_name = result.get('query') or relay.get('name') or 'unknown relay'
        if not result.get('available'):
            return f"Jake does not have a local DHCP relay-state snapshot loaded yet, so it cannot summarize {query_name}."
        if not relay:
            return f"Jake could not find relay {query_name} in the local DHCP relay-state snapshot."
        lines = [f"{relay.get('name')} is a DHCP relay at {relay.get('site')} on access node {relay.get('accessNode')} ({relay.get('mgmtIp')})."]
        lines.append(f"Current relay state: {relay.get('status')} | Option 82 policy: {relay.get('option82Policy')}.")
        lines.append(f"Modeled subscribers on this relay: {result.get('subscriber_count', 0)}.")
        subs = result.get('subscribers') or []
        if subs:
            first = subs[0]
            lines.append(f"Sample subscriber: {first.get('name')} ({first.get('id')}) vlan {first.get('vlan')} ip {first.get('ipv4')} circuit {first.get('circuitId')}.")
        findings = result.get('findings') or []
        if findings:
            lines.append("Related findings:")
            for row in findings[:3]:
                lines.append(f"- {row.get('severity')}: {row.get('title')} | {row.get('evidence')}")
        lines.append("Next useful questions:")
        if subs:
            lines.append(f"- break down circuit-id {subs[0].get('circuitId')}")
        lines.append(f"- find subscriber on relay {relay.get('name')}")
        return "\n".join(lines)

    if action == 'get_dhcp_circuit_summary':
        sub = result.get('subscriber') or {}
        decoded = result.get('decoded_path') or {}
        query_circuit = result.get('query') or 'unknown circuit'
        if not result.get('available'):
            return f"Jake does not have a local DHCP relay-state snapshot loaded yet, so it cannot decode {query_circuit}."
        lines = [f"Circuit-ID {query_circuit} breakdown:"]
        lines.append(
            f"- path tokens: site={decoded.get('site_token') or '?'} interface={decoded.get('interface_scope') or '?'} port={decoded.get('port_token') or '?'} subscriber={decoded.get('subscriber_token') or '?'}"
        )
        if sub:
            lines.append(
                f"- subscriber: {sub.get('name')} ({sub.get('id')}) status={sub.get('status')} plan={sub.get('plan')} ip={sub.get('ipv4')} mac={sub.get('cpeMac')}"
            )
            lines.append(
                f"- relay path: relay={sub.get('relay')} remote-id={sub.get('remoteId')} vlan={sub.get('vlan')} site={sub.get('site')}"
            )
        relay = result.get('relay') or {}
        if relay:
            lines.append(f"- access node: {relay.get('accessNode')} mgmt={relay.get('mgmtIp')} option82={relay.get('option82Policy')}")
        lynxmsp = (result.get('lynxmsp_status') or {}).get('db') or {}
        if lynxmsp.get('configured') and not lynxmsp.get('available'):
            lines.append("- final customer/service-plan joins beyond the snapshot are still blocked by the empty LynxMSP DB on this host.")
        lines.append("Next useful questions:")
        if sub.get('cpeMac'):
            lines.append(f"- find subscriber {sub.get('cpeMac')} from the dhcp snapshot")
        if sub.get('relay'):
            lines.append(f"- what do we know about {sub.get('relay')}?")
        return "\n".join(lines)

    if action == 'get_dhcp_subscriber_summary':
        if not result.get('available'):
            return "Jake does not have a local DHCP relay-state snapshot loaded yet, so it cannot correlate that lease/subscriber identity."
        matches = result.get('subscribers') or []
        if not matches:
            return "Jake could not match that DHCP/Option 82 identity in the local relay-state snapshot."
        sub = matches[0]
        lines = [
            f"DHCP subscriber match: {sub.get('name')} ({sub.get('id')}) at {sub.get('site')}.",
            f"Status/plan: {sub.get('status')} / {sub.get('plan')}.",
            f"Lease identity: ip={sub.get('ipv4')} mac={sub.get('cpeMac')} vlan={sub.get('vlan')} circuit={sub.get('circuitId')} remote-id={sub.get('remoteId')} relay={sub.get('relay')}.",
        ]
        relay = result.get('relay') or {}
        if relay:
            lines.append(f"Upstream relay: {relay.get('accessNode')} ({relay.get('mgmtIp')}) with policy {relay.get('option82Policy')}.")
        findings = result.get('related_findings') or []
        if findings:
            lines.append("Related findings:")
            for row in findings[:3]:
                lines.append(f"- {row.get('severity')}: {row.get('title')} | {row.get('evidence')}")
        lynxmsp = (result.get('lynxmsp_status') or {}).get('db') or {}
        if lynxmsp.get('configured') and not lynxmsp.get('available'):
            lines.append("Splynx/LynxMSP customer-plan joins are still blocked on this host because the local DB exists but has no populated customer rows.")
        lines.append("Next useful questions:")
        if sub.get('relay'):
            lines.append(f"- what do we know about {sub.get('relay')}?")
        if sub.get('circuitId'):
            lines.append(f"- break down circuit-id {sub.get('circuitId')}")
        return "\n".join(lines)

    if action == 'get_live_dhcp_lease_summary':
        if not result.get('available') and not result.get('lease_count'):
            return "Jake does not currently have a reachable live DHCP lease source on this host. LynxMSP API and DB paths were checked, but no matching live leases were returned."
        lines = [f"Live DHCP lease evidence: source={result.get('source')} leases={result.get('lease_count', 0)}."]
        if result.get('site_id'):
            lines.append(f"Site scope: {result.get('site_id')}.")
        if result.get('base_detail') or result.get('api_detail'):
            lines.append(f"Source detail: {result.get('base_detail') or result.get('api_detail')}.")
        for row in (result.get('leases') or [])[:8]:
            lines.append(f"- ip={row.get('address') or row.get('ip_address') or row.get('active_address') or row.get('activeAddress')} mac={row.get('mac_address') or row.get('macAddress') or row.get('active_mac_address') or row.get('activeMacAddress')} server={row.get('server') or row.get('active_server') or row.get('activeServer')} status={row.get('status')}")
        lines.append("Next useful questions:")
        lines.append("- find subscriber 84:2A:FD:19:22:11 from the dhcp snapshot")
        if result.get('site_id'):
            lines.append(f"- do we have option 82 drift anywhere near {result.get('site_id')}?")
        return "\n".join(lines)

    if action == 'get_live_splynx_online_summary':
        if not result.get('available'):
            return f"Jake does not currently have a reachable live Splynx online-customer source on this host. Detail: {result.get('detail') or 'not configured'}."
        lines = [f"Live Splynx online evidence: {result.get('online_count', 0)} matching online rows."]
        if result.get('site_id'):
            lines.append(f"Site hint: {result.get('site_id')}.")
        for row in (result.get('rows') or [])[:8]:
            lines.append(f"- {row.get('login') or row.get('name') or row.get('id')} ip={row.get('ip') or row.get('framed_ip') or row.get('framed_ip_address')} status={row.get('status') or 'online'}")
        lines.append("Next useful questions:")
        lines.append("- how many customers are online here?")
        lines.append("- does this match what we see elsewhere?")
        return "\n".join(lines)

    if action == 'get_live_source_readiness':
        lines = ["Live source readiness:"]
        for name in ('routeros', 'dhcp', 'splynx', 'cnwave', 'olt', 'syslog'):
            row = result.get(name) or {}
            bits = [f"configured={row.get('configured', False)}", f"available={row.get('available', False)}"]
            if row.get('mikrotik_count') is not None:
                bits.append(f"mikrotik_count={row.get('mikrotik_count')}")
            if row.get('device_count') is not None:
                bits.append(f"device_count={row.get('device_count')}")
            if row.get('event_count') is not None:
                bits.append(f"event_count={row.get('event_count')}")
            if row.get('detail'):
                bits.append(str(row.get('detail')))
            if row.get('api_detail'):
                bits.append(str(row.get('api_detail')))
            lines.append(f"- {name}: {' | '.join(bits[:5])}")
        lines.append("Next useful questions:")
        lines.append("- what live dhcp leases do we have for 000007 right now?")
        lines.append("- run live routeros resource on 000007.R1")
        lines.append("- show ont info for Savoy1Unit3N")
        lines.append("- show live cnwave rf metrics for Savoy")
        return "\n".join(lines)

    if action == 'run_live_olt_read':
        if not result.get('available'):
            return f"Jake could not run that live OLT read. {result.get('error') or 'OLT access is not ready.'}"
        lines = [f"Live OLT read: {result.get('olt_name') or result.get('host') or result.get('olt_ip')}."]
        for row in (result.get('outputs') or [])[:3]:
            lines.append(f"Command: {row.get('command')}")
            lines.append(str(row.get('output') or '')[:1200])
        return "\n".join(lines)

    if action == 'get_live_olt_ont_summary':
        resolved = result.get('resolved') or {}
        if not result.get('available'):
            base = "Jake could not run that live OLT ONU read."
            if resolved.get('olt_name') or resolved.get('olt_ip'):
                base += f" Resolved path: {resolved.get('olt_name') or resolved.get('olt_ip')} {resolved.get('pon') or '?'} ONU {resolved.get('onu_id') or '?'}."
            return f"{base} {result.get('error') or 'OLT access is not ready.'}"
        lines = []
        live_resolution = result.get('live_resolution') or {}
        parsed = result.get('parsed_row') or {}
        if parsed:
            olt_name = resolved.get('olt_name') or resolved.get('olt_ip')
            pon = parsed.get('pon') or resolved.get('pon')
            onu_id = parsed.get('onu_id') or resolved.get('onu_id') or '?'
            description = str(parsed.get('description') or '').strip()
            serial = str(parsed.get('serial') or '').strip()
            online_status = str(parsed.get('online_status') or 'unknown').strip()
            if online_status.lower() != 'online':
                prefix = "⚠ "
                lines.append(
                    f"{prefix}OLT correlation: {olt_name} {pon} ONU {onu_id}"
                    f"{f' ({description})' if description else ''} is {online_status}. "
                    f"{f'Serial: {serial}. ' if serial else ''}"
                    "This ONU is the physical endpoint — it is currently offline and needs investigation."
                )
            else:
                lines.append(
                    f"OLT correlation: {olt_name} {pon} ONU {onu_id}"
                    f"{f' ({description})' if description else ''} is online. "
                    f"{f'Serial: {serial}.' if serial else ''}"
                )
            lines.append(
                "Current state: "
                f"online={parsed.get('online_status')}, "
                f"admin={parsed.get('admin_status')}, "
                f"active={parsed.get('active_status')}, "
                f"config={parsed.get('config_status')}, "
                f"match={parsed.get('match_status')}."
            )
        else:
            lines.extend(
                [
                    f"Live OLT ONU read: {resolved.get('olt_name') or resolved.get('olt_ip')} {resolved.get('pon')} ONU {resolved.get('onu_id') or '?'}.",
                    f"Command: {result.get('command')}",
                ]
            )
        if live_resolution.get('scan_command'):
            lines.append(f"Live serial resolution: {live_resolution.get('scan_command')}")
        live = result.get('live') or {}
        for row in (live.get('outputs') or [])[:2]:
            lines.append(str(row.get('output') or '')[:1600])
        lines.append("Next useful questions:")
        lines.append("- what can you tell me about this ONU?")
        lines.append("- did this ONU flap recently?")
        return "\n".join(lines)

    if action == 'get_live_olt_log_summary':
        resolved = result.get('resolved') or {}
        if not result.get('available'):
            base = "Jake could not pull live OLT logs."
            if resolved.get('olt_name') or resolved.get('olt_ip'):
                base += f" Resolved OLT: {resolved.get('olt_name') or resolved.get('olt_ip')}."
            return f"{base} {result.get('error') or 'OLT access is not ready.'}"
        lines = [
            f"Live OLT log read: {resolved.get('olt_name') or resolved.get('olt_ip')}.",
            f"Command: {result.get('command')}",
        ]
        if result.get('empty'):
            lines.append("The OLT reports that there are no log records in flash for this query.")
        live = result.get('live') or {}
        for row in (live.get('outputs') or [])[:2]:
            text = str(row.get('output') or '').strip()
            if text:
                lines.append(text[:1800])
        lines.append("Next useful questions:")
        lines.append("- did this ONU flap recently?")
        lines.append("- show ont info for this subscriber")
        return "\n".join(lines)

    if action == 'get_tp_link_subscriber_join':
        resolved = result.get('resolved') or {}
        lines = ["TP-Link subscriber/ONU join attempt:"]
        if resolved.get('network_name'):
            lines.append(f"- subscriber: {resolved.get('network_name')}")
        if resolved.get('serial'):
            lines.append(f"- TP-Link CPE serial: {resolved.get('serial')}")
        if resolved.get('mac'):
            lines.append(f"- TP-Link CPE MAC: {resolved.get('mac')}")
        if resolved.get('site_id'):
            lines.append(f"- site: {resolved.get('site_id')}")
        local_row = result.get('local_row') or {}
        if local_row:
            lines.append(f"- local export: deviceId={local_row.get('deviceId') or '?'} topoId={local_row.get('topoId') or '?'} wanIp={local_row.get('wanIp') or '?'}")
        runtime = result.get('tauc_runtime') or {}
        devices_tr = (runtime.get('devices_tr') or {}).get('result') or []
        if devices_tr:
            row = devices_tr[0] or {}
            lines.append(f"- TAUC runtime device: {row.get('model')} {row.get('status')} ip={row.get('ip')} mac={row.get('mac')} sn={row.get('sn')}")
        waninfo = ((runtime.get('waninfo') or {}).get('result') or {}).get('wanList') or []
        if waninfo:
            wan = waninfo[0] or {}
            dyn = ((wan.get('dynamicIpInfo') or {}).get('ipv4Info') or {})
            lines.append(f"- TAUC WAN state: {wan.get('status')} {dyn.get('ip') or ''} gw={dyn.get('gateway') or ''} vlan={((wan.get('dynamicIpInfo') or {}).get('vlan'))}")
        mac_probe = result.get('olt_mac_probe') or {}
        hits = mac_probe.get('hits') or []
        variants = result.get('mac_variants') or []
        if variants:
            lines.append(f"- OLT MAC probe variants: {', '.join(variants[:9])}")
        if hits:
            lines.append("- OLT MAC-table hits:")
            for row in hits[:6]:
                lines.append(f"  {row.get('olt_name')} {row.get('mac')}: {compact(str(row.get('text') or ''), 240)}")
        else:
            lines.append("- OLT MAC-table result: no direct HC220 MAC or adjacent-MAC hit on the site OLTs.")
            lines.append("- interpretation: this OLT path is not exposing the TP-Link WAN-side MAC in the bridge table for this subscriber, so the join is still blocked at the OLT edge.")
        if result.get('tauc_runtime_error'):
            lines.append(f"- TAUC runtime error: {result.get('tauc_runtime_error')}")
        lines.append("Next useful questions:")
        if resolved.get('site_id'):
            lines.append(f"- show ont info for {resolved.get('site_id')}")
        if resolved.get('mac'):
            lines.append(f"- show cpe state for {resolved.get('mac')}")
        return "\n".join(lines)

    if action == 'get_live_cnwave_rf_summary':
        if not result.get('available'):
            return "Jake does not currently have usable live cnWave RF metrics on this host."
        lines = [f"Live cnWave RF evidence: {result.get('metric_row_count', 0)} RF-related metric rows."]
        metric_names = result.get('metric_names') or []
        if metric_names:
            lines.append(f"Observed metric names: {', '.join(metric_names[:12])}.")
        devices = result.get('devices') or []
        if devices:
            lines.append("Device summaries:")
            for row in devices[:6]:
                metrics = row.get('metrics') or {}
                compact_metrics = ", ".join(f"{k}={v}" for k, v in list(metrics.items())[:6])
                lines.append(f"- {row.get('name')}: {compact_metrics}")
        lines.append("Next useful questions:")
        lines.append("- which cambium radios have issues?")
        if result.get('site_id'):
            lines.append(f"- what is going on at {result.get('site_id')}?")
        return "\n".join(lines)

    if action == 'run_live_routeros_read':
        if not result.get('available'):
            return f"Jake could not run that live RouterOS read. {result.get('error') or 'The device is not present in ssh_mcp inventory/allowlist or credentials are missing.'}"
        lines = [
            f"Live RouterOS read: {result.get('device_name')} intent={result.get('intent')}.",
            f"Command: {result.get('rendered_command')}",
            f"Execution status: {result.get('status')} | proposal_id={result.get('proposal_id')}.",
        ]
        for row in (result.get('results') or [])[:4]:
            lines.append(f"- phase={row.get('phase')} exit={row.get('exit_code')}")
            stdout = str(row.get('stdout') or '').strip()
            stderr = str(row.get('stderr') or '').strip()
            if stdout:
                lines.append(stdout[:600])
            if stderr:
                lines.append(f"stderr: {stderr[:300]}")
        return "\n".join(lines)

    if action == 'get_live_rogue_dhcp_scan':
        if not result.get('available'):
            return f"Jake could not run that live rogue-DHCP scan. {result.get('error') or 'RouterOS live capture path is unavailable.'}"
        lines = [
            f"Live bounded DHCP capture on {result.get('device_name')} ({result.get('device_ip')}) interface {result.get('interface')} for {result.get('seconds')}s.",
            f"Packets captured: total={result.get('packet_count', 0)}, dhcp_like={result.get('dhcp_packet_count', 0)}, offer_like={result.get('offer_like_packet_count', 0)}, broadcasts={result.get('broadcast_count', 0)}.",
        ]
        talkers = result.get('dhcp_talkers') or []
        if talkers:
            lines.append("Top DHCP talkers:")
            for row in talkers[:5]:
                lines.append(f"- {row.get('mac')}: {row.get('packets')} packets")
        sample = result.get('sample') or []
        if sample:
            first = sample[0]
            lines.append(
                f"First sample: {first.get('src-mac')}:{first.get('src-port')} -> {first.get('dst-mac')}:{first.get('dst-port')} ({first.get('protocol') or first.get('ip-protocol')})."
            )
        lines.append("This is live packet evidence, not the artifact rogue-DHCP summary.")
        return "\n".join(lines)

    if action == 'get_live_capsman_summary':
        if not result.get('available'):
            return f"Live CAPsMAN summary is not available: {result.get('error')}"
        lines = [f"Live WiFi controller summary from {result.get('device_name')} ({result.get('target_ip')})."]
        capsman = result.get('capsman_manager') or {}
        wifi_cap = result.get('wifi_cap') or {}
        lines.append(
            f"CAPsMAN v1 manager rows: {capsman.get('row_count', 0)}. "
            f"WiFi CAP rows: {wifi_cap.get('row_count', 0)}."
        )
        if result.get('remote_cap_count') is not None:
            lines.append(f"Remote CAPs seen: {result.get('remote_cap_count')}.")
        if result.get('wifi_interface_count') is not None:
            lines.append(f"WiFi interfaces seen: {result.get('wifi_interface_count')}.")
        if capsman.get('sample'):
            lines.append("CAPsMAN manager sample:")
            lines.extend(f"- {row}" for row in (capsman.get('sample') or [])[:3])
        return "\n".join(lines)

    if action == 'get_live_wifi_registration_summary':
        if not result.get('available'):
            return f"Live WiFi registration summary is not available: {result.get('error')}"
        lines = [f"Live WiFi registration summary from {result.get('device_name')} ({result.get('target_ip')})."]
        lines.append(
            f"CAPsMAN v1 registrations: {result.get('capsman_registration_count', 0)}. "
            f"WiFi v2 registrations: {result.get('wifi_registration_count', 0)}."
        )
        sample = result.get('sample_clients') or []
        if sample:
            lines.append("Sample clients:")
            lines.extend(f"- {item}" for item in sample[:8])
        return "\n".join(lines)

    if action == 'get_live_wifi_provisioning_summary':
        if not result.get('available'):
            return f"Live WiFi provisioning summary is not available: {result.get('error')}"
        lines = [f"Live WiFi provisioning summary from {result.get('device_name')} ({result.get('target_ip')})."]
        lines.append(
            f"CAPsMAN provisioning rows: {result.get('capsman_provisioning_count', 0)}. "
            f"WiFi v2 provisioning rows: {result.get('wifi_provisioning_count', 0)}. "
            f"WiFi configuration rows: {result.get('wifi_configuration_count', 0)}."
        )
        sample = result.get('sample_rules') or []
        if sample:
            lines.append("Sample provisioning/config rows:")
            lines.extend(f"- {item}" for item in sample[:8])
        return "\n".join(lines)

    if action == 'get_site_radio_inventory':
        site_id = result.get('site_id') or '?'
        radios = result.get('radios') or []
        shared_pairs = result.get('shared_building_v2000_pairs') or []
        dn_radios = result.get('dn_radios') or []
        cn_count = int(result.get('cn_radio_count') or 0)
        alerts = result.get('active_radio_alerts') or []
        cnwave = (result.get('site_summary_hint') or {}).get('cnwave') or {}
        lines = [f"Radio inventory for {site_id}: {len(radios)} radio records across transport scan, NetBox, and alert evidence."]
        if dn_radios:
            dn = dn_radios[0]
            lines.append(f"Site radio topology hint: {site_id} has {cn_count} CN-class radios and {len(dn_radios)} DN-class radios. Primary DN: {dn.get('name')} at {dn.get('building_id')}.")
        if shared_pairs:
            lines.append("Shared-building V2000 pairs:")
            for pair in shared_pairs[:4]:
                ip_text = f" | IPs: {', '.join(pair.get('radio_ips') or [])}" if pair.get('radio_ips') else ""
                lines.append(f"- {pair.get('building_id')}: {', '.join(pair.get('radio_names') or [])}{ip_text}")
        else:
            sample = [str(row.get('name') or '') for row in radios[:6]]
            if sample:
                lines.append(f"Known radios: {', '.join(sample)}.")
        if alerts:
            lines.append("Active radio-related alerts:")
            for alert in alerts[:5]:
                lines.append(f"- {alert.get('summary')} (device={alert.get('name')}, severity={alert.get('severity') or '?'})")
        if cnwave.get('configured') and not cnwave.get('available'):
            lines.append("Live cnWave exporter note: configured but not returning usable site metrics from this host right now.")
        lower_query = query.lower()
        if any(token in lower_query for token in ('radio topology', 'which building is the dn', 'which buildings appear to be cns', 'fed from building')):
            if dn_radios:
                dn = dn_radios[0]
                lines.append(f"DN answer: building {dn.get('building_id')} hosts {dn.get('name')}.")
            cn_buildings = sorted({str(row.get('building_id') or '') for row in radios if 'v2000' in f"{row.get('name') or ''} {row.get('model') or ''}".lower() and row.get('building_id')})
            if cn_buildings:
                lines.append(f"CN buildings: {', '.join(cn_buildings)}.")
            if 'fed from building' in lower_query and dn_radios:
                lines.append(
                    "Inference: yes, Buildings 4, 5, and 6 are more likely intended to feed upstream toward the Building 3 DN than to behave like independent DN-class distribution nodes."
                )
        if any(token in lower_query for token in ('aux port', 'aux ports')):
            if shared_pairs:
                first = shared_pairs[0]
                lines.append(
                    f"Most likely pair for the aux-port complaint: {', '.join(first.get('radio_names') or [])} in building {first.get('building_id')}."
                )
            if dn_radios:
                lines.append(
                    f"Important topology note: the shared-building pair are V2000 client nodes, while the only DN-class radio currently known at {site_id} is {dn_radios[0].get('name')}."
                )
                lines.append(
                    "That means the complaint may be a role/topology expectation problem as much as a fault: two CNs are not the normal place to expect direct distribution-node behavior."
                )
            lines.append("Likely failure domain: local Ethernet handoff or VLAN mode mismatch on the radio-side port, not pure RF.")
            lines.append("What to check first:")
            lines.append("- Confirm both radios have Ethernet/AUX ports enabled and Layer 2 bridge mode enabled where required.")
            lines.append("- Confirm both sides agree on whether that port is a tagged trunk or an untagged/native management handoff.")
            lines.append("- If customer traffic rides that link too, treat it as tagged-only trunking; avoid native VLAN 10 behavior on one side and tagged VLAN 10 on the other.")
            lines.append("- Check for one side classifying untagged frames into management while the other side expects tagged VLANs. That causes management reachability without service traffic.")
            lines.append("- Verify the intended traffic path. If both units are CNs, confirm whether the design actually expects CN-to-CN local handoff or whether both should be feeding upstream toward the DN.")
            lines.append("- Check local cabling and port counters before blaming alignment. AUX-port failure with working management often points to L2 handoff mismatch, not beam alignment.")
        lines.append("Next useful questions:")
        lines.append(f"- which cambium radios have issues at {site_id}?")
        if shared_pairs:
            lines.append(f"- how is {shared_pairs[0].get('radio_names')[0]}?")
        lines.append(f"- what can you tell me about {site_id}?")
        return "\n".join(lines)

    if action == 'assess_site_incident':
        return str(result.get('summary') or '').strip()

    return json.dumps(result, indent=2)


def run_operator_query(ops: Any, query: str) -> dict[str, Any]:
    parsed = parse_operator_query(query)
    site_id = str(parsed.get('params', {}).get('site_id') or '').strip() or None
    site_profile = SITE_SERVICE_PROFILES.get(site_id) if site_id else None
    def assess_site_incident(site_id: str) -> dict[str, Any]:
        site = ops.get_site_summary(site_id, True)
        radios = ops.get_site_radio_inventory(site_id)
        history = ops.get_site_historical_evidence(site_id)
        active_alerts = site.get('active_alerts') or []
        def _extract_building_hint(text: str) -> str | None:
            value = str(text or "")
            match = re.search(r'positron0*([1-9]\d*)', value, re.I)
            if match:
                return match.group(1)
            match = re.search(r'building\s+([1-9]\d*)', value, re.I)
            if match:
                return match.group(1)
            match = re.search(r'\b(\d{6})\.(\d{3})\b', value)
            if match:
                return str(int(match.group(2)))
            return None

        optical_alerts = [
            a for a in active_alerts
            if str((a.get('labels') or {}).get('device_role') or '').lower() == 'onu'
            or 'onu' in str((a.get('annotations') or {}).get('summary') or '').lower()
        ]
        radio_alerts = [
            a for a in active_alerts
            if 'cambium' in str((a.get('labels') or {}).get('alertname') or '').lower()
            or 'cambium' in str((a.get('annotations') or {}).get('summary') or '').lower()
        ]
        ghn_alerts = [
            a for a in active_alerts
            if 'ghndown' in str((a.get('labels') or {}).get('alertname') or '').lower()
            or 'positron' in str((a.get('labels') or {}).get('name') or '').lower()
            or 'positron' in str((a.get('annotations') or {}).get('summary') or '').lower()
        ]
        shared_pairs = radios.get('shared_building_v2000_pairs') or []
        primary_pair = shared_pairs[0] if shared_pairs else None
        pair_names = set(primary_pair.get('radio_names') or []) if primary_pair else set()
        pair_rows = [r for r in (radios.get('radios') or []) if str(r.get('name') or '') in pair_names]
        pair_missing_ip = [str(r.get('name') or '') for r in pair_rows if not r.get('primary_ip')]
        pair_dn_count = sum(1 for r in pair_rows if 'v5000' in f"{r.get('name') or ''} {r.get('model') or ''}".lower())
        pair_cn_count = sum(1 for r in pair_rows if 'v2000' in f"{r.get('name') or ''} {r.get('model') or ''}".lower())
        online_count = int(((site.get('online_customers') or {}).get('count')) or 0)
        dn_radios = radios.get('dn_radios') or []
        ghn_by_building: dict[str, list[str]] = {}
        for alert in ghn_alerts:
            name = str((alert.get('labels') or {}).get('name') or (alert.get('annotations') or {}).get('summary') or '').strip()
            building_hint = _extract_building_hint(name)
            if building_hint:
                ghn_by_building.setdefault(building_hint, []).append(name)
        radio_by_building: dict[str, list[str]] = {}
        for alert in radio_alerts:
            name = str((alert.get('labels') or {}).get('name') or (alert.get('annotations') or {}).get('summary') or '').strip()
            building_hint = _extract_building_hint(name)
            if building_hint:
                radio_by_building.setdefault(building_hint, []).append(name)
        shared_building_outages = [
            {
                'building': building,
                'ghn_devices': sorted(set(ghn_by_building.get(building) or [])),
                'radio_devices': sorted(set(radio_by_building.get(building) or [])),
            }
            for building in sorted(set(ghn_by_building).intersection(radio_by_building), key=lambda x: int(x))
        ]

        lines = [f"Incident assessment for {site_id}."]
        lines.append(f"Current site state: {online_count} online customers, {len(optical_alerts)} ONU optical alerts, {len(radio_alerts)} active radio alerts.")
        if primary_pair:
            lines.append(f"Local radio complaint scope: building {primary_pair.get('building_id')} has shared V2000 pair {', '.join(primary_pair.get('radio_names') or [])}.")
        if dn_radios:
            lines.append(f"Radio topology: site has {int(radios.get('cn_radio_count') or 0)} CN-class radios and {len(dn_radios)} DN-class radios. Known DN: {dn_radios[0].get('name')}.")

        lines.append("Most likely causal issue:")
        if shared_building_outages:
            first = shared_building_outages[0]
            lines.append(f"- Building {first.get('building')} has both G.hn and radio faults at the same time: {', '.join(first.get('ghn_devices') or [])} and {', '.join(first.get('radio_devices') or [])}.")
            lines.append("- That pattern points to a shared building-path or power problem, not just a bad management IP on one Positron.")
            lines.append("- Treat the radio handoff, power, and local building distribution path as the first abnormal domain. The G.hn device is likely downstream impact, not the independent root cause.")
        elif primary_pair:
            lines.append("- The aux-port complaint is most likely a localized Building 4 Ethernet/L2 handoff problem, not a full-site outage.")
            if pair_cn_count >= 2 and pair_dn_count == 0:
                lines.append("- Both radios in the complained-of pair are CN-class V2000s. That makes a role/topology misunderstanding plausible if the team expects direct DN-style behavior between them.")
            if pair_missing_ip:
                lines.append(f"- One member of the pair is missing a management IP in NetBox: {', '.join(pair_missing_ip)}. That raises the chance of incomplete provisioning or stale inventory on that exact node.")
            lines.append("- The strongest technical hypothesis is AUX/Ethernet port disabled, bridge mode mismatch, or tagged-vs-native VLAN mismatch on the local radio-side handoff.")
        else:
            lines.append("- Jake does not have a confirmed shared-building pair, so the safest current hypothesis is a local radio-side L2 handoff problem.")

        lines.append("Probably unrelated or secondary noise:")
        if optical_alerts:
            olt_names = sorted({str((a.get('labels') or {}).get('olt_name') or '') for a in optical_alerts if (a.get('labels') or {}).get('olt_name')})
            lines.append(f"- The ONU optical alerts span multiple OLTs ({', '.join(olt_names[:6])}). That looks like ongoing subscriber optical noise across the site, not one clean explanation for a Building 4 aux-port complaint.")
        if radio_alerts:
            affected_radios = sorted({str((a.get('labels') or {}).get('name') or '') for a in radio_alerts if (a.get('labels') or {}).get('name')})
            if affected_radios:
                if shared_building_outages:
                    first = shared_building_outages[0]
                    lines.append(f"- The paired radio fault at Building {first.get('building')} is not background noise. It materially strengthens the case for a shared local outage domain there.")
                else:
                    lines.append(f"- There is an active Cambium radio-down alert on {affected_radios[0]}. Right now that is not the Building 4 pair, so treat it as separate until field evidence ties them together.")
        if online_count > 50:
            lines.append("- The site still shows substantial customer presence online, which argues against a site-wide router, upstream, or all-radios-down event.")
        if history.get('flap_port_count'):
            lines.append(f"- Archived flap evidence exists on {history.get('flap_port_count')} access ports. Treat it as background instability unless it clusters on the complained-of building.")
        syslog_summary = history.get('syslog_summary') or {}
        if syslog_summary.get('available') and int(syslog_summary.get('event_count') or 0) > 0:
            lines.append(f"- Local syslog history exists for this site ({syslog_summary.get('event_count')} events). Pull it before treating the current symptom set as the full story.")
        changelog_sample = ((history.get('netbox_changelogs') or {}).get('sample')) or []
        changed_names = sorted({
            str((row.get('changed_object') or {}).get('name') or '')
            for row in changelog_sample
            if (row.get('changed_object') or {}).get('name')
        })
        if changed_names:
            lines.append(f"- NetBox changelog history is active for this site. Recent touched objects include {', '.join(changed_names[:5])}.")

        lines.append("Technicians should check first:")
        lines.append("- Verify the intended design: should the two Building 4 V2000s pass traffic to each other at all, or should each be feeding upstream toward the Building 3 V5000 DN?")
        lines.append("- Check both radios for Ethernet/AUX port enablement and confirm Layer 2 bridge mode is enabled where required.")
        lines.append("- Compare the exact handoff mode on both ends: tagged trunk vs untagged/native management. Do not assume they match.")
        lines.append("- If customer traffic is expected over that handoff, force tagged-only trunk behavior and eliminate native VLAN 10 leakage.")
        lines.append("- Pull local port counters and link state before touching alignment. Management up plus no service over aux points at L2 handoff mismatch more than RF.")
        if shared_building_outages:
            first = shared_building_outages[0]
            lines.append(f"- For Building {first.get('building')}, verify power and uplink first. If both the Positron and its paired radio are dark, do not start with management-IP cleanup.")
        if pair_missing_ip:
            lines.append(f"- Validate provisioning and inventory on the no-IP radio first: {', '.join(pair_missing_ip)}.")
        notable_history = [row for row in (history.get('transport_history') or []) if row.get('likely_issue') not in {None, 'unknown', 'no_live_rf_stats', 'no_major_recent_signal'}]
        if notable_history:
            lines.append("Historical clues worth checking:")
            for row in notable_history[:3]:
                lines.append(f"- {row.get('name')}: {row.get('likely_issue')}.")
        if syslog_summary.get('available') and int(syslog_summary.get('event_count') or 0) == 0:
            lines.append("- Syslog ingestion path is ready, but there are no archived site-scoped syslog events loaded yet.")
        if changed_names:
            if '0000021-004-V2000-02' in changed_names:
                lines.append("- The no-IP Building 4 radio was recently created or updated in NetBox. That increases the odds of incomplete provisioning, wrong bridge mode, or stale inventory on the exact complained-of node.")
            if '000021.OLT06' in changed_names:
                lines.append("- 000021.OLT06 also has recent changelog activity. Treat that as context for the optical noise, not proof that it caused the Building 4 aux-port failure.")

        lines.append("Next useful questions:")
        if primary_pair:
            lines.append(f"- how is {primary_pair.get('radio_names')[0]}?")
        lines.append(f"- pull the logs for {site_id}")
        lines.append(f"- which cambium radios have issues at {site_id}?")
        lines.append(f"- what can you tell me about {site_id}?")
        return {
            'summary': "\n".join(lines),
            'site_id': site_id,
            'online_count': online_count,
            'optical_alert_count': len(optical_alerts),
            'radio_alert_count': len(radio_alerts),
            'historical': history,
        }

    handler = {
        'get_server_info': lambda p: ops.get_server_info(),
        'get_outage_context': lambda p: ops.get_outage_context(p['address_text'], p['unit']),
        'get_subnet_health': lambda p: ops.get_subnet_health(p.get('subnet'), p.get('site_id'), bool(p.get('include_alerts', True)), bool(p.get('include_bigmac', True))),
        'get_online_customers': lambda p: ops.get_online_customers(p.get('scope'), p.get('site_id'), p.get('building_id'), p.get('router_identity')),
        'compare_customer_evidence': lambda p: ops.compare_customer_evidence(p['site_id']),
        'get_customer_access_trace': lambda p: ops.get_customer_access_trace(p.get('network_name'), p.get('mac'), p.get('serial'), p.get('site_id')),
        'trace_mac': lambda p: ops.trace_mac(p['mac'], bool(p.get('include_bigmac', True))),
        'get_netbox_device': lambda p: ops.get_netbox_device(p['name']),
        'get_netbox_device_by_ip': lambda p: ops.get_netbox_device_by_ip(p['ip']),
        'get_site_alerts': lambda p: ops.get_site_alerts(p['site_id']),
        'get_site_summary': lambda p: ops.get_site_summary(p['site_id'], bool(p.get('include_alerts', True))),
        'get_site_historical_evidence': lambda p: ops.get_site_historical_evidence(p['site_id']),
        'get_site_syslog_summary': lambda p: ops.get_site_syslog_summary(p['site_id']),
        'get_dhcp_findings_summary': lambda p: ops.get_dhcp_findings_summary(),
        'get_dhcp_relay_summary': lambda p: ops.get_dhcp_relay_summary(p['relay_name']),
        'get_dhcp_circuit_summary': lambda p: ops.get_dhcp_circuit_summary(p['circuit_id']),
        'get_dhcp_subscriber_summary': lambda p: ops.get_dhcp_subscriber_summary(p.get('mac'), p.get('ip'), p.get('circuit_id'), p.get('remote_id'), p.get('subscriber_id'), p.get('relay_name')),
        'get_live_dhcp_lease_summary': lambda p: ops.get_live_dhcp_lease_summary(p.get('site_id'), p.get('mac'), p.get('ip'), int(p.get('limit', 25))),
        'get_live_splynx_online_summary': lambda p: ops.get_live_splynx_online_summary(p.get('site_id'), p.get('search'), int(p.get('limit', 25))),
        'get_live_cnwave_rf_summary': lambda p: ops.get_live_cnwave_rf_summary(p.get('site_id'), p.get('name'), int(p.get('limit', 20))),
        'get_site_logs': lambda p: ops.get_site_logs(p['site_id'], int(p.get('window_minutes', 15)), str(p.get('log_filter', 'all')), int(p.get('limit', 500))),
        'get_device_logs': lambda p: ops.get_device_logs(p['device_name'], int(p.get('window_minutes', 15)), str(p.get('log_filter', 'all')), int(p.get('limit', 500))),
        'correlate_event_window': lambda p: ops.correlate_event_window(p['site_id'], int(p.get('window_minutes', 15)), int(p.get('limit', 500))),
        'run_live_routeros_read': lambda p: ops.run_live_routeros_read(p['device_name'], p['intent'], p.get('params'), p.get('reason')),
        'get_live_source_readiness': lambda p: ops.get_live_source_readiness(),
        'get_live_rogue_dhcp_scan': lambda p: ops.get_live_rogue_dhcp_scan(p.get('site_id'), p.get('device_name'), p.get('interface'), int(p.get('seconds', 5)), p.get('mac')),
        'get_live_capsman_summary': lambda p: ops.get_live_capsman_summary(p.get('site_id'), p.get('device_name')),
        'get_live_wifi_registration_summary': lambda p: ops.get_live_wifi_registration_summary(p.get('site_id'), p.get('device_name'), int(p.get('limit', 25))),
        'get_live_wifi_provisioning_summary': lambda p: ops.get_live_wifi_provisioning_summary(p.get('site_id'), p.get('device_name')),
        'get_live_routeros_export': lambda p: ops.get_live_routeros_export(p.get('site_id'), p.get('device_name'), bool(p.get('show_sensitive', True)), bool(p.get('terse', True))),
        'review_live_upgrade_risk': lambda p: ops.review_live_upgrade_risk(p.get('site_id'), p.get('device_name'), p.get('target_version', '7.22.1')),
        'generate_upgrade_preflight_plan': lambda p: ops.generate_upgrade_preflight_plan(p.get('site_id'), p.get('device_name'), p.get('target_version', '7.22.1')),
        'render_upgrade_change_explanation': lambda p: ops.render_upgrade_change_explanation(p.get('site_id'), p.get('device_name'), p.get('target_version', '7.22.1')),
        'dispatch_troubleshooting_scenarios': lambda p: dispatch_troubleshooting_scenarios(p.get('query', query), site_profile, int(p.get('limit', 3))),
        'run_live_olt_read': lambda p: ops.run_live_olt_read(p['olt_ip'], p['command'], p.get('olt_name')),
        'get_live_olt_ont_summary': lambda p: ops.get_live_olt_ont_summary(p.get('mac'), p.get('serial'), p.get('olt_name'), p.get('olt_ip'), p.get('pon'), p.get('onu_id')),
            'get_live_olt_log_summary': lambda p: ops.get_live_olt_log_summary(p.get('site_id'), p.get('olt_name'), p.get('olt_ip'), p.get('mac'), p.get('serial'), p.get('word'), p.get('module'), p.get('level')),
            'get_tp_link_subscriber_join': lambda p: ops.get_tp_link_subscriber_join(p.get('network_name'), p.get('network_id'), p.get('mac'), p.get('serial'), p.get('site_id')),
            'list_sites_inventory': lambda p: ops.list_sites_inventory(int(p.get('limit', 200))),
            'search_sites_inventory': lambda p: ops.search_sites_inventory(p['query'], int(p.get('limit', 25))),
            'get_site_precheck': lambda p: ops.get_site_precheck(p['site_id']),
            'get_building_health': lambda p: ops.get_building_health(
                p['building_id'],
                bool(p.get('include_alerts', True)),
            ) if p.get('building_id') else ops.get_building_health(
                _canonical_scope_token(((ops._resolve_building_from_address(p.get('address_text')) or {}).get('best_match') or {}).get('prefix')),
                bool(p.get('include_alerts', True)),
            ),
            'get_switch_summary': lambda p: ops.get_switch_summary(p['switch_identity']),
        'get_building_customer_count': lambda p: ops.get_building_customer_count(p['building_id']),
        'get_building_flap_history': lambda p: ops.get_building_flap_history(p['building_id']),
        'get_site_flap_history': lambda p: ops.get_site_flap_history(p['site_id']),
        'get_rogue_dhcp_suspects': lambda p: ops.get_rogue_dhcp_suspects(p.get('building_id'), p.get('site_id')),
        'get_site_rogue_dhcp_summary': lambda p: ops.get_site_rogue_dhcp_summary(p['site_id']),
        'get_recovery_ready_cpes': lambda p: ops.get_recovery_ready_cpes(p.get('building_id'), p.get('site_id')),
        'get_site_punch_list': lambda p: ops.get_site_punch_list(p['site_id']),
        'find_cpe_candidates': lambda p: ops.find_cpe_candidates(p.get('site_id'), p.get('building_id'), p.get('oui'), bool(p.get('access_only', True)), int(p.get('limit', 100))),
        'get_cpe_state': lambda p: ops.get_cpe_state(p['mac'], bool(p.get('include_bigmac', True))),
        'get_cpe_management_surface': lambda p: ops.get_cpe_management_surface(p.get('network_name'), p.get('network_id'), p.get('mac'), p.get('serial'), p.get('site_id')),
        'get_cpe_management_readiness': lambda p: ops.get_cpe_management_readiness(p.get('vendor')),
        'get_vendor_site_presence': lambda p: ops.get_vendor_site_presence(p['vendor'], int(p.get('limit', 20))),
        'get_vendor_alt_mac_clusters': lambda p: ops.get_vendor_alt_mac_clusters(p['vendor'], p.get('site_id'), p.get('building_id'), int(p.get('limit', 50))),
        'capture_operator_note': lambda p: ops.capture_operator_note(p['note'], p.get('site_id'), p.get('tags')),
        'get_local_ont_path': lambda p: ops.get_local_ont_path(p.get('mac'), p.get('serial')),
        'get_vilo_server_info': lambda p: ops.get_vilo_server_info(),
        'get_vilo_inventory': lambda p: ops.get_vilo_inventory(int(p.get('page_index', 1)), int(p.get('page_size', 20))),
        'get_vilo_inventory_audit': lambda p: ops.audit_vilo_inventory(p.get('site_id'), p.get('building_id'), int(p.get('limit', 500))),
        'export_vilo_inventory_audit': lambda p: ops.export_vilo_inventory_audit(p.get('site_id'), p.get('building_id'), int(p.get('limit', 500))),
        'get_vilo_subscribers': lambda p: ops.get_vilo_subscribers(int(p.get('page_index', 1)), int(p.get('page_size', 20))),
        'get_vilo_networks': lambda p: ops.get_vilo_networks(int(p.get('page_index', 1)), int(p.get('page_size', 20))),
        'get_vilo_devices': lambda p: ops.get_vilo_devices(p['network_id']),
        'get_vilo_target_summary': lambda p: ops.get_vilo_target_summary(p.get('mac'), p.get('network_id'), p.get('network_name')),
        'get_site_radio_inventory': lambda p: ops.get_site_radio_inventory(p['site_id']),
        'get_transport_radio_summary': lambda p: ops.get_transport_radio_summary(p.get('query'), p.get('name'), p.get('ip'), p.get('mac')),
        'get_transport_radio_issues': lambda p: ops.get_transport_radio_issues(p.get('vendor'), p.get('site_id'), int(p.get('limit', 10))),
        'assess_site_incident': lambda p: assess_site_incident(p['site_id']),
        'get_site_loop_suspicion': lambda p: ops.get_site_loop_suspicion(p['site_id']),
        'get_site_bridge_host_weirdness': lambda p: ops.get_site_bridge_host_weirdness(p['site_id']),
        'get_nycha_port_audit': lambda p: ops.get_nycha_port_audit(p.get('site_id')),
        'generate_nycha_audit_workbook': lambda p: ops.generate_nycha_audit_workbook(p.get('address_text'), p.get('switch_identity'), p.get('site_id')),
        'get_live_cnwave_radio_neighbors': lambda p: ops.get_live_cnwave_radio_neighbors(p.get('site_id'), p.get('name'), p.get('query')),
        'get_radio_handoff_trace': lambda p: ops.get_radio_handoff_trace(p.get('query'), p.get('name')),
        'get_building_fault_domain': lambda p: ops.get_building_fault_domain(p['building_id']),
        'get_site_topology': lambda p: ops.get_site_topology(p['site_id']),
        'clarify_target': lambda p: p,
    }
    result = handler[parsed['action']](parsed['params'])
    preferred = preferred_troubleshooting_mcp(query, site_profile)
    formatted = format_operator_response(parsed['action'], result, query)
    return {
        'query': query,
        'matched_action': parsed['action'],
        'params': parsed['params'],
        'operator_summary': formatted,
        'assistant_answer': formatted,
        'result': result,
        'preferred_mcp': preferred.get('preferred_mcp'),
        'preferred_mcp_reason': preferred.get('reason'),
        'preferred_mcp_cues': preferred.get('matched_cues') or [],
    }


def run_structured_intent(ops: Any, intent: Any) -> dict[str, Any]:
    action = str(getattr(intent, "intent", "") or intent["intent"])
    raw = str(getattr(intent, "raw", "") or intent.get("raw") or "")
    entities = getattr(intent, "entities", None)
    site_id = getattr(entities, "site_id", None)
    building_id = getattr(entities, "building", None)
    site_profile = SITE_SERVICE_PROFILES.get(site_id) if site_id else None

    if action == "get_online_customers":
        params = {"scope": site_id, "site_id": site_id}
        result = ops.get_online_customers(site_id, site_id, None, None)
    elif action == "get_site_logs":
        window_minutes = _extract_log_window_minutes(raw)
        log_filter = _extract_log_filter(raw)
        params = {"site_id": site_id, "window_minutes": window_minutes, "log_filter": log_filter, "limit": 500}
        result = ops.get_site_logs(site_id, window_minutes, log_filter, 500)
    elif action == "get_device_logs":
        device = getattr(entities, "device", None) or _extract_device_hostname(raw)
        window_minutes = _extract_log_window_minutes(raw)
        log_filter = _extract_log_filter(raw)
        params = {"device_name": device, "window_minutes": window_minutes, "log_filter": log_filter, "limit": 500}
        result = ops.get_device_logs(device, window_minutes, log_filter, 500)
    elif action == "correlate_event_window":
        window_minutes = _extract_log_window_minutes(raw)
        params = {"site_id": site_id, "window_minutes": window_minutes, "limit": 500}
        result = ops.correlate_event_window(site_id, window_minutes, 500)
    elif action == "get_site_precheck":
        params = {"site_id": site_id}
        result = ops.get_site_precheck(site_id)
    elif action == "get_site_loop_suspicion":
        params = {"site_id": site_id}
        result = ops.get_site_loop_suspicion(site_id)
    elif action == "get_site_bridge_host_weirdness":
        params = {"site_id": site_id}
        result = ops.get_site_bridge_host_weirdness(site_id)
    elif action == "get_live_cnwave_radio_neighbors":
        params = {"site_id": site_id, "query": raw}
        result = ops.get_live_cnwave_radio_neighbors(site_id, None, raw)
    elif action == "get_radio_handoff_trace":
        params = {"query": raw}
        result = ops.get_radio_handoff_trace(raw, None)
    elif action == "get_building_fault_domain":
        device = getattr(entities, "device", None)
        resolved_building_id = building_id
        if not resolved_building_id and device:
            resolved = ops._resolve_building_from_address(str(device))
            resolved_building_id = _canonical_scope_token(((resolved or {}).get("best_match") or {}).get("prefix"))
        params = {"building_id": resolved_building_id, "address_text": (device if not building_id else None)}
        result = ops.get_building_fault_domain(resolved_building_id)
    elif action == "get_site_topology":
        params = {"site_id": site_id}
        result = ops.get_site_topology(site_id)
    elif action == "get_site_punch_list":
        params = {"site_id": site_id}
        result = ops.get_site_punch_list(site_id)
    elif action == "get_nycha_port_audit":
        params = {}
        result = ops.get_nycha_port_audit()
    elif action == "generate_nycha_audit_workbook":
        device = getattr(entities, "device", None)
        sw_match = re.search(r'\b(\d{6}\.\d{3}\.SW\d+)\b', raw, re.I)
        switch_identity = device if device and re.search(r'\bSW\d+$', str(device), re.I) else (sw_match.group(1) if sw_match else None)
        # WHY: When device entity is not a switch identity, it holds a street address (put there by
        # _heuristic_parse for "audit 225 Buffalo Ave" style queries). Distinguish by checking for SW suffix.
        address_text = None if switch_identity else (device if device and not re.search(r'\bSW\d+$', str(device), re.I) else None)
        params = {"switch_identity": switch_identity, "site_id": site_id, "address_text": address_text}
        result = ops.generate_nycha_audit_workbook(address_text=address_text, switch_identity=switch_identity, site_id=site_id)
    elif action == "get_building_health":
        device = getattr(entities, "device", None)
        resolved_building_id = building_id
        if not resolved_building_id and device:
            resolved = ops._resolve_building_from_address(str(device))
            resolved_building_id = _canonical_scope_token(((resolved or {}).get("best_match") or {}).get("prefix"))
        params = {"building_id": resolved_building_id, "address_text": (device if not building_id else None), "include_alerts": True}
        result = ops.get_building_health(resolved_building_id, True)
    elif action == "rerun_latest_scan":
        device = getattr(entities, "device", None)
        resolved_building_id = building_id
        if not resolved_building_id and device:
            resolved = ops._resolve_building_from_address(str(device))
            resolved_building_id = _canonical_scope_token(((resolved or {}).get("best_match") or {}).get("prefix"))
        params = {"site_id": site_id, "building_id": resolved_building_id, "address_text": (device if not building_id else None)}
        effective_site_id = site_id or (resolved_building_id.split(".", 1)[0] if resolved_building_id else None)
        result = ops.trigger_scan_refresh(
            site_id=effective_site_id,
            building_id=resolved_building_id,
            address_text=(device if not building_id else None),
        )
    elif action == "get_switch_summary":
        device = getattr(entities, "device", None)
        params = {"switch_identity": device}
        result = ops.get_switch_summary(device)
    elif action == "get_cpe_management_surface":
        device = getattr(entities, "device", None)
        raw_lower = raw.lower()
        serial = None
        serial_match = SERIAL_RE.search(raw)
        if serial_match:
            candidate = serial_match.group(0)
            if not device or candidate.lower() != str(device).lower():
                serial = candidate
        network_name = None
        mac = None
        if device and re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", str(device), re.I):
            mac = device
        else:
            network_name = device
        params = {"network_name": network_name, "network_id": None, "mac": mac, "serial": serial, "site_id": site_id}
        result = ops.get_cpe_management_surface(network_name, None, mac, serial, site_id)
    elif action == "get_cpe_management_readiness":
        vendor = None
        if "vilo" in raw.lower():
            vendor = "vilo"
        elif any(token in raw.lower() for token in ("hc220", "tp-link", "tplink")):
            vendor = "tplink_hc220"
        params = {"vendor": vendor}
        result = ops.get_cpe_management_readiness(vendor)
    elif action == "get_customer_access_trace":
        device = getattr(entities, "device", None)
        serial = None
        params = {"network_name": device, "mac": None, "serial": serial, "site_id": site_id}
        result = ops.get_customer_access_trace(device, None, serial, site_id)
    elif action == "trace_mac":
        device = getattr(entities, "device", None)
        params = {"mac": device, "include_bigmac": True}
        result = ops.trace_mac(device, True)
    elif action == "get_cpe_state":
        device = getattr(entities, "device", None)
        params = {"mac": device, "include_bigmac": True}
        result = ops.get_cpe_state(device, True)
    elif action == "get_live_olt_ont_summary":
        device = getattr(entities, "device", None)
        serial = None
        serial_match = SERIAL_RE.search(raw)
        if serial_match:
            serial = serial_match.group(0)
        normalized_subscriber = normalize_subscriber_label(device or "")
        subscriber_olt = SUBSCRIBER_NAME_TO_OLT.get(normalized_subscriber) if normalized_subscriber else None
        olt_name = subscriber_olt.get("olt") if subscriber_olt else None
        olt_ip = subscriber_olt.get("olt_ip") if subscriber_olt else None
        pon = subscriber_olt.get("pon") if subscriber_olt else None
        onu_id = subscriber_olt.get("onu") if subscriber_olt else None
        mac_value = device if not subscriber_olt else None
        params = {"mac": mac_value, "serial": serial, "olt_name": olt_name, "olt_ip": olt_ip, "pon": pon, "onu_id": onu_id}
        result = ops.get_live_olt_ont_summary(mac_value, serial, olt_name, olt_ip, pon, onu_id)
    elif action == "get_site_summary":
        params = {"site_id": site_id, "include_alerts": True}
        result = ops.get_site_summary(site_id, True)
    elif action == "get_site_alerts":
        params = {"site_id": site_id}
        result = ops.get_site_alerts(site_id)
    elif action == "dispatch_troubleshooting_scenarios":
        params = {"query": raw, "site_id": site_id}
        result = dispatch_troubleshooting_scenarios(raw, site_profile, 3)
    elif action == "find_cpe_candidates":
        oui = "E8:DA:00" if "vilo" in raw.lower() else None
        params = {"site_id": site_id, "building_id": building_id, "oui": oui, "access_only": True, "limit": 100}
        result = ops.find_cpe_candidates(site_id, building_id, oui, True, 100)
    else:
        raise ValueError(f"Unsupported structured intent for deterministic execution: {action}")

    preferred = preferred_troubleshooting_mcp(raw, site_profile)
    formatted = format_operator_response(action, result, raw)
    return {
        'query': raw,
        'matched_action': action,
        'params': params,
        'operator_summary': formatted,
        'assistant_answer': formatted,
        'result': result,
        'preferred_mcp': preferred.get('preferred_mcp'),
        'preferred_mcp_reason': preferred.get('reason'),
        'preferred_mcp_cues': preferred.get('matched_cues') or [],
    }
