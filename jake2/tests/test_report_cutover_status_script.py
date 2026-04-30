from __future__ import annotations

import json
from pathlib import Path

from scripts import report_cutover_status as report
from scripts import validate_workbook_cutover as validate


def test_report_cutover_status_aggregates_registry(tmp_path: Path, capsys) -> None:
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
                    "stable": True,
                    "needs_more_evidence_count": 0,
                    "top_unknown_fields": [],
                },
                {
                    "address": "999 Test St",
                    "last_validated_at": "2026-04-26T00:00:00Z",
                    "validation_status": "blocked",
                    "rendering_enabled": False,
                    "last_block_reason": "2 blocked row(s); top unknowns: auth_truth.pppoe_logs",
                    "stable": False,
                    "needs_more_evidence_count": 2,
                    "top_unknown_fields": ["auth_truth.pppoe_logs"],
                },
            ]
        },
        registry,
    )

    exit_code = report.main(["--registry-path", str(registry)])
    out = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert out["total_sites"] == 2
    assert out["safe_sites"] == 1
    assert out["enabled_sites"] == 1
    assert out["blocked_sites"] == 1
    assert out["stable_sites"] == 1
    assert out["percent_sites_safe"] == 50.0
    assert out["percent_sites_enabled"] == 50.0
    assert out["average_needs_more_evidence_count"] == 1.0
    assert out["top_unknown_fields"][0]["field"] == "auth_truth.pppoe_logs"
    assert out["top_blockers"][0]["count"] == 1


def test_report_cutover_status_writes_json(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    output = tmp_path / "report.json"
    validate.save_site_registry({"sites": []}, registry)

    exit_code = report.main(["--registry-path", str(registry), "--json-output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["total_sites"] == 0
