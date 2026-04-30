from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Literal
from typing import TYPE_CHECKING

import yaml

from agents.ollama_client import OllamaClient, OllamaClientError
from core.intent_schema import IntentEntities, IntentSchema
from core.query_core import normalize_query
from core.shared import (
    PROJECT_ROOT,
    SITE_ALIAS_MAP,
    SUBSCRIBER_NAME_TO_MAC,
    SUBSCRIBER_NAME_TO_OLT,
    extract_street_number_and_name,
    extract_subscriber_label,
    load_address_index,
    normalize_address_text,
    normalize_subscriber_label,
    resolve_address_candidates,
)

if TYPE_CHECKING:
    from core.context_builder import NetworkContext


@dataclass(slots=True)
class IntentParserError(RuntimeError):
    classification: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True, frozen=True)
class Target:
    kind: Literal["none", "building", "site", "device", "address"] = "none"
    site_id: str | None = None
    building_id: str | None = None
    device: str | None = None
    address_text: str | None = None


def load_intent_parser_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or (PROJECT_ROOT / "config" / "intent_parser.yaml")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise IntentParserError("config_error", f"Intent parser config must be a mapping: {config_path}")
    return payload


def _read_recent_examples(path: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    examples: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if payload.get("confirmed") is True:
            examples.append(payload)
    return examples[-limit:]


def _resolve_site_alias_id(raw: str, site_vocabulary: dict[str, list[str]]) -> str | None:
    lowered = raw.lower()
    for site_id, aliases in site_vocabulary.items():
        for alias in aliases:
            if re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", lowered):
                return site_id
    for alias, site_id in SITE_ALIAS_MAP.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered):
            return site_id
    # WHY: Operators often prefix addresses with a street number ("audit 2020 Pacific St").
    # Strip a leading street number (e.g. "2020 ") and retry the alias map so the
    # word-only form ("pacific st") can match without duplicating every number variant.
    stripped = re.sub(r"^\d+\s+", "", lowered).strip()
    if stripped != lowered:
        for alias, site_id in SITE_ALIAS_MAP.items():
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", stripped):
                return site_id
    return None


def _extract_ip(raw: str) -> str | None:
    match = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", raw)
    if match:
        return match.group(1)
    return None


def _intent_entities(site_id: str | None, *, scope: str = "all") -> IntentEntities:
    return IntentEntities(site_id=site_id, scope=scope)


def _extract_mac(raw: str) -> str | None:
    match = re.search(r"((?:[0-9a-f]{2}[:\-]){5}[0-9a-f]{2}|[0-9a-f]{12})", raw, re.I)
    if not match:
        return None
    value = match.group(1).lower().replace("-", ":")
    if ":" not in value:
        value = ":".join(value[i : i + 2] for i in range(0, len(value), 2))
    return value


def _extract_building_id(raw: str) -> str | None:
    match = re.search(r"\b(\d{6}\.\d{3})\b", raw)
    if match:
        return match.group(1)
    return None


def _extract_switch_identity(raw: str) -> str | None:
    match = re.search(r"\b(\d{6}\.\d{3}\.(?:SW\d+|RFSW\d+))\b", raw, re.I)
    if match:
        return match.group(1)
    return None


def _extract_street_address(raw: str) -> str | None:
    """Extract a street address from operator input (e.g. '225 Buffalo Ave', '726-752 Fenimore St').

    WHY: NYCHA audit workbook queries are keyed by building address. Operators say
    'audit 225 Buffalo Ave' — neither a site alias nor a switch identity, just an address.
    This pattern matches <number[-number]> <word(s)> [St|Ave|Rd|Pl|Blvd|Dr|...].
    """
    match = re.search(
        r"\b(\d{1,5}(?:-\d{1,5})?\s+[A-Za-z][A-Za-z\s]{2,40}?\s+(?:St|Ave|Rd|Pl|Blvd|Dr|Ln|Way|Ct|Pkwy|Terrace|Place|Street|Avenue|Road|Boulevard|Drive|Lane|Court|Parkway)\b)",
        raw,
        re.I,
    )
    return match.group(1).strip() if match else None


def _extract_street_name_phrase(raw: str) -> str | None:
    match = re.search(
        r"\b([A-Za-z][A-Za-z\s]{2,40}?\s+(?:St|Ave|Rd|Pl|Blvd|Dr|Ln|Way|Ct|Pkwy|Terrace|Place|Street|Avenue|Road|Boulevard|Drive|Lane|Court|Parkway))\b",
        raw,
        re.I,
    )
    if not match:
        return None
    phrase = match.group(1).strip()
    if re.search(r"\d", phrase):
        return None
    return phrase


def _extract_numbered_street_phrase(raw: str) -> str | None:
    match = re.search(r"\b(\d{1,5}\s+[A-Za-z][A-Za-z\s]{2,40})\b", raw, re.I)
    if not match:
        return None
    phrase = re.sub(r"\s+", " ", match.group(1).strip())
    if re.fullmatch(r"\d+", phrase):
        return None
    return phrase


def normalize_address(text: str) -> str:
    return normalize_address_text(text)


def _extract_serial(raw: str) -> str | None:
    match = re.search(r"\b(?:TPLG-[A-Z0-9]+|Y[0-9A-Z]{8,}|(?=[A-Z0-9]{10,}\b)(?=[A-Z0-9]*\d)[A-Z0-9]+)\b", raw, re.I)
    if match:
        return match.group(0)
    return None


def _extract_device_hostname(raw: str) -> str | None:
    match = re.search(r"\b(\d{6}(?:\.\d{3})?\.(?:R\d+|SR\d+|SW\d+|RFSW\d+|OLT\d+))\b", raw, re.I)
    if match:
        return match.group(1)
    return None


def parse_explicit_target(query: str) -> Target:
    switch_identity = _extract_switch_identity(query)
    if switch_identity:
        return Target(kind="device", site_id=switch_identity.split(".", 1)[0], device=switch_identity)

    device_hostname = _extract_device_hostname(query)
    if device_hostname:
        site_match = re.match(r"^(\d{6})", device_hostname)
        return Target(
            kind="device",
            site_id=site_match.group(1) if site_match else None,
            device=device_hostname,
        )

    building_id = _extract_building_id(query)
    if building_id:
        return Target(kind="building", site_id=building_id.split(".", 1)[0], building_id=building_id)

    mac = _extract_mac(query)
    if mac:
        return Target(kind="device", device=mac)

    ip = _extract_ip(query)
    if ip:
        return Target(kind="device", device=ip)

    explicit_site = re.search(r"\b(\d{6})\b(?!\.\d{3})", query)
    if explicit_site:
        return Target(kind="site", site_id=explicit_site.group(1))

    candidates = resolve_address_candidates(query)
    if len(candidates) == 1:
        row = candidates[0]
        return Target(kind="address", site_id=row.get("site_id"), address_text=row.get("address"))

    return Target()


def _resolve_site_id(raw: str, site_vocabulary: dict[str, list[str]]) -> str | None:
    explicit = parse_explicit_target(raw)
    if explicit.site_id:
        return explicit.site_id
    return _resolve_site_alias_id(raw, site_vocabulary)


def _resolve_subscriber_site_id(subscriber_label: str, site_vocabulary: dict[str, list[str]]) -> str | None:
    direct = _resolve_site_id(subscriber_label, site_vocabulary)
    if direct:
        return direct
    lowered = subscriber_label.lower()
    for site_id, aliases in site_vocabulary.items():
        for alias in aliases:
            alias_lower = alias.lower()
            if lowered.startswith(alias_lower):
                return site_id
    for alias, site_id in SITE_ALIAS_MAP.items():
        if lowered.startswith(alias):
            return site_id
    if lowered.startswith("nycha"):
        return "000007"
    return None


def _looks_like_statement(raw: str) -> bool:
    lowered = raw.lower().strip()
    if "?" in lowered:
        return False
    if re.match(r"^(what|how|who|where|when|why|which|can|could|would|should|does|do|did|is it|are there)\b", lowered):
        return False
    return True


class IntentParser:
    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        client: OllamaClient | None = None,
        examples_path: Path | None = None,
        context: NetworkContext | None = None,
    ) -> None:
        self.config = config or load_intent_parser_config()
        self.client = client
        self.examples_path = examples_path or (PROJECT_ROOT / "data" / "intent_examples.jsonl")
        self.context = context
        self.site_vocabulary: dict[str, list[str]] = {
            str(site_id): [str(alias) for alias in aliases]
            for site_id, aliases in (self.config.get("site_vocabulary") or {}).items()
        }
        self.known_intents = [str(item) for item in (self.config.get("known_intents") or [])]
        self.system_prompt_template = str(self.config.get("system_prompt_template") or "").strip()
        if not self.system_prompt_template:
            raise IntentParserError("config_error", "intent_parser.yaml is missing system_prompt_template")

    @classmethod
    def from_env(cls) -> "IntentParser":
        return cls(client=OllamaClient.from_env())

    def parse(self, raw: str, history: list[dict[str, Any]] | None = None) -> IntentSchema:
        if not isinstance(raw, str) or not raw.strip():
            raise IntentParserError("code_error", "Intent parser input must be a non-empty string")

        heuristic = self._heuristic_parse(raw, history=history)
        if heuristic is not None:
            return heuristic
        if self.client is None:
            return IntentSchema(
                intent="unknown",
                entities=IntentEntities(),
                confidence=0.2,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )
        compressed_history = self.compress_history(history)
        return self._model_parse(raw, history=compressed_history)

    def _history_recent_site_id(self, history: list[dict[str, Any]] | None) -> str | None:
        if not history:
            return None
        for item in reversed(history):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            site_id = _resolve_site_id(content, self.site_vocabulary)
            if site_id:
                return site_id
        return None

    def _history_recent_explicit_target(self, history: list[dict[str, Any]] | None) -> Target | None:
        if not history:
            return None
        for item in reversed(history):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role != "user":
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            target = parse_explicit_target(content)
            if target.kind != "none":
                return target
        return None

    def _history_first_explicit_target(self, history: list[dict[str, Any]] | None) -> Target | None:
        if not history:
            return None
        for item in history:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role != "user":
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            target = parse_explicit_target(content)
            if target.kind != "none":
                return target
        return None

    def _history_recent_street_phrase(self, history: list[dict[str, Any]] | None) -> str | None:
        if not history:
            return None
        for item in reversed(history):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role != "user":
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            candidates = resolve_address_candidates(content)
            if candidates:
                address = str(candidates[0].get("address") or "").strip()
                if address:
                    _number, street = extract_street_number_and_name(address)
                    if street:
                        return street
            _number, street = extract_street_number_and_name(content)
            if street:
                return street
        return None

    def _history_recent_user_intent(self, history: list[dict[str, Any]] | None) -> str | None:
        if not history:
            return None
        for item in reversed(history):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role != "user":
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            prior = self._heuristic_parse(content, history=None)
            if prior is not None and prior.intent != "unknown":
                return prior.intent
        return None

    def _heuristic_parse(self, raw: str, *, history: list[dict[str, Any]] | None = None) -> IntentSchema | None:
        normalized = normalize_query(raw)
        lowered = normalized.lower()
        raw_lower = raw.lower()
        explicit_target = parse_explicit_target(raw)
        if explicit_target.kind == "none":
            number_only_match = re.fullmatch(r"\s*(\d{3,5})\s*\??\s*", raw)
            if number_only_match:
                prior_street = self._history_recent_street_phrase(history)
                if prior_street:
                    resolved_candidates = resolve_address_candidates(f"{number_only_match.group(1)} {prior_street}")
                    if len(resolved_candidates) == 1:
                        row = resolved_candidates[0]
                        explicit_target = Target(kind="address", site_id=row.get("site_id"), address_text=row.get("address"))
        address_candidates = resolve_address_candidates(raw)
        alias_site_id = _resolve_site_alias_id(raw, self.site_vocabulary)
        site_id = alias_site_id or explicit_target.site_id
        history_target = self._history_recent_explicit_target(history) if explicit_target.kind == "none" and site_id is None else None
        first_history_target = self._history_first_explicit_target(history) if explicit_target.kind == "none" and site_id is None else None
        history_site_id = history_target.site_id if history_target and history_target.site_id else (self._history_recent_site_id(history) if site_id is None else None)
        mac = explicit_target.device if explicit_target.kind == "device" and _extract_mac(raw) else _extract_mac(raw)
        subscriber_label = extract_subscriber_label(raw)
        building_id = explicit_target.building_id or _extract_building_id(raw)
        switch_identity = _extract_switch_identity(raw)
        serial = _extract_serial(raw)
        device_hostname = _extract_device_hostname(raw)

        online_tokens = (
            "how many customers",
            "how many subscribers",
            "live count",
            "who's up right now",
            "who is up right now",
            "customers online",
            "subscribers online",
        )
        summary_tokens = (
            "what can you tell me about",
            "how are things looking",
            "what's going on at",
            "whats going on at",
            "what is going on at",
            "site summary",
            "status at",
        )
        # WHY: get_nycha_port_audit is site-agnostic. Keep legacy NYCHA tokens for
        # backward compat; add generic phrasing so any site can trigger port audits.
        nycha_port_audit_tokens = (
            "audit nycha ports",
            "nycha port audit",
            "which nycha switches",
            "nycha switches have wrong",
            "nycha switches using ether48",
            "ether48 instead of ether49",
            "wrong patching at nycha",
            "wrong patch",
            "wrong uplink at nycha",
            "nycha uplink",
            "nycha port issues",
            "nycha switch uplink",
            # Generic site-agnostic phrasing
            "audit the port patching",
            "port patching audit",
            "audit port patching",
            "audit switch uplinks",
            "switch uplink audit",
            "audit uplink ports",
            "uplink port audit",
            "wrong uplink",
            "switches have wrong uplink",
            "switches using wrong port",
            "uplink patching",
            "port mispatch",
            "wrong port patching",
        )
        site_punch_list_tokens = (
            "what needs to be fixed",
            "site punch list",
            "field-tech punch list",
            "field tech punch list",
        )
        site_precheck_tokens = (
            "precheck",
            "quick check",
            "before i go",
            "before touching",
            "before answering",
        )
        site_loop_suspicion_tokens = (
            "loop suspicion",
            "bridge loop",
            "loop-ish",
            "broadcast storm",
        )
        bridge_host_weirdness_tokens = (
            "bridge host weirdness",
            "bridge hosts weird",
            "bridge host weird",
            "bridge host behavior",
            "bridge host odd",
            "bridge host off",
            "mikrotik bridge host",
        )
        live_cnwave_radio_neighbor_tokens = (
            "cnwave neighbors",
            "radio neighbors",
            "live neighbors",
            "ipv4 neighbors",
            "what devices are behind",
            "what is behind this radio",
            "what is behind that radio",
            "devices behind this radio",
            "devices behind that radio",
            "neighbors on this radio",
            "neighbors on that radio",
        )
        radio_handoff_trace_tokens = (
            "radio handoff",
            "handoff trace",
            "handoff path",
            "sfp side",
            "sfp port",
            "sfp hosts",
            "macs on the sfp",
            "mac addresses via the sfp",
            "what macs are visible",
            "what macs do you see on the sfp",
        )
        building_fault_domain_tokens = (
            "fault domain",
            "building fault",
            "building path issue",
            "building-path issue",
            "floor issue",
            "one unit or floor",
            "shared path",
            "entire floor",
            "whole floor",
            "shared mux",
            "mux is bad",
        )
        site_topology_tokens = (
            "topology",
            "site layout",
            "laid out",
            "how is the network laid out",
            "transport topology",
            "backhaul path",
            "backhaul links",
            "transport links",
            "radio links",
        )
        building_health_tokens = (
            "building health",
            "what is going on with",
            "how is",
            "how's",
            "hows",
        )
        switch_summary_tokens = (
            "switch summary",
            "what can you tell me about",
            "show me this switch",
            "show this switch",
            "how is",
            "how's",
            "hows",
        )
        management_surface_tokens = (
            "local management",
            "management surface",
            "manage locally",
            "local gui",
            "what management do we have",
            "what local control do we have",
        )
        management_readiness_tokens = (
            "cpe management readiness",
            "management readiness",
            "local management readiness",
            "hc220 readiness",
            "vilo readiness",
            "cpe tooling readiness",
            "cpe management audit",
            "what can jake manage right now",
        )
        nycha_audit_workbook_tokens = (
            "audit workbook",
            "generate audit workbook",
            "audit all switches at nycha",
            "audit all nycha switches",
            "nycha switch audit workbook",
            "nycha unit audit",
        )
        troubleshooting_tokens = (
            "bridge",
            "bridge vlan",
            "vlan filtering",
            "stp",
            "rstp",
            "pppoe",
            "option 82",
            "capsman",
            "wifi-qcom",
            "bgp",
            "ospf",
        )
        vilo_candidate_tokens = ("probable vilo cpes", "show probable vilo cpes")
        cpe_state_tokens = (
            "what is wrong with",
            "seem healthy",
            "cpe state",
            "device state",
            "what is this device doing",
            "what is this mac doing",
        )
        trace_mac_tokens = (
            "trace this mac",
            "trace mac",
            "where does",
            "where is this device showing up",
            "where is this mac",
            "land on",
            "lands on",
            "terminate on",
        )
        live_olt_ont_tokens = (
            "show ont info",
            "live olt",
            "olt cli",
            "olt telnet",
        )
        customer_access_trace_tokens = (
            "access trace",
            "customer trace",
            "subscriber trace",
            "trace this subscriber",
            "full access trace",
            "what can you tell me about",
            "what do you know about",
            "what is going on with",
            "going on with",
            "check on",
        )
        alert_tokens = (
            "any alerts",
            "show alerts",
            "active alerts",
            "what alerts",
            "alerts at",
            "alerts for",
            "anything alarming",
            "show active alerts",
        )
        site_log_tokens = (
            "what happened at",
            "what happened on",
            "site logs",
            "any errors on",
            "errors on",
            "show me logs for",
            "pppoe errors",
            "dhcp errors",
            "interface errors",
            "bridge errors",
        )
        device_log_tokens = (
            "check logs for",
            "logs for",
            "what happened on",
            "errors on",
            "any errors on",
        )
        correlate_tokens = (
            "why did customers drop",
            "why did subs drop",
            "why did subscribers drop",
            "customers dropped",
        )
        alert_like = any(token in lowered for token in alert_tokens) or ("alert" in lowered)
        network_state_tokens = (
            "current state of the network",
            "state of the network",
            "network status overall",
            "overall network status",
        )
        carry_forward_tokens = (
            "same thing",
            "same for",
            "same at",
            "what about",
        )
        history_site_reference_tokens = (" there", "that site", "that building", "that switch")
        rerun_scan_tokens = (
            "rerun the scan",
            "re-run the scan",
            "run the scan again",
            "scan again",
            "rerun scan",
            "rescan",
        )
        go_back_first_tokens = (
            "go back to the first one",
            "back to the first one",
            "go back to the first",
            "the first one",
        )
        building_followup_health_tokens = (
            "is anything actually wrong here",
            "why do you think this building is healthy",
            "what evidence supports that",
            "what could contradict it",
            "what are we missing",
            "this building looks quiet",
            "should i be concerned",
            "is this low activity or low visibility",
            "do we have live switch data",
            "do we see historical evidence",
            "what's the safest interpretation",
            "what’s the safest interpretation",
            "has anything gotten worse",
            "what changed recently",
            "is this based on live or historical data",
            "how confident are you",
        )
        building_fault_domain_followup_tokens = (
            "what layer shows the issue",
            "what layer is failing",
            "which layer is failing",
            "show me the evidence for that conclusion",
            "show me the evidence",
            "why is visibility low here",
            "is this a scan gap or a real issue",
            "what’s the most likely explanation",
            "what's the most likely explanation",
            "what should i check first",
            "what kind of issues",
            "are devices attempting to come online",
            "is this likely service-layer or physical",
            "what pattern do you see",
            "pick one—what’s wrong with it",
            "pick one-what's wrong with it",
            "what do we see at l1/l2/service",
            "what’s the most likely cause",
            "what's the most likely cause",
            "what’s the fastest way to confirm",
            "what's the fastest way to confirm",
            "if you were walking into",
            "why that order",
            "what confirms each step",
            "what rules it out quickly",
            "what should i fix first",
            "what’s the impact",
            "what's the impact",
            "what’s the fastest verification",
            "what's the fastest verification",
            "why are customers",
        )
        building_to_site_compare_tokens = (
            "is this isolated or seen elsewhere on the site",
            "how does the rest of that site compare",
            "any other buildings there with issues",
            "is this building an outlier",
            "any outliers",
            "anything mispatched or swapped",
            "are issues clustered or random",
        )
        building_switch_followup_tokens = (
            "which switch is most likely involved",
            "what do we see on that switch",
            "any ports behaving abnormally",
            "where would you start investigating",
        )
        building_rescan_followup_tokens = (
            "what changed",
            "is it better or worse",
            "better or worse",
        )

        # WHY: switch_identity takes priority — "what can you tell me about 000007.001.SW01"
        # extracts building_id=000007.001 from the switch prefix, but the user is asking
        # about the switch, not the building. Exclude switch queries from the
        # building-summary path so they fall through to get_switch_summary below.
        explicit_building_summary_like = building_id and not switch_identity and (
            raw_lower.strip() == building_id.lower()
            or any(token in raw_lower for token in summary_tokens)
            or any(token in raw_lower for token in building_health_tokens)
        )

        if any(token in lowered for token in network_state_tokens):
            return IntentSchema(
                intent="general_question",
                entities=IntentEntities(),
                confidence=0.95,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if any(token in lowered for token in go_back_first_tokens) and first_history_target is not None:
            if first_history_target.kind == "building" and first_history_target.building_id:
                return IntentSchema(
                    intent="get_building_health",
                    entities=IntentEntities(
                        site_id=first_history_target.site_id or first_history_target.building_id.split(".", 1)[0],
                        building=first_history_target.building_id,
                        scope="building",
                    ),
                    confidence=0.9,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            if first_history_target.kind == "address" and first_history_target.address_text:
                return IntentSchema(
                    intent="get_building_health",
                    entities=IntentEntities(site_id=first_history_target.site_id, device=first_history_target.address_text, scope="building"),
                    confidence=0.9,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )

        if any(token in lowered for token in building_rescan_followup_tokens) and history_target is not None:
            prior_intent = self._history_recent_user_intent(history)
            if prior_intent == "rerun_latest_scan":
                if history_target.kind == "building" and history_target.building_id:
                    return IntentSchema(
                        intent="rerun_latest_scan",
                        entities=IntentEntities(
                            site_id=history_target.site_id or history_target.building_id.split(".", 1)[0],
                            building=history_target.building_id,
                            scope="building",
                        ),
                        confidence=0.88,
                        ambiguous=False,
                        clarification_needed=None,
                        raw=raw,
                    )
                if history_target.kind == "address" and history_target.address_text:
                    return IntentSchema(
                        intent="rerun_latest_scan",
                        entities=IntentEntities(site_id=history_target.site_id, device=history_target.address_text, scope="building"),
                        confidence=0.88,
                        ambiguous=False,
                        clarification_needed=None,
                        raw=raw,
                    )

        if history_target is not None and any(token in lowered for token in building_to_site_compare_tokens):
            resolved_site = history_target.site_id
            if history_target.kind == "building" and history_target.building_id and not resolved_site:
                resolved_site = history_target.building_id.split(".", 1)[0]
            return IntentSchema(
                intent="get_site_summary",
                entities=IntentEntities(site_id=resolved_site, scope="all"),
                confidence=0.88,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if history_target is not None and any(token in lowered for token in building_switch_followup_tokens):
            if history_target.kind == "building" and history_target.building_id:
                return IntentSchema(
                    intent="get_building_health",
                    entities=IntentEntities(
                        site_id=history_target.site_id or history_target.building_id.split(".", 1)[0],
                        building=history_target.building_id,
                        scope="building",
                    ),
                    confidence=0.88,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            if history_target.kind == "address" and history_target.address_text:
                return IntentSchema(
                    intent="get_building_health",
                    entities=IntentEntities(site_id=history_target.site_id, device=history_target.address_text, scope="building"),
                    confidence=0.88,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )

        if history_target is not None and any(token in lowered for token in building_fault_domain_followup_tokens):
            if history_target.kind == "building" and history_target.building_id:
                return IntentSchema(
                    intent="get_building_fault_domain",
                    entities=IntentEntities(
                        site_id=history_target.site_id or history_target.building_id.split(".", 1)[0],
                        building=history_target.building_id,
                        scope="building",
                    ),
                    confidence=0.89,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            if history_target.kind == "address" and history_target.address_text:
                return IntentSchema(
                    intent="get_building_fault_domain",
                    entities=IntentEntities(site_id=history_target.site_id, device=history_target.address_text, scope="building"),
                    confidence=0.89,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )

        if history_target is not None and any(token in lowered for token in building_followup_health_tokens):
            if history_target.kind == "building" and history_target.building_id:
                return IntentSchema(
                    intent="get_building_health",
                    entities=IntentEntities(
                        site_id=history_target.site_id or history_target.building_id.split(".", 1)[0],
                        building=history_target.building_id,
                        scope="building",
                    ),
                    confidence=0.88,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            if history_target.kind == "address" and history_target.address_text:
                return IntentSchema(
                    intent="get_building_health",
                    entities=IntentEntities(site_id=history_target.site_id, device=history_target.address_text, scope="building"),
                    confidence=0.88,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )

        if any(token in lowered for token in rerun_scan_tokens):
            if building_id or (history_target and history_target.kind == "building" and history_target.building_id):
                resolved_building = building_id or history_target.building_id
                resolved_site = site_id or history_target.site_id or (resolved_building.split(".", 1)[0] if resolved_building else None)
                return IntentSchema(
                    intent="rerun_latest_scan",
                    entities=IntentEntities(site_id=resolved_site, building=resolved_building, scope="building"),
                    confidence=0.92 if building_id else 0.9,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            if history_target and history_target.kind == "address" and history_target.address_text:
                return IntentSchema(
                    intent="rerun_latest_scan",
                    entities=IntentEntities(site_id=history_target.site_id, device=history_target.address_text, scope="building"),
                    confidence=0.9,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            if site_id or (history_target and history_target.site_id):
                resolved_site = site_id or history_target.site_id
                return IntentSchema(
                    intent="rerun_latest_scan",
                    entities=IntentEntities(site_id=resolved_site, scope="all"),
                    confidence=0.9,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="rerun_latest_scan",
                entities=IntentEntities(),
                confidence=0.5,
                ambiguous=True,
                clarification_needed="Which site or building should Jake re-check against the latest available scan?",
                raw=raw,
            )

        if explicit_building_summary_like:
            return IntentSchema(
                intent="get_building_health",
                entities=IntentEntities(site_id=site_id or building_id.split(".", 1)[0], building=building_id, scope="building"),
                confidence=0.96,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if any(token in lowered for token in correlate_tokens):
            if site_id:
                return IntentSchema(
                    intent="correlate_event_window",
                    entities=_intent_entities(site_id),
                    confidence=0.9,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="correlate_event_window",
                entities=_intent_entities(None),
                confidence=0.52,
                ambiguous=True,
                clarification_needed="I think you're asking for an event correlation window. Which site? For example: NYCHA, Chenoweth, or 000008.",
                raw=raw,
            )

        if device_hostname and any(token in lowered for token in device_log_tokens):
            return IntentSchema(
                intent="get_device_logs",
                entities=IntentEntities(site_id=site_id or device_hostname.split(".")[0], device=device_hostname, scope="device"),
                confidence=0.91,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if any(token in lowered for token in site_log_tokens):
            if site_id:
                return IntentSchema(
                    intent="get_site_logs",
                    entities=_intent_entities(site_id),
                    confidence=0.9,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="get_site_logs",
                entities=_intent_entities(None),
                confidence=0.52,
                ambiguous=True,
                clarification_needed="I think you're asking for site logs. Which site? For example: NYCHA, Chenoweth, or 000007.",
                raw=raw,
            )

        if site_id and any(token in lowered for token in carry_forward_tokens):
            prior_intent = self._history_recent_user_intent(history)
            if prior_intent in {
                "get_site_summary",
                "get_site_alerts",
                "get_online_customers",
                "get_site_punch_list",
                "get_site_precheck",
                "get_site_loop_suspicion",
                "get_site_bridge_host_weirdness",
                "get_site_topology",
            }:
                return IntentSchema(
                    intent=prior_intent,
                    entities=_intent_entities(site_id),
                    confidence=0.9,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )

        if any(token in lowered for token in online_tokens):
            if site_id:
                return IntentSchema(
                    intent="get_online_customers",
                    entities=_intent_entities(site_id),
                    confidence=0.93,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="get_online_customers",
                entities=_intent_entities(None),
                confidence=0.5,
                ambiguous=True,
                clarification_needed="Which site did you mean for the online-customer count?",
                raw=raw,
            )

        if alert_like:
            if site_id:
                return IntentSchema(
                    intent="get_site_alerts",
                    entities=_intent_entities(site_id),
                    confidence=0.92,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            if history_site_id and any(token in lowered for token in history_site_reference_tokens):
                return IntentSchema(
                    intent="get_site_alerts",
                    entities=_intent_entities(history_site_id),
                    confidence=0.84,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="get_site_alerts",
                entities=_intent_entities(None),
                confidence=0.52,
                ambiguous=True,
                clarification_needed="I think you're asking about active alerts. Which site? For example: NYCHA, Chenoweth, or a site ID like 000007.",
                raw=raw,
            )

        if any(token in lowered for token in site_precheck_tokens):
            if site_id:
                return IntentSchema(
                    intent="get_site_precheck",
                    entities=_intent_entities(site_id),
                    confidence=0.91,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="get_site_precheck",
                entities=_intent_entities(None),
                confidence=0.52,
                ambiguous=True,
                clarification_needed="I think you're asking for a site precheck. Which site? For example: NYCHA, Chenoweth, or a site ID like 000007.",
                raw=raw,
            )

        if any(token in lowered for token in site_loop_suspicion_tokens) or "loop" in lowered or "storm" in lowered:
            if site_id:
                return IntentSchema(
                    intent="get_site_loop_suspicion",
                    entities=_intent_entities(site_id),
                    confidence=0.91,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="get_site_loop_suspicion",
                entities=_intent_entities(None),
                confidence=0.52,
                ambiguous=True,
                clarification_needed="I think you're asking about loop suspicion at a site. Which site? For example: NYCHA, Chenoweth, or a site ID like 000007.",
                raw=raw,
            )

        if (
            (any(token in lowered for token in bridge_host_weirdness_tokens) and any(token in lowered for token in ("weird", "off", "odd", "wrong", "looks off")))
            or any(token in lowered for token in ("mixed mac", "mixed mac weirdness", "only showing upstream", "upstream but not at the edge", "upstream and not at the edge"))
        ):
            if site_id:
                return IntentSchema(
                    intent="get_site_bridge_host_weirdness",
                    entities=_intent_entities(site_id),
                    confidence=0.91,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="get_site_bridge_host_weirdness",
                entities=_intent_entities(None),
                confidence=0.52,
                ambiguous=True,
                clarification_needed="I think you're asking about bridge-host weirdness at a site. Which site? For example: NYCHA, Chenoweth, or a site ID like 000007.",
                raw=raw,
            )

        if any(token in lowered for token in live_cnwave_radio_neighbor_tokens):
            if site_id:
                return IntentSchema(
                    intent="get_live_cnwave_radio_neighbors",
                    entities=_intent_entities(site_id),
                    confidence=0.9,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="get_live_cnwave_radio_neighbors",
                entities=_intent_entities(None),
                confidence=0.52,
                ambiguous=True,
                clarification_needed="I think you're asking for live cnWave radio neighbors. Which site? For example: NYCHA, Chenoweth, or a site ID like 000007.",
                raw=raw,
            )

        if any(token in lowered for token in radio_handoff_trace_tokens):
            return IntentSchema(
                intent="get_radio_handoff_trace",
                entities=_intent_entities(site_id),
                confidence=0.9 if site_id else 0.84,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if building_id and any(token in lowered for token in building_fault_domain_tokens):
            return IntentSchema(
                intent="get_building_fault_domain",
                entities=IntentEntities(site_id=site_id or building_id.split(".")[0], building=building_id, scope="building"),
                confidence=0.91,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if any(token in lowered for token in site_topology_tokens):
            if site_id:
                return IntentSchema(
                    intent="get_site_topology",
                    entities=_intent_entities(site_id),
                    confidence=0.9,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="get_site_topology",
                entities=_intent_entities(None),
                confidence=0.52,
                ambiguous=True,
                clarification_needed="I think you're asking for site topology. Which site? For example: NYCHA, Chenoweth, or a site ID like 000007.",
                raw=raw,
            )

        if subscriber_label:
            normalized_subscriber = normalize_subscriber_label(subscriber_label)
            inferred_site_id = site_id or _resolve_subscriber_site_id(normalized_subscriber, self.site_vocabulary)
            resolved_mac = SUBSCRIBER_NAME_TO_MAC.get(normalized_subscriber)
            if resolved_mac:
                colonized_mac = ":".join(resolved_mac[i : i + 2] for i in range(0, 12, 2))
                return IntentSchema(
                    intent="get_cpe_state",
                    entities=IntentEntities(site_id=inferred_site_id, device=colonized_mac, scope="device"),
                    confidence=0.95,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            olt_target = SUBSCRIBER_NAME_TO_OLT.get(normalized_subscriber)
            if olt_target:
                return IntentSchema(
                    intent="get_live_olt_ont_summary",
                    entities=IntentEntities(
                        site_id=inferred_site_id or str(olt_target.get("olt") or "")[:6] or None,
                        device=normalized_subscriber,
                        scope="device",
                    ),
                    confidence=0.88,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )

        if subscriber_label and (
            any(token in lowered for token in customer_access_trace_tokens)
            or any(token in raw_lower for token in customer_access_trace_tokens)
        ):
            inferred_site_id = site_id
            if inferred_site_id is None:
                inferred_site_id = _resolve_subscriber_site_id(subscriber_label, self.site_vocabulary)
            return IntentSchema(
                intent="get_customer_access_trace",
                entities=IntentEntities(site_id=inferred_site_id, device=subscriber_label, scope="device"),
                confidence=0.92,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if any(token in lowered for token in site_punch_list_tokens):
            if site_id:
                return IntentSchema(
                    intent="get_site_punch_list",
                    entities=_intent_entities(site_id),
                    confidence=0.92,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="get_site_punch_list",
                entities=_intent_entities(None),
                confidence=0.5,
                ambiguous=True,
                clarification_needed="Which site should Jake build the punch list for?",
                raw=raw,
            )

        if any(token in lowered for token in nycha_port_audit_tokens):
            # WHY: site_id is resolved above from alias_site_id or explicit_target.
            # Do not hardcode 000007 — the port audit is site-agnostic.
            # Fall back to 000007 only when no site was specified (legacy NYCHA default).
            port_audit_site = site_id or "000007"
            return IntentSchema(
                intent="get_nycha_port_audit",
                entities=IntentEntities(site_id=port_audit_site, scope="all"),
                confidence=0.93,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        # WHY: switch_identity takes priority over building_id here.
        # "what can you tell me about 000007.001.SW01" extracts both a switch_identity
        # AND a building_id (000007.001 prefix). The switch path fires later at line ~1384;
        # we must not short-circuit to get_building_health when the user named a switch.
        if building_id and not switch_identity and any(token in raw_lower for token in building_health_tokens):
            return IntentSchema(
                intent="get_building_health",
                entities=IntentEntities(site_id=site_id, building=building_id, scope="building"),
                confidence=0.91,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        address_summary_request = not (
            raw_lower.startswith("audit ")
            or "audit workbook" in raw_lower
            or "generate audit" in raw_lower
        )
        if explicit_target.kind == "address" and explicit_target.address_text and alias_site_id is None and address_summary_request:
            return IntentSchema(
                intent="get_building_health",
                entities=IntentEntities(site_id=explicit_target.site_id, device=explicit_target.address_text, scope="building"),
                confidence=0.92,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        # WHY: Only treat multiple address candidates as ambiguous if no site alias was
        # already resolved. If alias_site_id is set (e.g. "park79" -> 000003), the
        # address matches are false positives from street-name fragments ("park" matching
        # NYCHA "Park Place" addresses). The alias takes precedence.
        if len(address_candidates) > 1 and explicit_target.kind == "none" and alias_site_id is None:
            rendered = " or ".join(row.get("address") or "" for row in address_candidates[:2] if row.get("address"))
            return IntentSchema(
                intent="unknown",
                entities=IntentEntities(site_id=None, scope="all"),
                confidence=0.45,
                ambiguous=True,
                clarification_needed=f"Do you mean {rendered}?",
                raw=raw,
            )

        if len(address_candidates) == 1 and explicit_target.kind == "none" and alias_site_id is None and address_summary_request:
            row = address_candidates[0]
            return IntentSchema(
                intent="get_building_health",
                entities=IntentEntities(site_id=row.get("site_id"), device=row.get("address"), scope="building"),
                confidence=0.91,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        # WHY: Switch-identity "audit switch <X>" or site-wide "audit all switches at NYCHA" routes to the
        # NYCHA audit workbook, not a port-audit or site summary. Must fire before the generic audit branch.
        # Also catches address-only queries like "audit 225 Buffalo Ave" — street address detected but no
        # site alias resolved (NYCHA buildings are not individually aliased in site_vocabulary).
        # WHY: Only treat as an address-based audit when the address did NOT resolve to a known site alias.
        # "audit 2020 Pacific St" resolves site_id=000007 and should stay as get_site_summary.
        # "audit 225 Buffalo Ave" resolves no site_id and should route to generate_nycha_audit_workbook.
        _audit_address_query = (
            len(address_candidates) == 1
            and alias_site_id is None
            and building_id is None
            and switch_identity is None
            and (raw_lower.startswith("audit ") or "audit workbook" in raw_lower or "generate audit" in raw_lower)
        )
        if any(token in lowered for token in nycha_audit_workbook_tokens) or (
            switch_identity
            and (raw_lower.startswith("audit ") or raw_lower.startswith("generate "))
        ) or _audit_address_query:
            inferred_site_id = site_id or (switch_identity.split(".", 1)[0] if switch_identity else None)
            # WHY: street_address goes in device entity — IntentEntities has no address_text field.
            # query_core reads it back as the raw address string for the audit call.
            device_entity = switch_identity or (address_candidates[0].get("address") if len(address_candidates) == 1 else None)
            return IntentSchema(
                intent="generate_nycha_audit_workbook",
                entities=IntentEntities(
                    site_id=inferred_site_id,
                    device=device_entity,
                    scope="device" if switch_identity else ("address" if len(address_candidates) == 1 else "site"),
                ),
                confidence=0.90,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        # WHY: "audit <address>" is a common operator phrasing to get a site overview.
        # Route it to get_site_summary, not get_site_punch_list, to match query_core behaviour.
        if alias_site_id and building_id is None and switch_identity is None and (
            raw_lower.startswith("audit ")
            or raw_lower.startswith("review ")
            or raw_lower.startswith("assess ")
        ):
            return IntentSchema(
                intent="get_site_summary",
                entities=_intent_entities(alias_site_id),
                confidence=0.88,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if site_id and building_id is None and switch_identity is None and (
            raw_lower.startswith("show me ")
            or raw_lower.startswith("show ")
            or ("show me " in raw_lower)
            or ("show " in raw_lower and len(raw_lower.split()) <= 4)
            or ("how is" in raw_lower)
            or ("how's" in raw_lower)
            or ("hows" in raw_lower)
            or ("doing" in raw_lower)
        ):
            return IntentSchema(
                intent="get_site_summary",
                entities=_intent_entities(site_id),
                confidence=0.84,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if switch_identity and any(token in raw_lower for token in switch_summary_tokens):
            inferred_site_id = site_id or switch_identity.split(".", 1)[0]
            return IntentSchema(
                intent="get_switch_summary",
                entities=IntentEntities(site_id=inferred_site_id, device=switch_identity, scope="device"),
                confidence=0.92,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if any(token in raw_lower for token in management_readiness_tokens):
            return IntentSchema(
                intent="get_cpe_management_readiness",
                entities=IntentEntities(site_id=site_id, device=None, scope="all"),
                confidence=0.89,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if any(token in raw_lower for token in management_surface_tokens) and (subscriber_label or mac or serial):
            inferred_site_id = site_id
            if inferred_site_id is None and subscriber_label:
                inferred_site_id = _resolve_subscriber_site_id(subscriber_label, self.site_vocabulary)
            device = subscriber_label or mac or serial
            return IntentSchema(
                intent="get_cpe_management_surface",
                entities=IntentEntities(site_id=inferred_site_id, device=device, scope="device"),
                confidence=0.91,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        declarative_site_summary = (
            site_id is not None
            and building_id is None
            and switch_identity is None
            and _looks_like_statement(raw)
            and re.search(r"\b(?:is|has|uses|runs|running)\b", raw_lower) is not None
        )
        if declarative_site_summary:
            return IntentSchema(
                intent="get_site_summary",
                entities=_intent_entities(site_id),
                confidence=0.75,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        summary_like = (
            any(token in lowered for token in summary_tokens)
            or any(token in raw_lower for token in summary_tokens)
            or ("looking" in raw_lower and any(token in raw_lower for token in ("how is", "how's", "hows")))
        )
        if summary_like:
            if history_target and history_target.kind == "building" and history_target.building_id:
                return IntentSchema(
                    intent="get_building_health",
                    entities=IntentEntities(
                        site_id=history_target.site_id or history_target.building_id.split(".", 1)[0],
                        building=history_target.building_id,
                        scope="building",
                    ),
                    confidence=0.86,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            if history_target and history_target.kind == "address" and history_target.address_text:
                return IntentSchema(
                    intent="get_building_health",
                    entities=IntentEntities(site_id=history_target.site_id, device=history_target.address_text, scope="building"),
                    confidence=0.86,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            if site_id:
                return IntentSchema(
                    intent="get_site_summary",
                    entities=_intent_entities(site_id),
                    confidence=0.9,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="get_site_summary",
                entities=_intent_entities(None),
                confidence=0.5,
                ambiguous=True,
                clarification_needed="Which site should Jake summarize?",
                raw=raw,
            )

        if any(token in lowered for token in troubleshooting_tokens):
            if site_id:
                return IntentSchema(
                    intent="dispatch_troubleshooting_scenarios",
                    entities=_intent_entities(site_id),
                    confidence=0.78,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="dispatch_troubleshooting_scenarios",
                entities=_intent_entities(None),
                confidence=0.5,
                ambiguous=True,
                clarification_needed="Which site did you mean for this troubleshooting question?",
                raw=raw,
            )

        vilo_candidate_like = any(token in lowered for token in vilo_candidate_tokens) or (
            "vilo" in lowered and any(token in lowered for token in ("offline", "down", "out"))
        )
        if vilo_candidate_like:
            if site_id:
                return IntentSchema(
                    intent="find_cpe_candidates",
                    entities=_intent_entities(site_id),
                    confidence=0.88,
                    ambiguous=False,
                    clarification_needed=None,
                    raw=raw,
                )
            return IntentSchema(
                intent="find_cpe_candidates",
                entities=_intent_entities(None),
                confidence=0.55,
                ambiguous=True,
                clarification_needed="Which site should Jake search for probable Vilo CPEs?",
                raw=raw,
            )

        if mac and any(token in lowered for token in cpe_state_tokens):
            return IntentSchema(
                intent="get_cpe_state",
                entities=IntentEntities(site_id=site_id, device=mac, scope="device"),
                confidence=0.95,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if mac and any(token in lowered for token in trace_mac_tokens):
            return IntentSchema(
                intent="trace_mac",
                entities=IntentEntities(site_id=site_id, device=mac, scope="device"),
                confidence=0.95,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )

        if any(token in lowered for token in live_olt_ont_tokens):
            return IntentSchema(
                intent="get_live_olt_ont_summary",
                entities=IntentEntities(site_id=site_id, device=mac, scope="device"),
                confidence=0.9,
                ambiguous=False,
                clarification_needed=None,
                raw=raw,
            )
        return None

    def _build_system_prompt(self) -> str:
        examples = _read_recent_examples(self.examples_path)
        prompt = self.system_prompt_template
        replacements = {
            "{known_intents}": json.dumps(self.known_intents, indent=2),
            "{site_vocabulary}": json.dumps(self.site_vocabulary, indent=2),
            "{equipment_vocabulary}": json.dumps(self.config.get("equipment_vocabulary") or {}, indent=2),
            "{examples}": json.dumps(examples, indent=2),
        }
        for placeholder, value in replacements.items():
            prompt = prompt.replace(placeholder, value)
        if self.context is not None:
            prompt = (
                "[ROLE]\n"
                "You are Jake, the NOC assistant for a WISP called Lynxnet/ResiBridge. You help operators understand and troubleshoot their network.\n\n"
                "When classifying intent: return only valid JSON matching the intent schema.\n"
                "When answering general questions: be direct, practical, and specific to this operator's network.\n\n"
                "[CURRENT NETWORK STATE]\n"
                f"{self.context.format_for_prompt()}\n\n"
                "[ACTION CATALOG AND INTENT SCHEMA]\n"
                f"{prompt}"
            )
        return prompt

    def compress_history(self, history: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        if not history:
            return None
        normalized: list[dict[str, str]] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            normalized.append({"role": role, "content": content})
        if not normalized:
            return None
        if len(normalized) < 8:
            return {"summary": None, "turns": normalized}

        recent_turns = normalized[-4:]
        if self.client is None:
            return {"summary": None, "turns": recent_turns}

        earlier_turns = normalized[:-4]
        transcript_lines: list[str] = []
        for item in earlier_turns:
            role = item["role"]
            content = item["content"]
            speaker = "Operator" if role == "user" else "Jake" if role == "assistant" else role.title() or "Context"
            transcript_lines.append(f"{speaker}: {content}")
        try:
            summary = self.client.generate(
                "Summarize this conversation history in 2-3 sentences focused on what network issues "
                f"were being discussed and what conclusions were reached:\n\n{chr(10).join(transcript_lines)}",
                system_prompt=(
                    "You compress prior Jake operator conversations. Return only a short plain-text summary. "
                    "Do not add bullets, headings, or commentary."
                ),
            ).strip()
        except Exception:
            summary = ""
        if not summary:
            return {"summary": None, "turns": recent_turns}
        return {"summary": summary, "turns": recent_turns}

    def _format_history_context(self, raw: str, history: dict[str, Any] | None) -> str:
        if not history:
            return ""
        lines: list[str] = []
        summary = str(history.get("summary") or "").strip()
        if summary:
            lines.append(f"Earlier in this session: {summary}")
        for item in history.get("turns") or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            speaker = "Operator" if role == "user" else "Jake" if role == "assistant" else role.title() or "Context"
            lines.append(f"{speaker}: {content}")
        if not lines:
            return ""
        lines.append("---")
        lines.append(f"Current question: {raw}")
        return "\n".join(lines)

    def _model_parse(self, raw: str, history: dict[str, Any] | None = None) -> IntentSchema:
        if self.client is None:
            raise IntentParserError("code_error", "Intent parser model fallback requires an Ollama client")
        context = self._format_history_context(raw, history)
        if context:
            prompt = context
        else:
            prompt = json.dumps({"raw": raw, "task": "parse_intent"})
        try:
            response_text = self.client.generate(prompt, system_prompt=self._build_system_prompt())
        except OllamaClientError as exc:
            raise IntentParserError(exc.classification, str(exc)) from exc
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        if "{" in cleaned and "}" in cleaned:
            cleaned = cleaned[cleaned.find("{") : cleaned.rfind("}") + 1]
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise IntentParserError("code_error", "Intent parser model returned malformed JSON") from exc
        try:
            return IntentSchema.from_dict(payload)
        except ValueError as exc:
            raise IntentParserError("code_error", f"Intent parser model returned invalid schema: {exc}") from exc
