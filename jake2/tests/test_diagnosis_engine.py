from __future__ import annotations

from diagnosis.engine import diagnose, diagnose_unit
from diagnosis.evidence import (
    AuthAttemptEvidence,
    AuthTruth,
    ControllerTruth,
    DhcpTruth,
    InventoryTruth,
    L2LocationEvidence,
    L2Truth,
    PhysicalTruth,
    ServiceTruth,
    UnitEvidence,
    build_reality_model,
)


def _base_evidence(unit: str = "000007.001/1A") -> UnitEvidence:
    return UnitEvidence(
        unit=unit,
        inventory_truth=InventoryTruth(
            expected_make="TP-Link",
            expected_model="HC220",
            expected_mac="aa:11:22:33:44:55",
            expected_pppoe="subscriber-1A",
            expected_switch="000007.001.SW01",
            expected_port="ether7",
            expected_vlan="20",
            evidence_sources=["inventory"],
        ),
        physical_truth=PhysicalTruth(
            port_up=True,
            port_speed="1G",
            port_duplex="full",
            evidence_sources=["physical"],
        ),
        l2_truth=L2Truth(
            expected_mac_seen=False,
            live_mac_seen=False,
            expected_port_checked=True,
            switch_scope_checked=True,
            global_scope_checked=True,
            historical_checked=True,
            evidence_sources=["bridge"],
        ),
        controller_truth=ControllerTruth(
            controller_seen=False,
            controller_online=False,
            mapping_matches_inventory=True,
            evidence_sources=["controller"],
        ),
        auth_truth=AuthTruth(
            pppoe_active=False,
            pppoe_failed_attempts_seen=False,
            pppoe_no_attempt_evidence=False,
            evidence_sources=["pppoe"],
        ),
        dhcp_truth=DhcpTruth(
            dhcp_expected=False,
            discovers_seen=0,
            offers_seen=0,
            evidence_sources=["dhcp"],
        ),
        service_truth=ServiceTruth(
            customer_traffic_seen=False,
            evidence_sources=["service"],
        ),
    )


def test_diagnose_unit_matches_reality_model_contract_for_equivalent_input() -> None:
    evidence = _base_evidence()
    evidence.l2_truth.expected_mac_seen = True
    evidence.l2_truth.live_mac_seen = True
    evidence.l2_truth.live_mac = "aa:11:22:33:44:55"
    evidence.auth_truth.pppoe_no_attempt_evidence = True

    from_evidence = diagnose_unit(evidence)
    from_reality = diagnose(build_reality_model(evidence))

    assert from_evidence.to_dict() == from_reality.to_dict()


def test_diagnose_unit_live_mac_still_prevents_not_seen_anywhere() -> None:
    evidence = _base_evidence()
    evidence.l2_truth.expected_mac_seen = True
    evidence.l2_truth.live_mac_seen = True
    evidence.l2_truth.live_mac = "aa:11:22:33:44:55"
    evidence.l2_truth.expected_mac_locations = [
        L2LocationEvidence(mac="aa:11:22:33:44:55", switch="000007.001.SW01", port="ether7", source="bridge")
    ]
    evidence.auth_truth.pppoe_no_attempt_evidence = True

    diagnosis = diagnose_unit(evidence)

    assert diagnosis.primary_status != "NOT_SEEN_ANYWHERE"
    assert "unplugged" not in diagnosis.explanation.lower()


def test_diagnose_unit_contradictions_still_produce_needs_more_evidence() -> None:
    evidence = _base_evidence()
    evidence.add_contradiction(
        layer="controller_truth",
        summary="Controller says online while live MAC search found nothing",
        sources=["controller", "bridge"],
    )

    diagnosis = diagnose_unit(evidence)

    assert diagnosis.primary_status == "NEEDS_MORE_EVIDENCE"
    assert diagnosis.confidence == "low"
    assert diagnosis.contradictions


def test_diagnose_unit_degraded_physical_evidence_still_works() -> None:
    evidence = _base_evidence()
    evidence.l2_truth.expected_mac_seen = True
    evidence.l2_truth.live_mac_seen = True
    evidence.l2_truth.live_mac = "aa:11:22:33:44:55"
    evidence.physical_truth.port_speed = "100M"
    evidence.physical_truth.port_flaps = 3
    evidence.physical_truth.port_errors = {"crc": 5}

    diagnosis = diagnose_unit(evidence)

    assert diagnosis.primary_status == "DEGRADED_LINK_BAD_CABLE_SUSPECTED"
    assert diagnosis.dispatch_required is True


def test_diagnose_unit_equivalent_to_reality_model_for_pppoe_failure() -> None:
    evidence = _base_evidence()
    evidence.l2_truth.expected_mac_seen = True
    evidence.l2_truth.live_mac_seen = True
    evidence.l2_truth.live_mac = "aa:11:22:33:44:55"
    evidence.auth_truth.pppoe_failed_attempts_seen = True
    evidence.auth_truth.pppoe_failures = [
        AuthAttemptEvidence(username="subscriber-1A", outcome="failure", reason="auth_reject", source="loki")
    ]

    assert diagnose_unit(evidence).to_dict() == diagnose(build_reality_model(evidence)).to_dict()
