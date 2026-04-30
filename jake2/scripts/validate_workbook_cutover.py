#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audits import jake_audit_workbook as workbook_module
from mcp.jake_ops_mcp import JakeOps


def _normalize_top_unknown_fields(items: Any) -> list[str]:
    fields: list[str] = []
    for item in list(items or []):
        if isinstance(item, dict):
            field = str(item.get("field") or "").strip()
            if field:
                fields.append(field)
        else:
            text = str(item or "").strip()
            if text:
                fields.append(text)
    return fields


def _registry_path() -> Path:
    return workbook_module.DIAGNOSIS_RENDERING_SITE_REGISTRY_PATH


def load_site_registry(path: str | Path | None = None) -> dict[str, Any]:
    registry_path = Path(path) if path else _registry_path()
    if not registry_path.exists():
        return {"sites": []}
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return {"sites": []}
    if not isinstance(payload, dict):
        return {"sites": []}
    sites = payload.get("sites")
    if not isinstance(sites, list):
        payload["sites"] = []
    return payload


def save_site_registry(payload: dict[str, Any], path: str | Path | None = None) -> Path:
    registry_path = Path(path) if path else _registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return registry_path


def _normalize_address(address: str) -> str:
    return workbook_module.normalize_address_text(address)


def _block_reason_from_summary(summary: dict[str, Any]) -> str:
    blockers: list[str] = []
    if int(summary.get("rows_blocked_from_cutover") or 0):
        blockers.append(f"{int(summary.get('rows_blocked_from_cutover') or 0)} blocked row(s)")
    if int(summary.get("needs_more_evidence_count") or 0):
        blockers.append(f"{int(summary.get('needs_more_evidence_count') or 0)} need more evidence")
    if int(summary.get("blocking_contradictions_count") or 0):
        blockers.append(f"{int(summary.get('blocking_contradictions_count') or 0)} blocking contradiction(s)")
    if int(summary.get("remaining_high_severity_mismatches") or 0):
        blockers.append(f"{int(summary.get('remaining_high_severity_mismatches') or 0)} high-severity mismatch(es)")
    unknowns = list(summary.get("top_unknown_fields") or [])
    if unknowns:
        blockers.append(f"top unknowns: {', '.join(unknowns[:3])}")
    return "; ".join(blockers) or "site is not safe for diagnosis rendering"


def update_site_registry_from_summary(
    summary: dict[str, Any],
    *,
    enable_on_safe: bool = False,
    path: str | Path | None = None,
) -> dict[str, Any]:
    payload = load_site_registry(path)
    sites = list(payload.get("sites") or [])
    normalized = _normalize_address(str(summary.get("address") or ""))
    now = datetime.now(timezone.utc).isoformat()
    safe = bool(summary.get("safe_to_enable_diagnosis_rendering"))
    matched = False
    for row in sites:
        if _normalize_address(str(row.get("address") or "")) != normalized:
            continue
        matched = True
        was_enabled = bool(row.get("rendering_enabled"))
        previous_status = str(row.get("validation_status") or "")
        previous_consecutive_safe = int(row.get("consecutive_safe_validations") or 0)
        previous_consecutive_blocked = int(row.get("consecutive_blocked_validations") or 0)
        previous_failure_count = int(row.get("validation_failure_count") or 0)
        row["address"] = str(summary.get("address") or row.get("address") or "")
        row["last_validated_at"] = now
        row["validation_status"] = "safe" if safe else "blocked"
        row["rendering_enabled"] = True if (safe and (enable_on_safe or was_enabled)) else False
        row["last_block_reason"] = "" if safe else _block_reason_from_summary(summary)
        row["verified_ready_percent"] = int(summary.get("verified_ready_percent") or 0)
        row["rows_blocked_from_cutover"] = int(summary.get("rows_blocked_from_cutover") or 0)
        row["needs_more_evidence_count"] = int(summary.get("needs_more_evidence_count") or 0)
        row["blocking_contradictions_count"] = int(summary.get("blocking_contradictions_count") or 0)
        row["remaining_high_severity_mismatches"] = int(summary.get("remaining_high_severity_mismatches") or 0)
        row["top_unknown_fields"] = list(summary.get("top_unknown_fields") or [])
        row["recommended_collector_improvements"] = list(summary.get("recommended_collector_improvements") or [])
        row["consecutive_safe_validations"] = previous_consecutive_safe + 1 if safe else 0
        row["consecutive_blocked_validations"] = previous_consecutive_blocked + 1 if not safe else 0
        row["validation_failure_count"] = previous_failure_count + (0 if safe else 1)
        row["last_validation_summary"] = {
            "verified_ready_percent": int(summary.get("verified_ready_percent") or 0),
            "rows_blocked_from_cutover": int(summary.get("rows_blocked_from_cutover") or 0),
            "needs_more_evidence_count": int(summary.get("needs_more_evidence_count") or 0),
            "blocking_contradictions_count": int(summary.get("blocking_contradictions_count") or 0),
            "remaining_high_severity_mismatches": int(summary.get("remaining_high_severity_mismatches") or 0),
            "top_unknown_fields": list(summary.get("top_unknown_fields") or []),
        }
        if was_enabled and not safe:
            row["regression_detected"] = True
        elif safe:
            row.pop("regression_detected", None)
        if previous_status == "safe" and safe:
            row["stable"] = bool(row["consecutive_safe_validations"] >= 7)
        elif safe:
            row["stable"] = bool(row["consecutive_safe_validations"] >= 7)
        else:
            row["stable"] = False
        break
    if not matched:
        sites.append(
            {
                "address": str(summary.get("address") or ""),
                "last_validated_at": now,
                "validation_status": "safe" if safe else "blocked",
                "rendering_enabled": bool(safe and enable_on_safe),
                "last_block_reason": "" if safe else _block_reason_from_summary(summary),
                "verified_ready_percent": int(summary.get("verified_ready_percent") or 0),
                "rows_blocked_from_cutover": int(summary.get("rows_blocked_from_cutover") or 0),
                "needs_more_evidence_count": int(summary.get("needs_more_evidence_count") or 0),
                "blocking_contradictions_count": int(summary.get("blocking_contradictions_count") or 0),
                "remaining_high_severity_mismatches": int(summary.get("remaining_high_severity_mismatches") or 0),
                "top_unknown_fields": list(summary.get("top_unknown_fields") or []),
                "recommended_collector_improvements": list(summary.get("recommended_collector_improvements") or []),
                "consecutive_safe_validations": 1 if safe else 0,
                "consecutive_blocked_validations": 0 if safe else 1,
                "validation_failure_count": 0 if safe else 1,
                "stable": False,
                "last_validation_summary": {
                    "verified_ready_percent": int(summary.get("verified_ready_percent") or 0),
                    "rows_blocked_from_cutover": int(summary.get("rows_blocked_from_cutover") or 0),
                    "needs_more_evidence_count": int(summary.get("needs_more_evidence_count") or 0),
                    "blocking_contradictions_count": int(summary.get("blocking_contradictions_count") or 0),
                    "remaining_high_severity_mismatches": int(summary.get("remaining_high_severity_mismatches") or 0),
                    "top_unknown_fields": list(summary.get("top_unknown_fields") or []),
                },
            }
        )
    payload["sites"] = sorted(sites, key=lambda item: _normalize_address(str(item.get("address") or "")))
    save_site_registry(payload, path)
    return payload


def enable_diagnosis_rendering_for_site(
    address: str,
    *,
    output_path: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> dict[str, Any]:
    summary = validate_address(address, output_path=output_path)
    payload = update_site_registry_from_summary(summary, enable_on_safe=True, path=registry_path)
    site_row = next(
        (
            row
            for row in list(payload.get("sites") or [])
            if _normalize_address(str(row.get("address") or "")) == _normalize_address(address)
        ),
        {},
    )
    return {
        "address": address,
        "validated_summary": summary,
        "rendering_enabled": bool(site_row.get("rendering_enabled")),
        "validation_status": str(site_row.get("validation_status") or "blocked"),
        "last_block_reason": str(site_row.get("last_block_reason") or ""),
        "registry_path": str(Path(registry_path) if registry_path else _registry_path()),
    }


def _safe_to_enable_diagnosis_rendering(result: dict[str, Any]) -> bool:
    cutover_report = result.get("cutover_report")
    evidence_gap_report = result.get("evidence_gap_report")
    if not isinstance(cutover_report, dict) or not isinstance(evidence_gap_report, dict):
        return False
    return (
        int(cutover_report.get("rows_blocked_from_cutover") or 0) == 0
        and int(cutover_report.get("remaining_high_severity_mismatches") or 0) == 0
        and int(cutover_report.get("needs_more_evidence_count") or 0) == 0
        and int(cutover_report.get("blocking_contradictions_count") or 0) == 0
    )


def summarize_validation_result(address: str, result: dict[str, Any]) -> dict[str, Any]:
    cutover_report = result.get("cutover_report") if isinstance(result.get("cutover_report"), dict) else {}
    evidence_gap_report = result.get("evidence_gap_report") if isinstance(result.get("evidence_gap_report"), dict) else {}
    summary = {
        "address": address,
        "row_count": int(result.get("row_count") or 0),
        "verified_ready_percent": int(result.get("weighted_ready_percent") or 0),
        "rows_safe_for_cutover": int(cutover_report.get("rows_safe_for_cutover") or 0),
        "rows_blocked_from_cutover": int(cutover_report.get("rows_blocked_from_cutover") or 0),
        "needs_more_evidence_count": int(cutover_report.get("needs_more_evidence_count") or 0),
        "blocking_contradictions_count": int(cutover_report.get("blocking_contradictions_count") or 0),
        "remaining_high_severity_mismatches": int(cutover_report.get("remaining_high_severity_mismatches") or 0),
        "top_unknown_fields": _normalize_top_unknown_fields(evidence_gap_report.get("top_unknown_fields")),
        "recommended_collector_improvements": list(evidence_gap_report.get("recommended_collector_improvements") or []),
        "rendering_mode": str(result.get("rendering_mode") or "legacy"),
        "safe_to_enable_diagnosis_rendering": _safe_to_enable_diagnosis_rendering(result),
    }
    return summary


@contextmanager
def _validation_flag_overrides():
    old_debug = workbook_module.CAPTURE_DIAGNOSIS_DEBUG_FOR_WORKBOOK
    old_render = workbook_module.USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING
    try:
        workbook_module.CAPTURE_DIAGNOSIS_DEBUG_FOR_WORKBOOK = True
        workbook_module.USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING = False
        yield
    finally:
        workbook_module.CAPTURE_DIAGNOSIS_DEBUG_FOR_WORKBOOK = old_debug
        workbook_module.USE_DIAGNOSIS_ENGINE_FOR_WORKBOOK_RENDERING = old_render


def validate_address(address: str, *, output_path: str | Path | None = None) -> dict[str, Any]:
    with _validation_flag_overrides():
        ops = JakeOps()
        if output_path is not None:
            result = ops.generate_nycha_audit_workbook(address_text=address, out_path=str(output_path))
        else:
            with tempfile.TemporaryDirectory(prefix="jake2-cutover-") as tmpdir:
                temp_output = Path(tmpdir) / "validation_workbook.xlsx"
                result = ops.generate_nycha_audit_workbook(address_text=address, out_path=str(temp_output))
        return summarize_validation_result(address, result)


def aggregate_site_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    blocked_reasons_by_site: list[dict[str, Any]] = []
    for summary in summaries:
        if not summary.get("safe_to_enable_diagnosis_rendering"):
            blocked_reasons_by_site.append(
                {
                    "address": summary.get("address"),
                    "rows_blocked_from_cutover": summary.get("rows_blocked_from_cutover"),
                    "needs_more_evidence_count": summary.get("needs_more_evidence_count"),
                    "blocking_contradictions_count": summary.get("blocking_contradictions_count"),
                    "remaining_high_severity_mismatches": summary.get("remaining_high_severity_mismatches"),
                }
            )
    return {
        "total_sites": len(summaries),
        "sites_safe": sum(1 for item in summaries if item.get("safe_to_enable_diagnosis_rendering")),
        "sites_blocked": sum(1 for item in summaries if not item.get("safe_to_enable_diagnosis_rendering")),
        "blocked_reasons_by_site": blocked_reasons_by_site,
    }


def _load_addresses(args) -> list[str]:
    addresses = list(args.address or [])
    if args.addresses_file:
        file_path = Path(args.addresses_file)
        for line in file_path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text:
                addresses.append(text)
    seen: set[str] = set()
    deduped: list[str] = []
    for address in addresses:
        if address not in seen:
            seen.add(address)
            deduped.append(address)
    return deduped


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate whether diagnosis-driven workbook rendering is safe for one or more live sites. Run with .venv/bin/python scripts/validate_workbook_cutover.py ..."
    )
    parser.add_argument("--address", action="append", help="NYCHA building address to validate. Repeat for multiple sites.")
    parser.add_argument("--addresses-file", help="Path to a newline-delimited file of addresses to validate.")
    parser.add_argument("--output-path", help="Optional workbook output path for single-site validation.")
    parser.add_argument("--json-report-path", help="Optional path to write the JSON validation summary.")
    parser.add_argument("--enable-safe-site", action="store_true", help="For a single site, validate first and enable diagnosis rendering only if the site is safe.")
    parser.add_argument("--registry-path", help="Optional path to the per-site rendering registry JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    addresses = _load_addresses(args)
    if not addresses:
        parser.error("Provide at least one --address or an --addresses-file.")

    payload: dict[str, Any]
    if args.enable_safe_site:
        if len(addresses) != 1:
            parser.error("--enable-safe-site requires exactly one address.")
        payload = enable_diagnosis_rendering_for_site(
            addresses[0],
            output_path=args.output_path,
            registry_path=args.registry_path,
        )
    else:
        summaries = [
            validate_address(
                address,
                output_path=args.output_path if len(addresses) == 1 and args.output_path else None,
            )
            for address in addresses
        ]
        if len(summaries) == 1:
            payload = summaries[0]
        else:
            payload = {
                "sites": summaries,
                "aggregate": aggregate_site_summaries(summaries),
            }

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if args.json_report_path:
        Path(args.json_report_path).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
