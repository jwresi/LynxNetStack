from __future__ import annotations

import json
from pathlib import Path

from core.query_core import run_operator_query
from mcp.jake_ops_mcp import JakeOps


ROOT = Path(__file__).resolve().parents[1]
QUERY_BASELINE = ROOT / "tests" / "baselines" / "query_baseline.json"


def _get_path(payload: dict[str, object], dotted: str):
    current = payload
    for part in dotted.split("."):
        if not isinstance(current, dict):
            raise AssertionError(f"Cannot descend into non-dict for path {dotted}")
        current = current[part]
    return current


def test_query_contract_matches_reviewed_baseline(monkeypatch) -> None:
    monkeypatch.setenv("JAKE_OPS_DB", "data/network_map.db")
    ops = JakeOps()
    baseline = json.loads(QUERY_BASELINE.read_text(encoding="utf-8"))

    for case in baseline:
        payload = run_operator_query(ops, case["query"])
        for path, expected in case["expected"].items():
            assert _get_path(payload, path) == expected, f"{case['query']} -> {path}"
