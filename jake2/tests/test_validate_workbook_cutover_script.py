from __future__ import annotations

import json
from pathlib import Path

from scripts import validate_workbook_cutover as script


def _result(
    *,
    row_count: int = 7,
    verified_ready_percent: int = 29,
    rows_safe_for_cutover: int = 7,
    rows_blocked_from_cutover: int = 0,
    needs_more_evidence_count: int = 0,
    blocking_contradictions_count: int = 0,
    remaining_high_severity_mismatches: int = 0,
    top_unknown_fields: list[dict[str, object]] | None = None,
    recommended: list[str] | None = None,
    rendering_mode: str = "legacy",
) -> dict:
    return {
        "row_count": row_count,
        "weighted_ready_percent": verified_ready_percent,
        "cutover_report": {
            "rows_safe_for_cutover": rows_safe_for_cutover,
            "rows_blocked_from_cutover": rows_blocked_from_cutover,
            "needs_more_evidence_count": needs_more_evidence_count,
            "blocking_contradictions_count": blocking_contradictions_count,
            "remaining_high_severity_mismatches": remaining_high_severity_mismatches,
        },
        "evidence_gap_report": {
            "top_unknown_fields": top_unknown_fields or [{"field": "auth_truth.pppoe_logs", "count": 3}],
            "recommended_collector_improvements": recommended or ["Improve PPPoE diagnostics collection."],
        },
        "rendering_mode": rendering_mode,
    }


def test_safe_site_returns_safe_to_enable_true() -> None:
    summary = script.summarize_validation_result("123-125 Test St", _result())

    assert summary["safe_to_enable_diagnosis_rendering"] is True
    assert summary["rows_blocked_from_cutover"] == 0
    assert summary["rendering_mode"] == "legacy"


def test_blocked_site_returns_safe_to_enable_false() -> None:
    summary = script.summarize_validation_result(
        "123-125 Test St",
        _result(rows_safe_for_cutover=4, rows_blocked_from_cutover=3, blocking_contradictions_count=1),
    )

    assert summary["safe_to_enable_diagnosis_rendering"] is False
    assert summary["blocking_contradictions_count"] == 1


def test_missing_report_sections_fail_closed() -> None:
    summary = script.summarize_validation_result("123-125 Test St", {"row_count": 7, "weighted_ready_percent": 29})

    assert summary["safe_to_enable_diagnosis_rendering"] is False
    assert summary["rows_blocked_from_cutover"] == 0
    assert summary["top_unknown_fields"] == []


def test_aggregate_multi_site_summary_works() -> None:
    summaries = [
        script.summarize_validation_result("A", _result()),
        script.summarize_validation_result("B", _result(rows_safe_for_cutover=5, rows_blocked_from_cutover=2, needs_more_evidence_count=1)),
    ]

    aggregate = script.aggregate_site_summaries(summaries)

    assert aggregate["total_sites"] == 2
    assert aggregate["sites_safe"] == 1
    assert aggregate["sites_blocked"] == 1
    assert aggregate["blocked_reasons_by_site"][0]["address"] == "B"


def test_cli_writes_json_report(monkeypatch, tmp_path: Path, capsys) -> None:
    def fake_validate(address: str, *, output_path=None):
        return {
            "address": address,
            "row_count": 7,
            "verified_ready_percent": 29,
            "rows_safe_for_cutover": 7,
            "rows_blocked_from_cutover": 0,
            "needs_more_evidence_count": 0,
            "blocking_contradictions_count": 0,
            "remaining_high_severity_mismatches": 0,
            "top_unknown_fields": [],
            "recommended_collector_improvements": [],
            "rendering_mode": "legacy",
            "safe_to_enable_diagnosis_rendering": True,
        }

    monkeypatch.setattr(script, "validate_address", fake_validate)
    report_path = tmp_path / "cutover_report.json"

    exit_code = script.main(["--address", "123-125 Test St", "--json-report-path", str(report_path)])

    assert exit_code == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["safe_to_enable_diagnosis_rendering"] is True
    assert "123-125 Test St" in capsys.readouterr().out


def test_enable_diagnosis_rendering_for_safe_site_updates_registry(monkeypatch, tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"

    monkeypatch.setattr(
        script,
        "validate_address",
        lambda address, output_path=None: {
            "address": address,
            "row_count": 7,
            "verified_ready_percent": 29,
            "rows_safe_for_cutover": 7,
            "rows_blocked_from_cutover": 0,
            "needs_more_evidence_count": 0,
            "blocking_contradictions_count": 0,
            "remaining_high_severity_mismatches": 0,
            "top_unknown_fields": [],
            "recommended_collector_improvements": [],
            "rendering_mode": "legacy",
            "safe_to_enable_diagnosis_rendering": True,
        },
    )

    result = script.enable_diagnosis_rendering_for_site("123-125 Test St", registry_path=registry)
    payload = json.loads(registry.read_text(encoding="utf-8"))

    assert result["rendering_enabled"] is True
    assert payload["sites"][0]["validation_status"] == "safe"
    assert payload["sites"][0]["rendering_enabled"] is True


def test_enable_diagnosis_rendering_for_blocked_site_returns_reasons(monkeypatch, tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"

    monkeypatch.setattr(
        script,
        "validate_address",
        lambda address, output_path=None: {
            "address": address,
            "row_count": 7,
            "verified_ready_percent": 29,
            "rows_safe_for_cutover": 4,
            "rows_blocked_from_cutover": 3,
            "needs_more_evidence_count": 1,
            "blocking_contradictions_count": 0,
            "remaining_high_severity_mismatches": 0,
            "top_unknown_fields": ["auth_truth.pppoe_logs"],
            "recommended_collector_improvements": [],
            "rendering_mode": "legacy",
            "safe_to_enable_diagnosis_rendering": False,
        },
    )

    result = script.enable_diagnosis_rendering_for_site("123-125 Test St", registry_path=registry)

    assert result["rendering_enabled"] is False
    assert "blocked row" in result["last_block_reason"]


def test_previously_enabled_site_is_removed_on_regression(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    script.save_site_registry(
        {
            "sites": [
                {
                    "address": "123-125 Test St",
                    "last_validated_at": "2026-04-26T00:00:00Z",
                    "validation_status": "safe",
                    "rendering_enabled": True,
                    "last_block_reason": "",
                }
            ]
        },
        registry,
    )

    payload = script.update_site_registry_from_summary(
        {
            "address": "123-125 Test St",
            "rows_blocked_from_cutover": 2,
            "needs_more_evidence_count": 1,
            "blocking_contradictions_count": 0,
            "remaining_high_severity_mismatches": 0,
            "top_unknown_fields": ["physical_truth.port_up"],
            "safe_to_enable_diagnosis_rendering": False,
        },
        path=registry,
    )

    row = payload["sites"][0]
    assert row["rendering_enabled"] is False
    assert row["validation_status"] == "blocked"
    assert row["regression_detected"] is True


def test_site_becomes_stable_after_seven_safe_validations(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    validate_payload = {
        "address": "123-125 Test St",
        "rows_blocked_from_cutover": 0,
        "needs_more_evidence_count": 0,
        "blocking_contradictions_count": 0,
        "remaining_high_severity_mismatches": 0,
        "verified_ready_percent": 29,
        "top_unknown_fields": [],
        "recommended_collector_improvements": [],
        "safe_to_enable_diagnosis_rendering": True,
    }
    script.save_site_registry(
        {
            "sites": [
                {
                    "address": "123-125 Test St",
                    "last_validated_at": "2026-04-26T00:00:00Z",
                    "validation_status": "safe",
                    "rendering_enabled": True,
                    "last_block_reason": "",
                    "consecutive_safe_validations": 6,
                    "consecutive_blocked_validations": 0,
                    "validation_failure_count": 0,
                    "stable": False,
                }
            ]
        },
        registry,
    )

    payload = script.update_site_registry_from_summary(validate_payload, enable_on_safe=False, path=registry)
    row = payload["sites"][0]

    assert row["consecutive_safe_validations"] == 7
    assert row["stable"] is True
