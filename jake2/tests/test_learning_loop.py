from __future__ import annotations

import json

from core.intent_schema import IntentEntities, IntentSchema
from core.jake_query import confirm_last_query, save_last_query_result


def test_save_last_query_and_confirm_append_confirmed_example(tmp_path) -> None:
    last_query_path = tmp_path / ".jake_last_query.json"
    examples_path = tmp_path / "intent_examples.jsonl"
    archive_path = tmp_path / "intent_examples_archive.jsonl"
    intent = IntentSchema(
        intent="get_cpe_state",
        entities=IntentEntities(site_id="000007"),
        confidence=0.94,
        raw="what is wrong with DC:62:79:9D:C1:AD",
    )

    saved = save_last_query_result(intent.raw, intent, last_query_path=last_query_path)
    assert saved["resolved_intent"] == "get_cpe_state"
    assert saved["resolved_site"] == "000007"
    assert saved["confidence"] == 0.94

    confirmed = confirm_last_query(
        last_query_path=last_query_path,
        examples_path=examples_path,
        archive_path=archive_path,
    )
    assert confirmed["confirmed"] is True

    lines = [json.loads(line) for line in examples_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0]["raw"] == "what is wrong with DC:62:79:9D:C1:AD"
    assert lines[0]["resolved_intent"] == "get_cpe_state"
    assert lines[0]["resolved_site"] == "000007"
    assert lines[0]["confidence"] == 0.94
    assert lines[0]["confirmed"] is True
    assert "timestamp" in lines[0]


def test_confirm_archives_entries_above_limit(tmp_path) -> None:
    last_query_path = tmp_path / ".jake_last_query.json"
    examples_path = tmp_path / "intent_examples.jsonl"
    archive_path = tmp_path / "intent_examples_archive.jsonl"
    examples_path.write_text(
        "".join(
            json.dumps(
                {
                    "raw": f"q{i}",
                    "resolved_intent": "get_online_customers",
                    "resolved_site": "000007",
                    "confidence": 0.9,
                    "confirmed": True,
                    "timestamp": f"2026-04-17T00:00:{i % 60:02d}+00:00",
                },
                sort_keys=True,
            )
            + "\n"
            for i in range(500)
        ),
        encoding="utf-8",
    )
    intent = IntentSchema(
        intent="trace_mac",
        entities=IntentEntities(site_id="000007"),
        confidence=0.91,
        raw="trace this MAC for me DC:62:79:9D:C1:AD",
    )
    save_last_query_result(intent.raw, intent, last_query_path=last_query_path)

    confirm_last_query(
        last_query_path=last_query_path,
        examples_path=examples_path,
        archive_path=archive_path,
        max_entries=500,
    )

    current = [json.loads(line) for line in examples_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    archived = [json.loads(line) for line in archive_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(current) == 500
    assert len(archived) == 1
    assert archived[0]["raw"] == "q0"
    assert current[-1]["resolved_intent"] == "trace_mac"
