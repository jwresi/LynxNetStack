from __future__ import annotations

from audits import jake_audit_workbook as workbook
from audits.jake_audit_workbook import generate_nycha_audit_workbook
from tests.test_workbook_diagnosis_comparison import (
    FIXTURE_DIR,
    _configure_audit_fixture_env,
    _make_live_context,
    _make_sparse_live_context,
)


def _row_by_unit(result: dict, unit: str) -> dict:
    return next(row for row in result["rows"] if row["unit"] == unit)


def _comparison_by_unit(result: dict, unit: str) -> dict:
    return next(row for row in result["comparison_report"]["comparisons"] if row["unit"] == unit)


def test_rendering_flag_off_uses_legacy_rendering(tmp_path, monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    monkeypatch.setattr(workbook, "USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING", False)

    result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=tmp_path / "legacy_render.xlsx",
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_live_context(),
    )

    row_1b = _row_by_unit(result, "1B")
    assert result["rendering_mode"] == "legacy"
    assert result["cutover_blocked_reason"] == ""
    assert row_1b["notes"] == "Good"


def test_rendering_flag_on_with_all_rows_safe_uses_diagnosis_rendering(tmp_path, monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    monkeypatch.setattr(workbook, "USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING", True)

    result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=tmp_path / "diagnosis_render.xlsx",
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_live_context(),
    )

    row_1b = _row_by_unit(result, "1B")
    comparison_1b = _comparison_by_unit(result, "1B")

    assert result["rendering_mode"] == "diagnosis"
    assert result["cutover_report"]["rows_blocked_from_cutover"] == 0
    assert row_1b["notes"] == "PPPoE AUTH FAILURE"
    assert comparison_1b["legacy_status"] == "Good"
    assert comparison_1b["diagnosis_primary_status"] == "PPPoE_AUTH_FAILURE"


def test_rendering_flag_on_with_blocked_rows_falls_back_to_legacy(tmp_path, monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    monkeypatch.setattr(workbook, "USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING", True)

    result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=tmp_path / "blocked_render.xlsx",
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_sparse_live_context(),
    )

    row_1b = _row_by_unit(result, "1B")

    assert result["rendering_mode"] == "legacy_fallback"
    assert result["cutover_report"]["rows_blocked_from_cutover"] > 0
    assert result["cutover_blocked_reason"]
    assert row_1b["notes"] == "Good"


def test_legacy_status_is_preserved_during_diagnosis_cutover(tmp_path, monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    monkeypatch.setattr(workbook, "USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING", True)

    result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=tmp_path / "preserved_legacy.xlsx",
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_live_context(),
    )

    row_1d = _row_by_unit(result, "1D")
    comparison_1d = _comparison_by_unit(result, "1D")

    assert row_1d["notes"] == "WRONG UNIT / DEVICE SWAPPED"
    assert comparison_1d["legacy_status"] == "UNKNOWN MAC ON PORT"
    assert comparison_1d["override_applied"] is True


def test_per_site_rendering_allowlist_enables_diagnosis_with_global_flag_off(tmp_path, monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    monkeypatch.setattr(workbook, "USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING", False)
    registry = tmp_path / "registry.json"
    registry.write_text(
        '{"sites":[{"address":"123-125 Test St","last_validated_at":"2026-04-26T00:00:00Z","validation_status":"safe","rendering_enabled":true,"last_block_reason":""}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(workbook, "DIAGNOSIS_RENDERING_SITE_REGISTRY_PATH", registry)

    result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=tmp_path / "allowlisted_render.xlsx",
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_live_context(),
    )

    assert result["diagnosis_rendering_enabled_for_address"] is True
    assert result["rendering_mode"] == "diagnosis"


def test_non_allowlisted_site_stays_legacy_when_global_flag_off(tmp_path, monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    monkeypatch.setattr(workbook, "USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING", False)
    registry = tmp_path / "registry.json"
    registry.write_text('{"sites":[]}', encoding="utf-8")
    monkeypatch.setattr(workbook, "DIAGNOSIS_RENDERING_SITE_REGISTRY_PATH", registry)

    result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=tmp_path / "not_allowlisted_render.xlsx",
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_live_context(),
    )

    assert result["diagnosis_rendering_enabled_for_address"] is False
    assert result["rendering_mode"] == "legacy"
