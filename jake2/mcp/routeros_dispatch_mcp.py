#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import traceback
from typing import Any

from core.tooling import TROUBLESHOOTING_MCP_REGISTRY, _scenario_catalog_for_mcp

ROUTEROS_DOMAIN_NAMES = (
    "routeros_access_mcp",
    "routeros_switching_mcp",
    "routeros_routing_mcp",
    "routeros_platform_mcp",
    "routeros_ops_mcp",
    "routeros_wireless_mcp",
    "swos_switching_mcp",
)

DISPATCH_THRESHOLD = 0.70
CLARIFY_THRESHOLD = 0.45

TOOLS = [
    {
        "name": "get_server_info",
        "description": "Return RouterOS dispatch MCP status and thresholds.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "explain_routing_decision",
        "description": "Explain how Jake would classify a RouterOS or SwOS troubleshooting question and which signals fired.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "site_profile": {"type": "object"},
            },
        },
    },
    {
        "name": "dispatch_routeros_question",
        "description": "Classify a RouterOS or SwOS troubleshooting question, ask for clarification if needed, or return the best scenario matches and a deterministic operator-facing answer.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "site_profile": {"type": "object"},
                "ros_version": {"type": "string"},
                "device_model": {"type": "string"},
                "limit": {"type": "integer", "default": 3},
            },
        },
    },
]


def _lowered(query: str) -> str:
    return str(query or "").strip().lower()


def _contains_term(text: str, term: str) -> bool:
    lowered = _lowered(text)
    needle = str(term or "").strip().lower()
    if not needle:
        return False
    pattern = re.escape(needle)
    pattern = pattern.replace(r"\ ", r"\s+")
    pattern = pattern.replace(r"\-", r"[-\s]+")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", lowered, re.I) is not None


def _contains_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _site_primary_sources(site_profile: dict[str, Any] | None) -> list[str]:
    return list((site_profile or {}).get("primary_sources") or [])


def _site_service_mode(site_profile: dict[str, Any] | None) -> str:
    return str((site_profile or {}).get("service_mode") or "").strip().lower()


def _extract_device_hint(query: str) -> str | None:
    lowered = _lowered(query)
    hints = (
        "ccr2004",
        "rb5009",
        "l009",
        "crs354",
        "crs328",
        "crs326",
        "crs3xx",
        "css326",
        "css610",
        "cap ax",
        "cap ac",
        "wap ax",
        "wap ac",
        "headend",
        "router",
        "switch",
        "access point",
        "ap",
    )
    for hint in hints:
        if _contains_term(lowered, hint):
            return hint
    return None


def _extract_version_hint(query: str) -> str | None:
    match = re.search(r"\b7\.\d{1,2}(?:\.\d+)?\b", query or "")
    return match.group(0) if match else None


def _score_domain(query: str, site_profile: dict[str, Any] | None, mcp_name: str) -> tuple[int, list[str]]:
    lowered = _lowered(query)
    primary_sources = _site_primary_sources(site_profile)
    service_mode = _site_service_mode(site_profile)
    meta = TROUBLESHOOTING_MCP_REGISTRY[mcp_name]

    score = 0
    matched_cues: list[str] = []

    for cue in meta.get("invoke_when", []):
        if _contains_term(lowered, cue):
            score += 2
            matched_cues.append(cue)
    for cue in meta.get("avoid_when", []):
        if _contains_term(lowered, cue):
            score -= 2

    if mcp_name == "swos_switching_mcp":
        if "switchos_edge_state" in primary_sources:
            score += 2
            matched_cues.append("site:switchos_edge_state")
        if _contains_any(lowered, ("port comment", "wrong-port", "wrong port", "host learning", "same port", "css326", "css610", "swos")):
            score += 2
            matched_cues.append("signal:swos_edge")

    if mcp_name == "routeros_switching_mcp":
        if any(src in primary_sources for src in ("switch_mac_evidence", "router_bridge_state")):
            score += 1
            matched_cues.append("site:bridge_or_switch_mac")
        if _contains_any(lowered, ("bridge", "vlan")):
            score += 1
            matched_cues.append("signal:bridge_vlan")

    if mcp_name == "routeros_access_mcp":
        if service_mode in {"pppoe", "ipoe", "dhcp"}:
            score += 1
            matched_cues.append(f"site:{service_mode}")
        if any(src in primary_sources for src in ("router_ppp_active", "live_dhcp_leases", "router_arp")):
            score += 1
            matched_cues.append("site:router_access_plane")

    if mcp_name == "routeros_routing_mcp":
        if _contains_any(lowered, ("bgp", "ospf", "vrf", "route", "check-gateway", "failover", "prefix", "as-path", "prepend")):
            score += 1
            matched_cues.append("signal:routing")
        if service_mode in {"routeros_ppp_primary", "routeros_ppp_primary_with_dhcp_evidence", "routeros_ppp_primary_with_local_online_cpe_export"}:
            score += 1
            matched_cues.append("site:router_control_plane")

    if mcp_name == "routeros_platform_mcp":
        if _contains_any(lowered, ("upgrade", "7.22.1", "7.22", "7.21", "routerboard", "firmware", "device mode", "device-mode", "nand", "poe firmware", "power interruption", "ccr2004", "rb5009", "l009", "channel strategy", "release strategy", "headend")):
            score += 2
        if _contains_any(lowered, ("upgrade", "firmware", "headend")):
            matched_cues.append("platform:upgrade_or_hardware")

    if mcp_name == "routeros_ops_mcp":
        if _contains_any(lowered, ("export", "show-sensitive", "api sensitive", "ansible", "terraform", "oxidized", "unimus", "snmp", "getbulk", "sysdescr", "ifspeed", "script", "scheduler", "fetch", "http/2", "date format", "file id", "netwatch", "check-gateway", "logging", "supout")):
            score += 2
        if _contains_any(lowered, ("script", "api", "snmp", "export", "logging", "netwatch")):
            matched_cues.append("ops:automation_or_monitoring")

    if mcp_name == "routeros_wireless_mcp":
        if _contains_any(lowered, ("capsman", "wifi-qcom", "wifi-qcom-ac", "roaming", "ssid", "community wifi", "campus wifi", "mikrotik ap", "cap ax", "cap ac", "wifi registrations", "capsman registrations", "wifi registration", "registration table", "wireless clients", "wifi provisioning", "wifi configuration", "access point")):
            score += 2
        if _contains_any(lowered, ("community wifi", "campus wifi", "walk around", "roaming domain", "capsman", "wifi registrations", "capsman registrations", "wifi registration", "wifi provisioning")):
            matched_cues.append("wireless:campus_or_capsman")

    return score, matched_cues


def classify_routeros_domain(query: str, site_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    for mcp_name in ROUTEROS_DOMAIN_NAMES:
        score, matched_cues = _score_domain(query, site_profile, mcp_name)
        scored.append({"mcp_name": mcp_name, "score": score, "matched_cues": matched_cues})

    scored.sort(key=lambda row: row["score"], reverse=True)
    positive_total = sum(max(0, int(row["score"])) for row in scored)
    best = scored[0]
    second_score = max(0, int(scored[1]["score"])) if len(scored) > 1 else 0
    best_score = max(0, int(best["score"]))
    if positive_total <= 0 or best_score <= 0:
        confidence = 0.0
    else:
        ratio = best_score / positive_total
        separation = 0.1 if best_score > second_score else 0.0
        confidence = min(0.99, round(ratio + separation, 2))

    return {
        "primary_domain": best["mcp_name"] if best_score > 0 else None,
        "confidence": confidence,
        "matched_cues": best["matched_cues"],
        "candidate_domains": scored[:3],
        "device_hint": _extract_device_hint(query),
        "version_hint": _extract_version_hint(query),
    }


def _question_asks_for_diagnostics(query: str) -> bool:
    lowered = _lowered(query)
    return _contains_any(lowered, ("how do i check", "what commands", "what should i run", "how do i verify", "show me the commands", "diagnostic"))


def _needs_upgrade_target_clarification(query: str) -> bool:
    lowered = _lowered(query)
    if not _contains_any(lowered, ("upgrade", "7.22", "firmware", "routerboard")):
        return False
    return _extract_device_hint(query) is None


def _build_clarification(query: str, classified: dict[str, Any]) -> str:
    lowered = _lowered(query)
    top = classified.get("primary_domain")
    candidates = classified.get("candidate_domains") or []
    candidate_names = [c["mcp_name"] for c in candidates[:2]]

    if _needs_upgrade_target_clarification(query):
        return "I can help with that, but I need the target first. Pick one: `CCR2004 headend`, `RB5009`, `CRS3xx switch`, `CSS/SwOS edge switch`, or `wAP/cAP AP`."
    if _contains_term(lowered, "dhcp") and any(name in candidate_names for name in ("routeros_access_mcp", "routeros_switching_mcp")):
        return "Is this about subscribers getting the wrong or no IP, or is it about bridge/VLAN forwarding not passing traffic? Pick one: `subscriber DHCP`, `bridge/VLAN forwarding`."
    if _contains_any(lowered, ("script", "export", "api", "snmp", "upgrade")) and "routeros_platform_mcp" in candidate_names and "routeros_ops_mcp" in candidate_names:
        return "Is this about the upgrade itself, or about scripts and automation that broke after the upgrade? Pick one: `upgrade/hardware risk`, `automation/scripts after upgrade`."
    if top == "routeros_wireless_mcp" and not _contains_any(lowered, ("capsman", "wifi-qcom", "cap", "wap", "ssid", "wireless", "ap")):
        return "Do you want help with `CAPsMAN/controller design`, `AP client issues`, or `upgrade risk on the WiFi gear`?"
    return "I can work this, but I need one more detail first. Tell me the device class or the symptom family: `subscriber access`, `bridge/VLAN`, `routing`, `wireless`, `platform/upgrade`, `automation`, or `SwOS edge switching`."


def _rank_scenarios(query: str, mcp_name: str, limit: int = 3) -> list[dict[str, Any]]:
    lowered = _lowered(query)
    catalog = _scenario_catalog_for_mcp(mcp_name)
    ranked: list[tuple[int, dict[str, Any]]] = []
    for tool_name, scenario in catalog.items():
        score = 0
        for phrase in scenario.get("invoke_when") or []:
            phrase_lower = str(phrase).lower()
            if phrase_lower and _contains_term(lowered, phrase_lower):
                score += 4
                continue
            tokens = [token for token in phrase_lower.replace("/", " ").replace("-", " ").split() if len(token) >= 3]
            score += sum(1 for token in tokens if _contains_term(lowered, token))
        summary_tokens = [token for token in str(scenario.get("summary") or "").lower().replace("/", " ").replace("-", " ").split() if len(token) >= 4]
        score += sum(1 for token in summary_tokens[:12] if _contains_term(lowered, token))
        if mcp_name == "routeros_wireless_mcp" and tool_name == "design_capsman_community_wifi_roaming_domain":
            if _contains_any(lowered, ("community wifi", "campus wifi", "walk around", "roaming domain", "capsman")):
                score += 8
        if score > 0:
            ranked.append((score, {"tool_name": tool_name, **scenario}))

    ranked.sort(key=lambda row: (-row[0], row[1]["tool_name"]))
    scenarios: list[dict[str, Any]] = []
    for score, scenario in ranked[: max(1, limit)]:
        entry = dict(scenario)
        entry["match_score"] = score
        scenarios.append(entry)
    return scenarios


def _parse_version(version: str | None) -> tuple[int, ...] | None:
    if not version:
        return None
    match = re.search(r"(\d+(?:\.\d+)+)", str(version))
    if not match:
        return None
    try:
        return tuple(int(piece) for piece in match.group(1).split("."))
    except ValueError:
        return None


def _version_before(current: str | None, fixed_in: str | None) -> bool | None:
    current_parts = _parse_version(current)
    fixed_parts = _parse_version(fixed_in)
    if not current_parts or not fixed_parts:
        return None
    return current_parts < fixed_parts


def render_routeros_dispatch(result: dict[str, Any], *, query: str | None = None, ros_version: str | None = None, device_model: str | None = None) -> str:
    status = result.get("status")
    if status == "clarify":
        return str(result.get("clarification") or "I need one more detail before I can route that cleanly.")
    if status != "dispatch":
        return "I do not have a sharp RouterOS troubleshooting match for that yet."

    scenario = dict((result.get("scenario_matches") or [{}])[0])
    if not scenario:
        return "I do not have a sharp RouterOS troubleshooting match for that yet."

    lines: list[str] = []
    lines.append(str(scenario.get("summary") or "").strip())

    applies = str(scenario.get("applies_to_versions") or "").strip()
    confirmed_hw = scenario.get("confirmed_hardware") or []
    if applies or confirmed_hw or device_model:
        applies_bits: list[str] = []
        if applies:
            applies_bits.append(applies)
        if device_model:
            applies_bits.append(f"device hint: {device_model}")
        elif confirmed_hw:
            applies_bits.append(f"hardware: {', '.join(str(item) for item in confirmed_hw[:3])}")
        lines.append(f"Applies to: {'; '.join(applies_bits)}.")

    likely_causes = scenario.get("likely_root_cause") or []
    if likely_causes:
        lines.append("Likely cause:")
        lines.extend(f"- {item}" for item in likely_causes[:2])

    safe_actions = scenario.get("safe_fix") or scenario.get("safe_actions") or []
    if safe_actions:
        lines.append("Safe actions:")
        for idx, item in enumerate(safe_actions[:3], start=1):
            lines.append(f"{idx}. {item}")

    dangerous = scenario.get("dangerous_actions") or []
    if dangerous:
        lines.append("Avoid:")
        lines.extend(f"- {item}" for item in dangerous[:3])

    fixed_in = scenario.get("fixed_in")
    if fixed_in:
        before = _version_before(ros_version, fixed_in)
        if before is True:
            lines.append(f"Fixed in: {fixed_in}.")
        elif before is False:
            lines.append(f"Your version already includes the upstream fix baseline: {fixed_in}.")
        else:
            lines.append(f"Fixed in: {fixed_in}.")

    if _question_asks_for_diagnostics(query or ""):
        diagnostic = scenario.get("diagnostic_commands") or []
        if diagnostic:
            lines.append("Checks:")
            lines.extend(f"- {item}" for item in diagnostic[:5])

    confidence = str(scenario.get("confidence") or result.get("confidence") or "").strip()
    if confidence:
        lines.append(f"Confidence: {confidence.capitalize()}.")

    return "\n".join(line for line in lines if line)


def dispatch_routeros_question(
    query: str,
    site_profile: dict[str, Any] | None = None,
    ros_version: str | None = None,
    device_model: str | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    classified = classify_routeros_domain(query, site_profile)
    domain = classified.get("primary_domain")
    confidence = float(classified.get("confidence") or 0.0)
    if _needs_upgrade_target_clarification(query):
        clarification = _build_clarification(query, classified)
        return {
            "status": "clarify",
            "primary_domain": domain,
            "confidence": confidence,
            "candidate_domains": classified.get("candidate_domains") or [],
            "matched_cues": classified.get("matched_cues") or [],
            "clarification": clarification,
            "rendered_answer": clarification,
        }
    if not domain:
        clarification = _build_clarification(query, classified)
        return {
            "status": "clarify",
            "primary_domain": None,
            "confidence": confidence,
            "candidate_domains": classified.get("candidate_domains") or [],
            "matched_cues": classified.get("matched_cues") or [],
            "clarification": clarification,
            "rendered_answer": clarification,
        }

    if confidence < DISPATCH_THRESHOLD:
        clarification = _build_clarification(query, classified)
        return {
            "status": "clarify",
            "primary_domain": domain,
            "confidence": confidence,
            "candidate_domains": classified.get("candidate_domains") or [],
            "matched_cues": classified.get("matched_cues") or [],
            "clarification": clarification,
            "rendered_answer": clarification,
        }

    scenarios = _rank_scenarios(query, domain, limit=limit)
    result = {
        "status": "dispatch",
        "primary_domain": domain,
        "confidence": confidence,
        "candidate_domains": classified.get("candidate_domains") or [],
        "matched_cues": classified.get("matched_cues") or [],
        "version_hint": ros_version or classified.get("version_hint"),
        "device_hint": device_model or classified.get("device_hint"),
        "scenario_matches": scenarios,
    }
    result["rendered_answer"] = render_routeros_dispatch(
        result,
        query=query,
        ros_version=ros_version or classified.get("version_hint"),
        device_model=device_model or classified.get("device_hint"),
    )
    return result


class RouterOsDispatch:
    def get_server_info(self) -> dict[str, Any]:
        return {
            "name": "routeros-dispatch-mcp",
            "version": "0.1.0",
            "intent_group": "routeros_dispatch",
            "tool_count": len(TOOLS),
            "dispatch_threshold": DISPATCH_THRESHOLD,
            "clarify_threshold": CLARIFY_THRESHOLD,
            "domains": list(ROUTEROS_DOMAIN_NAMES),
        }


class Server:
    def __init__(self) -> None:
        self.impl = RouterOsDispatch()

    def handle(self, req: dict[str, Any]) -> dict[str, Any] | None:
        method = req.get("method")
        req_id = req.get("id")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "routeros-dispatch-mcp", "version": "0.1.0"},
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            if name == "get_server_info":
                data = self.impl.get_server_info()
            elif name == "explain_routing_decision":
                data = classify_routeros_domain(args["query"], args.get("site_profile"))
            elif name == "dispatch_routeros_question":
                data = dispatch_routeros_question(
                    args["query"],
                    args.get("site_profile"),
                    args.get("ros_version"),
                    args.get("device_model"),
                    int(args.get("limit", 3)),
                )
            else:
                raise ValueError(f"Unknown tool: {name}")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(data)}]},
            }
        if method == "notifications/initialized":
            return None
        raise ValueError(f"Unknown method: {method}")


def main() -> None:
    server = Server()
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = server.handle(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            err = {
                "jsonrpc": "2.0",
                "id": req.get("id") if "req" in locals() and isinstance(req, dict) else None,
                "error": {"code": -32000, "message": str(exc), "data": traceback.format_exc()},
            }
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
