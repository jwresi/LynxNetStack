from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class ContradictionRecord:
    layer: str
    summary: str
    details: str | None = None
    sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UnknownRecord:
    layer: str
    field_name: str
    reason: str
    sources_checked: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StaleSourceRecord:
    layer: str
    source: str
    last_seen: str | None = None
    reason: str | None = None


@dataclass(slots=True)
class InventoryTruth:
    expected_make: str | None = None
    expected_model: str | None = None
    expected_mac: str | None = None
    expected_pppoe: str | None = None
    expected_controller: str | None = None
    expected_switch: str | None = None
    expected_port: str | None = None
    expected_vlan: str | None = None
    expected_service_profile: str | None = None
    evidence_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PhysicalTruth:
    port_up: bool | None = None
    port_speed: str | None = None
    port_duplex: str | None = None
    link_partner_speed: str | None = None
    link_partner_duplex: str | None = None
    rx_errors: int | None = None
    tx_errors: int | None = None
    fcs_errors: int | None = None
    crc_errors: int | None = None
    link_flaps: int | None = None
    link_flaps_window_seconds: int | None = None
    port_flaps: int | None = None
    port_errors: dict[str, int] = field(default_factory=dict)
    port_last_down: str | None = None
    poe_relevant: bool | None = None
    poe_enabled: bool | None = None
    cable_degraded_signal: list[str] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class L2LocationEvidence:
    mac: str
    switch: str | None = None
    port: str | None = None
    vlan: str | None = None
    learned_at: str | None = None
    is_historical: bool = False
    source: str | None = None


@dataclass(slots=True)
class L2Truth:
    expected_port_checked: bool | None = None
    switch_scope_checked: bool | None = None
    global_scope_checked: bool | None = None
    historical_checked: bool | None = None
    expected_mac_seen: bool | None = None
    expected_mac_locations: list[L2LocationEvidence] = field(default_factory=list)
    any_mac_on_expected_port: bool | None = None
    macs_on_expected_port: list[str] = field(default_factory=list)
    live_mac_seen: bool | None = None
    live_mac: str | None = None
    live_switch: str | None = None
    live_port: str | None = None
    live_vlan: str | None = None
    historical_locations: list[L2LocationEvidence] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ControllerTruth:
    controller_seen: bool | None = None
    controller_name: str | None = None
    controller_mac: str | None = None
    controller_unit: str | None = None
    controller_online: bool | None = None
    controller_last_seen: str | None = None
    controller_last_seen_timestamp: str | None = None
    controller_data_age_seconds: int | None = None
    controller_stale: bool | None = None
    mapping_matches_inventory: bool | None = None
    evidence_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AuthAttemptEvidence:
    username: str | None = None
    outcome: str | None = None
    reason: str | None = None
    observed_at: str | None = None
    source: str | None = None


@dataclass(slots=True)
class AuthTruth:
    pppoe_active: bool | None = None
    pppoe_username: str | None = None
    pppoe_active_sessions: list[dict[str, Any]] = field(default_factory=list)
    pppoe_failures: list[AuthAttemptEvidence] = field(default_factory=list)
    pppoe_failed_attempts_seen: bool | None = None
    pppoe_failure_reason: str | None = None
    pppoe_last_attempt_timestamp: str | None = None
    pppoe_no_attempt_evidence: bool | None = None
    evidence_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DhcpOfferEvidence:
    server: str | None = None
    lease_ip: str | None = None
    accepted: bool | None = None
    observed_at: str | None = None
    source: str | None = None


@dataclass(slots=True)
class DhcpTruth:
    dhcp_expected: bool | None = None
    discovers_seen: int | None = None
    dhcp_discovers_seen: int | None = None
    dhcp_discovers: list[dict[str, Any]] = field(default_factory=list)
    offers_seen: int | None = None
    dhcp_offers_seen: int | None = None
    dhcp_offers: list[DhcpOfferEvidence] = field(default_factory=list)
    dhcp_server: str | None = None
    dhcp_offer_source: str | None = None
    dhcp_expected_server: str | None = None
    rogue_dhcp_suspected: bool | None = None
    rogue_dhcp_detected: bool | None = None
    wrong_server_seen: bool | None = None
    evidence_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ServiceTruth:
    service_ip: str | None = None
    gateway_reachable: bool | None = None
    dns_reachable: bool | None = None
    customer_traffic_seen: bool | None = None
    management_plane_only: bool | None = None
    evidence_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UnitEvidence:
    unit: str
    inventory_truth: InventoryTruth = field(default_factory=InventoryTruth)
    physical_truth: PhysicalTruth = field(default_factory=PhysicalTruth)
    l2_truth: L2Truth = field(default_factory=L2Truth)
    controller_truth: ControllerTruth = field(default_factory=ControllerTruth)
    auth_truth: AuthTruth = field(default_factory=AuthTruth)
    dhcp_truth: DhcpTruth = field(default_factory=DhcpTruth)
    service_truth: ServiceTruth = field(default_factory=ServiceTruth)
    contradictions: list[ContradictionRecord] = field(default_factory=list)
    unknowns: list[UnknownRecord] = field(default_factory=list)
    stale_data_sources: list[StaleSourceRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError("UnitEvidence requires a non-empty unit string")

    def add_contradiction(
        self,
        *,
        layer: str,
        summary: str,
        details: str | None = None,
        sources: list[str] | None = None,
    ) -> None:
        self.contradictions.append(
            ContradictionRecord(
                layer=layer,
                summary=summary,
                details=details,
                sources=list(sources or []),
            )
        )

    def add_unknown(
        self,
        *,
        layer: str,
        field_name: str,
        reason: str,
        sources_checked: list[str] | None = None,
    ) -> None:
        self.unknowns.append(
            UnknownRecord(
                layer=layer,
                field_name=field_name,
                reason=reason,
                sources_checked=list(sources_checked or []),
            )
        )

    def add_stale_source(
        self,
        *,
        layer: str,
        source: str,
        last_seen: str | None = None,
        reason: str | None = None,
    ) -> None:
        self.stale_data_sources.append(
            StaleSourceRecord(
                layer=layer,
                source=source,
                last_seen=last_seen,
                reason=reason,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RealityModel:
    unit: str
    inventory_truth: dict[str, Any]
    physical_truth: dict[str, Any]
    l2_truth: dict[str, Any]
    controller_truth: dict[str, Any]
    auth_truth: dict[str, Any]
    dhcp_truth: dict[str, Any]
    service_truth: dict[str, Any]
    contradictions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    stale_data_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_timestamp(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _append_unique(items: list[str], value: str | None) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _expected_port_was_checked(evidence: UnitEvidence) -> bool | None:
    if evidence.l2_truth.expected_port_checked is not None:
        return evidence.l2_truth.expected_port_checked
    if evidence.inventory_truth.expected_port:
        if evidence.l2_truth.live_port == evidence.inventory_truth.expected_port:
            return True
        if evidence.l2_truth.any_mac_on_expected_port is not None:
            return True
    return None


def _switch_scope_was_checked(evidence: UnitEvidence) -> bool | None:
    if evidence.l2_truth.switch_scope_checked is not None:
        return evidence.l2_truth.switch_scope_checked
    if evidence.inventory_truth.expected_switch and (
        evidence.l2_truth.live_switch == evidence.inventory_truth.expected_switch
        or bool(evidence.l2_truth.expected_mac_locations)
    ):
        return True
    return None


def _global_scope_was_checked(evidence: UnitEvidence) -> bool | None:
    if evidence.l2_truth.global_scope_checked is not None:
        return evidence.l2_truth.global_scope_checked
    if evidence.l2_truth.expected_mac_locations:
        return True
    if evidence.l2_truth.live_mac_seen is not None or evidence.l2_truth.expected_mac_seen is not None:
        return True
    return None


def _historical_scope_was_checked(evidence: UnitEvidence) -> bool | None:
    if evidence.l2_truth.historical_checked is not None:
        return evidence.l2_truth.historical_checked
    if evidence.l2_truth.historical_locations:
        return True
    return None


def build_reality_model(
    evidence: UnitEvidence,
    *,
    controller_stale_after_seconds: int = 3600,
    bridge_stale_after_seconds: int = 900,
) -> RealityModel:
    contradictions: list[str] = []
    unknowns: list[str] = []
    stale_data_sources: list[str] = []

    for item in evidence.contradictions:
        _append_unique(contradictions, item.summary)
    for item in evidence.unknowns:
        _append_unique(unknowns, f"{item.layer}.{item.field_name}: {item.reason}")
    for item in evidence.stale_data_sources:
        details = f"{item.layer}.{item.source}"
        if item.reason:
            details = f"{details}: {item.reason}"
        _append_unique(stale_data_sources, details)

    expected_mac = str(evidence.inventory_truth.expected_mac or "").strip()
    expected_pppoe = str(evidence.inventory_truth.expected_pppoe or "").strip()
    live_mac_present = evidence.l2_truth.live_mac_seen is True or evidence.l2_truth.expected_mac_seen is True
    pppoe_active = evidence.auth_truth.pppoe_active is True
    pppoe_failure_seen = evidence.auth_truth.pppoe_failed_attempts_seen is True or bool(evidence.auth_truth.pppoe_failures)
    pppoe_no_attempt = evidence.auth_truth.pppoe_no_attempt_evidence is True
    dhcp_expected = evidence.dhcp_truth.dhcp_expected is True
    dhcp_offer_source = str(evidence.dhcp_truth.dhcp_offer_source or "").strip()
    dhcp_expected_server = str(
        evidence.dhcp_truth.dhcp_expected_server or evidence.dhcp_truth.dhcp_server or ""
    ).strip()

    if evidence.controller_truth.controller_online is True and not live_mac_present:
        _append_unique(
            contradictions,
            "Controller says the device is online, but no live MAC is seen anywhere.",
        )
    if live_mac_present and expected_pppoe and not pppoe_active and not pppoe_failure_seen and pppoe_no_attempt:
        _append_unique(
            contradictions,
            "MAC is present at L2, but PPPoE is expected and no PPPoE attempt is visible.",
        )
    if pppoe_active and evidence.controller_truth.controller_online is False:
        _append_unique(
            contradictions,
            "PPPoE is active while the controller reports the device offline.",
        )
    if dhcp_offer_source and dhcp_expected_server and dhcp_offer_source.lower() != dhcp_expected_server.lower():
        _append_unique(
            contradictions,
            "DHCP offers are coming from an unexpected server.",
        )

    expected_port_checked = _expected_port_was_checked(evidence)
    switch_scope_checked = _switch_scope_was_checked(evidence)
    global_scope_checked = _global_scope_was_checked(evidence)
    historical_checked = _historical_scope_was_checked(evidence)

    if expected_mac and expected_port_checked is None:
        _append_unique(
            unknowns,
            "l2_truth.expected_port_checked: expected port search was not recorded.",
        )
    if expected_mac and switch_scope_checked is None:
        _append_unique(
            unknowns,
            "l2_truth.switch_scope_checked: whole-switch MAC search was not recorded.",
        )
    if expected_mac and global_scope_checked is None:
        _append_unique(
            unknowns,
            "l2_truth.global_scope_checked: all-switch MAC search was not recorded.",
        )
    if expected_mac and historical_checked is None:
        _append_unique(
            unknowns,
            "l2_truth.historical_checked: historical MAC sightings were not checked.",
        )

    if evidence.inventory_truth.expected_port and evidence.physical_truth.port_up is None:
        _append_unique(
            unknowns,
            "physical_truth.port_up: expected port state is unknown.",
        )
    if evidence.inventory_truth.expected_port and not str(evidence.physical_truth.port_speed or "").strip():
        _append_unique(
            unknowns,
            "physical_truth.port_speed: expected port speed is unknown.",
        )
    if expected_pppoe and evidence.auth_truth.pppoe_active is None and evidence.auth_truth.pppoe_failed_attempts_seen is None:
        _append_unique(
            unknowns,
            "auth_truth.pppoe_logs: PPPoE session and failure evidence are both unknown.",
        )
    if dhcp_expected and evidence.dhcp_truth.dhcp_discovers_seen is None and evidence.dhcp_truth.discovers_seen is None:
        _append_unique(
            unknowns,
            "dhcp_truth.dhcp_discovers_seen: DHCP discover evidence is unknown.",
        )
    if dhcp_expected and evidence.dhcp_truth.dhcp_offers_seen is None and evidence.dhcp_truth.offers_seen is None:
        _append_unique(
            unknowns,
            "dhcp_truth.dhcp_offers_seen: DHCP offer evidence is unknown.",
        )
    if evidence.controller_truth.controller_seen is True and not evidence.controller_truth.controller_last_seen_timestamp:
        _append_unique(
            unknowns,
            "controller_truth.controller_last_seen_timestamp: controller freshness timestamp is missing.",
        )

    controller_age = evidence.controller_truth.controller_data_age_seconds
    if evidence.controller_truth.controller_seen is True:
        if evidence.controller_truth.controller_stale is True:
            _append_unique(
                stale_data_sources,
                "controller_truth.controller_snapshot: controller data is marked stale.",
            )
        elif controller_age is not None and int(controller_age or 0) > controller_stale_after_seconds:
            _append_unique(
                stale_data_sources,
                f"controller_truth.controller_snapshot: controller data age {int(controller_age)}s exceeds freshness threshold.",
            )
        elif not evidence.controller_truth.controller_last_seen_timestamp:
            _append_unique(
                stale_data_sources,
                "controller_truth.controller_snapshot: controller timestamp is missing, so freshness is unproven.",
            )

    live_l2_times = [
        _parse_timestamp(location.learned_at)
        for location in evidence.l2_truth.expected_mac_locations
        if location.learned_at
    ]
    live_l2_times = [value for value in live_l2_times if value is not None]
    if live_l2_times:
        newest = max(live_l2_times)
        age_seconds = int((datetime.now(timezone.utc) - newest).total_seconds())
        if age_seconds > bridge_stale_after_seconds:
            _append_unique(
                stale_data_sources,
                f"l2_truth.bridge_table: newest live MAC sighting is {age_seconds}s old.",
            )
    elif evidence.l2_truth.historical_locations:
        _append_unique(
            stale_data_sources,
            "l2_truth.historical_locations: only historical MAC sightings are available.",
        )

    inventory_truth = asdict(evidence.inventory_truth)
    physical_truth = asdict(evidence.physical_truth)
    l2_truth = asdict(evidence.l2_truth)
    controller_truth = asdict(evidence.controller_truth)
    auth_truth = asdict(evidence.auth_truth)
    dhcp_truth = asdict(evidence.dhcp_truth)
    service_truth = asdict(evidence.service_truth)

    l2_truth["expected_port_checked"] = expected_port_checked
    l2_truth["switch_scope_checked"] = switch_scope_checked
    l2_truth["global_scope_checked"] = global_scope_checked
    l2_truth["historical_checked"] = historical_checked

    return RealityModel(
        unit=evidence.unit,
        inventory_truth=inventory_truth,
        physical_truth=physical_truth,
        l2_truth=l2_truth,
        controller_truth=controller_truth,
        auth_truth=auth_truth,
        dhcp_truth=dhcp_truth,
        service_truth=service_truth,
        contradictions=contradictions,
        unknowns=unknowns,
        stale_data_sources=stale_data_sources,
    )
