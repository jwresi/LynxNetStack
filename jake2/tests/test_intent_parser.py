from __future__ import annotations

import json
from pathlib import Path

from core.dispatch import IntentDispatcher
from core.intent_parser import IntentParser, load_intent_parser_config


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "nl"


class FakeClient:
    def __init__(self, response: str) -> None:
        self.response = response

    def generate(self, prompt: str, *, system_prompt: str) -> str:
        assert prompt
        assert system_prompt
        return self.response


class FailingClient:
    def generate(self, prompt: str, *, system_prompt: str) -> str:
        raise RuntimeError("summary failed")


def _load_cases(name: str) -> list[dict[str, str]]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_known_query_variants_map_to_same_intent_and_site() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=None)
    cases = _load_cases("everyday_language_regression.json")[:3]
    for case in cases:
        payload = parser.parse(case["raw"])
        assert payload.intent == case["expected_intent"]
        assert payload.entities.site_id == case["expected_site"]
        assert payload.confidence >= 0.85


def test_ambiguous_query_requires_specific_clarification() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=None)
    payload = parser.parse("how many customers are online right now?")
    assert payload.intent == "get_online_customers"
    assert payload.ambiguous is True
    assert payload.entities.site_id is None
    assert payload.clarification_needed


def test_unrecognized_query_stays_below_confidence_floor_and_does_not_execute() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=None)
    call_count = {"count": 0}

    def fake_executor(_ops, _intent):
        call_count["count"] += 1
        return {"assistant_answer": "should not run", "operator_summary": "should not run"}

    dispatcher = IntentDispatcher(parser=parser, executor=fake_executor)
    result = dispatcher.dispatch(object(), "can you vibe check the goblin router")
    assert result.status == "rephrase"
    assert result.intent is not None
    assert result.intent.confidence < 0.40
    assert result.intent.raw == "can you vibe check the goblin router"
    assert call_count["count"] == 0


def test_malformed_parser_response_is_classified_and_blocked() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=FakeClient("not-json"))
    call_count = {"count": 0}

    def fake_executor(_ops, _intent):
        call_count["count"] += 1
        return {"assistant_answer": "should not run", "operator_summary": "should not run"}

    dispatcher = IntentDispatcher(parser=parser, executor=fake_executor)
    result = dispatcher.dispatch(object(), "describe moonbeam turbulence at nowhere")
    assert result.status == "error"
    assert result.classification == "code_error"
    assert call_count["count"] == 0


def test_dispatch_executes_structured_intent_not_raw_text() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=None)
    captured = {}

    def fake_executor(_ops, intent):
        captured["intent"] = intent
        return {"assistant_answer": "ok", "operator_summary": "ok"}

    dispatcher = IntentDispatcher(parser=parser, executor=fake_executor)
    result = dispatcher.dispatch(object(), "what's the live count at the NYCHA site")
    assert result.status == "executed"
    assert captured["intent"].intent == "get_online_customers"
    assert captured["intent"].entities.site_id == "000007"
    assert captured["intent"].raw == "what's the live count at the NYCHA site"


def test_declarative_site_statement_maps_to_site_summary_without_clarification() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=None)
    payload = parser.parse("Chenoweth is running dhcp")
    assert payload.intent == "get_site_summary"
    assert payload.entities.site_id == "000008"
    assert payload.confidence == 0.75
    assert payload.ambiguous is False
    assert payload.clarification_needed is None


def test_compress_history_keeps_short_sessions_as_is() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=None)
    history = [
        {"role": "user", "content": "how is nycha doing"},
        {"role": "assistant", "content": "NYCHA looks stable."},
    ]
    compressed = parser.compress_history(history)
    assert compressed == {"summary": None, "turns": history}


def test_compress_history_falls_back_to_last_four_turns_on_summary_failure() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=FailingClient())
    history = [
        {"role": "user", "content": f"turn {index}"}
        for index in range(8)
    ]
    compressed = parser.compress_history(history)
    assert compressed == {"summary": None, "turns": history[-4:]}


def test_street_address_resolves_to_correct_site() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=None)
    cases = _load_cases("get_site_summary_street_address.json")
    for case in cases:
        payload = parser.parse(case["raw"])
        assert payload.intent == case["expected_intent"], f"{case['raw']!r}: intent={payload.intent}"
        assert payload.entities.site_id == case["expected_site"], f"{case['raw']!r}: site_id={payload.entities.site_id}"
        assert payload.confidence >= 0.75, f"{case['raw']!r}: confidence={payload.confidence}"


def test_history_reference_resolves_alerts_there_to_prior_site() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=None)
    payload = parser.parse(
        "what about the alerts there",
        history=[
            {"role": "user", "content": "how is nycha doing"},
            {"role": "assistant", "content": "000007 looks stable."},
        ],
    )
    assert payload.intent == "get_site_alerts"
    assert payload.entities.site_id == "000007"
    assert payload.ambiguous is False


def test_history_reference_carries_forward_previous_site_action() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=None)
    payload = parser.parse(
        "same thing for chenoweth",
        history=[
            {"role": "user", "content": "how is nycha doing"},
            {"role": "assistant", "content": "000007 looks stable."},
            {"role": "user", "content": "what about the alerts there"},
            {"role": "assistant", "content": "000007 has no active alerts."},
        ],
    )
    assert payload.intent == "get_site_alerts"
    assert payload.entities.site_id == "000008"
    assert payload.ambiguous is False


def test_known_subscriber_name_resolves_to_cpe_state_without_model() -> None:
    parser = IntentParser(config=load_intent_parser_config(), client=None)
    payload = parser.parse("what is wrong with savoy1unit3f")
    assert payload.intent == "get_cpe_state"
    assert payload.entities.device == "60:83:e7:af:5f:ce"
    assert payload.confidence >= 0.95
