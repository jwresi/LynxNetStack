#!/usr/bin/env python3
"""kea_mcp — on-demand Kea DHCP4 lease queries via SSH to jumpB.

Queries the Kea control agent at 127.0.0.1:8000 on jumpB by SSHing in,
reading the per-container API secret, and issuing a lease4-get-all command.
No polling daemon, no stored credentials — secret is read live each call.

Tools:
  get_leases_for_site(site_id)       — all active leases for a site's /24
  find_lease_by_mac(mac)             — find a lease by MAC address
  find_lease_by_ip(ip)               — find a lease by IP address
  get_lease_summary()                — count of active leases per site
"""
from __future__ import annotations

import json
import subprocess
import sys
import traceback
from typing import Any


# SSH target — matches ~/.ssh/config Host alias on the Jake host.
# Override with KEA_JUMP_HOST env var if needed.
import os
JUMP_HOST = os.environ.get("KEA_JUMP_HOST", "jumpB")
KEA_CONTAINER = os.environ.get("KEA_CONTAINER", "kea-dhcp4")


TOOLS = [
    {
        "name": "get_server_info",
        "description": "Return Kea MCP status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_leases_for_site",
        "description": (
            "Return all active DHCP leases for a site. "
            "Accepts site alias (e.g. 'savoy', 'nycha') or six-digit site ID (e.g. '000007'). "
            "Returns ip, mac, hostname, subnet_id, giaddr, circuit_id (decoded) for each lease."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["site_id"],
            "properties": {
                "site_id": {"type": "string", "description": "Site alias or six-digit site ID"},
            },
        },
    },
    {
        "name": "find_lease_by_mac",
        "description": "Find the active DHCP lease for a given MAC address.",
        "inputSchema": {
            "type": "object",
            "required": ["mac"],
            "properties": {
                "mac": {"type": "string", "description": "MAC address (any separator format)"},
            },
        },
    },
    {
        "name": "find_lease_by_ip",
        "description": "Find the DHCP lease record for a given IP address.",
        "inputSchema": {
            "type": "object",
            "required": ["ip"],
            "properties": {
                "ip": {"type": "string", "description": "IPv4 address"},
            },
        },
    },
    {
        "name": "get_lease_summary",
        "description": "Return count of active leases per site across all 63 subnets.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

# Site alias → subnet third octet (site number).
# Subnet for site N is 100.65.N.0/24.
_SITE_ALIAS_MAP: dict[str, int] = {
    "savoy": 2, "park79": 3, "park 79": 3, "cambridge": 4,
    "essex": 5, "claiborne": 6, "nycha": 7, "2020 pacific": 7,
    "pacific st": 7, "pacific street": 7, "chenoweth": 8,
    "euclid": 11, "longwood": 12, "londonderry": 14,
    "millersville": 15, "woodlea": 16, "liberty terrace": 17,
    "libertyterrace": 17, "findlay": 18, "lefferts": 20,
    "festival field": 21, "festivalfield": 21, "sweetwater": 22,
    "atlantis": 23,
}


def _normalize_mac(mac: str) -> str:
    """Normalize MAC to Kea format: aa:bb:cc:dd:ee:ff."""
    stripped = mac.replace(":", "").replace("-", "").replace(".", "").lower()
    return ":".join(stripped[i:i+2] for i in range(0, 12, 2))


def _decode_circuit_id(hex_str: str) -> str:
    """Decode hex circuit-id to ASCII. Returns raw hex if decode fails."""
    try:
        clean = hex_str.replace("0x", "").replace("0X", "")
        return bytes.fromhex(clean).decode("ascii", errors="replace")
    except Exception:
        return hex_str


def _site_id_to_subnet_octet(site_id: str) -> int | None:
    """Map site alias or six-digit ID to the /24 third octet."""
    lower = site_id.strip().lower()
    if lower in _SITE_ALIAS_MAP:
        return _SITE_ALIAS_MAP[lower]
    # Six-digit canonical form: 000007 → 7
    digits = lower.lstrip("0")
    if digits.isdigit():
        return int(digits)
    return None


def _ssh_get_all_leases() -> list[dict]:
    """SSH to jumpB, read the Kea API secret, query lease4-get-all, return leases."""
    # One SSH session: read the secret and curl Kea in a single shell command.
    # The secret file lives inside the container; docker exec reads it without sudo.
    script = (
        f"SECRET=$(docker exec {KEA_CONTAINER} cat /etc/kea/kea-api-secret) && "
        f"USER=$(echo $SECRET | cut -d: -f1) && "
        f"PASS=$(echo $SECRET | cut -d: -f2) && "
        f"curl -sf -u \"$USER:$PASS\" -X POST http://127.0.0.1:8000/ "
        f"-H 'Content-Type: application/json' "
        f"-d '{{\"command\":\"lease4-get-all\",\"service\":[\"dhcp4\"]}}'"
    )
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", JUMP_HOST, script],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"SSH to {JUMP_HOST} failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    data = json.loads(result.stdout)
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"Unexpected Kea response: {result.stdout[:200]}")
    response = data[0]
    if response.get("result") != 0:
        raise RuntimeError(f"Kea error: {response.get('text', 'unknown')}")
    return response.get("arguments", {}).get("leases", [])


def _enrich_lease(lease: dict) -> dict:
    """Add decoded circuit-id and relay site number to a lease record."""
    out = {
        "ip": lease.get("ip-address"),
        "mac": lease.get("hw-address"),
        "hostname": lease.get("hostname", ""),
        "subnet_id": lease.get("subnet-id"),
        "giaddr": lease.get("giaddr"),
        "state": lease.get("state", 0),
    }
    circuit_hex = (
        lease.get("user-context", {})
        .get("ISC", {})
        .get("relay-agent-info", {})
        .get("circuit-id", "")
    )
    out["circuit_id"] = _decode_circuit_id(circuit_hex) if circuit_hex else ""
    return out


class KeaClient:
    def get_server_info(self) -> dict[str, Any]:
        return {
            "name": "kea-mcp",
            "version": "1.0.0",
            "jump_host": JUMP_HOST,
            "kea_container": KEA_CONTAINER,
            "description": "On-demand Kea lease queries via SSH — no polling daemon.",
        }

    def get_leases_for_site(self, site_id: str) -> dict[str, Any]:
        octet = _site_id_to_subnet_octet(site_id)
        if octet is None:
            return {"error": f"Unknown site: {site_id!r}"}
        prefix = f"100.65.{octet}."
        # Essex (site 5) uses 100.64.36.0/22 — wider range
        if octet == 5:
            prefix = "100.64."
        leases = _ssh_get_all_leases()
        site_leases = [
            _enrich_lease(l) for l in leases
            if (l.get("ip-address") or "").startswith(prefix)
        ]
        site_leases.sort(key=lambda l: tuple(int(o) for o in l["ip"].split(".")))
        return {
            "site_id": site_id,
            "subnet": f"100.65.{octet}.0/24" if octet != 5 else "100.64.36.0/22",
            "count": len(site_leases),
            "leases": site_leases,
        }

    def find_lease_by_mac(self, mac: str) -> dict[str, Any]:
        normalized = _normalize_mac(mac)
        leases = _ssh_get_all_leases()
        for l in leases:
            if l.get("hw-address") == normalized:
                return {"found": True, "lease": _enrich_lease(l)}
        return {"found": False, "mac": normalized}

    def find_lease_by_ip(self, ip: str) -> dict[str, Any]:
        leases = _ssh_get_all_leases()
        for l in leases:
            if l.get("ip-address") == ip:
                return {"found": True, "lease": _enrich_lease(l)}
        return {"found": False, "ip": ip}

    def get_lease_summary(self) -> dict[str, Any]:
        leases = _ssh_get_all_leases()
        by_subnet: dict[int, int] = {}
        for l in leases:
            sid = l.get("subnet-id", 0)
            by_subnet[sid] = by_subnet.get(sid, 0) + 1
        rows = sorted(by_subnet.items())
        return {
            "total": len(leases),
            "by_subnet": [{"subnet_id": sid, "count": cnt} for sid, cnt in rows],
        }


class Server:
    def __init__(self) -> None:
        self.client = KeaClient()

    def handle(self, req: dict[str, Any]) -> dict[str, Any] | None:
        method = req.get("method")
        req_id = req.get("id")
        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "kea-mcp", "version": "1.0.0"},
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            if name == "get_server_info":
                data = self.client.get_server_info()
            elif name == "get_leases_for_site":
                data = self.client.get_leases_for_site(args["site_id"])
            elif name == "find_lease_by_mac":
                data = self.client.find_lease_by_mac(args["mac"])
            elif name == "find_lease_by_ip":
                data = self.client.find_lease_by_ip(args["ip"])
            elif name == "get_lease_summary":
                data = self.client.get_lease_summary()
            else:
                raise ValueError(f"Unknown tool: {name}")
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(data, indent=2)}]},
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
