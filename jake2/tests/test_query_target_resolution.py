from __future__ import annotations

from core.dispatch import IntentDispatcher
from core.intent_parser import IntentParser, load_intent_parser_config, parse_explicit_target
from core.query_core import format_operator_response, parse_operator_query, run_structured_intent
from mcp.jake_ops_mcp import JakeOps


def _parser() -> IntentParser:
    return IntentParser(config=load_intent_parser_config(), client=None)


def test_parse_explicit_target_prefers_building_over_site_component() -> None:
    target = parse_explicit_target("000007.030")
    assert target.kind == "building"
    assert target.building_id == "000007.030"
    assert target.site_id == "000007"


def test_bare_building_identifier_resolves_to_building_health() -> None:
    payload = _parser().parse("000007.030")
    assert payload.intent == "get_building_health"
    assert payload.entities.building == "000007.030"
    assert payload.entities.site_id == "000007"
    assert payload.ambiguous is False


def test_summary_question_with_explicit_building_stays_building_scoped() -> None:
    payload = _parser().parse("What can you tell me about 000007.030?")
    assert payload.intent == "get_building_health"
    assert payload.entities.building == "000007.030"
    assert payload.entities.site_id == "000007"
    assert payload.clarification_needed is None


def test_follow_up_without_identifier_reuses_previous_explicit_building() -> None:
    payload = _parser().parse(
        "What can you tell me about it?",
        history=[
            {"role": "user", "content": "how is 000007.030"},
            {"role": "assistant", "content": "Building 000007.030 health: 1 devices, 8 probable CPEs."},
        ],
    )
    assert payload.intent == "get_building_health"
    assert payload.entities.building == "000007.030"
    assert payload.entities.site_id == "000007"
    assert payload.ambiguous is False


def test_follow_up_with_new_explicit_identifier_overrides_previous_target() -> None:
    payload = _parser().parse(
        "What can you tell me about 000008.003?",
        history=[
            {"role": "user", "content": "how is 000007.030"},
            {"role": "assistant", "content": "Building 000007.030 health: 1 devices, 8 probable CPEs."},
        ],
    )
    assert payload.intent == "get_building_health"
    assert payload.entities.building == "000008.003"
    assert payload.entities.site_id == "000008"


def test_ambiguous_summary_without_identifier_prompts_clarification() -> None:
    parser = _parser()
    dispatcher = IntentDispatcher(parser=parser, executor=lambda _ops, _intent: {"assistant_answer": "ok", "operator_summary": "ok"})
    result = dispatcher.dispatch(object(), "What can you tell me about it?")
    assert result.status == "clarify"
    assert result.intent is not None
    assert result.intent.entities.building is None


def test_direct_query_parser_keeps_explicit_building_scoped() -> None:
    parsed = parse_operator_query("What can you tell me about 000007.030?")
    assert parsed["action"] == "get_building_health"
    assert parsed["params"]["building_id"] == "000007.030"


def test_rerun_scan_followup_reuses_previous_building_target() -> None:
    payload = _parser().parse(
        "Yes, rerun the scan",
        history=[
            {"role": "user", "content": "how is 000007.030"},
            {"role": "assistant", "content": "Building 000007.030 health: 1 devices, 8 probable CPEs."},
        ],
    )
    assert payload.intent == "rerun_latest_scan"
    assert payload.entities.building == "000007.030"
    assert payload.entities.site_id == "000007"
    assert payload.ambiguous is False


def test_building_followup_routes_to_fault_domain_without_timing_out() -> None:
    payload = _parser().parse(
        "What layer shows the issue (if any)?",
        history=[
            {"role": "user", "content": "How does 1145 Lenox Rd look?"},
            {"role": "assistant", "content": "Building 000007.004 summary."},
        ],
    )
    assert payload.intent == "get_building_fault_domain"
    assert payload.entities.site_id == "000007"
    assert payload.entities.device == "1145 Lenox Rd"


def test_building_followup_can_compare_against_parent_site() -> None:
    payload = _parser().parse(
        "Is this isolated or seen elsewhere on the site?",
        history=[
            {"role": "user", "content": "How does 1145 Lenox Rd look?"},
            {"role": "assistant", "content": "Building 000007.004 summary."},
        ],
    )
    assert payload.intent == "get_site_summary"
    assert payload.entities.site_id == "000007"


def test_rerun_result_followup_reuses_same_building_scope() -> None:
    payload = _parser().parse(
        "what changed?",
        history=[
            {"role": "user", "content": "How is 104 Tapscott?"},
            {"role": "assistant", "content": "Building 000007.001 summary."},
            {"role": "user", "content": "rescan"},
            {"role": "assistant", "content": "Jake cannot re-run the underlying network scan from chat yet for 000007.001."},
        ],
    )
    assert payload.intent == "rerun_latest_scan"
    assert payload.entities.device == "104 Tapscott St"


def test_clarified_street_number_reuses_prior_street_phrase() -> None:
    payload = _parser().parse(
        "1145",
        history=[
            {"role": "user", "content": "What’s going on at Lenox Rd?"},
            {"role": "assistant", "content": "Do you mean 1142 Lenox Rd or 1144 Lenox Rd?"},
        ],
    )
    assert payload.intent == "get_building_health"
    assert payload.entities.device == "1145 Lenox Rd"


def test_building_health_response_labels_subnet_scan_context_clearly() -> None:
    text = format_operator_response(
        "get_building_health",
        {
            "building_id": "000007.030",
            "device_count": 1,
            "probable_cpe_count": 8,
            "outlier_count": 0,
            "active_alerts": [],
            "scan": {
                "subnet": "192.168.44.0/24",
                "api_reachable": 62,
                "hosts_tested": 254,
                "started_at": "2026-03-14T16:13:44Z",
            },
        },
        "What can you tell me about 000007.030?",
    )
    assert "Context:" in text
    assert "this reachability is subnet-wide context, not a building device count" in text
    assert "Mar 14, 2026" in text
    assert "12:13:44 PM EDT" in text


def test_rerun_latest_scan_response_is_deterministic_and_honest() -> None:
    text = format_operator_response(
        "rerun_latest_scan",
        {
            "building_id": "000007.030",
            "site_id": "000007",
            "scan": {"started_at": "2026-03-14T16:13:44Z"},
        },
        "Yes, rerun the scan",
    )
    assert "cannot re-run the underlying network scan from chat yet" in text
    assert "000007.030" in text


def test_rerun_latest_scan_uses_trigger_backend_when_available() -> None:
    intent = _parser().parse(
        "rescan",
        history=[
            {"role": "user", "content": "How is 225 buffalo?"},
            {"role": "assistant", "content": "Building 000007.040 summary."},
        ],
    )

    class FakeOps:
        def _resolve_building_from_address(self, address: str):
            assert address == "225 Buffalo Ave"
            return {"best_match": {"prefix": "000007.040"}}

        def trigger_scan_refresh(self, site_id=None, building_id=None, address_text=None):
            assert site_id == "000007"
            assert building_id == "000007.040"
            assert address_text == "225 Buffalo Ave"
            return {
                "available": True,
                "triggered": True,
                "scan_changed": False,
                "before_scan": {"started_at": "2026-03-14T16:13:44Z"},
                "after_scan": {"started_at": "2026-03-14T16:13:44Z"},
                "site_id": site_id,
                "building_id": building_id,
                "address_text": address_text,
            }

    payload = run_structured_intent(FakeOps(), intent)
    assert payload["matched_action"] == "rerun_latest_scan"
    assert payload["params"]["building_id"] == "000007.040"
    assert payload["result"]["triggered"] is True


def test_jakeops_builds_local_network_mapper_trigger_command() -> None:
    ops = JakeOps.__new__(JakeOps)
    command = ops._local_scan_trigger_command("192.168.44.0/24")
    assert command is not None
    assert command[1].endswith("scripts/network_mapper.py")
    assert "--db" in command
    assert "--env" in command
    assert "scan" in command
    assert "--subnet" in command
    assert "192.168.44.0/24" in command
