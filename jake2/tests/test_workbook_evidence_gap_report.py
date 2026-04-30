from __future__ import annotations

from audits.jake_audit_workbook import AuditRow, generate_nycha_audit_workbook, generate_workbook_evidence_gap_report
from tests.test_workbook_diagnosis_comparison import (
    FIXTURE_DIR,
    _configure_audit_fixture_env,
    _make_live_context,
    _make_sparse_live_context,
)


def _row(
    unit: str,
    *,
    unknowns: list[str] | None = None,
    stale_sources: list[str] | None = None,
) -> AuditRow:
    unknowns = unknowns or []
    stale_sources = stale_sources or []
    return AuditRow(
        unit_key=unit,
        unit_label=unit,
        mac_cpe="AA:11:22:33:44:55",
        pppoe_unit=unit,
        notes="Good",
        image_ap_make="",
        image_ap_sticker_apartment="",
        image_ap_mac="",
        inventory_mac_verification="",
        implication="",
        action="None",
        legacy_status="Good",
        diagnosis_status="HEALTHY",
        diagnosis_confidence="high",
        evidence_unknowns=list(unknowns),
        evidence_unknowns_summary="; ".join(unknowns),
        evidence_contradictions=[],
        evidence_contradictions_summary="",
        evidence_stale_sources=list(stale_sources),
        evidence_stale_sources_summary="; ".join(stale_sources),
        reality_unknowns_count=len(unknowns),
    )


def test_missing_l1_counted_correctly() -> None:
    rows = [
        _row("1A", unknowns=["physical_truth.port_up: expected port state is unknown."]),
        _row("1B", unknowns=["physical_truth.port_speed: expected port speed is unknown."]),
        _row("1C"),
    ]

    report = generate_workbook_evidence_gap_report(rows)

    assert report["rows_missing_l1"] == 2


def test_missing_pppoe_counted_correctly() -> None:
    report = generate_workbook_evidence_gap_report(
        [
            _row("1A", unknowns=["auth_truth.pppoe_logs: PPPoE session and failure evidence are both unknown."]),
            _row("1B"),
        ]
    )

    assert report["rows_missing_pppoe"] == 1


def test_missing_dhcp_counted_correctly() -> None:
    report = generate_workbook_evidence_gap_report(
        [
            _row("1A", unknowns=["dhcp_truth.offers_seen: DHCP offer evidence is unavailable."]),
            _row("1B", unknowns=["dhcp_truth.discovers_seen: DHCP discover evidence is unavailable."]),
            _row("1C"),
        ]
    )

    assert report["rows_missing_dhcp"] == 2


def test_missing_controller_freshness_counted_correctly() -> None:
    report = generate_workbook_evidence_gap_report(
        [
            _row("1A", stale_sources=["controller_truth.controller_snapshot: controller data is marked stale."]),
            _row("1B", unknowns=["controller_truth.controller_last_seen: controller timestamp missing."]),
        ]
    )

    assert report["rows_missing_controller_freshness"] == 2


def test_missing_global_and_historical_mac_search_counted_correctly() -> None:
    report = generate_workbook_evidence_gap_report(
        [
            _row(
                "1A",
                unknowns=[
                    "l2_truth.global_search: all-switch MAC search completion is unknown.",
                    "l2_truth.historical_search: historical MAC search completion is unknown.",
                ],
            ),
            _row("1B", unknowns=["l2_truth.global_search: all-switch MAC search completion is unknown."]),
        ]
    )

    assert report["rows_missing_global_mac_search"] == 2
    assert report["rows_missing_historical_mac_search"] == 1


def test_top_unknown_fields_sorted_by_count() -> None:
    report = generate_workbook_evidence_gap_report(
        [
            _row("1A", unknowns=["physical_truth.port_up: expected port state is unknown."]),
            _row("1B", unknowns=["physical_truth.port_up: expected port state is unknown."]),
            _row("1C", unknowns=["auth_truth.pppoe_logs: PPPoE evidence unavailable."]),
        ]
    )

    assert report["top_unknown_fields"][0] == {"field": "physical_truth.port_up", "count": 2}
    assert report["top_unknown_fields"][1] == {"field": "auth_truth.pppoe_logs", "count": 1}


def test_recommended_collector_improvements_populated() -> None:
    report = generate_workbook_evidence_gap_report(
        [
            _row(
                "1A",
                unknowns=[
                    "physical_truth.port_speed: expected port speed is unknown.",
                    "auth_truth.pppoe_logs: PPPoE evidence unavailable.",
                    "dhcp_truth.offers_seen: DHCP offer evidence is unavailable.",
                    "l2_truth.global_search: all-switch MAC search completion is unknown.",
                    "l2_truth.historical_search: historical MAC search completion is unknown.",
                ],
                stale_sources=["controller_truth.controller_snapshot: controller data is marked stale."],
            )
        ]
    )

    recommendations = report["recommended_collector_improvements"]
    assert any("MikroTik L1 collectors" in item for item in recommendations)
    assert any("PPPoE diagnostics" in item for item in recommendations)
    assert any("DHCP observation" in item for item in recommendations)
    assert any("controller freshness" in item.lower() for item in recommendations)
    assert any("global MAC search completion" in item for item in recommendations)
    assert any("historical MAC search completion" in item for item in recommendations)


def test_enriched_fixture_reduces_unknown_heavy_gaps(tmp_path, monkeypatch) -> None:
    _configure_audit_fixture_env(monkeypatch)
    sparse_result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=tmp_path / "sparse_gap.xlsx",
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_sparse_live_context(),
    )
    enriched_result = generate_nycha_audit_workbook(
        "123-125 Test St",
        out_path=tmp_path / "enriched_gap.xlsx",
        template_path=FIXTURE_DIR / "nycha_template.xlsx",
        ops=None,
        _live_context_override=_make_live_context(),
    )

    sparse_gap = sparse_result["evidence_gap_report"]
    enriched_gap = enriched_result["evidence_gap_report"]

    assert enriched_gap["rows_missing_l1"] < sparse_gap["rows_missing_l1"]
    assert enriched_gap["rows_missing_pppoe"] < sparse_gap["rows_missing_pppoe"]
    assert enriched_gap["rows_missing_controller_freshness"] < sparse_gap["rows_missing_controller_freshness"]
    sparse_unknown_rows = sum(item["rows"] for item in sparse_gap["unknown_count_distribution"] if item["unknown_count"] >= 3)
    enriched_unknown_rows = sum(item["rows"] for item in enriched_gap["unknown_count_distribution"] if item["unknown_count"] >= 3)
    assert enriched_unknown_rows < sparse_unknown_rows
