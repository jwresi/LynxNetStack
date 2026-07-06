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
    {"name": "get_server_info", "description": "Return Vilo access MCP status.", "inputSchema": {"type": "object", "properties": {}}},
    {
        "name": "get_vilo_target_summary",
        "description": "Return deterministic Vilo summary for a MAC, network id, or network name.",
        "inputSchema": {"type": "object", "properties": {"mac": {"type": "string"}, "network_id": {"type": "string"}, "network_name": {"type": "string"}}},
    },
    {
        "name": "get_vilo_inventory_audit",
        "description": "Audit Vilo inventory against scan and port-map evidence.",
        "inputSchema": {"type": "object", "properties": {"site_id": {"type": "string"}, "building_id": {"type": "string"}, "limit": {"type": "integer", "default": 500}}},
    },
    {
        "name": "get_vendor_alt_mac_clusters",
        "description": "Return Vilo alternate-MAC clusters for one site/building.",
        "inputSchema": {"type": "object", "required": ["vendor"], "properties": {"vendor": {"type": "string"}, "site_id": {"type": "string"}, "building_id": {"type": "string"}, "limit": {"type": "integer", "default": 50}}},
    },
]


class ViloAccess:
    def __init__(self) -> None:
        self.ops = JakeOps()

    def get_server_info(self) -> dict[str, Any]:
        return {"name": "vilo-access-mcp", "version": "0.1.0", "tool_count": len(TOOLS), "backing_server": "jake_ops_mcp"}


class Server:
    def __init__(self) -> None:
        self.impl = ViloAccess()
        self.ops = self.impl.ops

    def handle(self, req: dict[str, Any]) -> dict[str, Any] | None:
        method = req.get("method")
        req_id = req.get("id")
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "vilo-access-mcp", "version": "0.1.0"}}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            if name == "get_server_info":
                data = self.impl.get_server_info()
            elif name == "get_vilo_target_summary":
                data = self.ops.get_vilo_target_summary(args.get("mac"), args.get("network_id"), args.get("network_name"))
            elif name == "get_vilo_inventory_audit":
                data = self.ops.audit_vilo_inventory(args.get("site_id"), args.get("building_id"), int(args.get("limit", 500)))
            elif name == "get_vendor_alt_mac_clusters":
                data = self.ops.get_vendor_alt_mac_clusters(args["vendor"], args.get("site_id"), args.get("building_id"), int(args.get("limit", 50)))
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
