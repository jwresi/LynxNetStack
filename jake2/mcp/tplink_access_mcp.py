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
    {"name": "get_server_info", "description": "Return TP-Link access MCP status.", "inputSchema": {"type": "object", "properties": {}}},
    {
        "name": "get_live_olt_ont_summary",
        "description": "Resolve an ONU by MAC/serial/path and run the read-only OLT show ont info command.",
        "inputSchema": {"type": "object", "properties": {"mac": {"type": "string"}, "serial": {"type": "string"}, "olt_name": {"type": "string"}, "olt_ip": {"type": "string"}, "pon": {"type": "string"}, "onu_id": {"type": "string"}}},
    },
    {
        "name": "get_live_olt_log_summary",
        "description": "Run read-only OLT log queries.",
        "inputSchema": {"type": "object", "properties": {"site_id": {"type": "string"}, "olt_name": {"type": "string"}, "olt_ip": {"type": "string"}, "mac": {"type": "string"}, "serial": {"type": "string"}, "word": {"type": "string"}, "module": {"type": "string"}, "level": {"type": "integer"}}},
    },
    {
        "name": "get_tp_link_subscriber_join",
        "description": "Correlate TP-Link subscriber, OLT, TAUC, and local export evidence.",
        "inputSchema": {"type": "object", "properties": {"network_name": {"type": "string"}, "network_id": {"type": "string"}, "mac": {"type": "string"}, "serial": {"type": "string"}, "site_id": {"type": "string"}}},
    },
    {
        "name": "get_local_ont_path",
        "description": "Return local OLT-path evidence for a MAC or serial.",
        "inputSchema": {"type": "object", "properties": {"mac": {"type": "string"}, "serial": {"type": "string"}}},
    },
]


class TpLinkAccess:
    def __init__(self) -> None:
        self.ops = JakeOps()

    def get_server_info(self) -> dict[str, Any]:
        return {"name": "tplink-access-mcp", "version": "0.1.0", "tool_count": len(TOOLS), "backing_server": "jake_ops_mcp"}


class Server:
    def __init__(self) -> None:
        self.impl = TpLinkAccess()
        self.ops = self.impl.ops

    def handle(self, req: dict[str, Any]) -> dict[str, Any] | None:
        method = req.get("method")
        req_id = req.get("id")
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "tplink-access-mcp", "version": "0.1.0"}}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            if name == "get_server_info":
                data = self.impl.get_server_info()
            elif name == "get_live_olt_ont_summary":
                data = self.ops.get_live_olt_ont_summary(args.get("mac"), args.get("serial"), args.get("olt_name"), args.get("olt_ip"), args.get("pon"), args.get("onu_id"))
            elif name == "get_live_olt_log_summary":
                data = self.ops.get_live_olt_log_summary(args.get("site_id"), args.get("olt_name"), args.get("olt_ip"), args.get("mac"), args.get("serial"), args.get("word"), args.get("module"), args.get("level"))
            elif name == "get_tp_link_subscriber_join":
                data = self.ops.get_tp_link_subscriber_join(args.get("network_name"), args.get("network_id"), args.get("mac"), args.get("serial"), args.get("site_id"))
            elif name == "get_local_ont_path":
                data = self.ops.get_local_ont_path(args.get("mac"), args.get("serial"))
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
            err = {"jsonrpc": "2.0", "id": req.get("id") if "req" in locals() and isinstance(req, dict) else None, "error": {"code": -32000, "message": str(exc), "data": traceback.format_exc()}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
