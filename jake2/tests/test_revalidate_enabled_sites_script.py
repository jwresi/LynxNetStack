from __future__ import annotations

import json
from pathlib import Path

from scripts import revalidate_enabled_sites as revalidate
from scripts import validate_workbook_cutover as validate


def test_revalidate_enabled_sites_keeps_safe_sites_enabled(monkeypatch, tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    validate.save_site_registry(
        {
            "sites": [
                {
                    "address": "1145 Lenox Rd",
                    "last_validated_at": "2026-04-26T00:00:00Z",
                    "validation_status": "safe",
                    "rendering_enabled": True,
                    "last_block_reason": "",
                    "consecutive_safe_validations": 2,
                    "consecutive_blocked_validations": 0,
                    "validation_failure_count": 0,
                    "stable": False,
                }
            ]
        },
        registry,
    )
    monkeypatch.setattr(
        revalidate,
        "validate_address",
        lambda address: {
            "address": address,
            "verified_ready_percent": 52,
            "rows_blocked_from_cutover": 0,
            "needs_more_evidence_count": 0,
            "blocking_contradictions_count": 0,
            "remaining_high_severity_mismatches": 0,
            "top_unknown_fields": [],
            "recommended_collector_improvements": [],
            "safe_to_enable_diagnosis_rendering": True,
        },
    )

    report = revalidate.revalidate_enabled_sites(registry_path=registry)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    row = payload["sites"][0]

    assert report["enabled_sites_checked"] == 1
    assert report["regressions_detected"] == 0
    assert row["rendering_enabled"] is True
    assert row["consecutive_safe_validations"] == 3
    assert row["consecutive_blocked_validations"] == 0


def test_revalidate_enabled_sites_disables_regressions(monkeypatch, tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    validate.save_site_registry(
        {
            "sites": [
                {
                    "address": "1145 Lenox Rd",
                    "last_validated_at": "2026-04-26T00:00:00Z",
                    "validation_status": "safe",
                    "rendering_enabled": True,
                    "last_block_reason": "",
                    "consecutive_safe_validations": 5,
                    "consecutive_blocked_validations": 0,
                    "validation_failure_count": 0,
                    "stable": False,
                }
            ]
        },
        registry,
    )
    monkeypatch.setattr(
        revalidate,
        "validate_address",
        lambda address: {
            "address": address,
            "verified_ready_percent": 10,
            "rows_blocked_from_cutover": 4,
            "needs_more_evidence_count": 2,
            "blocking_contradictions_count": 0,
            "remaining_high_severity_mismatches": 0,
            "top_unknown_fields": ["physical_truth.port_up"],
            "recommended_collector_improvements": [],
            "safe_to_enable_diagnosis_rendering": False,
        },
    )

    report = revalidate.revalidate_enabled_sites(registry_path=registry)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    row = payload["sites"][0]

    assert report["regressions_detected"] == 1
    assert row["rendering_enabled"] is False
    assert row["validation_status"] == "blocked"
    assert row["regression_detected"] is True
    assert row["consecutive_safe_validations"] == 0
    assert row["consecutive_blocked_validations"] == 1


def test_revalidate_cli_writes_json(monkeypatch, tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    output = tmp_path / "revalidate.json"
    validate.save_site_registry({"sites": []}, registry)
    monkeypatch.setattr(revalidate, "revalidate_enabled_sites", lambda registry_path=None: {"enabled_sites_checked": 0, "regressions_detected": 0, "results": [], "sites": []})

    exit_code = revalidate.main(["--registry-path", str(registry), "--json-output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["enabled_sites_checked"] == 0
