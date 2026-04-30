from __future__ import annotations

from core.dispatch import IntentDispatcher
from core.intent_parser import IntentParser, load_intent_parser_config, normalize_address, parse_explicit_target
from core.query_core import parse_operator_query, run_structured_intent


def _parser() -> IntentParser:
    return IntentParser(config=load_intent_parser_config(), client=None)


def test_normalize_address_expands_common_suffixes() -> None:
    assert normalize_address("725 Howard Ave") == "725 howard avenue"
    assert normalize_address("170   Tapscott st.") == "170 tapscott street"


def test_exact_address_resolves_to_authoritative_target() -> None:
    target = parse_explicit_target("What can you tell me about 725 Howard Ave?")
    assert target.kind == "address"
    assert target.site_id == "000007"
    assert target.address_text == "725 Howard Ave"


def test_address_query_routes_to_building_health() -> None:
    payload = _parser().parse("How does 170 tapscott look?")
    assert payload.intent == "get_building_health"
    assert payload.entities.site_id == "000007"
    assert payload.entities.device == "170 Tapscott St"
    assert payload.ambiguous is False


def test_normalized_address_query_routes_without_clarification() -> None:
    payload = _parser().parse("What can you tell me about 725 Howard Ave?")
    assert payload.intent == "get_building_health"
    assert payload.entities.site_id == "000007"
    assert payload.entities.device == "725 Howard Ave"
    assert payload.clarification_needed is None


def test_street_only_address_prompts_clarification() -> None:
    parser = _parser()
    dispatcher = IntentDispatcher(parser=parser, executor=lambda _ops, _intent: {"assistant_answer": "ok", "operator_summary": "ok"})
    result = dispatcher.dispatch(object(), "What can you tell me about Howard Ave?")
    assert result.status == "clarify"
    assert result.intent is not None
    assert "Howard" in (result.intent.clarification_needed or "")


def test_followup_with_identifier_overrides_prior_address_context() -> None:
    payload = _parser().parse(
        "What can you tell me about 000007.030?",
        history=[
            {"role": "user", "content": "How does 170 tapscott look?"},
            {"role": "assistant", "content": "Building summary."},
        ],
    )
    assert payload.intent == "get_building_health"
    assert payload.entities.building == "000007.030"


def test_followup_without_identifier_reuses_prior_address_target() -> None:
    payload = _parser().parse(
        "What can you tell me about it?",
        history=[
            {"role": "user", "content": "How does 170 tapscott look?"},
            {"role": "assistant", "content": "Building summary."},
        ],
    )
    assert payload.intent == "get_building_health"
    assert payload.entities.site_id == "000007"
    assert payload.entities.device == "170 Tapscott St"


def test_direct_query_parser_resolves_exact_address_to_building_health() -> None:
    parsed = parse_operator_query("What can you tell me about 725 Howard Ave?")
    assert parsed["action"] == "get_building_health"
    assert parsed["params"]["address_text"] == "725 Howard Ave"
    assert parsed["params"]["site_id"] == "000007"


def test_rerun_followup_from_address_stays_building_scoped() -> None:
    parser = _parser()
    intent = parser.parse(
        "rescan",
        history=[
            {"role": "user", "content": "How is 225 buffalo?"},
            {"role": "assistant", "content": "Building 000007.040 summary."},
        ],
    )
    assert intent.intent == "rerun_latest_scan"
    assert intent.entities.device == "225 Buffalo Ave"

    class FakeOps:
        def _resolve_building_from_address(self, address: str):
            assert address == "225 Buffalo Ave"
            return {"best_match": {"prefix": "000007.040"}}

        def trigger_scan_refresh(self, site_id=None, building_id=None, address_text=None):
            assert site_id == "000007"
            assert building_id == "000007.040"
            assert address_text == "225 Buffalo Ave"
            return {
                "available": False,
                "triggered": False,
                "error": "No scan trigger command is configured for Jake.",
                "before_scan": {"started_at": "2026-03-14T16:13:44Z"},
                "site_id": site_id,
                "building_id": building_id,
                "address_text": address_text,
            }

    payload = run_structured_intent(FakeOps(), intent)
    assert payload["matched_action"] == "rerun_latest_scan"
    assert payload["params"]["building_id"] == "000007.040"
    assert payload["result"]["building_id"] == "000007.040"
    assert payload["result"]["available"] is False
    assert "for 000007.040" in payload["operator_summary"]
