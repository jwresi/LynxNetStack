from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast, get_args

from diagnosis.engine import PrimaryStatus, Diagnosis, diagnose
from diagnosis.evidence import (
    AuthTruth,
    ControllerTruth,
    DhcpTruth,
    InventoryTruth,
    L2LocationEvidence,
    L2Truth,
    PhysicalTruth,
    RealityModel,
    ServiceTruth,
    UnitEvidence,
    build_reality_model,
)
from mcp.jake_ops_mcp import find_local_online_cpe_row, load_nycha_info_rows, norm_mac, parse_unit_token


WORKBOOK_STATUS_BY_PRIMARY_STATUS: dict[PrimaryStatus, str] = {
    "HEALTHY": "Good",
    "NOT_SEEN_ANYWHERE": "NOT SEEN ANYWHERE",
    "L2_PRESENT_NO_SERVICE": "L2 PRESENT / NO SERVICE",
    "DEGRADED_LINK_BAD_CABLE_SUSPECTED": "DEGRADED LINK / BAD CABLE SUSPECTED",
    "CONTROLLER_MAPPING_MISMATCH": "CONTROLLER MISMATCH",
    "INVENTORY_MAC_MISMATCH": "INVENTORY MAC MISMATCH",
    "DEVICE_SWAPPED_OR_WRONG_UNIT": "WRONG UNIT / DEVICE SWAPPED",
    "PPPoE_AUTH_FAILURE": "PPPoE AUTH FAILURE",
    "PPPoE_NO_ATTEMPT": "PPPoE NO ATTEMPT",
    "DHCP_NO_OFFER": "DHCP NO OFFER",
    "DHCP_ROGUE_OR_WRONG_SERVER": "ROGUE DHCP / WRONG SERVER",
    "SWITCH_PORT_DISABLED_OR_WRONG_VLAN": "SWITCH PORT / VLAN ISSUE",
    "CONTROLLER_STALE_DEVICE": "CONTROLLER STALE",
    "NEEDS_MORE_EVIDENCE": "NEEDS MORE EVIDENCE",
}


def _canonical_unit_token(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    text = text.replace("UNIT", "").replace(" ", "")
    match = re.match(r"^0*(\d+)([A-Z]+)?$", text)
    if match:
        number = str(int(match.group(1)))
        suffix = match.group(2) or ""
        return f"{number}{suffix}"
    return text


def _extract_pppoe_unit(pppoe_label: str | None) -> str:
    text = str(pppoe_label or "").strip()
    for row in load_nycha_info_rows():
        if str(row.get("PPPoE") or "").strip().lower() == text.lower():
            return _canonical_unit_token(parse_unit_token(row.get("Unit")))
    return ""


def _switch_port_to_interface(label: str | None) -> str | None:
    text = str(label or "").strip()
    if not text:
        return None
    if text.lower().startswith("ether"):
        return text
    upper = text.upper()
    if "-E" in upper:
        _, _, suffix = upper.partition("-E")
        if suffix.isdigit():
            return f"ether{int(suffix)}"
    if "-" in upper:
        _, _, suffix = upper.partition("-")
        if suffix.isdigit():
            return f"ether{int(suffix)}"
    return None


def _switch_port_prefix(label: str | None) -> str | None:
    text = str(label or "").strip().upper()
    if "-" not in text:
        return None
    prefix, _, _ = text.partition("-")
    return prefix or None


def _known_mac_bug_kind(expected_mac: str | None, observed_mac: str | None) -> str | None:
    expected = norm_mac(expected_mac or "")
    observed = norm_mac(observed_mac or "")
    if not expected or not observed or expected == observed:
        return None
    expected_parts = expected.split(":")
    observed_parts = observed.split(":")
    differing = [idx for idx, (lhs, rhs) in enumerate(zip(expected_parts, observed_parts)) if lhs != rhs]
    if len(differing) != 1:
        return None
    idx = differing[0]
    if idx not in {0, 5}:
        return None
    try:
        if abs(int(expected_parts[idx], 16) - int(observed_parts[idx], 16)) != 1:
            return None
    except ValueError:
        return None
    return "first_octet" if idx == 0 else "last_octet"


def _build_expected_mac_locations(expected_mac: str, live: Any) -> list[L2LocationEvidence]:
    locations: list[L2LocationEvidence] = []
    for switch_identity, by_interface in dict(getattr(live, "live_port_macs_by_switch_identity", {}) or {}).items():
        for iface, macs in dict(by_interface or {}).items():
            normalized = [norm_mac(mac or "") for mac in list(macs or [])]
            if expected_mac in normalized:
                locations.append(
                    L2LocationEvidence(
                        mac=expected_mac,
                        switch=str(switch_identity or "").strip() or None,
                        port=str(iface or "").strip() or None,
                        source="bridge/live_lookup",
                    )
                )
    return locations


def _build_historical_mac_locations(unit: str, unit_label: str, live: Any) -> list[L2LocationEvidence]:
    raw = dict(getattr(live, "historical_locations_by_unit", {}) or {}).get(unit or "")
    if not raw:
        raw = dict(getattr(live, "historical_locations_by_unit", {}) or {}).get(unit_label) or []
    locations: list[L2LocationEvidence] = []
    for row in list(raw or []):
        mac = norm_mac(row.get("mac") or "")
        if not mac:
            continue
        locations.append(
            L2LocationEvidence(
                mac=mac,
                switch=str(row.get("switch") or row.get("identity") or "").strip() or None,
                port=str(row.get("port") or row.get("on_interface") or "").strip() or None,
                vlan=str(row.get("vlan") or row.get("vid") or "").strip() or None,
                learned_at=str(row.get("learned_at") or row.get("seen_at") or row.get("scan_id") or "").strip() or None,
                is_historical=True,
                source=str(row.get("source") or "historical_mac_lookup"),
            )
        )
    return locations


def _parse_timestamp(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _observed_port_candidates(audit_row: Any, live: Any, expected_mac: str) -> tuple[str | None, str | None, list[str]]:
    observed_interface = _switch_port_to_interface(getattr(audit_row, "switch_port", ""))
    switch_prefix = _switch_port_prefix(getattr(audit_row, "switch_port", ""))
    target_switch_identity = (
        dict(getattr(live, "switch_identities_by_label_prefix", {}) or {}).get(switch_prefix or "")
        or getattr(live, "inferred_switch_identity", None)
    )
    if observed_interface and target_switch_identity:
        by_interface = dict(getattr(live, "live_port_macs_by_switch_identity", {}) or {}).get(target_switch_identity, {}) or {}
        candidates = [norm_mac(mac or "") for mac in list((dict(by_interface).get(observed_interface) or []))]
        return observed_interface, target_switch_identity, [mac for mac in candidates if mac]
    if observed_interface:
        fallback = dict(getattr(live, "live_port_macs_by_interface", {}) or {}).get(observed_interface) or []
        return observed_interface, target_switch_identity, [norm_mac(mac or "") for mac in fallback if norm_mac(mac or "")]
    if expected_mac:
        for switch_identity, by_interface in dict(getattr(live, "live_port_macs_by_switch_identity", {}) or {}).items():
            for iface, macs in dict(by_interface or {}).items():
                normalized = [norm_mac(mac or "") for mac in list(macs or []) if norm_mac(mac or "")]
                if expected_mac in normalized:
                    return str(iface or "").strip() or None, str(switch_identity or "").strip() or None, normalized
    return None, target_switch_identity, []


@dataclass(slots=True)
class WorkbookDiagnosisResult:
    diagnosis: Diagnosis
    evidence: UnitEvidence
    reality: RealityModel
    workbook_status: str
    workbook_verification: str
    workbook_action: str | None
    dispatch_required: bool
    dispatch_priority: str
    backend_action: str | None
    field_action: str | None
    evidence_summary: str
    confidence: str


def build_workbook_unit_evidence(audit_row: Any, source_row: dict[str, str], live: Any) -> UnitEvidence:
    unit_label = str(getattr(audit_row, "unit_label", "") or "")
    unit = _canonical_unit_token(parse_unit_token(unit_label) or getattr(audit_row, "unit_key", "") or unit_label)
    expected_mac = norm_mac(source_row.get("MAC Address") or source_row.get("mac") or "")
    expected_pppoe = str(source_row.get("PPPoE") or "").strip() or None
    expected_make = str(source_row.get("AP Make") or "").strip() or None
    switch_identity = None
    expected_port = None
    exact = dict(getattr(live, "exact_matches_by_unit", {}) or {}).get(unit or "") or {}
    if exact:
        switch_identity = str(exact.get("switch_identity") or "").strip() or None
        expected_port = str(exact.get("interface") or "").strip() or None
    if not expected_port:
        expected_port = _switch_port_to_interface(getattr(audit_row, "switch_port", ""))
    if not switch_identity:
        switch_prefix = _switch_port_prefix(getattr(audit_row, "switch_port", ""))
        switch_identity = (
            dict(getattr(live, "switch_identities_by_label_prefix", {}) or {}).get(switch_prefix or "")
            or getattr(live, "inferred_switch_identity", None)
        )

    inventory_truth = InventoryTruth(
        expected_make=expected_make,
        expected_mac=expected_mac or None,
        expected_pppoe=expected_pppoe,
        expected_controller="vilo" if "vilo" in str(expected_make or "").lower() else "tauc" if "tp-link" in str(expected_make or "").lower() or "tplink" in str(expected_make or "").lower() else None,
        expected_switch=str(switch_identity or "").strip() or None,
        expected_port=str(expected_port or "").strip() or None,
        expected_vlan=None,
        evidence_sources=["inventory_csv"],
    )

    expected_mac_locations = _build_expected_mac_locations(expected_mac, live) if expected_mac else []
    historical_search_completed = getattr(live, "historical_search_completed", None)
    if isinstance(historical_search_completed, dict):
        historical_search_completed = (
            historical_search_completed.get(unit or "")
            if (unit or "") in historical_search_completed
            else historical_search_completed.get(unit_label)
            if unit_label in historical_search_completed
            else True
        )
    expected_port_search_completed = getattr(live, "expected_port_search_completed_by_unit", None)
    if isinstance(expected_port_search_completed, dict):
        expected_port_search_completed = (
            expected_port_search_completed.get(unit or "")
            if (unit or "") in expected_port_search_completed
            else expected_port_search_completed.get(unit_label)
            if unit_label in expected_port_search_completed
            else True
        )
    switch_scope_search_completed = getattr(live, "switch_scope_search_completed_by_unit", None)
    if isinstance(switch_scope_search_completed, dict):
        switch_scope_search_completed = (
            switch_scope_search_completed.get(unit or "")
            if (unit or "") in switch_scope_search_completed
            else switch_scope_search_completed.get(unit_label)
            if unit_label in switch_scope_search_completed
            else True
        )
    global_search_completed = getattr(live, "global_search_completed_by_unit", None)
    if isinstance(global_search_completed, dict):
        global_search_completed = (
            global_search_completed.get(unit or "")
            if (unit or "") in global_search_completed
            else global_search_completed.get(unit_label)
            if unit_label in global_search_completed
            else True
        )
    observed_interface, observed_switch, observed_candidates = _observed_port_candidates(audit_row, live, expected_mac)
    historical_locations = _build_historical_mac_locations(unit, unit_label, live)
    observed_mac = ""
    if expected_mac and expected_mac in observed_candidates:
        observed_mac = expected_mac
    elif expected_mac:
        bug_adjusted = next((mac for mac in observed_candidates if _known_mac_bug_kind(expected_mac, mac)), "")
        if bug_adjusted:
            observed_mac = bug_adjusted
    if not observed_mac and observed_candidates:
        observed_mac = observed_candidates[0]

    l2_truth = L2Truth(
        expected_port_checked=(
            True
            if expected_port_search_completed is True
            else True
            if expected_port and switch_identity and observed_interface == expected_port
            else True
            if expected_port and bool(observed_candidates)
            else None
        ),
        switch_scope_checked=(
            True
            if switch_scope_search_completed is True
            else True
            if switch_identity and switch_identity in dict(getattr(live, "live_port_macs_by_switch_identity", {}) or {})
            else None
        ),
        global_scope_checked=(
            True
            if global_search_completed is True
            else True
            if dict(getattr(live, "live_port_macs_by_switch_identity", {}) or {})
            else None
        ),
        historical_checked=True if historical_locations or expected_mac_locations or historical_search_completed is True else None,
        expected_mac_seen=bool(expected_mac_locations),
        expected_mac_locations=expected_mac_locations,
        any_mac_on_expected_port=bool(observed_candidates) if observed_interface else None,
        macs_on_expected_port=observed_candidates if observed_interface else [],
        live_mac_seen=bool(observed_mac or expected_mac_locations),
        live_mac=observed_mac or (expected_mac_locations[0].mac if expected_mac_locations else None),
        live_switch=observed_switch or (expected_mac_locations[0].switch if expected_mac_locations else None),
        live_port=observed_interface or (expected_mac_locations[0].port if expected_mac_locations else None),
        live_vlan=None,
        historical_locations=historical_locations,
        evidence_sources=["bridge/live_lookup"],
    )

    controller_row = dict(getattr(live, "controller_verification_by_mac", {}) or {}).get(expected_mac or "") or {}
    controller_snap = dict(controller_row.get("snapshot_row") or {})
    controller_status = str(controller_row.get("status") or "").strip().lower()
    controller_mac = norm_mac(
        controller_snap.get("device_mac") or controller_snap.get("tauc_mac") or controller_snap.get("mac") or expected_mac or ""
    )
    controller_unit = _canonical_unit_token(
        parse_unit_token(
            controller_snap.get("expected_unit")
            or controller_snap.get("unit")
            or controller_snap.get("subscriber_unit")
            or controller_snap.get("notes")
        )
    )
    controller_last_seen = str(
        controller_snap.get("last_seen")
        or controller_snap.get("lastSeen")
        or controller_snap.get("updated_at")
        or controller_snap.get("timestamp")
        or ""
    ).strip() or None
    collected_at = str(getattr(live, "captured_at_timestamp", "") or "").strip() or None
    controller_last_seen_dt = _parse_timestamp(controller_last_seen)
    collected_at_dt = _parse_timestamp(collected_at)
    controller_data_age_seconds = None
    controller_stale = None
    if controller_last_seen_dt and collected_at_dt:
        controller_data_age_seconds = max(0, int((collected_at_dt - controller_last_seen_dt).total_seconds()))
        controller_stale = controller_data_age_seconds > 900
    controller_online_value = controller_snap.get("online")
    controller_online = bool(controller_online_value) if controller_online_value is not None else None
    controller_seen = controller_status in {"match", "mismatch", "lookup_failed"} or bool(controller_snap)
    mapping_matches_inventory = True if controller_status == "match" else False if controller_status == "mismatch" else None
    controller_truth = ControllerTruth(
        controller_seen=controller_seen if controller_seen else None,
        controller_name=inventory_truth.expected_controller,
        controller_mac=controller_mac or None,
        controller_unit=controller_unit or None,
        controller_online=controller_online,
        controller_last_seen=controller_last_seen,
        controller_last_seen_timestamp=controller_last_seen,
        controller_data_age_seconds=controller_data_age_seconds,
        controller_stale=controller_stale,
        mapping_matches_inventory=mapping_matches_inventory,
        evidence_sources=["controller_snapshot"] if controller_seen else [],
    )

    auth_truth = AuthTruth(
        pppoe_active=None,
        pppoe_username=expected_pppoe,
        pppoe_failed_attempts_seen=None,
        pppoe_failure_reason=None,
        pppoe_last_attempt_timestamp=None,
        pppoe_no_attempt_evidence=False,
        evidence_sources=[],
    )
    address_online = dict(getattr(live, "online_units_by_token", {}) or {}).get(unit or "") or {}
    sources = [str(item) for item in list(address_online.get("sources") or address_online.get("evidence_sources") or [])]
    if "router_pppoe_session" in sources:
        auth_truth.pppoe_active = True
        auth_truth.evidence_sources.append("router_pppoe_session")

    local_online = find_local_online_cpe_row(
        network_name=source_row.get("PPPoE"),
        mac=source_row.get("MAC Address") or source_row.get("mac"),
        serial=source_row.get("AP Serial Number"),
    )
    if local_online and expected_pppoe and auth_truth.pppoe_active is not True:
        auth_truth.pppoe_active = True
        if "local_online_export" not in auth_truth.evidence_sources:
            auth_truth.evidence_sources.append("local_online_export")

    dhcp_truth = DhcpTruth(
        dhcp_expected=None,
        discovers_seen=None,
        dhcp_discovers_seen=None,
        offers_seen=None,
        dhcp_offers_seen=None,
        dhcp_offer_source=None,
        dhcp_expected_server=None,
        rogue_dhcp_detected=None,
        evidence_sources=[],
    )

    service_truth = ServiceTruth(
        customer_traffic_seen=True if auth_truth.pppoe_active or local_online else False,
        evidence_sources=["local_online_export"] if local_online else [],
    )

    port_observations = dict(getattr(live, "port_observations_by_unit", {}) or {}).get(unit or "") or {}
    auth_observations = dict(getattr(live, "auth_observations_by_unit", {}) or {}).get(unit or "") or {}
    dhcp_observations = dict(getattr(live, "dhcp_observations_by_unit", {}) or {}).get(unit or "") or {}
    if auth_observations:
        auth_truth.pppoe_failed_attempts_seen = auth_observations.get("pppoe_failed_attempts_seen")
        auth_truth.pppoe_failure_reason = str(auth_observations.get("pppoe_failure_reason") or "").strip() or None
        auth_truth.pppoe_last_attempt_timestamp = str(auth_observations.get("pppoe_last_attempt_timestamp") or "").strip() or None
        if auth_observations.get("pppoe_no_attempt_evidence") is not None:
            auth_truth.pppoe_no_attempt_evidence = bool(auth_observations.get("pppoe_no_attempt_evidence"))
        if auth_observations.get("pppoe_active") is not None:
            auth_truth.pppoe_active = bool(auth_observations.get("pppoe_active"))
        auth_truth.evidence_sources.extend([str(src) for src in list(auth_observations.get("evidence_sources") or []) if str(src)])
        if auth_truth.pppoe_failed_attempts_seen is False and auth_truth.pppoe_no_attempt_evidence is False:
            auth_truth.pppoe_no_attempt_evidence = False
    if dhcp_observations:
        dhcp_truth.dhcp_expected = dhcp_observations.get("dhcp_expected")
        dhcp_truth.discovers_seen = dhcp_observations.get("dhcp_discovers_seen")
        dhcp_truth.dhcp_discovers_seen = dhcp_observations.get("dhcp_discovers_seen")
        dhcp_truth.offers_seen = dhcp_observations.get("dhcp_offers_seen")
        dhcp_truth.dhcp_offers_seen = dhcp_observations.get("dhcp_offers_seen")
        dhcp_truth.dhcp_offer_source = str(dhcp_observations.get("dhcp_offer_source") or "").strip() or None
        dhcp_truth.dhcp_expected_server = str(dhcp_observations.get("dhcp_expected_server") or "").strip() or None
        dhcp_truth.rogue_dhcp_suspected = dhcp_observations.get("rogue_dhcp_detected")
        dhcp_truth.rogue_dhcp_detected = dhcp_observations.get("rogue_dhcp_detected")
        dhcp_truth.wrong_server_seen = dhcp_observations.get("rogue_dhcp_detected")
        dhcp_truth.evidence_sources.extend([str(src) for src in list(dhcp_observations.get("evidence_sources") or []) if str(src)])
    evidence = UnitEvidence(
        unit=unit or unit_label,
        inventory_truth=inventory_truth,
        physical_truth=PhysicalTruth(
            port_up=port_observations.get("port_up"),
            port_speed=str(port_observations.get("port_speed") or "").strip() or None,
            port_duplex=str(port_observations.get("port_duplex") or "").strip() or None,
            link_partner_speed=str(port_observations.get("link_partner_speed") or "").strip() or None,
            link_partner_duplex=str(port_observations.get("link_partner_duplex") or "").strip() or None,
            rx_errors=port_observations.get("rx_errors"),
            tx_errors=port_observations.get("tx_errors"),
            fcs_errors=port_observations.get("fcs_errors"),
            crc_errors=port_observations.get("crc_errors"),
            link_flaps=port_observations.get("link_flaps"),
            link_flaps_window_seconds=port_observations.get("link_flaps_window_seconds"),
            port_flaps=port_observations.get("port_flaps"),
            port_errors=dict(port_observations.get("port_errors") or {}),
            evidence_sources=["port_observations"] if port_observations else [],
        ),
        l2_truth=l2_truth,
        controller_truth=controller_truth,
        auth_truth=auth_truth,
        dhcp_truth=dhcp_truth,
        service_truth=service_truth,
    )

    if controller_seen and not controller_last_seen:
        evidence.add_stale_source(
            layer="controller_truth",
            source="controller_snapshot",
            reason="Controller snapshot is present but has no usable timestamp.",
        )
    for failure in list(getattr(live, "live_failures", []) or []):
        evidence.add_unknown(
            layer=str(failure.get("source") or "live_evidence"),
            field_name="runtime",
            reason=str(failure.get("detail") or failure.get("classification") or "Live evidence lookup failed."),
            sources_checked=[str(failure.get("source") or "live_evidence")],
        )
    return evidence


def workbook_status_for_primary_status(primary_status: PrimaryStatus) -> str:
    return WORKBOOK_STATUS_BY_PRIMARY_STATUS[primary_status]


def build_workbook_diagnosis_result(audit_row: Any, source_row: dict[str, str], live: Any) -> WorkbookDiagnosisResult:
    evidence = build_workbook_unit_evidence(audit_row, source_row, live)
    reality = build_reality_model(evidence)
    diagnosis = diagnose(reality)
    workbook_status = workbook_status_for_primary_status(cast(PrimaryStatus, diagnosis.primary_status))

    workbook_verification = ""
    expected_mac = norm_mac(source_row.get("MAC Address") or source_row.get("mac") or "")
    live_mac = norm_mac(evidence.l2_truth.live_mac or "")
    if expected_mac and live_mac and expected_mac == live_mac:
        workbook_verification = "Match"
    elif diagnosis.primary_status in {"INVENTORY_MAC_MISMATCH", "DEVICE_SWAPPED_OR_WRONG_UNIT", "CONTROLLER_MAPPING_MISMATCH"}:
        workbook_verification = "Mismatch"

    backend_action = diagnosis.backend_actions[0] if diagnosis.backend_actions else None
    field_action = diagnosis.field_actions[0] if diagnosis.field_actions else None
    workbook_action = backend_action or field_action or diagnosis.next_best_check or None
    evidence_parts = [diagnosis.explanation]
    if evidence.l2_truth.live_mac_seen:
        evidence_parts.append(f"Live MAC: {evidence.l2_truth.live_mac or expected_mac}.")
    else:
        evidence_parts.append("Live MAC not seen.")
    if diagnosis.evidence_missing:
        evidence_parts.append(f"Missing: {'; '.join(diagnosis.evidence_missing[:2])}.")
    if diagnosis.contradictions:
        evidence_parts.append(f"Contradictions: {'; '.join(diagnosis.contradictions[:2])}.")
    evidence_summary = " ".join(part.strip() for part in evidence_parts if part.strip())

    return WorkbookDiagnosisResult(
        diagnosis=diagnosis,
        evidence=evidence,
        reality=reality,
        workbook_status=workbook_status,
        workbook_verification=workbook_verification,
        workbook_action=workbook_action,
        dispatch_required=diagnosis.dispatch_required,
        dispatch_priority=diagnosis.dispatch_priority,
        backend_action=backend_action,
        field_action=field_action,
        evidence_summary=evidence_summary,
        confidence=diagnosis.confidence,
    )


def assert_workbook_status_mapping_complete() -> None:
    valid = set(get_args(PrimaryStatus))
    mapped = set(WORKBOOK_STATUS_BY_PRIMARY_STATUS)
    if valid != mapped:
        missing = sorted(valid - mapped)
        extra = sorted(mapped - valid)
        raise AssertionError(f"Workbook status mapping mismatch: missing={missing}, extra={extra}")
