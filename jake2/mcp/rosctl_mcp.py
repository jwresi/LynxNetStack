#!/usr/bin/env python3
"""rosctl_mcp — RouterOS fleet operations via the rosctl REST API.

rosctl (https://rosctl.lynxnet.co / http://172.27.226.246:3200) is an internal
RouterOS fleet management platform. It maintains a live connection to all 122
devices via the MikroTik API and exposes a REST API that returns parsed JSON
for any RouterOS /path/print command.

Authentication: POST /api/v1/auth/login → JWT bearer token.
The token is acquired once per process and reused; if it expires (401) a new
one is obtained transparently.

Fleet as of 2026-07-07: 122 devices, 118 online, 19 sites.
Device naming: SSSSSS.BBB.ROLE## (e.g. 000007.039.SW01, 000001.001.R01)

Write operations (reboot, staging apply) are disabled by default.
Set ROSCTL_ENABLE_WRITES=true to unlock.

Tools:
  get_server_info()                    — fleet stats, API health
  get_devices(site_id?)                — device inventory, optional site filter
  get_device(device_name)              — single device detail by name
  get_device_status()                  — bulk online/offline for all devices
  run_command(device_name, command)    — execute a RouterOS /path/print command
  get_interfaces(device_name)          — /interface/print detail
  get_bridge_hosts(device_name)        — MAC table via /interface/bridge/host/print
  get_arp(device_name)                 — ARP table via /ip/arp/print
  get_routes(device_name)              — routing table via /ip/route/print
  get_ppp_active(device_name)          — active PPPoE sessions
  get_ip_addresses(device_name)        — IP addresses via /ip/address/print
  get_system_health(device_name)       — temperature, fans, PSU
  get_system_resource(device_name)     — CPU, memory, uptime, ROS version
  get_neighbors(device_name)           — CDP/LLDP neighbors
  get_logs(device_name)                — device syslog (last N entries)
  get_sites()                          — site inventory
  get_pending_enrollment()             — devices seen but not yet adopted
"""
from __future__ import annotations

import json
import os
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


ROSCTL_URL     = os.environ.get("ROSCTL_URL",      "http://172.27.226.246:3200").rstrip("/")
ROSCTL_USER    = os.environ.get("ROSCTL_USER",     "jonathan")
ROSCTL_PASS    = os.environ.get("ROSCTL_PASSWORD", "F7pdn*AQ0Uu4S#t")
ENABLE_WRITES  = os.environ.get("ROSCTL_ENABLE_WRITES", "false").lower() == "true"

TOOLS = [
    {
        "name": "get_server_info",
        "description": (
            "Return rosctl API health, fleet stats (total/online/offline device counts), "
            "and firmware posture summary."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_sites",
        "description": "Return all sites with device counts. Site names are six-digit IDs (e.g. '000007').",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_devices",
        "description": (
            "Return device inventory. Optionally filter by site_id (six-digit string, e.g. '000007'). "
            "Each device includes name, host, board, ROS version, status, last_seen."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "Six-digit site ID to filter by (e.g. '000007'). Omit for all devices.",
                },
            },
        },
    },
    {
        "name": "get_device",
        "description": (
            "Return full detail for a single device by name (e.g. '000007.039.SW01'). "
            "Includes host, board, ROS version, connection mode, site, location."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string", "description": "Device name (e.g. '000007.039.SW01')"},
            },
        },
    },
    {
        "name": "get_device_status",
        "description": "Return online/offline status and last_seen timestamp for every device in the fleet.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_command",
        "description": (
            "Execute a RouterOS /path/print command on a device and return parsed JSON output. "
            "Only read (print) operations are permitted. "
            "Example commands: '/ip/arp/print', '/interface/bridge/host/print detail', "
            "'/ppp/active/print', '/ip/dhcp-server/lease/print'. "
            "Do NOT use for reboot, set, add, remove, or other mutating commands."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["device_name", "command"],
            "properties": {
                "device_name": {"type": "string", "description": "Device name (e.g. '000007.039.SW01')"},
                "command": {
                    "type": "string",
                    "description": "RouterOS API command path (must end in /print or /print detail)",
                },
            },
        },
    },
    {
        "name": "get_interfaces",
        "description": "Return all interfaces with type, status, MAC, MTU, and traffic counters.",
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_bridge_hosts",
        "description": (
            "Return the bridge MAC table (FDB) for a device — "
            "which MAC addresses are learned on which interfaces. "
            "Use this to locate a subscriber CPE by MAC address."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_arp",
        "description": "Return ARP table — IP-to-MAC mappings and reachability status.",
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_routes",
        "description": "Return the IP routing table including static, DHCP, and dynamic routes.",
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_ppp_active",
        "description": (
            "Return active PPPoE sessions on a device. "
            "Each entry includes username, caller-id (MAC), assigned IP, and uptime. "
            "Useful for NYCHA site (000007) which uses PPPoE for subscriber access."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_ip_addresses",
        "description": "Return IP addresses assigned to interfaces on a device.",
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_system_health",
        "description": "Return hardware health: temperature, fan speeds, PSU state.",
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_system_resource",
        "description": (
            "Return system resource summary: uptime, ROS version, CPU load, "
            "free/total memory, architecture, board name."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_neighbors",
        "description": (
            "Return CDP/LLDP neighbor discovery entries — "
            "which devices are directly connected, their identity, platform, and IP."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_logs",
        "description": "Return recent syslog entries from the device.",
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
            },
        },
    },
    {
        "name": "get_pending_enrollment",
        "description": (
            "Return devices that have contacted rosctl but are not yet adopted into the fleet. "
            "These are pending import from NetBox or manual enrollment."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class RosctlClient:
    """Thin HTTP client for the rosctl REST API."""

    def __init__(self) -> None:
        self._token: str | None = None
        # Cache: device_name -> device_id
        self._device_cache: dict[str, int] = {}

    def _login(self) -> None:
        payload = json.dumps({"username": ROSCTL_USER, "password": ROSCTL_PASS}).encode()
        req = urllib.request.Request(
            f"{ROSCTL_URL}/api/v1/auth/login",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            self._token = data["access_token"]

    def _headers(self) -> dict[str, str]:
        if not self._token:
            self._login()
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _get(self, path: str) -> Any:
        url = f"{ROSCTL_URL}/api/v1/{path.lstrip('/')}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self._token = None
                self._login()
                req = urllib.request.Request(url, headers=self._headers())
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read())
            raise

    def _post(self, path: str, body: dict) -> Any:
        url = f"{ROSCTL_URL}/api/v1/{path.lstrip('/')}"
        payload = json.dumps(body).encode()
        req = urllib.request.Request(url, data=payload, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self._token = None
                self._login()
                req = urllib.request.Request(url, data=payload, headers=self._headers(), method="POST")
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return json.loads(resp.read())
            raise

    def _get_all_devices(self) -> dict:
        """
        Fetch the FULL device list.

        The server defaults to 100 rows and silently truncates: /api/v1/devices
        returns 100 of 134 (ids 37..138), hiding the 36 lowest-id devices — the
        oldest NYCHA gear (104 Tapscott, 2058 Union, 692 Ralph, ...). That made
        _resolve_device raise "not found in rosctl" for real, online switches,
        and get_devices under-report every site. Page explicitly instead.
        """
        page_size = 500
        skip = 0
        out: list = []
        total = None
        for _ in range(50):  # runaway guard
            data = self._get(f"devices?limit={page_size}&skip={skip}")
            batch = data.get("devices", [])
            if total is None:
                total = data.get("total")
            out.extend(batch)
            if len(batch) < page_size or (total is not None and len(out) >= total):
                break
            skip += page_size
        return {"devices": out, "total": total if total is not None else len(out)}

    def _resolve_device(self, device_name: str) -> int:
        """Resolve device name to rosctl internal ID, with local cache."""
        name = device_name.strip().upper()
        if name in self._device_cache:
            return self._device_cache[name]
        data = self._get_all_devices()
        for d in data.get("devices", []):
            self._device_cache[d["name"].upper()] = d["id"]
        if name not in self._device_cache:
            raise ValueError(
                f"Device {device_name!r} not found in rosctl. "
                f"Known names: {', '.join(sorted(self._device_cache)[:10])}..."
            )
        return self._device_cache[name]

    def device_command(self, device_name: str, command: str) -> dict:
        dev_id = self._resolve_device(device_name)
        return self._post(f"devices/{dev_id}/command", {"command": command})

    def get_dashboard(self) -> dict:
        return self._get("devices/dashboard")

    def get_devices(self, site_name: str | None = None) -> dict:
        data = self._get_all_devices()
        devices = data.get("devices", [])
        if site_name:
            target = site_name.strip().lstrip("0") or "0"
            devices = [
                d for d in devices
                if (d.get("site_name") or "").lstrip("0") == target
                or str(d.get("site_id", "")) == target
            ]
        return {"devices": devices, "total": len(devices)}

    def get_device(self, device_name: str) -> dict:
        dev_id = self._resolve_device(device_name)
        return self._get(f"devices/{dev_id}")

    def get_device_status(self) -> dict:
        return self._get("devices/status")

    def get_sites(self) -> dict:
        return self._get("sites")

    def get_pending_enrollment(self) -> dict:
        return self._get("enrollment/pending")


_client = RosctlClient()

_PRINT_COMMANDS = {
    "get_interfaces":     "/interface/print detail",
    "get_bridge_hosts":   "/interface/bridge/host/print",
    "get_arp":            "/ip/arp/print detail",
    "get_routes":         "/ip/route/print detail",
    "get_ppp_active":     "/ppp/active/print",
    "get_ip_addresses":   "/ip/address/print detail",
    "get_system_health":  "/system/health/print",
    "get_system_resource": "/system/resource/print",
    "get_neighbors":      "/ip/neighbor/print detail",
    "get_logs":           "/log/print",
}

_WRITE_COMMANDS = {"reboot", "reset", "set", "add", "remove", "enable", "disable", "move", "import", "export"}


def _is_safe_command(cmd: str) -> bool:
    """Allow only RouterOS read (print) operations."""
    stripped = cmd.strip().lstrip("/")
    last_segment = stripped.split("/")[-1].split()[0].lower()
    return last_segment == "print"


class RosctlMCP:

    def get_server_info(self) -> dict[str, Any]:
        dash = _client.get_dashboard()
        stats = dash.get("stats", {})
        return {
            "rosctl_url":          ROSCTL_URL,
            "writes_enabled":      ENABLE_WRITES,
            "total_devices":       stats.get("total_devices"),
            "online_count":        stats.get("online_count"),
            "offline_count":       stats.get("offline_count"),
            "online_pct":          stats.get("online_percentage"),
            "devices_needing_update": stats.get("devices_needing_update"),
            "latest_stable":       stats.get("latest_stable_version"),
            "latest_lts":          stats.get("latest_lts_version"),
            "direct_mode_count":   stats.get("direct_mode_count"),
            "agent_mode_count":    stats.get("agent_mode_count"),
            "outdated_sample":     [
                {"name": d["name"], "current": d["current_version"], "latest": d["latest_version"]}
                for d in (dash.get("outdated_devices") or [])[:5]
            ],
        }

    def get_sites(self) -> dict[str, Any]:
        return _client.get_sites()

    def get_devices(self, site_id: str | None = None) -> dict[str, Any]:
        data = _client.get_devices(site_id)
        devices = data["devices"]
        return {
            "total": data["total"],
            "site_filter": site_id,
            "devices": [
                {
                    "id":        d["id"],
                    "name":      d["name"],
                    "host":      d["host"],
                    "board":     d.get("board"),
                    "version":   d.get("version"),
                    "status":    d.get("status"),
                    "last_seen": d.get("last_seen"),
                    "site":      d.get("site_name"),
                    "location":  d.get("location"),
                    "role":      d.get("device_role"),
                }
                for d in devices
            ],
        }

    def get_device(self, device_name: str) -> dict[str, Any]:
        d = _client.get_device(device_name)
        return {
            "id":             d["id"],
            "name":           d["name"],
            "identity":       d.get("identity"),
            "host":           d["host"],
            "board":          d.get("board"),
            "version":        d.get("version"),
            "architecture":   d.get("architecture"),
            "serial":         d.get("serial"),
            "status":         d.get("status"),
            "last_seen":      d.get("last_seen"),
            "site":           d.get("site_name"),
            "location":       d.get("location"),
            "role":           d.get("device_role"),
            "connection_mode": d.get("connection_mode"),
            "api_port":       d.get("api_port"),
            "terminal_enabled": d.get("terminal_enabled"),
        }

    def get_device_status(self) -> dict[str, Any]:
        data = _client.get_device_status()
        statuses = data.get("statuses", [])
        online  = [s for s in statuses if s.get("status") == "online"]
        offline = [s for s in statuses if s.get("status") != "online"]
        return {
            "total":   len(statuses),
            "online":  len(online),
            "offline": len(offline),
            "offline_devices": offline,
            "statuses": statuses,
        }

    def run_command(self, device_name: str, command: str) -> dict[str, Any]:
        if not _is_safe_command(command):
            return {
                "error": (
                    f"Command {command!r} is not a read-only print operation. "
                    "Only /path/print commands are permitted."
                )
            }
        result = _client.device_command(device_name, command)
        return {
            "device":  device_name,
            "command": command,
            "success": result.get("success"),
            "data":    result.get("data"),
            "error":   result.get("error"),
        }

    def _simple_command(self, device_name: str, tool_name: str) -> dict[str, Any]:
        command = _PRINT_COMMANDS[tool_name]
        result = _client.device_command(device_name, command)
        return {
            "device":  device_name,
            "command": command,
            "success": result.get("success"),
            "data":    result.get("data"),
            "error":   result.get("error"),
        }

    def get_interfaces(self, device_name: str) -> dict[str, Any]:
        return self._simple_command(device_name, "get_interfaces")

    def get_bridge_hosts(self, device_name: str) -> dict[str, Any]:
        return self._simple_command(device_name, "get_bridge_hosts")

    def get_arp(self, device_name: str) -> dict[str, Any]:
        return self._simple_command(device_name, "get_arp")

    def get_routes(self, device_name: str) -> dict[str, Any]:
        return self._simple_command(device_name, "get_routes")

    def get_ppp_active(self, device_name: str) -> dict[str, Any]:
        return self._simple_command(device_name, "get_ppp_active")

    def get_ip_addresses(self, device_name: str) -> dict[str, Any]:
        return self._simple_command(device_name, "get_ip_addresses")

    def get_system_health(self, device_name: str) -> dict[str, Any]:
        return self._simple_command(device_name, "get_system_health")

    def get_system_resource(self, device_name: str) -> dict[str, Any]:
        return self._simple_command(device_name, "get_system_resource")

    def get_neighbors(self, device_name: str) -> dict[str, Any]:
        return self._simple_command(device_name, "get_neighbors")

    def get_logs(self, device_name: str) -> dict[str, Any]:
        return self._simple_command(device_name, "get_logs")

    def get_pending_enrollment(self) -> dict[str, Any]:
        return _client.get_pending_enrollment()


class Server:
    def __init__(self) -> None:
        self.impl = RosctlMCP()

    def handle(self, req: dict[str, Any]) -> dict[str, Any] | None:
        method = req.get("method")
        req_id = req.get("id")
        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "rosctl-mcp", "version": "1.0.0"},
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = req.get("params", {})
            name   = params.get("name")
            args   = params.get("arguments", {})
            impl   = self.impl
            if name == "get_server_info":
                data = impl.get_server_info()
            elif name == "get_sites":
                data = impl.get_sites()
            elif name == "get_devices":
                data = impl.get_devices(args.get("site_id"))
            elif name == "get_device":
                data = impl.get_device(args["device_name"])
            elif name == "get_device_status":
                data = impl.get_device_status()
            elif name == "run_command":
                data = impl.run_command(args["device_name"], args["command"])
            elif name == "get_interfaces":
                data = impl.get_interfaces(args["device_name"])
            elif name == "get_bridge_hosts":
                data = impl.get_bridge_hosts(args["device_name"])
            elif name == "get_arp":
                data = impl.get_arp(args["device_name"])
            elif name == "get_routes":
                data = impl.get_routes(args["device_name"])
            elif name == "get_ppp_active":
                data = impl.get_ppp_active(args["device_name"])
            elif name == "get_ip_addresses":
                data = impl.get_ip_addresses(args["device_name"])
            elif name == "get_system_health":
                data = impl.get_system_health(args["device_name"])
            elif name == "get_system_resource":
                data = impl.get_system_resource(args["device_name"])
            elif name == "get_neighbors":
                data = impl.get_neighbors(args["device_name"])
            elif name == "get_logs":
                data = impl.get_logs(args["device_name"])
            elif name == "get_pending_enrollment":
                data = impl.get_pending_enrollment()
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
