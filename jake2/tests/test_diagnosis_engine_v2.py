from __future__ import annotations

from diagnosis.engine import diagnose
from diagnosis.evidence import RealityModel


def _base_reality(unit: str = "000007.004/02A") -> RealityModel:
    return RealityModel(
        unit=unit,
        inventory_truth={
            "expected_mac": "30:68:93:c1:99:5d",
            "expected_pppoe": "NYCHA1145LenoxRd2A",
            "expected_switch": "000007.004.SW01",
            "expected_port": "ether6",
            "expected_vlan": "20",
            "expected_make": "TP-Link HC220-G5",
            "evidence_sources": ["inventory_csv"],
        },
        physical_truth={
            "port_up": True,
            "port_speed": "1G",
            "link_flaps": 0,
            "rx_errors": 0,
            "tx_errors": 0,
            "fcs_errors": 0,
            "crc_errors": 0,
            "evidence_sources": ["port_observations"],
        },
        l2_truth={
            "expected_port_checked": True,
            "switch_scope_checked": True,
            "global_scope_checked": True,
            "historical_checked": True,
            "expected_mac_seen": True,
            "live_mac_seen": True,
            "live_mac": "30:68:93:c1:99:5d",
            "live_switch": "000007.004.SW01",
            "live_port": "ether6",
            "any_mac_on_expected_port": True,
            "expected_mac_locations": [{"mac": "30:68:93:c1:99:5d", "switch": "000007.004.SW01", "port": "ether6"}],
            "evidence_sources": ["bridge/live_lookup"],
        },
        controller_truth={
            "controller_seen": True,
            "mapping_matches_inventory": True,
            "controller_online": True,
            "controller_mac": "30:68:93:c1:99:5d",
            "controller_unit": "2A",
            "controller_stale": False,
            "evidence_sources": ["controller_snapshot"],
        },
        auth_truth={
            "pppoe_active": False,
            "pppoe_failed_attempts_seen": False,
            "pppoe_no_attempt_evidence": False,
            "pppoe_failure_reason": None,
            "pppoe_failures": [],
            "evidence_sources": ["pppoe_diagnostics"],
        },
        dhcp_truth={
            "dhcp_expected": False,
            "dhcp_discovers_seen": 0,
            "dhcp_offers_seen": 0,
            "rogue_dhcp_detected": False,
            "evidence_sources": ["dhcp_behavior"],
        },
        service_truth={
            "customer_traffic_seen": False,
            "gateway_reachable": False,
            "service_ip": None,
            "evidence_sources": ["service_probe"],
        },
        contradictions=[],
        unknowns=[],
        stale_data_sources=[],
    )


def test_l2_present_no_pppoe_attempt_yields_pppoe_no_attempt() -> None:
    reality = _base_reality()
    reality.auth_truth["pppoe_no_attempt_evidence"] = True

    diagnosis = diagnose(reality)

    assert diagnosis.primary_status == "PPPoE_NO_ATTEMPT"
    assert diagnosis.dispatch_required is False


def test_l2_present_pppoe_failure_yields_auth_failure() -> None:
    reality = _base_reality()
    reality.auth_truth["pppoe_failed_attempts_seen"] = True
    reality.auth_truth["pppoe_failure_reason"] = "auth_failed"

    diagnosis = diagnose(reality)

    assert diagnosis.primary_status == "PPPoE_AUTH_FAILURE"
    assert diagnosis.dispatch_required is False


def test_no_mac_anywhere_with_full_search_yields_not_seen_anywhere() -> None:
    reality = _base_reality()
    reality.l2_truth["expected_mac_seen"] = False
    reality.l2_truth["live_mac_seen"] = False
    reality.l2_truth["live_mac"] = None
    reality.l2_truth["expected_mac_locations"] = []
    reality.controller_truth["controller_online"] = False
    reality.controller_truth["controller_seen"] = False

    diagnosis = diagnose(reality)

    assert diagnosis.primary_status == "NOT_SEEN_ANYWHERE"
    assert diagnosis.dispatch_required is True


def test_mac_present_with_100m_link_yields_degraded_link() -> None:
    reality = _base_reality()
    reality.physical_truth["port_speed"] = "100M"

    diagnosis = diagnose(reality)

    assert diagnosis.primary_status == "DEGRADED_LINK_BAD_CABLE_SUSPECTED"
    assert diagnosis.dispatch_required is True


def test_controller_mismatch_is_backend_only() -> None:
    reality = _base_reality()
    reality.controller_truth["mapping_matches_inventory"] = False

    diagnosis = diagnose(reality)

    assert diagnosis.primary_status == "CONTROLLER_MAPPING_MISMATCH"
    assert diagnosis.dispatch_required is False
    assert diagnosis.backend_actions


def test_wrong_mac_on_port_yields_device_swapped() -> None:
    reality = _base_reality()
    reality.l2_truth["live_mac"] = "30:68:93:c1:aa:aa"
    reality.l2_truth["expected_mac_locations"] = [
        {"mac": "30:68:93:c1:99:5d", "switch": "000007.004.SW02", "port": "ether9"}
    ]

    diagnosis = diagnose(reality)

    assert diagnosis.primary_status == "DEVICE_SWAPPED_OR_WRONG_UNIT"


def test_contradictions_yield_needs_more_evidence() -> None:
    reality = _base_reality()
    reality.contradictions = ["Controller says online but no live MAC is seen anywhere."]
    reality.l2_truth["expected_mac_seen"] = False
    reality.l2_truth["live_mac_seen"] = False
    reality.l2_truth["live_mac"] = None
    reality.l2_truth["expected_mac_locations"] = []

    diagnosis = diagnose(reality)

    assert diagnosis.primary_status == "NEEDS_MORE_EVIDENCE"
    assert diagnosis.confidence == "low"


def test_l2_present_no_attempt_contradiction_still_classifies_pppoe_no_attempt() -> None:
    reality = _base_reality()
    reality.auth_truth["pppoe_no_attempt_evidence"] = True
    reality.contradictions = ["MAC is present at L2, but PPPoE is expected and no PPPoE attempt is visible."]

    diagnosis = diagnose(reality)

    assert diagnosis.primary_status == "PPPoE_NO_ATTEMPT"
    assert diagnosis.confidence == "medium"
    assert diagnosis.contradictions


def test_strong_device_swap_evidence_can_be_high_confidence() -> None:
    reality = _base_reality()
    reality.l2_truth["expected_mac_seen"] = False
    reality.l2_truth["expected_mac_locations"] = [
        {"mac": "30:68:93:c1:99:5d", "switch": "000007.004.SW02", "port": "ether9"}
    ]
    reality.l2_truth["live_mac"] = "de:ad:be:ef:00:01"
    reality.l2_truth["macs_on_expected_port"] = ["de:ad:be:ef:00:01"]
    reality.l2_truth["any_mac_on_expected_port"] = True
    reality.contradictions = ["MAC is present at L2, but PPPoE is expected and no PPPoE attempt is visible."]
    reality.auth_truth["pppoe_no_attempt_evidence"] = True

    diagnosis = diagnose(reality)

    assert diagnosis.primary_status == "DEVICE_SWAPPED_OR_WRONG_UNIT"
    assert diagnosis.confidence == "high"
    assert diagnosis.contradictions


def test_incomplete_search_yields_needs_more_evidence() -> None:
    reality = _base_reality()
    reality.l2_truth["expected_mac_seen"] = False
    reality.l2_truth["live_mac_seen"] = False
    reality.l2_truth["live_mac"] = None
    reality.l2_truth["expected_mac_locations"] = []
    reality.l2_truth["global_scope_checked"] = None

    diagnosis = diagnose(reality)

    assert diagnosis.primary_status == "NEEDS_MORE_EVIDENCE"
    assert diagnosis.dispatch_required is False
