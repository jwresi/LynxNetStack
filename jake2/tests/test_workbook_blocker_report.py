from __future__ import annotations

from audits.jake_audit_workbook import AuditRow, generate_workbook_blocker_report


def _row(
    *,
    unit: str,
    legacy_status: str,
    diagnosis_status: str,
    confidence: str,
    cutover_safe: bool,
    cutover_block_reason: str = "",
    comparison_category: str = "classification_difference",
    contradictions: list[str] | None = None,
    unknowns: list[str] | None = None,
    override_applied: bool = False,
    severity: str = "medium",
    next_best_check: str = "next check",
) -> AuditRow:
    row = AuditRow(
        unit_key=unit,
        unit_label=unit,
        mac_cpe="AA:11:22:33:44:55",
        pppoe_unit=unit,
        notes=legacy_status,
        image_ap_make="",
        image_ap_sticker_apartment="",
        image_ap_mac="",
        inventory_mac_verification="",
        implication="",
        action=next_best_check,
        legacy_status=legacy_status,
        diagnosis_status=diagnosis_status,
        diagnosis_confidence=confidence,
        diagnosis_explanation="diagnosis summary",
        diagnosis_backend_action=next_best_check,
        evidence_contradictions=list(contradictions or []),
        evidence_unknowns=list(unknowns or []),
        cutover_safe=cutover_safe,
        cutover_block_reason=cutover_block_reason,
        override_applied=override_applied,
    )
    row.mac_live = "AA:11:22:33:44:55" if severity == "high" else ""
    return row


def test_needs_more_evidence_rows_are_listed() -> None:
    row = _row(
        unit="1A",
        legacy_status="LIVE LOOKUP FAILED",
        diagnosis_status="NEEDS_MORE_EVIDENCE",
        confidence="low",
        cutover_safe=False,
        cutover_block_reason="Diagnosis still needs more evidence.",
        unknowns=["auth_truth.pppoe_logs: missing"],
    )

    report = generate_workbook_blocker_report([row])

    assert report["total_blocked_rows"] == 1
    assert report["needs_more_evidence_rows"][0]["unit"] == "1A"


def test_unresolved_high_severity_rows_are_listed() -> None:
    row = _row(
        unit="1B",
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="PPPoE_AUTH_FAILURE",
        confidence="high",
        cutover_safe=False,
        cutover_block_reason="High-severity legacy mismatch remains unresolved.",
        next_best_check="Check RADIUS account",
        severity="high",
    )

    report = generate_workbook_blocker_report([row])

    assert report["unresolved_high_severity_rows"][0]["unit"] == "1B"


def test_per_row_blocker_contains_next_best_check() -> None:
    row = _row(
        unit="1C",
        legacy_status="CONTROLLER MISMATCH",
        diagnosis_status="NEEDS_MORE_EVIDENCE",
        confidence="medium",
        cutover_safe=False,
        cutover_block_reason="Reality model contains contradictions.",
        contradictions=["controller says online but no MAC anywhere"],
        next_best_check="Resolve controller vs L2 evidence",
    )

    report = generate_workbook_blocker_report([row])

    assert report["per_row_blockers"][0]["next_best_check"] == "Resolve controller vs L2 evidence"
    assert report["per_row_blockers"][0]["blocking_contradictions"] == ["controller says online but no MAC anywhere"]
    assert report["per_row_blockers"][0]["non_blocking_diagnostic_signals"] == []


def test_blocker_categories_are_counted_correctly() -> None:
    rows = [
        _row(
            unit="1A",
            legacy_status="LIVE LOOKUP FAILED",
            diagnosis_status="NEEDS_MORE_EVIDENCE",
            confidence="low",
            cutover_safe=False,
            cutover_block_reason="Diagnosis still needs more evidence.",
        ),
        _row(
            unit="1B",
            legacy_status="UNPLUGGED / BAD CABLE",
            diagnosis_status="PPPoE_AUTH_FAILURE",
            confidence="high",
            cutover_safe=False,
            cutover_block_reason="High-severity legacy mismatch remains unresolved.",
            severity="high",
        ),
        _row(
            unit="1C",
            legacy_status="Good",
            diagnosis_status="HEALTHY",
            confidence="high",
            cutover_safe=True,
        ),
    ]

    report = generate_workbook_blocker_report(rows)

    assert report["total_blocked_rows"] == 2
    assert report["blocked_by_status"]["NEEDS_MORE_EVIDENCE"] == 1
    assert report["blocked_by_status"]["PPPoE_AUTH_FAILURE"] == 1
    assert report["blocked_by_reason"]["Diagnosis still needs more evidence."] == 1
    assert report["blocked_by_reason"]["High-severity legacy mismatch remains unresolved."] == 1


def test_blocker_report_separates_blocking_and_non_blocking_signals() -> None:
    rows = [
        _row(
            unit="1D",
            legacy_status="CONTROLLER MISMATCH",
            diagnosis_status="DEVICE_SWAPPED_OR_WRONG_UNIT",
            confidence="high",
            cutover_safe=False,
            cutover_block_reason="Reality model contains blocking contradictions.",
            contradictions=["controller says online but no MAC anywhere"],
        ),
        _row(
            unit="1E",
            legacy_status="UNPLUGGED / BAD CABLE",
            diagnosis_status="PPPoE_NO_ATTEMPT",
            confidence="medium",
            cutover_safe=False,
            cutover_block_reason="Diagnosis confidence is too low for cutover.",
            contradictions=["MAC is present at L2, but PPPoE is expected and no PPPoE attempt is visible."],
        ),
    ]

    report = generate_workbook_blocker_report(rows)

    assert report["blocking_contradictions_count"] == 1
    assert report["non_blocking_diagnostic_signals_count"] == 1
    by_unit = {item["unit"]: item for item in report["per_row_blockers"]}
    assert by_unit["1D"]["blocking_contradictions"] == ["controller says online but no MAC anywhere"]
    assert by_unit["1D"]["non_blocking_diagnostic_signals"] == []
    assert by_unit["1E"]["blocking_contradictions"] == []
    assert by_unit["1E"]["non_blocking_diagnostic_signals"] == [
        "MAC is present at L2, but PPPoE is expected and no PPPoE attempt is visible."
    ]
