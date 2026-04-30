from __future__ import annotations

from audits.jake_audit_workbook import (
    AuditRow,
    _maybe_apply_diagnosis_override,
    compare_legacy_vs_diagnosis,
)
from diagnosis.engine import Diagnosis
from diagnosis.evidence import (
    AuthTruth,
    ControllerTruth,
    InventoryTruth,
    L2LocationEvidence,
    L2Truth,
    PhysicalTruth,
    UnitEvidence,
    build_reality_model,
)
from diagnosis.workbook_adapter import WorkbookDiagnosisResult


def _row(
    *,
    legacy_status: str,
    diagnosis_status: str,
    diagnosis_confidence: str,
    mac_live: str = "",
    diagnosis_dispatch_required: bool | None = None,
) -> AuditRow:
    return AuditRow(
        unit_key="1A",
        unit_label="1A",
        mac_cpe="AA:11:22:33:44:55",
        pppoe_unit="1A",
        notes=legacy_status,
        image_ap_make="",
        image_ap_sticker_apartment="",
        image_ap_mac="",
        inventory_mac_verification="",
        implication="legacy implication",
        action="legacy action",
        mac_live=mac_live,
        legacy_status=legacy_status,
        diagnosis_status=diagnosis_status,
        diagnosis_confidence=diagnosis_confidence,
        diagnosis_explanation="diagnosis explanation",
        diagnosis_dispatch_required=diagnosis_dispatch_required,
        diagnosis_dispatch_priority="none",
    )


def _result(
    *,
    primary_status: str,
    dispatch_required: bool = False,
    dispatch_priority: str = "none",
    backend_action: str | None = None,
    field_action: str | None = None,
    confidence: str = "medium",
    evidence: UnitEvidence | None = None,
) -> WorkbookDiagnosisResult:
    diagnosis = Diagnosis(
        unit="1A",
        observed_state="observed",
        primary_status=primary_status,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        dispatch_required=dispatch_required,
        dispatch_priority=dispatch_priority,  # type: ignore[arg-type]
        backend_actions=[backend_action] if backend_action else [],
        field_actions=[field_action] if field_action else [],
        explanation="diagnosis evidence summary",
        next_best_check="next check",
    )
    evidence = evidence or UnitEvidence(unit="1A")
    workbook_action = backend_action or field_action or "next check"
    return WorkbookDiagnosisResult(
        diagnosis=diagnosis,
        evidence=evidence,
        reality=build_reality_model(evidence),
        workbook_status=f"mapped {primary_status}",
        workbook_verification="Mismatch",
        workbook_action=workbook_action,
        dispatch_required=dispatch_required,
        dispatch_priority=dispatch_priority,  # type: ignore[arg-type]
        backend_action=backend_action,
        field_action=field_action,
        evidence_summary="diagnosis evidence summary",
        confidence=confidence,
    )


def _evidence(
    *,
    expected_mac: str = "aa:11:22:33:44:55",
    expected_port: str = "ether1",
    live_mac_seen: bool | None = None,
    live_mac: str | None = None,
    any_mac_on_expected_port: bool | None = None,
    macs_on_expected_port: list[str] | None = None,
    expected_mac_seen: bool | None = None,
    expected_mac_locations: list[L2LocationEvidence] | None = None,
    pppoe_active: bool | None = None,
    pppoe_failed_attempts_seen: bool | None = None,
    controller_seen: bool | None = None,
) -> UnitEvidence:
    return UnitEvidence(
        unit="1A",
        inventory_truth=InventoryTruth(expected_mac=expected_mac, expected_port=expected_port, expected_pppoe="site-1A"),
        physical_truth=PhysicalTruth(port_up=True, port_speed="1G"),
        l2_truth=L2Truth(
            expected_port_checked=True,
            switch_scope_checked=True,
            global_scope_checked=True,
            historical_checked=True,
            live_mac_seen=live_mac_seen,
            live_mac=live_mac,
            any_mac_on_expected_port=any_mac_on_expected_port,
            macs_on_expected_port=macs_on_expected_port or [],
            expected_mac_seen=expected_mac_seen,
            expected_mac_locations=expected_mac_locations or [],
            live_port=expected_port if any_mac_on_expected_port else None,
        ),
        auth_truth=AuthTruth(
            pppoe_active=pppoe_active,
            pppoe_failed_attempts_seen=pppoe_failed_attempts_seen,
            pppoe_no_attempt_evidence=True if pppoe_active is False and not pppoe_failed_attempts_seen else None,
        ),
        controller_truth=ControllerTruth(controller_seen=controller_seen),
    )


def test_override_triggers_for_unplugged_vs_live_mac() -> None:
    row = _row(
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="L2_PRESENT_NO_SERVICE",
        diagnosis_confidence="medium",
        mac_live="AA:11:22:33:44:55",
        diagnosis_dispatch_required=False,
    )

    _maybe_apply_diagnosis_override(
        row,
        _result(
            primary_status="L2_PRESENT_NO_SERVICE",
            evidence=_evidence(live_mac_seen=True, live_mac="aa:11:22:33:44:55", any_mac_on_expected_port=True),
        ),
    )

    assert row.override_applied is True
    assert row.notes == "mapped L2_PRESENT_NO_SERVICE"
    assert "live MAC is present" in row.override_reason


def test_override_triggers_for_field_vs_backend_mismatch() -> None:
    row = _row(
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="PPPoE_AUTH_FAILURE",
        diagnosis_confidence="high",
        diagnosis_dispatch_required=False,
    )

    _maybe_apply_diagnosis_override(
        row,
        _result(
            primary_status="PPPoE_AUTH_FAILURE",
            backend_action="Check RADIUS account",
            evidence=_evidence(live_mac_seen=True, live_mac="aa:11:22:33:44:55", any_mac_on_expected_port=True),
        ),
    )

    assert row.override_applied is True
    assert row.action == "Check RADIUS account"
    assert "backend-fixable" in row.override_reason or "dispatch is not required" in row.override_reason


def test_override_triggers_for_device_swap_vs_controller_mismatch() -> None:
    row = _row(
        legacy_status="CONTROLLER MISMATCH",
        diagnosis_status="DEVICE_SWAPPED_OR_WRONG_UNIT",
        diagnosis_confidence="high",
        diagnosis_dispatch_required=True,
    )

    _maybe_apply_diagnosis_override(
        row,
        _result(
            primary_status="DEVICE_SWAPPED_OR_WRONG_UNIT",
            field_action="Verify device label onsite",
            evidence=_evidence(
                live_mac_seen=True,
                live_mac="de:ad:be:ef:00:01",
                any_mac_on_expected_port=True,
                macs_on_expected_port=["de:ad:be:ef:00:01"],
                expected_mac_seen=False,
            ),
            confidence="high",
        ),
    )

    assert row.override_applied is True
    assert row.notes == "mapped DEVICE_SWAPPED_OR_WRONG_UNIT"
    assert "swapped device" in row.override_reason or "wrong-unit path" in row.override_reason


def test_low_severity_mismatch_does_not_trigger_override() -> None:
    row = _row(
        legacy_status="MOVE CPE TO CORRECT UNIT",
        diagnosis_status="DEVICE_SWAPPED_OR_WRONG_UNIT",
        diagnosis_confidence="medium",
        diagnosis_dispatch_required=False,
    )
    comparison = compare_legacy_vs_diagnosis(row)
    assert comparison["severity"] == "low"

    _maybe_apply_diagnosis_override(
        row,
        _result(
            primary_status="DEVICE_SWAPPED_OR_WRONG_UNIT",
            field_action="Verify label",
            evidence=_evidence(live_mac_seen=True, live_mac="de:ad:be:ef:00:01", any_mac_on_expected_port=True, expected_mac_seen=False),
        ),
    )

    assert row.override_applied is False
    assert row.notes == "MOVE CPE TO CORRECT UNIT"


def test_medium_severity_mismatch_does_not_trigger_override() -> None:
    row = _row(
        legacy_status="CONTROLLER MISMATCH",
        diagnosis_status="INVENTORY_MAC_MISMATCH",
        diagnosis_confidence="medium",
        diagnosis_dispatch_required=False,
    )
    comparison = compare_legacy_vs_diagnosis(row)
    assert comparison["severity"] == "medium"

    _maybe_apply_diagnosis_override(
        row,
        _result(
            primary_status="INVENTORY_MAC_MISMATCH",
            backend_action="Correct inventory MAC",
            evidence=_evidence(live_mac_seen=True, live_mac="de:ad:be:ef:00:01", any_mac_on_expected_port=True, expected_mac_seen=False),
        ),
    )

    assert row.override_applied is False
    assert row.notes == "CONTROLLER MISMATCH"


def test_needs_more_evidence_does_not_trigger_override() -> None:
    row = _row(
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="NEEDS_MORE_EVIDENCE",
        diagnosis_confidence="high",
        mac_live="AA:11:22:33:44:55",
        diagnosis_dispatch_required=False,
    )

    _maybe_apply_diagnosis_override(
        row,
        _result(
            primary_status="NEEDS_MORE_EVIDENCE",
            evidence=_evidence(live_mac_seen=True, live_mac="aa:11:22:33:44:55", any_mac_on_expected_port=True),
        ),
    )

    assert row.override_applied is False
    assert row.notes == "UNPLUGGED / BAD CABLE"


def test_blocking_contradictions_prevent_high_severity_override() -> None:
    row = _row(
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="PPPoE_AUTH_FAILURE",
        diagnosis_confidence="high",
        diagnosis_dispatch_required=False,
    )
    result = _result(
        primary_status="PPPoE_AUTH_FAILURE",
        confidence="high",
        backend_action="Check RADIUS account",
        evidence=_evidence(live_mac_seen=True, live_mac="aa:11:22:33:44:55", any_mac_on_expected_port=True),
    )
    result.reality.contradictions.append("controller says online but no MAC anywhere")

    comparison = compare_legacy_vs_diagnosis(row, result)

    assert comparison["diagnosis_primary_status"] == "PPPoE_AUTH_FAILURE"
    assert comparison["reality_contradictions_count"] == 1
    _maybe_apply_diagnosis_override(row, result)

    assert row.override_applied is False
    assert row.notes == "UNPLUGGED / BAD CABLE"


def test_unknown_heavy_reality_blocks_medium_confidence_override() -> None:
    row = _row(
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="L2_PRESENT_NO_SERVICE",
        diagnosis_confidence="medium",
        mac_live="AA:11:22:33:44:55",
        diagnosis_dispatch_required=False,
    )
    result = _result(
        primary_status="L2_PRESENT_NO_SERVICE",
        confidence="medium",
        evidence=_evidence(live_mac_seen=True, live_mac="aa:11:22:33:44:55", any_mac_on_expected_port=True),
    )
    result.reality.unknowns.extend(["pppoe logs unavailable", "dhcp evidence unavailable", "port speed unknown"])

    _maybe_apply_diagnosis_override(row, result)

    assert row.override_applied is False
    assert row.override_confidence == ""


def test_unknown_heavy_reality_allows_explicit_category_with_high_confidence() -> None:
    row = _row(
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="PPPoE_NO_ATTEMPT",
        diagnosis_confidence="high",
        mac_live="AA:11:22:33:44:55",
        diagnosis_dispatch_required=False,
    )
    result = _result(
        primary_status="PPPoE_NO_ATTEMPT",
        confidence="high",
        evidence=_evidence(
            live_mac_seen=True,
            live_mac="aa:11:22:33:44:55",
            any_mac_on_expected_port=True,
            expected_mac_seen=True,
            pppoe_active=False,
            pppoe_failed_attempts_seen=False,
        ),
    )
    result.reality.unknowns.extend(["dhcp evidence unavailable", "controller timestamp missing", "port duplex unknown"])

    _maybe_apply_diagnosis_override(row, result)

    assert row.override_applied is True
    assert row.override_confidence == "high"


def test_device_swap_override_requires_strong_evidence() -> None:
    row = _row(
        legacy_status="CONTROLLER MISMATCH",
        diagnosis_status="DEVICE_SWAPPED_OR_WRONG_UNIT",
        diagnosis_confidence="high",
        diagnosis_dispatch_required=True,
    )

    _maybe_apply_diagnosis_override(
        row,
        _result(
            primary_status="DEVICE_SWAPPED_OR_WRONG_UNIT",
            confidence="high",
            field_action="Verify label onsite",
            evidence=_evidence(
                live_mac_seen=True,
                live_mac="de:ad:be:ef:00:01",
                any_mac_on_expected_port=True,
                macs_on_expected_port=["de:ad:be:ef:00:01"],
                expected_mac_seen=False,
                expected_mac_locations=[L2LocationEvidence(mac="aa:11:22:33:44:55", switch="sw2", port="ether9")],
            ),
        ),
    )

    assert row.override_applied is True
    assert row.override_confidence == "high"


def test_service_domain_override_requires_mac_and_missing_service() -> None:
    row = _row(
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="PPPoE_NO_ATTEMPT",
        diagnosis_confidence="high",
        mac_live="AA:11:22:33:44:55",
        diagnosis_dispatch_required=False,
    )

    _maybe_apply_diagnosis_override(
        row,
        _result(
            primary_status="PPPoE_NO_ATTEMPT",
            confidence="high",
            evidence=_evidence(
                live_mac_seen=True,
                live_mac="aa:11:22:33:44:55",
                any_mac_on_expected_port=True,
                expected_mac_seen=True,
                pppoe_active=False,
                pppoe_failed_attempts_seen=False,
            ),
        ),
    )

    assert row.override_applied is True
    assert row.notes == "mapped PPPoE_NO_ATTEMPT"


def test_lookup_failed_override_requires_alternate_evidence() -> None:
    row = _row(
        legacy_status="LIVE LOOKUP FAILED",
        diagnosis_status="INVENTORY_MAC_MISMATCH",
        diagnosis_confidence="high",
        diagnosis_dispatch_required=False,
    )

    _maybe_apply_diagnosis_override(
        row,
        _result(
            primary_status="INVENTORY_MAC_MISMATCH",
            confidence="high",
            backend_action="Correct inventory MAC",
            evidence=_evidence(controller_seen=True),
        ),
    )

    assert row.override_applied is True
    assert row.action == "Correct inventory MAC"


def test_insufficient_evidence_blocks_new_category_override() -> None:
    row = _row(
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="PPPoE_NO_ATTEMPT",
        diagnosis_confidence="high",
        diagnosis_dispatch_required=True,
    )

    _maybe_apply_diagnosis_override(
        row,
        _result(
            primary_status="PPPoE_NO_ATTEMPT",
            confidence="high",
            dispatch_required=True,
            evidence=_evidence(
                live_mac_seen=True,
                live_mac="aa:11:22:33:44:55",
                any_mac_on_expected_port=True,
                pppoe_active=False,
                pppoe_failed_attempts_seen=True,
            ),
        ),
    )

    assert row.override_applied is False
    assert row.override_confidence == ""
