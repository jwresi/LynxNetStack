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

from mcp.jake_ops_mcp import JakeOps  # noqa: E402

TOOLS = [
    {
        "name": "get_server_info",
        "description": "Return Site Observability MCP status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_site_summary",
        "description": "Return deterministic site summary, counts, and top alerts.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}, "include_alerts": {"type": "boolean", "default": True}}},
    },
    {
        "name": "get_site_topology",
        "description": "Return deterministic site topology and grouped hardware context.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}},
    },
    {
        "name": "get_site_syslog_summary",
        "description": "Return ingested local syslog evidence for a site.",
        "inputSchema": {"type": "object", "required": ["site_id"], "properties": {"site_id": {"type": "string"}}},
    },
    {
        "name": "get_live_source_readiness",
        "description": "Return readiness of live sources on this host.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "trace_mac",
        "description": "Trace a MAC through latest scan, switch evidence, and router evidence.",
        "inputSchema": {"type": "object", "required": ["mac"], "properties": {"mac": {"type": "string"}, "include_bigmac": {"type": "boolean", "default": True}}},
    },
]


class SiteObservability:
    def __init__(self) -> None:
        self.ops = JakeOps()

    def get_server_info(self) -> dict[str, Any]:
        return {
            "name": "site-observability-mcp",
            "version": "0.1.0",
            "tool_count": len(TOOLS),
            "backing_server": "jake_ops_mcp",
        }


class Server:
    def __init__(self) -> None:
        self.impl = SiteObservability()
        self.ops = self.impl.ops

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
                    "serverInfo": {"name": "site-observability-mcp", "version": "0.1.0"},
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
            elif name == "get_site_summary":
                data = self.ops.get_site_summary(args["site_id"], bool(args.get("include_alerts", True)))
            elif name == "get_site_topology":
                data = self.ops.get_site_topology(args["site_id"])
            elif name == "get_site_syslog_summary":
                data = self.ops.get_site_syslog_summary(args["site_id"])
            elif name == "get_live_source_readiness":
                data = self.ops.get_live_source_readiness()
            elif name == "trace_mac":
                data = self.ops.trace_mac(args["mac"], bool(args.get("include_bigmac", True)))
            else:
                raise ValueError(f"Unknown tool: {name}")
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(data)}]}}
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
