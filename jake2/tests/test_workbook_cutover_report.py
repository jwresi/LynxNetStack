from __future__ import annotations

from audits.jake_audit_workbook import AuditRow, generate_nycha_audit_workbook, generate_workbook_cutover_report
from tests.test_workbook_diagnosis_comparison import (
    FIXTURE_DIR,
    _configure_audit_fixture_env,
    _make_live_context,
    _make_sparse_live_context,
)


def _row(
    *,
    unit: str,
    legacy_status: str,
    diagnosis_status: str,
    diagnosis_confidence: str,
    severity: str,
    override_applied: bool = False,
    override_reason: str = "",
    contradictions: int = 0,
    unknowns: int = 0,
) -> AuditRow:
    return AuditRow(
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
        action="legacy action",
        legacy_status=legacy_status,
        diagnosis_status=diagnosis_status,
        diagnosis_confidence=diagnosis_confidence,
        diagnosis_explanation="diagnosis summary",
        diagnosis_dispatch_required=False,
        diagnosis_dispatch_priority="none",
        reality_contradictions_count=contradictions,
        reality_unknowns_count=unknowns,
        override_applied=override_applied,
        override_reason=override_reason,
        evidence_contradictions=[],
    )


def test_fully_aligned_row_is_safe_for_cutover() -> None:
    row = _row(
        unit="1A",
        legacy_status="Good",
        diagnosis_status="HEALTHY",
        diagnosis_confidence="high",
        severity="low",
    )

    report = generate_workbook_cutover_report([row])

    assert row.cutover_safe is True
    assert row.cutover_block_reason == ""
    assert report["rows_safe_for_cutover"] == 1
    assert report["rows_blocked_from_cutover"] == 0


def test_high_severity_mismatch_without_override_is_blocked() -> None:
    row = _row(
        unit="1A",
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="L2_PRESENT_NO_SERVICE",
        diagnosis_confidence="high",
        severity="high",
    )
    row.mac_live = "AA:11:22:33:44:55"

    report = generate_workbook_cutover_report([row])

    assert row.cutover_safe is False
    assert "High-severity legacy mismatch" in row.cutover_block_reason
    assert report["remaining_high_severity_mismatches"] == 1


def test_needs_more_evidence_is_blocked() -> None:
    row = _row(
        unit="1A",
        legacy_status="LIVE LOOKUP FAILED",
        diagnosis_status="NEEDS_MORE_EVIDENCE",
        diagnosis_confidence="low",
        severity="medium",
    )

    report = generate_workbook_cutover_report([row])

    assert row.cutover_safe is False
    assert "needs more evidence" in row.cutover_block_reason.lower()
    assert report["needs_more_evidence_count"] == 1


def test_hard_contradiction_row_is_blocked() -> None:
    row = _row(
        unit="1A",
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="PPPoE_AUTH_FAILURE",
        diagnosis_confidence="high",
        severity="high",
        override_applied=True,
        contradictions=1,
    )
    row.evidence_contradictions = ["Controller says online but no MAC anywhere."]

    report = generate_workbook_cutover_report([row])

    assert row.cutover_safe is False
    assert "blocking contradictions" in row.cutover_block_reason.lower()
    assert report["contradiction_count"] == 1
    assert report["blocking_contradictions_count"] == 1


def test_pppoe_no_attempt_diagnostic_signal_does_not_block_cutover() -> None:
    row = _row(
        unit="1A",
        legacy_status="Good",
        diagnosis_status="PPPoE_NO_ATTEMPT",
        diagnosis_confidence="medium",
        severity="medium",
        contradictions=1,
    )
    row.evidence_contradictions = [
        "MAC is present at L2, but PPPoE is expected and no PPPoE attempt is visible."
    ]

    report = generate_workbook_cutover_report([row])

    assert row.cutover_safe is True
    assert report["contradiction_count"] == 1
    assert report["blocking_contradictions_count"] == 0
    assert report["non_blocking_diagnostic_signals_count"] == 1


def test_strong_device_swap_diagnostic_signal_does_not_block_cutover() -> None:
    row = _row(
        unit="1D",
        legacy_status="CONTROLLER MISMATCH",
        diagnosis_status="DEVICE_SWAPPED_OR_WRONG_UNIT",
        diagnosis_confidence="high",
        severity="medium",
        contradictions=1,
        override_applied=True,
        override_reason="Legacy controller mismatch was overridden by strong device-swap evidence.",
    )
    row.evidence_contradictions = [
        "Historical MAC found elsewhere while diagnosis is DEVICE_SWAPPED_OR_WRONG_UNIT."
    ]

    report = generate_workbook_cutover_report([row])

    assert row.cutover_safe is True
    assert report["blocking_contradictions_count"] == 0


def test_unknown_heavy_row_is_blocked() -> None:
    row = _row(
        unit="1A",
        legacy_status="Good",
        diagnosis_status="HEALTHY",
        diagnosis_confidence="medium",
        severity="low",
        unknowns=3,
    )

    report = generate_workbook_cutover_report([row])

    assert row.cutover_safe is False
    assert "unknown-heavy" in row.cutover_block_reason.lower()
    assert report["unknown_heavy_count"] == 1


def test_high_severity_mismatch_with_override_is_safe() -> None:
    row = _row(
        unit="1A",
        legacy_status="UNPLUGGED / BAD CABLE",
        diagnosis_status="PPPoE_AUTH_FAILURE",
        diagnosis_confidence="high",
        severity="high",
        override_applied=True,
        override_reason="Legacy points to field issue but diagnosis is backend-fixable.",
    )

    report = generate_workbook_cutover_report([row])

    assert row.cutover_safe is True
    assert report["overrides_applied_count"] == 1
    assert report["remaining_high_severity_mismatches"] == 0


def test_cutover_summary_counts_are_correct() -> None:
    rows = [
        _row(unit="1A", legacy_status="Good", diagnosis_status="HEALTHY", diagnosis_confidence="high", severity="low"),
        _row(
            unit="1B",
            legacy_status="UNPLUGGED / BAD CABLE",
            diagnosis_status="PPPoE_AUTH_FAILURE",
            diagnosis_confidence="high",
            severity="high",
            override_applied=True,
        ),
        _row(
            unit="1C",
            legacy_status="LIVE LOOKUP FAILED",
            diagnosis_status="NEEDS_MORE_EVIDENCE",
            diagnosis_confidence="low",
            severity="medium",
        ),
        _row(unit="1D", legacy_status="CONTROLLER MISMATCH", diagnosis_status="DEVICE_SWAPPED_OR_WRONG_UNIT", diagnosis_confidence="medium", severity="medium", unknowns=3),
    ]
    rows[1].mac_live = "AA:11:22:33:44:55"

    report = generate_workbook_cutover_report(rows)

    assert report["total_rows"] == 4
    assert report["exact_matches"] == 1
    assert report["mismatches"] == 3
    assert report["high_severity_mismatches"] == 2
    assert report["medium_severity_mismatches"] == 1
    assert report["low_severity_mismatches"] == 1
    assert report["needs_more_evidence_count"] == 1
    assert report["unknown_heavy_count"] == 1
    assert report["rows_safe_for_cutover"] == 2
    assert report["rows_blocked_from_cutover"] == 2
    assert report["legacy_status_counts"]["Good"] == 1
    assert report["diagnosis_status_counts"]["HEALTHY"] == 1


def test_enriched_fixture_increases_cutover_safe_rows(tmp_path, monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    sparse_result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=tmp_path / "sparse_cutover.xlsx",
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_sparse_live_context(),
    )
    enriched_result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=tmp_path / "enriched_cutover.xlsx",
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_live_context(),
    )

    assert enriched_result["cutover_report"]["rows_safe_for_cutover"] > sparse_result["cutover_report"]["rows_safe_for_cutover"]
    assert enriched_result["cutover_report"]["rows_safe_for_cutover"] >= 1
    assert enriched_result["cutover_report"]["blocking_contradictions_count"] == 0
