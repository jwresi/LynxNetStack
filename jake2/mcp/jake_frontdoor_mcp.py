#!/usr/bin/env python3
from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.jake_ops_mcp import JakeOps  # noqa: E402
from mcp.routeros_dispatch_mcp import dispatch_routeros_question  # noqa: E402

TOOLS = [
    {
        "name": "query_summary",
        "description": "Primary Jake front door. Accept a normal network operations question and return the deterministic Jake answer with matched action, operator summary, and raw result.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
            },
        },
    },
    {
        "name": "get_server_info",
        "description": "Return Jake Front Door MCP status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class JakeFrontDoor:
    def __init__(self) -> None:
        self.ops = JakeOps()

    def get_server_info(self) -> dict[str, Any]:
        return {
            "name": "jake-frontdoor-mcp",
            "version": "0.1.0",
            "tool_count": len(TOOLS),
            "tools": [t["name"] for t in TOOLS],
            "backing_server": "jake_ops_mcp",
            "preferred_troubleshooting_mcps": [
                "routeros_dispatch_mcp",
                "routeros_access_mcp",
                "routeros_switching_mcp",
                "routeros_routing_mcp",
                "routeros_platform_mcp",
                "routeros_ops_mcp",
                "routeros_wireless_mcp",
                "swos_switching_mcp",
            ],
        }

    def query_summary(self, query: str) -> dict[str, Any]:
        try:
            data = self.ops.query_summary(query)
            matched_action = data.get("matched_action")
            routeros_dispatch = dispatch_routeros_question(query, None, limit=3)
            if matched_action == "dispatch_troubleshooting_scenarios" and routeros_dispatch.get("rendered_answer"):
                data["assistant_answer"] = str(routeros_dispatch.get("rendered_answer"))
                data["operator_summary"] = str(routeros_dispatch.get("rendered_answer"))
                data["preferred_mcp"] = routeros_dispatch.get("primary_domain")
                data["dispatched_scenarios"] = routeros_dispatch.get("scenario_matches") or []
            elif matched_action in {"get_site_summary", "get_site_alerts"} and routeros_dispatch.get("status") == "dispatch":
                top = (routeros_dispatch.get("scenario_matches") or [{}])[0]
                lines = [
                    str(data.get("assistant_answer") or data.get("operator_summary") or "").strip(),
                    "",
                    f"Best troubleshooting path: `{routeros_dispatch.get('primary_domain')}`.",
                    f"Best scenario match: `{top.get('tool_name')}`.",
                    str(top.get("summary") or "").strip(),
                ]
                data["assistant_answer"] = "\n".join(line for line in lines if line)
                data["dispatched_scenarios"] = routeros_dispatch.get("scenario_matches") or []
            return data
        except Exception as exc:
            dispatch = dispatch_routeros_question(query, None, limit=3)
            preferred_mcp = dispatch.get("primary_domain")
            if preferred_mcp:
                cues = dispatch.get("matched_cues") or []
                lines = [f"Jake would start with `{preferred_mcp}` for this question."]
                if cues:
                    lines.append(f"Matched cues: {', '.join(cues[:6])}.")
                scenarios = dispatch.get("scenario_matches") or []
                if scenarios:
                    lines.append("Best scenario matches:")
                    for scenario in scenarios[:3]:
                        lines.append(f"- `{scenario.get('tool_name')}`: {scenario.get('summary')}")
                elif dispatch.get("clarification"):
                    lines.append(str(dispatch.get("clarification")))
                return {
                    "query": query,
                    "matched_action": None,
                    "params": {},
                    "operator_summary": "\n".join(line for line in lines if line),
                    "assistant_answer": "\n".join(line for line in lines if line),
                    "result": {"frontdoor_fallback": True, "error": str(exc)},
                    "preferred_mcp": preferred_mcp,
                    "preferred_mcp_reason": None,
                    "preferred_mcp_cues": cues,
                    "dispatched_scenarios": scenarios,
                }
            raise


class Server:
    def __init__(self) -> None:
        self.impl = JakeFrontDoor()

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
                    "serverInfo": {"name": "jake-frontdoor-mcp", "version": "0.1.0"},
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
                text = json.dumps(data)
            elif name == "query_summary":
                data = self.impl.query_summary(args["query"])
                text = str(data.get("assistant_answer") or data.get("operator_summary") or json.dumps(data))
            else:
                raise ValueError(f"Unknown tool: {name}")
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": text}]}}
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
                "id": req.get("id") if 'req' in locals() and isinstance(req, dict) else None,
                "error": {"code": -32000, "message": str(exc), "data": traceback.format_exc()},
            }
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
