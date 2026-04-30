from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable
import warnings

from agents.ollama_client import OllamaClient, OllamaClientError
from core.context_builder import NetworkContext, NetworkContextBuilder
from core.intent_parser import IntentParser, IntentParserError, load_intent_parser_config
from core.intent_schema import IntentEntities, IntentSchema
from core.query_core import run_structured_intent
from core.shared import classify_port_role


@dataclass(slots=True)
class DispatchResult:
    status: str
    response: str
    intent: IntentSchema | None
    execution: dict[str, Any] | None
    classification: str | None = None
    synthesized_response: str | None = None


INTENT_CLARIFICATION_GUIDE: dict[str, tuple[str, str, str]] = {
    "get_site_summary": ("a site health summary", "site", "NYCHA, Chenoweth, or a site ID like 000007"),
    "get_site_alerts": ("active alerts for a site", "site", "NYCHA, Chenoweth, or 000007"),
    "get_online_customers": ("an online subscriber count", "site", "NYCHA, Chenoweth, or 000007"),
    "get_site_punch_list": ("the site punch list", "site", "NYCHA, Chenoweth, or 000007"),
    "get_building_health": ("health for a specific building", "building", "000007.001 or 000008.003"),
    "rerun_latest_scan": ("a scan refresh request against the latest available site or building scan context", "site or building", "000007 or 000007.030"),
    "get_switch_summary": ("a switch summary", "switch", "000007.001.SW01 or 000008.003.SW01"),
    "get_cpe_state": ("the state of a CPE device", "device", "a MAC address like DC:62:79:9D:C1:AD"),
    "trace_mac": ("a MAC address trace", "MAC address", "DC:62:79:9D:C1:AD"),
    "get_customer_access_trace": ("a subscriber access trace", "subscriber", "Chenoweth1Unit201 or NYCHA726-752Fenimore1B"),
    "dispatch_troubleshooting_scenarios": ("a troubleshooting scenario", "details", "mention the site and the problem type"),
    "find_cpe_candidates": ("a CPE candidate search", "site", "NYCHA or Sweetwater"),
    "get_live_olt_ont_summary": ("a live OLT or ONT summary", "device", "a serial like TPLG-5F2024D5"),
}


def _site_display_name(context: NetworkContext | None, site_id: str) -> str:
    if context is not None:
        for site in context.site_inventory:
            if site.site_id == site_id:
                if site.aliases:
                    return site.aliases[0].title()
                break
    return site_id


def _suggested_sites(context: NetworkContext | None) -> list[str]:
    if context is None:
        return []
    site_ids: list[str] = []
    for site_id in context.active_alert_sites:
        if site_id not in site_ids:
            site_ids.append(site_id)
    for site_id in context.sites_needing_attention:
        if site_id not in site_ids:
            site_ids.append(site_id)
    return site_ids[:2]


def _clarification_response(intent: IntentSchema) -> str:
    guide = INTENT_CLARIFICATION_GUIDE.get(intent.intent)
    if guide is None:
        return intent.clarification_needed or "Which site or object did you mean?"
    description, missing_entity, example = guide
    return f"I think you're asking for {description}. Which {missing_entity}? For example: {example}."


def _contextual_clarification_response(intent: IntentSchema, context: NetworkContext | None) -> str:
    if intent.intent not in {"get_site_alerts", "get_site_summary"}:
        return _clarification_response(intent)
    suggested = _suggested_sites(context)
    if suggested:
        labels = [_site_display_name(context, site_id) for site_id in suggested]
        if len(labels) == 1:
            return f"Got it — you want {'alerts' if intent.intent == 'get_site_alerts' else 'the site summary'}. Are you asking about {labels[0]}?"
        return (
            f"Got it — you want {'alerts' if intent.intent == 'get_site_alerts' else 'the site summary'}. "
            f"Are you asking about {labels[0]} or {labels[1]}?"
        )
    if intent.intent == "get_site_alerts":
        return "Which site? For example: NYCHA or Chenoweth."
    return "Which site? For example: NYCHA or Chenoweth."


def _missing_required_entity(intent: IntentSchema) -> bool:
    entities = intent.entities
    if intent.intent in {
        "get_site_summary",
        "get_site_alerts",
        "get_online_customers",
        "get_site_punch_list",
        "find_cpe_candidates",
    }:
        return not bool(entities.site_id)
    if intent.intent == "get_building_health":
        return not bool(entities.building or entities.device)
    if intent.intent == "rerun_latest_scan":
        return not bool(entities.building or entities.site_id)
    if intent.intent in {
        "get_switch_summary",
        "get_cpe_state",
        "trace_mac",
        "get_customer_access_trace",
        "get_live_olt_ont_summary",
    }:
        return not bool(entities.device)
    return False


def _build_synthesis_prompt(raw: str, execution: dict[str, Any]) -> str:
    result_payload = execution.get("result", {})
    rendered = json.dumps(result_payload, indent=2, default=str)[:2000]
    topology_note = ""
    cpe_reasoning_note = ""
    if execution.get("matched_action") == "get_cpe_state" and isinstance(result_payload, dict):
        bridge = result_payload.get("bridge") or {}
        primary = bridge.get("primary_sighting") or {}
        port_name = str(primary.get("port_name") or primary.get("on_interface") or "").strip()
        device_name = str(primary.get("device_name") or primary.get("identity") or "").strip()
        if classify_port_role(port_name) == "uplink":
            topology_note = (
                "IMPORTANT TOPOLOGY NOTE: The port where this MAC was seen "
                f"({port_name} on {device_name or 'the reporting device'}) is an uplink/trunk port, not a direct subscriber port. "
                "Do not suggest bouncing this port — it would affect all subscribers behind it. "
                "Instead, direct the operator to check the OLT ONU table or DHCP lease agent-circuit-id to find the actual subscriber port.\n\n"
            )
        if result_payload.get("olt_correlation") or result_payload.get("dhcp_correlation"):
            cpe_reasoning_note = (
                "You are a NOC engineer. Given this CPE state and OLT correlation data, give a direct conclusion: "
                "what is wrong, which specific ONU/port is the source, and what is the single most useful next action. "
                "Be specific — use ONU IDs, PON names, signal levels, and DHCP churn rates. Do not give a checklist.\n\n"
            )
    return (
        f'The operator asked: "{raw}"\n\n'
        f"{topology_note}"
        f"{cpe_reasoning_note}"
        f"Network data returned:\n{rendered}\n\n"
        "Write a 2-4 sentence direct answer that:\n"
        "- Answers the specific question asked\n"
        "- Uses real values from the data (device names, counts, site IDs, timestamps)\n"
        "- Flags anything that needs attention\n"
        "- Skips zero/empty fields unless zero IS the answer\n"
        "- Ends with 1-2 follow-up questions if something looks worth investigating\n\n"
        'Do not say "Based on the data" or "According to the results". Just answer directly as Jake.'
    )


def _build_uncertain_prompt(raw: str, context: NetworkContext | None) -> str:
    summary = context.operator_context_summary if context is not None else ""
    return (
        f'The operator said: "{raw}"\n\n'
        "Current network context:\n"
        f"{summary}\n\n"
        "I could not match this to a specific network action.\n"
        "Based on the operator's phrasing and the current\n"
        "network state, write 2-3 sentences directly to the\n"
        "operator that:\n"
        "- State what you understood them to be asking\n"
        "- Offer the closest action you can actually run\n"
        "- Ask one specific question to get what you need\n\n"
        "Do not say you cannot help. Offer something concrete.\n"
        "Do not list all available commands."
    )


def _default_uncertain_response(raw: str) -> str:
    lowered = raw.lower()
    if any(token in lowered for token in ("radio", "mesh", "cambium", "cnwave", "handoff")):
        return (
            "It sounds like you're asking about a radio or mesh path issue. "
            "I can check site health, radio neighbors, or handoff traces for a specific site. Which site are you looking at?"
        )
    if "alert" in lowered:
        return "It sounds like you want alert status. Which site should I check?"
    return "I wasn't sure what you meant — can you say which site or device you're asking about?"


def _history_recent_mac(history: list[dict[str, Any]] | None) -> str | None:
    if not history:
        return None
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        match = re.search(r"((?:[0-9a-f]{2}[:\-]){5}[0-9a-f]{2}|[0-9a-f]{12})", content, re.I)
        if not match:
            continue
        value = match.group(1).lower().replace("-", ":")
        if ":" not in value:
            value = ":".join(value[i : i + 2] for i in range(0, len(value), 2))
        return value
    return None


class IntentDispatcher:
    def __init__(
        self,
        *,
        parser: IntentParser | None = None,
        config: dict[str, Any] | None = None,
        executor: Callable[[Any, IntentSchema], dict[str, Any]] | None = None,
        context: NetworkContext | None = None,
    ) -> None:
        self.config = config or load_intent_parser_config()
        if context is None:
            try:
                context = NetworkContextBuilder.build()
            except Exception:
                context = None
        self.context = context
        if parser is not None:
            self.parser = parser
            if self.context is not None and getattr(self.parser, "context", None) is None:
                self.parser.context = self.context
        else:
            client = None
            try:
                client = OllamaClient.from_env()
            except Exception as exc:
                warnings.warn(
                    f"Ollama intent parsing unavailable; falling back to heuristics only: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                client = None
            self.parser = IntentParser(config=self.config, client=client, context=self.context)
        self.executor = executor or run_structured_intent
        confidence = self.config.get("confidence_thresholds") or {}
        self.execute_direct_min = float(confidence.get("execute_direct_min", 0.85))
        self.execute_with_note_min = float(confidence.get("execute_with_note_min", 0.60))
        self.clarify_min = float(confidence.get("clarify_min", 0.40))

    def _maybe_synthesize(self, raw: str, execution: dict[str, Any]) -> str | None:
        if execution.get("matched_action") in {
            "get_building_health",
            "rerun_latest_scan",
            "get_site_summary",
            "get_switch_summary",
            "get_cpe_state",
            "trace_mac",
            "get_building_fault_domain",
        }:
            return None
        client = getattr(self.parser, "client", None)
        if client is None:
            return None
        prompt = _build_synthesis_prompt(raw, execution)
        try:
            synthesis_client = OllamaClient(client.endpoint, client.model, 15.0)
            synthesized = synthesis_client.generate(
                prompt,
                system_prompt=(
                    "You are Jake, a NOC assistant for a WISP. Be direct and specific. "
                    "Use real values. Do not hedge or pad. 3 sentences maximum."
                ),
            )
        except OllamaClientError:
            return None
        except Exception:
            return None
        text = str(synthesized or "").strip()
        return text or None

    def _uncertain_response(self, raw: str) -> str:
        client = getattr(self.parser, "client", None)
        if client is None:
            return _default_uncertain_response(raw)
        try:
            uncertain_client = OllamaClient(client.endpoint, client.model, 20.0)
            answer = uncertain_client.generate(
                _build_uncertain_prompt(raw, self.context),
                system_prompt="You are Jake, a NOC assistant. Be direct. Offer something useful. One question maximum.",
            )
        except Exception:
            return _default_uncertain_response(raw)
        text = str(answer or "").strip()
        return text or _default_uncertain_response(raw)

    def _maybe_rescue_cpe_clue(
        self,
        ops: Any,
        raw: str,
        history: list[dict[str, Any]] | None = None,
    ) -> IntentSchema | None:
        lowered = raw.lower()
        if "dhcp" not in lowered or "hc220" not in lowered:
            return None
        port_match = re.search(r"\b(sfp-sfpplus\d+|sfp\d+|ether\d+|bond\d+|bridge\d+)\b", lowered, re.I)
        port_name = port_match.group(1) if port_match else None
        history_mac = _history_recent_mac(history)
        if history_mac:
            return IntentSchema(
                intent="get_cpe_state",
                entities=IntentEntities(device=history_mac, scope="cpe"),
                confidence=0.9,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )
        if not hasattr(ops, "resolve_cpe_mac_from_clue"):
            return None
        try:
            clue = ops.resolve_cpe_mac_from_clue(cpe_hostname="HC220", port_name=port_name, window_minutes=60, limit=500)
        except Exception:
            return None
        if not isinstance(clue, dict) or not clue.get("found") or not clue.get("mac"):
            return None
        return IntentSchema(
            intent="get_cpe_state",
            entities=IntentEntities(site_id=clue.get("site_id"), device=clue.get("mac"), scope="cpe"),
            confidence=0.9,
            ambiguous=False,
            clarification_needed=None,
            raw=raw,
        )

    def dispatch(self, ops: Any, raw: str, history: list[dict[str, Any]] | None = None) -> DispatchResult:
        try:
            intent = self.parser.parse(raw, history=history)
        except IntentParserError as exc:
            rescued_intent = self._maybe_rescue_cpe_clue(ops, raw, history)
            if rescued_intent is not None:
                intent = rescued_intent
            elif exc.classification in {"code_error", "missing_runtime"} and isinstance(getattr(self.parser, "client", None), OllamaClient):
                return DispatchResult(
                    status="uncertain",
                    response=self._uncertain_response(raw),
                    intent=None,
                    execution=None,
                    classification=exc.classification,
                )
            else:
                return DispatchResult(
                    status="error",
                    response=f"Intent parsing failed ({exc.classification}): {exc}",
                    intent=None,
                    execution=None,
                    classification=exc.classification,
                )

        if intent.intent == "unknown":
            rescued_intent = self._maybe_rescue_cpe_clue(ops, raw, history)
            if rescued_intent is not None:
                intent = rescued_intent

        if intent.intent == "general_question":
            try:
                if self.parser.client is None:
                    raise RuntimeError("general-question answering requires an active Ollama client")
                context_summary = self.context.operator_context_summary if self.context is not None else "No live network context available."
                answer = self.parser.client.generate(
                    f"Current network context:\n{context_summary}\n\nQuestion: {intent.raw}",
                    system_prompt=(
                        "You are Jake, a knowledgeable NOC assistant for a WISP called Lynxnet/ResiBridge. "
                        "Answer the following operator question directly and concisely. Use your expertise in networking, "
                        "MikroTik RouterOS, Cambium cnWave, TP-Link GPON, and wireless ISP operations. Keep your answer "
                        "practical and operator-focused."
                    ),
                )
                return DispatchResult(
                    status="answered",
                    response=answer,
                    intent=intent,
                    execution=None,
                )
            except Exception as exc:
                return DispatchResult(
                    status="error",
                    response=f"Jake could not answer that: {exc}",
                    intent=intent,
                    execution=None,
                    classification="code_error",
                )

        if _missing_required_entity(intent):
            return DispatchResult("clarify", _contextual_clarification_response(intent, self.context), intent, None)

        if intent.confidence >= self.execute_direct_min:
            try:
                execution = self.executor(ops, intent)
            except Exception as exc:
                return DispatchResult(
                    status="error",
                    response=f"Jake could not complete {intent.intent}: {exc}",
                    intent=intent,
                    execution=None,
                    classification="code_error",
                )
            return DispatchResult(
                "executed",
                execution["assistant_answer"],
                intent,
                execution,
                synthesized_response=self._maybe_synthesize(raw, execution),
            )

        if intent.confidence >= self.execute_with_note_min:
            try:
                execution = self.executor(ops, intent)
            except Exception as exc:
                return DispatchResult(
                    status="error",
                    response=f"Jake could not complete {intent.intent}: {exc}",
                    intent=intent,
                    execution=None,
                    classification="code_error",
                )
            note = "Jake executed this query, but the intent confidence was below the direct-execute threshold."
            execution["operator_summary"] = f"{execution['operator_summary']}\n\n{note}"
            execution["assistant_answer"] = execution["operator_summary"]
            return DispatchResult(
                "executed_with_note",
                execution["assistant_answer"],
                intent,
                execution,
                synthesized_response=self._maybe_synthesize(raw, execution),
            )

        if intent.confidence >= self.clarify_min or intent.ambiguous:
            if intent.intent in {"get_cpe_management_readiness", "general_question"}:
                guessed = intent.intent if intent.intent != "unknown" else "an unsupported query"
                response = f"Jake thinks you might mean {guessed}, but confidence is too low. Please rephrase."
                return DispatchResult("rephrase", response, intent, None)
            question = _contextual_clarification_response(intent, self.context)
            return DispatchResult("clarify", question, intent, None)

        if intent.intent == "unknown" and self.parser.client is not None:
            return DispatchResult("uncertain", self._uncertain_response(raw), intent, None)
        guessed = intent.intent if intent.intent != "unknown" else "an unsupported query"
        response = f"Jake thinks you might mean {guessed}, but confidence is too low. Please rephrase."
        return DispatchResult("rephrase", response, intent, None)
