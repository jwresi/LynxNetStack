from __future__ import annotations

import json
from pathlib import Path

from core.intent_parser import IntentParser, load_intent_parser_config


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "nl"


def test_all_intent_fixtures_resolve_to_expected_intent() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=None)
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        cases = json.loads(path.read_text(encoding="utf-8"))
        for case in cases:
            payload = parser.parse(case["raw"])
            assert payload.intent == case["expected_intent"], f"{path.name}: {case['raw']}"
            assert payload.entities.site_id == case["expected_site"], f"{path.name}: {case['raw']}"
