#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from core.shared import seed_project_envs


TOOLS = [
    {
        "name": "get_server_info",
        "description": "Return Bigmac MCP configuration status and basic diagnostics.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_stats",
        "description": "Fetch Bigmac dashboard stats.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_filters",
        "description": "Fetch Bigmac filter lists such as sites, platforms, roles, and VLANs.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_macs",
        "description": "Search Bigmac MAC records by partial MAC and optional filters.",
        "inputSchema": {
            "type": "object",
            "required": ["mac"],
            "properties": {
                "mac": {"type": "string"},
                "site": {"type": "string"},
                "platform": {"type": "string"},
                "role": {"type": "string"},
                "port_type": {"type": "string"},
                "vlan": {"type": "string"},
                "hide_sfp": {"type": "boolean", "default": False},
                "offset": {"type": "integer", "default": 0},
            },
        },
    },
    {
        "name": "get_mac_history",
        "description": "Fetch historical Bigmac sightings for a specific MAC.",
        "inputSchema": {
            "type": "object",
            "required": ["mac"],
            "properties": {"mac": {"type": "string"}},
        },
    },
    {
        "name": "get_site_macs",
        "description": "Fetch all Bigmac MAC records for a site.",
        "inputSchema": {
            "type": "object",
            "required": ["site"],
            "properties": {"site": {"type": "string"}},
        },
    },
]


class BigmacClient:
    def __init__(self, base_url: str = "", user: str = "", password: str = "") -> None:
        self.url = str(base_url or "").rstrip("/")
        self.user = str(user or "")
        self.password = str(password or "")

    @classmethod
    def from_env(cls, project_root: Path) -> "BigmacClient":
        seed_project_envs(project_root)
        import os

        return cls(
            os.environ.get("BIGMAC_URL", ""),
            os.environ.get("BIGMAC_USER", ""),
            os.environ.get("BIGMAC_PASSWORD", ""),
        )

    def configured(self) -> bool:
        return bool(self.url and self.user and self.password)

    def _auth_header(self) -> str:
        token = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        return f"Basic {token}"

    def request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.configured():
            raise ValueError("BIGMAC_URL or credentials are not configured")
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        full_url = f"{self.url}{path}"
        if query:
            full_url = f"{full_url}?{query}"
        req = urllib.request.Request(
            full_url,
            headers={"Authorization": self._auth_header(), "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Bigmac HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Bigmac connection error: {exc}") from exc
        return json.loads(body)

    def probe(self) -> dict[str, Any]:
        if not self.configured():
            return {"ok": False, "error": "BIGMAC_URL or credentials are not configured"}
        try:
            data = self.request("/api/stats")
            return {"ok": True, "stats": data}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def search_macs(self, mac: str, **filters: Any) -> dict[str, Any]:
        query = {"mac": str(mac or "").replace(":", "").replace("-", "")}
        query.update(filters)
        return self.request("/api/search", query)

    def get_mac_history(self, mac: str) -> dict[str, Any]:
        normalized = str(mac or "").replace(":", "").replace("-", "").lower()
        return self.request(f"/api/mac/{normalized}/history")

    def get_site_macs(self, site: str) -> dict[str, Any]:
        return self.request(f"/api/site/{site}/macs")


class MCPServer:
    def __init__(self) -> None:
        self.client = BigmacClient.from_env(Path(__file__).resolve().parent.parent)

    def run(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                return
            if "method" in message and message.get("id") is None:
                continue
            self._handle_request(message)

    def _handle_request(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = message.get("method")
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "bigmac-readonly-mcp", "version": "0.1.0"},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self._call_tool(message.get("params", {}))
            else:
                raise ValueError(f"Unsupported method: {method}")
            self._write_message({"jsonrpc": "2.0", "id": request_id, "result": result})
        except Exception as exc:
            self._write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": str(exc), "data": traceback.format_exc()},
                }
            )

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "get_server_info":
            text = json.dumps(
                {
                    "configured": self.client.configured(),
                    "bigmac_url": self.client.url,
                    "tools": [tool["name"] for tool in TOOLS],
                    "connectivity_probe": self.client.probe(),
                }
            )
            return {"content": [{"type": "text", "text": text}]}
        if name == "get_stats":
            return {"content": [{"type": "text", "text": json.dumps(self.client.request("/api/stats"))}]}
        if name == "get_filters":
            return {"content": [{"type": "text", "text": json.dumps(self.client.request("/api/filters"))}]}
        if name == "search_macs":
            return {"content": [{"type": "text", "text": json.dumps(self.client.search_macs(arguments["mac"]))}]}
        if name == "get_mac_history":
            return {"content": [{"type": "text", "text": json.dumps(self.client.get_mac_history(arguments["mac"]))}]}
        if name == "get_site_macs":
            return {"content": [{"type": "text", "text": json.dumps(self.client.get_site_macs(arguments["site"]))}]}
        raise ValueError(f"Unknown tool: {name}")

    def _read_message(self) -> dict[str, Any] | None:
        line = input()
        if not line:
            return None
        return json.loads(line)

    def _write_message(self, message: dict[str, Any]) -> None:
        print(json.dumps(message), flush=True)


if __name__ == "__main__":
    MCPServer().run()
