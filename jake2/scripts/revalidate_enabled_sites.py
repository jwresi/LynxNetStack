#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.validate_workbook_cutover import (
    load_site_registry,
    update_site_registry_from_summary,
    validate_address,
)


def revalidate_enabled_sites(*, registry_path: str | Path | None = None) -> dict[str, Any]:
    payload = load_site_registry(registry_path)
    enabled_rows = [row for row in list(payload.get("sites") or []) if bool(row.get("rendering_enabled"))]
    results: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    for row in enabled_rows:
        address = str(row.get("address") or "").strip()
        if not address:
            continue
        summary = validate_address(address)
        updated = update_site_registry_from_summary(summary, enable_on_safe=False, path=registry_path)
        refreshed = next(
            (
                site_row
                for site_row in list(updated.get("sites") or [])
                if str(site_row.get("address") or "").strip().lower() == address.lower()
            ),
            {},
        )
        result_row = {
            "address": address,
            "validation_status": refreshed.get("validation_status"),
            "rendering_enabled": refreshed.get("rendering_enabled"),
            "last_block_reason": refreshed.get("last_block_reason") or "",
            "consecutive_safe_validations": int(refreshed.get("consecutive_safe_validations") or 0),
            "consecutive_blocked_validations": int(refreshed.get("consecutive_blocked_validations") or 0),
            "stable": bool(refreshed.get("stable")),
        }
        results.append(result_row)
        if refreshed.get("regression_detected"):
            regressions.append(result_row)

    final_payload = load_site_registry(registry_path)
    return {
        "registry_path": str(Path(registry_path).resolve() if registry_path else ""),
        "enabled_sites_checked": len(enabled_rows),
        "regressions_detected": len(regressions),
        "results": results,
        "regressions": regressions,
        "sites": list(final_payload.get("sites") or []),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Revalidate all currently enabled diagnosis-rendering sites and disable regressions automatically. Run with .venv/bin/python scripts/revalidate_enabled_sites.py ..."
    )
    parser.add_argument("--registry-path", help="Optional path to the site registry JSON.")
    parser.add_argument("--json-output", help="Optional path to write the JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = revalidate_enabled_sites(registry_path=args.registry_path)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.json_output:
        Path(args.json_output).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
