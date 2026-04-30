from __future__ import annotations

from pathlib import Path

from audits.jake_audit_workbook import (
    AuditRow,
    LiveContext,
    compare_legacy_vs_diagnosis,
    generate_nycha_audit_workbook,
)
from diagnosis.engine import Diagnosis
from diagnosis.evidence import UnitEvidence, build_reality_model
from diagnosis.workbook_adapter import WorkbookDiagnosisResult
from mcp import jake_ops_mcp as opsmod


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "audit"


def _configure_audit_fixture_env(monkeypatch) -> None:
    monkeypatch.setenv("JAKE_AUDIT_TEMPLATE_WORKBOOK", str(FIXTURE_DIR / "nycha_template.xlsx"))
    monkeypatch.setenv("JAKE_NYCHA_INFO_CSV", str(FIXTURE_DIR / "nycha_info_fixture.csv"))
    monkeypatch.setenv("JAKE_TAUC_AUDIT_CSV", str(FIXTURE_DIR / "tauc_nycha_audit_fixture.csv"))
    monkeypatch.setenv("JAKE_VILO_INVENTORY_SNAPSHOT", str(FIXTURE_DIR / "vilo_inventory_fixture.json"))
    opsmod.NYCHA_INFO_CSV = Path(str(FIXTURE_DIR / "nycha_info_fixture.csv"))
    opsmod.TAUC_NYCHA_AUDIT_CSV = Path(str(FIXTURE_DIR / "tauc_nycha_audit_fixture.csv"))
    opsmod.load_nycha_info_rows.cache_clear()
    opsmod.load_tauc_nycha_audit_rows.cache_clear()


def _make_sparse_live_context() -> LiveContext:
    switch_identity = "000007.001.SW01"
    return LiveContext(
        building_id="000007.001",
        site_id="000007",
        online_units_by_token={},
        exact_matches_by_unit={},
        active_alert_count=0,
        building_device_count=7,
        site_online_count=7,
        inferred_switch_identity=switch_identity,
        live_port_macs_by_interface={
            "ether1": ["aa:11:22:33:44:55"],
            "ether2": ["11:22:33:44:55:66"],
            "ether3": ["20:22:33:44:55:61"],
            "ether4": ["aa:11:22:33:44:55"],
            "ether5": ["de:ad:be:ef:00:01"],
            "ether6": [],
            "ether7": ["aa:11:22:33:44:55"],
        },
        switch_identities_by_label_prefix={"SW1": switch_identity},
        live_port_macs_by_switch_identity={
            switch_identity: {
                "ether1": ["aa:11:22:33:44:55"],
                "ether2": ["11:22:33:44:55:66"],
                "ether3": ["20:22:33:44:55:61"],
                "ether4": ["aa:11:22:33:44:55"],
                "ether5": ["de:ad:be:ef:00:01"],
                "ether6": [],
                "ether7": ["aa:11:22:33:44:55"],
            }
        },
        controller_verification_by_mac={
            "aa:11:22:33:44:55": {"status": "match", "label": "Vilo inventory match"},
            "10:22:33:44:55:66": {"status": "match", "label": "TAUC audit match"},
            "20:22:33:44:55:60": {"status": "match", "label": "TAUC audit match"},
            "30:22:33:44:55:70": {"status": "match", "label": "Vilo inventory match"},
            "40:22:33:44:55:80": {"status": "unverified", "label": "Not verified"},
            "50:22:33:44:55:90": {"status": "mismatch", "label": "TAUC audit mismatch"},
        },
        live_failures=[],
    )


def _make_live_context() -> LiveContext:
    switch_identity = "000007.001.SW01"
    return LiveContext(
        building_id="000007.001",
        site_id="000007",
        online_units_by_token={},
        exact_matches_by_unit={
            "1A": {"switch_identity": switch_identity, "interface": "ether1"},
            "1B": {"switch_identity": switch_identity, "interface": "ether2"},
            "1C": {"switch_identity": switch_identity, "interface": "ether3"},
            "1D": {"switch_identity": switch_identity, "interface": "ether4"},
            "1E": {"switch_identity": switch_identity, "interface": "ether5"},
            "1F": {"switch_identity": switch_identity, "interface": "ether6"},
            "1G": {"switch_identity": switch_identity, "interface": "ether7"},
        },
        active_alert_count=0,
        building_device_count=7,
        site_online_count=7,
        inferred_switch_identity=switch_identity,
        live_port_macs_by_interface={
            "ether1": ["aa:11:22:33:44:55"],
            "ether2": ["10:22:33:44:55:66"],
            "ether3": ["20:22:33:44:55:60"],
            "ether4": ["de:ad:be:ef:00:01"],
            "ether5": ["40:22:33:44:55:80"],
            "ether6": ["50:22:33:44:55:90"],
            "ether7": ["aa:11:22:33:44:55"],
        },
        switch_identities_by_label_prefix={"SW1": switch_identity},
        live_port_macs_by_switch_identity={
            switch_identity: {
                "ether1": ["aa:11:22:33:44:55"],
                "ether2": ["10:22:33:44:55:66"],
                "ether3": ["20:22:33:44:55:60"],
                "ether4": ["de:ad:be:ef:00:01"],
                "ether5": ["40:22:33:44:55:80"],
                "ether6": ["50:22:33:44:55:90"],
                "ether7": ["aa:11:22:33:44:55"],
            }
        },
        controller_verification_by_mac={
            "aa:11:22:33:44:55": {
                "status": "match",
                "label": "Vilo inventory match",
                "snapshot_row": {
                    "device_mac": "AA:11:22:33:44:55",
                    "notes": "site-1A",
                    "last_seen": "2026-04-25T11:56:00Z",
                },
            },
            "10:22:33:44:55:66": {
                "status": "match",
                "label": "TAUC audit match",
                "snapshot_row": {
                    "tauc_mac": "10:22:33:44:55:66",
                    "expected_unit": "1B",
                    "last_seen": "2026-04-25T11:57:00Z",
                },
            },
            "20:22:33:44:55:60": {
                "status": "match",
                "label": "TAUC audit match",
                "snapshot_row": {
                    "tauc_mac": "20:22:33:44:55:60",
                    "expected_unit": "1C",
                    "last_seen": "2026-04-25T11:55:00Z",
                },
            },
            "30:22:33:44:55:70": {
                "status": "match",
                "label": "Vilo inventory match",
                "snapshot_row": {
                    "device_mac": "30:22:33:44:55:70",
                    "notes": "site-1D",
                    "last_seen": "2026-04-25T11:54:00Z",
                },
            },
            "40:22:33:44:55:80": {
                "status": "match",
                "label": "Vilo inventory match",
                "snapshot_row": {
                    "device_mac": "40:22:33:44:55:80",
                    "notes": "site-1E",
                    "last_seen": "2026-04-25T11:53:00Z",
                },
            },
            "50:22:33:44:55:90": {
                "status": "match",
                "label": "TAUC audit match",
                "snapshot_row": {
                    "tauc_mac": "50:22:33:44:55:90",
                    "expected_unit": "1F",
                    "last_seen": "2026-04-25T11:52:00Z",
                },
            },
        },
        live_failures=[],
        port_observations_by_unit={
            "1A": {"port_up": True, "port_speed": "1G", "link_partner_speed": "1G", "rx_errors": 0, "tx_errors": 0, "crc_errors": 0, "fcs_errors": 0, "link_flaps": 0, "link_flaps_window_seconds": 900},
            "1B": {"port_up": True, "port_speed": "1G", "link_partner_speed": "1G", "rx_errors": 0, "tx_errors": 0, "crc_errors": 0, "fcs_errors": 0, "link_flaps": 0, "link_flaps_window_seconds": 900},
            "1C": {"port_up": True, "port_speed": "100M", "link_partner_speed": "1G", "rx_errors": 1, "tx_errors": 0, "crc_errors": 6, "fcs_errors": 4, "link_flaps": 3, "link_flaps_window_seconds": 900},
            "1D": {"port_up": True, "port_speed": "1G", "link_partner_speed": "1G", "rx_errors": 0, "tx_errors": 0, "crc_errors": 0, "fcs_errors": 0, "link_flaps": 0, "link_flaps_window_seconds": 900},
            "1E": {"port_up": True, "port_speed": "1G", "link_partner_speed": "1G", "rx_errors": 0, "tx_errors": 0, "crc_errors": 0, "fcs_errors": 0, "link_flaps": 0, "link_flaps_window_seconds": 900},
            "1F": {"port_up": True, "port_speed": "1G", "link_partner_speed": "1G", "rx_errors": 0, "tx_errors": 0, "crc_errors": 0, "fcs_errors": 0, "link_flaps": 0, "link_flaps_window_seconds": 900},
            "1G": {"port_up": True, "port_speed": "1G", "link_partner_speed": "1G", "rx_errors": 0, "tx_errors": 0, "crc_errors": 0, "fcs_errors": 0, "link_flaps": 0, "link_flaps_window_seconds": 900},
        },
        auth_observations_by_unit={
            "1A": {"pppoe_active": True, "pppoe_failed_attempts_seen": False, "pppoe_last_attempt_timestamp": "2026-04-25T11:58:00Z", "evidence_sources": ["pppoe_diagnostics"]},
            "1B": {"pppoe_active": False, "pppoe_failed_attempts_seen": True, "pppoe_failure_reason": "auth_failed", "pppoe_last_attempt_timestamp": "2026-04-25T11:57:30Z", "evidence_sources": ["pppoe_diagnostics"]},
            "1C": {"pppoe_active": False, "pppoe_last_attempt_timestamp": "2026-04-25T11:56:30Z", "evidence_sources": ["pppoe_diagnostics"]},
            "1D": {"pppoe_active": False, "pppoe_failed_attempts_seen": False, "pppoe_no_attempt_evidence": True, "pppoe_last_attempt_timestamp": "2026-04-25T11:55:30Z", "evidence_sources": ["pppoe_diagnostics"]},
            "1E": {"pppoe_active": False, "pppoe_failed_attempts_seen": False, "pppoe_no_attempt_evidence": True, "pppoe_last_attempt_timestamp": "2026-04-25T11:54:30Z", "evidence_sources": ["pppoe_diagnostics"]},
            "1F": {"pppoe_active": False, "pppoe_failed_attempts_seen": True, "pppoe_failure_reason": "auth_failed", "pppoe_last_attempt_timestamp": "2026-04-25T11:53:30Z", "evidence_sources": ["pppoe_diagnostics"]},
            "1G": {"pppoe_active": False, "pppoe_failed_attempts_seen": False, "pppoe_no_attempt_evidence": True, "pppoe_last_attempt_timestamp": "2026-04-25T11:52:30Z", "evidence_sources": ["pppoe_diagnostics"]},
        },
        captured_at_timestamp="2026-04-25T12:00:00Z",
        historical_search_completed={unit: True for unit in ("1A", "1B", "1C", "1D", "1E", "1F", "1G")},
    )


def test_workbook_comparison_report_runs_on_fixture_data(tmp_path, monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    output_path = tmp_path / "audit_fixture_workbook.xlsx"
    result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=output_path,
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_live_context(),
    )

    report = result.get("comparison_report")
    assert report is not None
    assert report["total_rows"] == result["row_count"]
    assert "matches" in report
    assert "mismatches" in report
    assert "high_severity_mismatches" in report
    assert isinstance(report["top_mismatch_categories"], list)
    assert "overrides_applied_count" in report
    assert isinstance(report["overrides_by_category"], list)
    assert isinstance(report["sample_override_rows"], list)
    assert "remaining_high_severity_mismatches" in report
    sample = report["comparisons"][0]
    assert "diagnosis_primary_status" in sample
    assert "diagnosis_confidence" in sample
    assert "diagnosis_dispatch_required" in sample
    assert "diagnosis_dispatch_priority" in sample
    assert "reality_contradictions_count" in sample
    assert "reality_unknowns_count" in sample
    assert "override_applied" in sample
    assert "override_reason" in sample


def test_enriched_fixture_exercises_richer_diagnosis_categories(tmp_path, monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    output_path = tmp_path / "audit_fixture_workbook_enriched.xlsx"
    result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=output_path,
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_live_context(),
    )

    comparison_rows = result["comparison_report"]["comparisons"]
    diagnosis_statuses = {row["diagnosis_primary_status"] for row in comparison_rows}

    assert "HEALTHY" in diagnosis_statuses
    assert "DEGRADED_LINK_BAD_CABLE_SUSPECTED" in diagnosis_statuses
    assert "PPPoE_AUTH_FAILURE" in diagnosis_statuses


def test_high_severity_when_legacy_says_unplugged_but_mac_live() -> None:
    row = AuditRow(
        unit_key="1A",
        unit_label="1A",
        mac_cpe="AA:11:22:33:44:55",
        pppoe_unit="1A",
        notes="UNPLUGGED / BAD CABLE",
        image_ap_make="",
        image_ap_sticker_apartment="",
        image_ap_mac="",
        inventory_mac_verification="",
        implication="",
        action="Check cable",
        mac_live="AA:11:22:33:44:55",
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="L2_PRESENT_NO_SERVICE",
        diagnosis_confidence="medium",
        diagnosis_explanation="Live MAC is present so the issue remains beyond L2.",
        diagnosis_dispatch_required=False,
        diagnosis_dispatch_priority="none",
    )

    comparison = compare_legacy_vs_diagnosis(row)

    assert comparison["match"] is False
    assert comparison["severity"] == "high"
    assert "live MAC is present" in comparison["reason"]


def test_high_severity_when_legacy_dispatches_but_diagnosis_backend_first() -> None:
    row = AuditRow(
        unit_key="1A",
        unit_label="1A",
        mac_cpe="AA:11:22:33:44:55",
        pppoe_unit="1A",
        notes="UNPLUGGED / BAD CABLE",
        image_ap_make="",
        image_ap_sticker_apartment="",
        image_ap_mac="",
        inventory_mac_verification="",
        implication="",
        action="Check cable",
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="PPPoE_AUTH_FAILURE",
        diagnosis_confidence="high",
        diagnosis_explanation="PPPoE failures make this backend-fixable.",
        diagnosis_dispatch_required=False,
        diagnosis_dispatch_priority="none",
    )

    comparison = compare_legacy_vs_diagnosis(row)

    assert comparison["severity"] == "high"
    assert "backend-fixable" in comparison["reason"] or "dispatch is not required" in comparison["reason"]


def test_low_severity_for_wording_only_identity_difference() -> None:
    row = AuditRow(
        unit_key="1D",
        unit_label="1D",
        mac_cpe="30:22:33:44:55:70",
        pppoe_unit="1D",
        notes="MOVE CPE TO CORRECT UNIT",
        image_ap_make="",
        image_ap_sticker_apartment="",
        image_ap_mac="",
        inventory_mac_verification="",
        implication="",
        action="Move CPE",
        legacy_status="MOVE CPE TO CORRECT UNIT",
        diagnosis_status="DEVICE_SWAPPED_OR_WRONG_UNIT",
        diagnosis_confidence="medium",
        diagnosis_explanation="Wrong unit path.",
        diagnosis_dispatch_required=False,
        diagnosis_dispatch_priority="low",
    )

    comparison = compare_legacy_vs_diagnosis(row)

    assert comparison["severity"] == "low"


def test_comparison_prefers_diagnosis_object_over_row_strings() -> None:
    row = AuditRow(
        unit_key="1A",
        unit_label="1A",
        mac_cpe="AA:11:22:33:44:55",
        pppoe_unit="1A",
        notes="UNPLUGGED / BAD CABLE",
        image_ap_make="",
        image_ap_sticker_apartment="",
        image_ap_mac="",
        inventory_mac_verification="",
        implication="",
        action="Check cable",
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="NOT_SEEN_ANYWHERE",
        diagnosis_confidence="low",
        diagnosis_dispatch_required=True,
        diagnosis_dispatch_priority="high",
    )
    reality = build_reality_model(UnitEvidence(unit="1A"))
    reality.contradictions.append("controller says online but no live MAC anywhere")
    reality.unknowns.append("pppoe logs unavailable")
    result = WorkbookDiagnosisResult(
        diagnosis=Diagnosis(
            unit="1A",
            observed_state="observed",
            primary_status="PPPoE_AUTH_FAILURE",
            confidence="high",
            dispatch_required=False,
            dispatch_priority="none",
            explanation="backend fix",
            next_best_check="check radius",
        ),
        evidence=None,  # type: ignore[arg-type]
        reality=reality,
        workbook_status="PPPoE AUTH FAILURE",
        workbook_verification="Mismatch",
        workbook_action="Check RADIUS account",
        dispatch_required=False,
        dispatch_priority="none",
        backend_action="Check RADIUS account",
        field_action=None,
        evidence_summary="backend fix",
        confidence="high",
    )

    comparison = compare_legacy_vs_diagnosis(row, result)

    assert comparison["diagnosis_primary_status"] == "PPPoE_AUTH_FAILURE"
    assert comparison["diagnosis_confidence"] == "high"
    assert comparison["diagnosis_dispatch_required"] is False
    assert comparison["diagnosis_dispatch_priority"] == "none"
    assert comparison["reality_contradictions_count"] == 1
    assert comparison["reality_unknowns_count"] == 1
