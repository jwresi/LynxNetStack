from __future__ import annotations

from datetime import datetime, timedelta, timezone

from diagnosis.evidence import (
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


def _base_evidence(unit: str = "000007.004/02A") -> UnitEvidence:
    now = datetime.now(timezone.utc)
    return UnitEvidence(
        unit=unit,
        inventory_truth=InventoryTruth(
            expected_mac="30:68:93:c1:99:5d",
            expected_pppoe="NYCHA1145LenoxRd2A",
            expected_switch="000007.004.SW01",
            expected_port="ether6",
            expected_make="TP-Link HC220-G5",
            evidence_sources=["inventory_csv"],
        ),
        physical_truth=PhysicalTruth(
            port_up=True,
            port_speed="1G",
            port_duplex="full",
            evidence_sources=["port_observations"],
        ),
        l2_truth=L2Truth(
            expected_port_checked=True,
            switch_scope_checked=True,
            global_scope_checked=True,
            historical_checked=True,
            expected_mac_seen=True,
            live_mac_seen=True,
            live_mac="30:68:93:c1:99:5d",
            live_switch="000007.004.SW01",
            live_port="ether6",
            expected_mac_locations=[
                L2LocationEvidence(
                    mac="30:68:93:c1:99:5d",
                    switch="000007.004.SW01",
                    port="ether6",
                    learned_at=(now - timedelta(minutes=2)).isoformat(),
                    source="bridge_table",
                )
            ],
            evidence_sources=["bridge/live_lookup"],
        ),
        controller_truth=ControllerTruth(
            controller_seen=True,
            controller_online=True,
            controller_mac="30:68:93:c1:99:5d",
            controller_unit="2A",
            controller_last_seen_timestamp="2026-04-25T11:58:00+00:00",
            controller_data_age_seconds=120,
            controller_stale=False,
            evidence_sources=["controller_snapshot"],
        ),
        auth_truth=AuthTruth(
            pppoe_active=True,
            pppoe_username="NYCHA1145LenoxRd2A",
            pppoe_failed_attempts_seen=False,
            pppoe_no_attempt_evidence=False,
            evidence_sources=["pppoe_diagnostics"],
        ),
        dhcp_truth=DhcpTruth(
            dhcp_expected=False,
            evidence_sources=[],
        ),
        service_truth=ServiceTruth(
            customer_traffic_seen=True,
            gateway_reachable=True,
            evidence_sources=["service_probe"],
        ),
    )


def test_reality_model_full_data_present_has_no_diagnosis_fields() -> None:
    reality = build_reality_model(_base_evidence())

    payload = reality.to_dict()

    assert reality.contradictions == []
    assert reality.unknowns == []
    assert reality.stale_data_sources == []
    assert "primary_status" not in payload
    assert "dispatch_required" not in payload
    assert payload["l2_truth"]["global_scope_checked"] is True


def test_reality_model_records_missing_l1_data() -> None:
    evidence = _base_evidence()
    evidence.physical_truth.port_up = None
    evidence.physical_truth.port_speed = None

    reality = build_reality_model(evidence)

    assert "physical_truth.port_up: expected port state is unknown." in reality.unknowns
    assert "physical_truth.port_speed: expected port speed is unknown." in reality.unknowns


def test_reality_model_records_missing_pppoe_logs() -> None:
    evidence = _base_evidence()
    evidence.auth_truth.pppoe_active = None
    evidence.auth_truth.pppoe_failed_attempts_seen = None
    evidence.auth_truth.pppoe_no_attempt_evidence = None

    reality = build_reality_model(evidence)

    assert "auth_truth.pppoe_logs: PPPoE session and failure evidence are both unknown." in reality.unknowns


def test_reality_model_records_missing_dhcp_data() -> None:
    evidence = _base_evidence()
    evidence.auth_truth.pppoe_active = False
    evidence.dhcp_truth.dhcp_expected = True
    evidence.dhcp_truth.dhcp_discovers_seen = None
    evidence.dhcp_truth.dhcp_offers_seen = None

    reality = build_reality_model(evidence)

    assert "dhcp_truth.dhcp_discovers_seen: DHCP discover evidence is unknown." in reality.unknowns
    assert "dhcp_truth.dhcp_offers_seen: DHCP offer evidence is unknown." in reality.unknowns


def test_reality_model_detects_l2_present_without_auth_attempt() -> None:
    evidence = _base_evidence()
    evidence.auth_truth.pppoe_active = False
    evidence.auth_truth.pppoe_failed_attempts_seen = False
    evidence.auth_truth.pppoe_no_attempt_evidence = True

    reality = build_reality_model(evidence)

    assert "MAC is present at L2, but PPPoE is expected and no PPPoE attempt is visible." in reality.contradictions


def test_reality_model_detects_controller_vs_switch_contradiction() -> None:
    evidence = _base_evidence()
    evidence.l2_truth.expected_mac_seen = False
    evidence.l2_truth.live_mac_seen = False
    evidence.l2_truth.live_mac = None
    evidence.l2_truth.expected_mac_locations = []
    evidence.service_truth.customer_traffic_seen = False
    evidence.service_truth.gateway_reachable = None
    evidence.auth_truth.pppoe_active = False

    reality = build_reality_model(evidence)

    assert "Controller says the device is online, but no live MAC is seen anywhere." in reality.contradictions


def test_reality_model_marks_stale_controller_data() -> None:
    evidence = _base_evidence()
    evidence.controller_truth.controller_data_age_seconds = 7200
    evidence.controller_truth.controller_stale = True
    evidence.controller_truth.controller_last_seen_timestamp = "2026-04-25T09:00:00+00:00"

    reality = build_reality_model(evidence)

    assert "controller_truth.controller_snapshot: controller data is marked stale." in reality.stale_data_sources


def test_reality_model_records_missing_global_search_steps() -> None:
    evidence = _base_evidence()
    evidence.l2_truth.expected_port_checked = None
    evidence.l2_truth.switch_scope_checked = None
    evidence.l2_truth.global_scope_checked = None
    evidence.l2_truth.historical_checked = None
    evidence.l2_truth.expected_mac_seen = None
    evidence.l2_truth.live_mac_seen = None
    evidence.l2_truth.live_port = None
    evidence.l2_truth.live_switch = None
    evidence.l2_truth.any_mac_on_expected_port = None
    evidence.l2_truth.expected_mac_locations = []

    reality = build_reality_model(evidence)

    assert "l2_truth.expected_port_checked: expected port search was not recorded." in reality.unknowns
    assert "l2_truth.switch_scope_checked: whole-switch MAC search was not recorded." in reality.unknowns
    assert "l2_truth.global_scope_checked: all-switch MAC search was not recorded." in reality.unknowns
    assert "l2_truth.historical_checked: historical MAC sightings were not checked." in reality.unknowns
