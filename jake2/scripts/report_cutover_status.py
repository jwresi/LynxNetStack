#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.validate_workbook_cutover import load_site_registry


def summarize_registry(payload: dict[str, Any]) -> dict[str, Any]:
    sites = list(payload.get("sites") or [])
    blockers = Counter()
    unknown_fields = Counter()
    safe_sites = 0
    enabled_sites = 0
    blocked_sites = 0
    stable_sites = 0
    total_needs_more_evidence = 0
    for row in sites:
        status = str(row.get("validation_status") or "blocked")
        enabled = bool(row.get("rendering_enabled"))
        if status == "safe":
            safe_sites += 1
        else:
            blocked_sites += 1
        if enabled:
            enabled_sites += 1
        if bool(row.get("stable")):
            stable_sites += 1
        total_needs_more_evidence += int(row.get("needs_more_evidence_count") or 0)
        block_reason = str(row.get("last_block_reason") or "").strip()
        if status != "safe" and block_reason:
            blockers[block_reason] += 1
        for field in list(row.get("top_unknown_fields") or []):
            text = str(field or "").strip()
            if text:
                unknown_fields[text] += 1
    total_sites = len(sites)
    return {
        "total_sites": total_sites,
        "safe_sites": safe_sites,
        "enabled_sites": enabled_sites,
        "blocked_sites": blocked_sites,
        "stable_sites": stable_sites,
        "percent_sites_safe": round((safe_sites / total_sites) * 100, 2) if total_sites else 0.0,
        "percent_sites_enabled": round((enabled_sites / total_sites) * 100, 2) if total_sites else 0.0,
        "percent_sites_stable": round((stable_sites / total_sites) * 100, 2) if total_sites else 0.0,
        "average_needs_more_evidence_count": round(total_needs_more_evidence / total_sites, 2) if total_sites else 0.0,
        "top_blockers": [{"reason": reason, "count": count} for reason, count in blockers.most_common(10)],
        "top_unknown_fields": [{"field": field, "count": count} for field, count in unknown_fields.most_common(10)],
        "sites": sites,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report persistent diagnosis-rendering cutover status from the site registry. Run with .venv/bin/python scripts/report_cutover_status.py ..."
    )
    parser.add_argument("--registry-path", help="Optional path to the site registry JSON.")
    parser.add_argument("--json-output", help="Optional path to write the JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = load_site_registry(Path(args.registry_path) if args.registry_path else None)
    summary = summarize_registry(payload)
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    print(rendered)
    if args.json_output:
        Path(args.json_output).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
