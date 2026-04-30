from __future__ import annotations

from pathlib import Path

from audits.jake_audit_workbook import AuditRow, LiveContext
from diagnosis.engine import diagnose
from diagnosis.evidence import build_reality_model
from diagnosis.workbook_adapter import (
    WORKBOOK_STATUS_BY_PRIMARY_STATUS,
    assert_workbook_status_mapping_complete,
    build_workbook_diagnosis_result,
)
from mcp import jake_ops_mcp as opsmod


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "audit"


def _configure_audit_fixture_env(monkeypatch) -> None:
    monkeypatch.setenv("JAKE_NYCHA_INFO_CSV", str(FIXTURE_DIR / "nycha_info_fixture.csv"))
    monkeypatch.setenv("JAKE_TAUC_AUDIT_CSV", str(FIXTURE_DIR / "tauc_nycha_audit_fixture.csv"))
    monkeypatch.setenv("JAKE_VILO_INVENTORY_SNAPSHOT", str(FIXTURE_DIR / "vilo_inventory_fixture.json"))
    opsmod.NYCHA_INFO_CSV = Path(str(FIXTURE_DIR / "nycha_info_fixture.csv"))
    opsmod.TAUC_NYCHA_AUDIT_CSV = Path(str(FIXTURE_DIR / "tauc_nycha_audit_fixture.csv"))
    opsmod.load_nycha_info_rows.cache_clear()
    opsmod.load_tauc_nycha_audit_rows.cache_clear()


def _row_case(unit_label: str, mac: str, switch_port: str, pppoe_unit: str | None = None) -> AuditRow:
    return AuditRow(
        unit_key=unit_label,
        unit_label=unit_label,
        mac_cpe=mac,
        pppoe_unit=pppoe_unit or unit_label,
        notes="Good",
        image_ap_make="",
        image_ap_sticker_apartment="",
        image_ap_mac="",
        inventory_mac_verification="",
        implication="",
        action="None",
        switch_port=switch_port,
    )


def _source_row(unit_label: str, mac: str, ap_make: str, serial: str, pppoe_unit: str | None = None) -> dict[str, str]:
    return {
        "Unit": unit_label,
        "PPPoE": f"site-{pppoe_unit or unit_label}",
        "MAC Address": mac,
        "AP Make": ap_make,
        "AP Serial Number": serial,
    }


def _live_context(
    *,
    port_map: dict[str, list[str]],
    controller_verification_by_mac: dict[str, dict] | None = None,
    online_units_by_token: dict[str, dict] | None = None,
    exact_matches_by_unit: dict[str, dict] | None = None,
    failures: list[dict[str, str]] | None = None,
) -> LiveContext:
    switch_identity = "000007.001.SW01"
    return LiveContext(
        building_id="000007.001",
        site_id="000007",
        online_units_by_token=online_units_by_token or {},
        exact_matches_by_unit=exact_matches_by_unit or {},
        active_alert_count=0,
        building_device_count=7,
        site_online_count=7,
        inferred_switch_identity=switch_identity,
        live_port_macs_by_interface=port_map,
        switch_identities_by_label_prefix={"SW1": switch_identity},
        live_port_macs_by_switch_identity={switch_identity: port_map},
        controller_verification_by_mac=controller_verification_by_mac or {},
        live_failures=failures or [],
        building_has_db_bridge_hosts=bool(port_map),
    )


def test_live_mac_prevents_unplugged_label(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "Vilo", "VILO-1A")
    live = _live_context(
        port_map={"ether1": ["aa:11:22:33:44:55"]},
        controller_verification_by_mac={},
    )

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.reality.unit == result.evidence.unit
    assert result.diagnosis.to_dict() == diagnose(result.reality).to_dict()
    assert result.workbook_status != "UNPLUGGED / BAD CABLE"
    assert result.diagnosis.primary_status in {"L2_PRESENT_NO_SERVICE", "PPPoE_NO_ATTEMPT"}


def test_no_mac_anywhere_maps_to_not_seen_anywhere(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "Vilo", "VILO-1A")
    live = _live_context(port_map={})
    live.historical_search_completed = True

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.diagnosis.primary_status == "NOT_SEEN_ANYWHERE"
    assert result.workbook_status == "NOT SEEN ANYWHERE"
    assert result.dispatch_required is True
    assert "Live MAC not seen" in result.evidence_summary


def test_controller_mismatch_maps_backend_first(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "TP-Link", "HC220-1A")
    live = _live_context(
        port_map={"ether1": ["aa:11:22:33:44:55"]},
        controller_verification_by_mac={
            "aa:11:22:33:44:55": {
                "status": "mismatch",
                "label": "TAUC audit mismatch",
                "snapshot_row": {"tauc_mac": "AA:11:22:33:44:55", "expected_unit": "1B"},
            }
        },
    )
    live.historical_search_completed = True

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.diagnosis.primary_status == "CONTROLLER_MAPPING_MISMATCH"
    assert result.workbook_status == "CONTROLLER MISMATCH"
    assert result.dispatch_required is False
    assert result.backend_action


def test_wrong_mac_on_expected_port_is_not_bad_cable(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1D", "30:22:33:44:55:70", "SW1-4")
    source = _source_row("1D", "30:22:33:44:55:70", "Vilo", "VILO-1D")
    live = _live_context(port_map={"ether4": ["aa:11:22:33:44:55"]})

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.diagnosis.primary_status in {"DEVICE_SWAPPED_OR_WRONG_UNIT", "INVENTORY_MAC_MISMATCH"}
    assert result.workbook_status in {"WRONG UNIT / DEVICE SWAPPED", "INVENTORY MAC MISMATCH"}
    assert result.workbook_status != "UNPLUGGED / BAD CABLE"


def test_degraded_cable_maps_to_workbook_label(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "TP-Link", "HC220-1A")
    live = _live_context(port_map={"ether1": ["aa:11:22:33:44:55"]})
    live.port_observations_by_unit = {
        "1A": {"port_speed": "100M", "port_flaps": 2, "port_errors": {"crc": 4}, "port_up": True}
    }

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.diagnosis.primary_status == "DEGRADED_LINK_BAD_CABLE_SUSPECTED"
    assert result.workbook_status == "DEGRADED LINK / BAD CABLE SUSPECTED"
    assert result.dispatch_required is True


def test_workbook_adapter_carries_enriched_evidence(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "TP-Link", "HC220-1A")
    live = _live_context(port_map={"ether1": ["aa:11:22:33:44:55"]})
    live.captured_at_timestamp = "2026-04-23T09:00:00Z"
    live.port_observations_by_unit = {
        "1A": {
            "port_speed": "100M",
            "link_partner_speed": "1G",
            "crc_errors": 4,
            "link_flaps": 2,
            "link_flaps_window_seconds": 300,
            "port_up": True,
        }
    }
    live.auth_observations_by_unit = {
        "1A": {
            "pppoe_failed_attempts_seen": True,
            "pppoe_failure_reason": "auth_failed",
            "pppoe_last_attempt_timestamp": "2026-04-23T08:58:00Z",
            "evidence_sources": ["loki_pppoe_logs"],
        }
    }
    live.dhcp_observations_by_unit = {
        "1A": {
            "dhcp_expected": True,
            "dhcp_discovers_seen": 1,
            "dhcp_offers_seen": 1,
            "dhcp_offer_source": "10.0.0.254",
            "dhcp_expected_server": "10.0.0.1",
            "rogue_dhcp_detected": True,
            "evidence_sources": ["dhcp_summary"],
        }
    }
    live.controller_verification_by_mac = {
        "aa:11:22:33:44:55": {
            "status": "match",
            "label": "TAUC audit match",
            "snapshot_row": {"tauc_mac": "AA:11:22:33:44:55", "expected_unit": "1A", "last_seen": "2026-04-23T08:30:00Z"},
        }
    }

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.reality.unit == "1A"
    assert result.evidence.physical_truth.link_partner_speed == "1G"
    assert result.evidence.physical_truth.crc_errors == 4
    assert result.evidence.physical_truth.link_flaps == 2
    assert result.evidence.auth_truth.pppoe_failure_reason == "auth_failed"
    assert result.evidence.auth_truth.pppoe_last_attempt_timestamp == "2026-04-23T08:58:00Z"
    assert result.evidence.dhcp_truth.dhcp_offer_source == "10.0.0.254"
    assert result.evidence.dhcp_truth.dhcp_expected_server == "10.0.0.1"
    assert result.evidence.dhcp_truth.rogue_dhcp_detected is True
    assert result.evidence.controller_truth.controller_data_age_seconds == 1800
    assert result.evidence.controller_truth.controller_stale is True
    assert any(item.startswith("controller_truth.controller_snapshot") for item in result.reality.stale_data_sources)
    assert result.diagnosis.to_dict() == diagnose(result.reality).to_dict()


def test_workbook_adapter_normalizes_zero_padded_units_for_live_observations(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("02A", "AA:11:22:33:44:55", "SW1-6")
    source = _source_row("02A", "AA:11:22:33:44:55", "TP-Link", "HC220-2A")
    live = _live_context(port_map={"ether6": ["aa:11:22:33:44:55"]})
    live.port_observations_by_unit = {
        "2A": {"port_speed": "100M", "port_up": True}
    }
    live.auth_observations_by_unit = {
        "2A": {
            "pppoe_active": False,
            "pppoe_failed_attempts_seen": False,
            "pppoe_no_attempt_evidence": True,
            "evidence_sources": ["pppoe_diagnostics"],
        }
    }

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.evidence.physical_truth.port_speed == "100M"
    assert result.evidence.auth_truth.pppoe_active is False
    assert result.evidence.auth_truth.pppoe_no_attempt_evidence is True


def test_needs_more_evidence_maps_cleanly(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "Vilo", "VILO-1A")
    live = _live_context(
        port_map={},
        controller_verification_by_mac={
            "aa:11:22:33:44:55": {
                "status": "match",
                "label": "Vilo inventory match",
                "snapshot_row": {"device_mac": "AA:11:22:33:44:55", "online": True},
            }
        },
    )

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.diagnosis.primary_status == "NEEDS_MORE_EVIDENCE"
    assert result.workbook_status == "NEEDS MORE EVIDENCE"
    assert result.confidence == "low"
    assert result.diagnosis.contradictions
    assert result.reality.contradictions


def test_workbook_adapter_preserves_unknowns_and_reality_model(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "Vilo", "VILO-1A")
    live = _live_context(
        port_map={"ether1": ["aa:11:22:33:44:55"]},
        failures=[{"source": "pppoe_logs", "detail": "PPPoE logs unavailable"}],
    )

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.evidence.unknowns
    assert any("PPPoE logs unavailable" in item for item in result.reality.unknowns)
    assert result.reality.unit == result.evidence.unit
    assert result.reality.inventory_truth == build_reality_model(result.evidence).inventory_truth
    assert result.diagnosis.to_dict() == diagnose(result.reality).to_dict()


def test_search_attempt_flags_populate_when_attempted(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "Vilo", "VILO-1A")
    live = _live_context(port_map={})
    live.expected_port_search_completed_by_unit = {"1A": True}
    live.switch_scope_search_completed_by_unit = {"1A": True}
    live.global_search_completed_by_unit = {"1A": True}
    live.historical_search_completed = {"1A": True}

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.evidence.l2_truth.expected_port_checked is True
    assert result.evidence.l2_truth.switch_scope_checked is True
    assert result.evidence.l2_truth.global_scope_checked is True
    assert result.evidence.l2_truth.historical_checked is True
    assert not any(item.startswith("l2_truth.expected_port_checked") for item in result.reality.unknowns)
    assert not any(item.startswith("l2_truth.historical_checked") for item in result.reality.unknowns)


def test_historical_locations_flow_into_reality(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "Vilo", "VILO-1A")
    live = _live_context(port_map={})
    live.historical_search_completed = {"1A": True}
    live.historical_locations_by_unit = {
        "1A": [
            {
                "mac": "aa:11:22:33:44:55",
                "switch": "000007.001.SW02",
                "port": "ether9",
                "scan_id": 123,
                "source": "historical_bridge_hosts",
            }
        ]
    }

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.evidence.l2_truth.historical_checked is True
    assert result.evidence.l2_truth.historical_locations
    assert result.evidence.l2_truth.historical_locations[0].switch == "000007.001.SW02"


def test_failed_pppoe_log_source_stays_unknown(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "TP-Link", "HC220-1A")
    live = _live_context(
        port_map={"ether1": ["aa:11:22:33:44:55"]},
        failures=[
            {
                "source": "get_pppoe_diagnostics",
                "detail": "PPPoE log query failed.",
            }
        ],
    )

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.evidence.auth_truth.pppoe_failed_attempts_seen is None
    assert any(item.startswith("auth_truth.pppoe_logs") for item in result.reality.unknowns)
    assert any(item.startswith("get_pppoe_diagnostics.runtime") for item in result.reality.unknowns)


def test_l1_collector_failure_is_visible_in_reality(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "TP-Link", "HC220-1A")
    live = _live_context(
        port_map={"ether1": ["aa:11:22:33:44:55"]},
        failures=[
            {
                "source": "get_port_physical_state",
                "detail": "Port physical read failed for 1A.",
            }
        ],
    )
    live.expected_port_search_completed_by_unit = {"1A": True}

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.evidence.physical_truth.port_up is None
    assert any(item.startswith("get_port_physical_state.runtime") for item in result.reality.unknowns)


def test_controller_freshness_uses_timestamp_fallback(monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    row = _row_case("1A", "AA:11:22:33:44:55", "SW1-1")
    source = _source_row("1A", "AA:11:22:33:44:55", "Vilo", "VILO-1A")
    live = _live_context(
        port_map={"ether1": ["aa:11:22:33:44:55"]},
        controller_verification_by_mac={
            "aa:11:22:33:44:55": {
                "status": "match",
                "label": "Vilo inventory match",
                "snapshot_row": {
                    "device_mac": "AA:11:22:33:44:55",
                    "notes": "site-1A",
                    "timestamp": "2026-04-25T11:45:00Z",
                },
            }
        },
    )
    live.captured_at_timestamp = "2026-04-25T12:00:00Z"

    result = build_workbook_diagnosis_result(row, source, live)

    assert result.evidence.controller_truth.controller_last_seen_timestamp == "2026-04-25T11:45:00Z"
    assert result.evidence.controller_truth.controller_data_age_seconds == 900
    assert result.evidence.controller_truth.controller_stale is False


def test_workbook_status_mapping_complete() -> None:
    assert_workbook_status_mapping_complete()
