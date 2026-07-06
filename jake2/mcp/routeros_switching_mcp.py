#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.routeros_switching_catalog import ROUTEROS_SWITCHING_SCENARIOS  # noqa: E402


COMMON_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ros_version": {"type": "string"},
        "device_model": {"type": "string"},
        "symptoms": {"type": "array", "items": {"type": "string"}, "default": []},
        "site_id": {"type": "string"},
        "notes": {"type": "string"},
    },
}


TOOLS = [
    {
        "name": "get_server_info",
        "description": "Return RouterOS switching MCP status and batch scope.",
        "inputSchema": {"type": "object", "properties": {}},
    }
]

for tool_name, scenario in ROUTEROS_SWITCHING_SCENARIOS.items():
    TOOLS.append(
        {
            "name": tool_name,
            "description": scenario["summary"],
            "inputSchema": COMMON_INPUT_SCHEMA,
        }
    )


def build_scenario_result(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    scenario = dict(ROUTEROS_SWITCHING_SCENARIOS[tool_name])
    scenario["observed_context"] = {
        "ros_version": arguments.get("ros_version"),
        "device_model": arguments.get("device_model"),
        "symptoms": arguments.get("symptoms") or [],
        "site_id": arguments.get("site_id"),
        "notes": arguments.get("notes"),
    }
    return scenario


class RouterOsSwitching:
    def get_server_info(self) -> dict[str, Any]:
        return {
            "name": "routeros-switching-mcp",
            "version": "0.1.0",
            "intent_group": "switching_l2",
            "tool_count": len(TOOLS),
            "scenario_count": len(ROUTEROS_SWITCHING_SCENARIOS),
            "scenarios": list(ROUTEROS_SWITCHING_SCENARIOS.keys()),
        }


class Server:
    def __init__(self) -> None:
        self.impl = RouterOsSwitching()

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
                    "serverInfo": {"name": "routeros-switching-mcp", "version": "0.1.0"},
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
            elif name in ROUTEROS_SWITCHING_SCENARIOS:
                data = build_scenario_result(name, args)
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
