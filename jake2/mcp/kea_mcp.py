#!/usr/bin/env python3
"""kea_mcp — on-demand Kea DHCP4 lease queries via the ISC Stork REST API.

Stork (http://172.27.209.248:9080) is the monitoring layer sitting in front of
Kea on jumpB. It exposes a stable REST API over ZeroTier with a fixed credential,
eliminating the need to SSH to jumpB or manage Kea's ephemeral per-container
API secret.

Authentication: session cookie obtained by POST /api/sessions. The cookie is
acquired once per process and reused; if it expires a new one is fetched
transparently.

Stork lease coverage note:
  Stork caches leases via its kea_leases_puller (60s interval). At any given
  moment it holds a subset of live leases (~59 of 415 observed). For point
  lookups (by MAC or IP) this is sufficient — Stork searches Kea live for
  text queries. For full site dumps the count reflects Stork's current cache.

Stork base URL: http://172.27.209.248:9080
Credentials:    STORK_URL / STORK_USER / STORK_PASSWORD env vars

Tools:
  get_server_info()               — Stork version, Kea daemon status, stats
  get_leases_for_site(site_id)    — leases for a site subnet via Stork cache
  find_lease_by_mac(mac)          — live Kea lookup by MAC via Stork
  find_lease_by_ip(ip)            — live Kea lookup by IP via Stork
  get_lease_summary()             — assigned/total counts per subnet from Stork
  get_subnet_stats()              — utilization across all 70 subnets
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


STORK_URL  = os.environ.get("STORK_URL",      "http://172.27.209.248:9080").rstrip("/")
STORK_USER = os.environ.get("STORK_USER",     "admin")
STORK_PASS = os.environ.get("STORK_PASSWORD", "*azBXCsw9XL#DF6")

# Stork subnet IDs match the third octet of 100.65.X.0/24 directly.
# Exception: Essex uses a flat /22 (id=70, 100.64.36.0/22).
# Site alias → Stork subnet ID
_SITE_TO_SUBNET_ID: dict[str, int] = {
    "savoy": 2,            "park79": 3,          "park 79": 3,
    "cambridge": 4,        "essex": 70,           "claiborne": 6,
    "nycha": 7,            "2020 pacific": 7,     "pacific st": 7,
    "pacific street": 7,   "chenoweth": 8,        "euclid": 11,
    "longwood": 12,        "londonderry": 14,     "millersville": 15,
    "woodlea": 16,         "liberty terrace": 17, "libertyterrace": 17,
    "findlay": 18,         "lefferts": 20,        "festival field": 21,
    "festivalfield": 21,   "sweetwater": 22,      "atlantis": 23,
}

# Subnet ID → human label (for summary output)
_SUBNET_LABELS: dict[int, str] = {
    2: "savoy", 3: "park79", 4: "cambridge", 5: "essex-old",
    6: "claiborne", 7: "nycha", 8: "chenoweth", 11: "euclid",
    12: "longwood", 14: "londonderry", 15: "millersville", 16: "woodlea",
    17: "liberty-terrace", 18: "findlay", 20: "lefferts",
    21: "festival-field", 22: "sweetwater", 23: "atlantis", 70: "essex",
}


def _normalize_mac(mac: str) -> str:
    """Normalize MAC to colon-separated lowercase: aa:bb:cc:dd:ee:ff."""
    stripped = mac.replace(":", "").replace("-", "").replace(".", "").lower()
    return ":".join(stripped[i:i+2] for i in range(0, 12, 2))


def _site_to_subnet_id(site_id: str) -> int | None:
    """Resolve site alias or six-digit ID to a Stork subnet ID."""
    lower = site_id.strip().lower()
    if lower in _SITE_TO_SUBNET_ID:
        return _SITE_TO_SUBNET_ID[lower]
    digits = lower.lstrip("0") or "0"
    if digits.isdigit():
        n = int(digits)
        # Essex canonical six-digit → subnet id 70
        if n == 5:
            return 70
        return n
    return None


class StorkClient:
    """Thin HTTP client for the Stork REST API."""

    def __init__(self) -> None:
        self._cookie: str | None = None

    def _login(self) -> None:
        payload = json.dumps({
            "authenticationMethodId": "internal",
            "identifier": STORK_USER,
            "secret": STORK_PASS,
        }).encode()
        req = urllib.request.Request(
            f"{STORK_URL}/api/sessions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            # Extract session cookie
            set_cookie = resp.headers.get("Set-Cookie", "")
            # Grab the first name=value pair
            self._cookie = set_cookie.split(";")[0] if set_cookie else ""

    def _get(self, path: str, params: dict | None = None) -> Any:
        if not self._cookie:
            self._login()
        url = f"{STORK_URL}/api/{path.lstrip('/')}"
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        req = urllib.request.Request(url, headers={"Cookie": self._cookie})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # Session expired — re-login once
                self._cookie = None
                self._login()
                req = urllib.request.Request(url, headers={"Cookie": self._cookie})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read())
            raise

    def get_overview(self) -> dict:
        return self._get("overview")

    def get_machines(self) -> dict:
        return self._get("machines")

    def lease_search(self, text: str | None = None, subnet_id: int | None = None,
                     start: int = 0, limit: int = 500) -> dict:
        return self._get("lease-list", {
            "text": text or "",
            "subnetId": subnet_id,
            "start": start,
            "limit": limit,
        })

    def get_subnets(self, limit: int = 100) -> dict:
        return self._get("subnets", {"start": 0, "limit": limit})


# Module-level singleton — one session per process
_client = StorkClient()


def _fmt_lease(item: dict) -> dict:
    """Normalise a Stork lease record to a consistent output shape."""
    return {
        "ip":          item.get("ipAddress"),
        "mac":         item.get("hwAddress"),
        "client_id":   item.get("clientId"),
        "subnet":      item.get("subnetPrefix"),
        "subnet_id":   item.get("subnetId"),
        "state":       item.get("state", 0),
        "valid_lft":   item.get("validLifetime"),
        "cltt":        item.get("cltt"),
    }


class KeaClient:

    def get_server_info(self) -> dict[str, Any]:
        ov = _client.get_overview()
        machines = _client.get_machines()
        daemon = (ov.get("dhcpDaemons") or [{}])[0]
        stats4 = ov.get("dhcp4Stats", {})
        machine = (machines.get("items") or [{}])[0]
        return {
            "stork_url":        STORK_URL,
            "stork_version":    "2.5.0",
            "kea_version":      daemon.get("version"),
            "kea_label":        daemon.get("label"),
            "kea_uptime_sec":   daemon.get("uptime"),
            "kea_reloaded_at":  daemon.get("reloadedAt"),
            "kea_active":       daemon.get("active"),
            "rps_1min":         daemon.get("rps1"),
            "rps_5min":         daemon.get("rps2"),
            "assigned_addresses": stats4.get("assignedAddresses"),
            "total_addresses":    stats4.get("totalAddresses"),
            "declined_addresses": stats4.get("declinedAddresses"),
            "machine_host":     machine.get("hostname"),
            "machine_os":       machine.get("platform"),
            "machine_arch":     machine.get("kernelArch"),
            "machine_memory_gb": machine.get("memory"),
        }

    def get_leases_for_site(self, site_id: str) -> dict[str, Any]:
        subnet_id = _site_to_subnet_id(site_id)
        if subnet_id is None:
            return {"error": f"Unknown site: {site_id!r}"}
        result = _client.lease_search(subnet_id=subnet_id)
        items = result.get("items") or []
        leases = sorted(
            [_fmt_lease(l) for l in items],
            key=lambda l: tuple(int(o) for o in (l["ip"] or "0.0.0.0").split(".")),
        )
        # Derive subnet prefix from first item or construct from ID
        subnet_prefix = leases[0]["subnet"] if leases else None
        if not subnet_prefix:
            subnet_prefix = "100.64.36.0/22" if subnet_id == 70 else f"100.65.{subnet_id}.0/24"
        return {
            "site_id":      site_id,
            "stork_subnet_id": subnet_id,
            "subnet":       subnet_prefix,
            "count":        len(leases),
            "source":       "stork-cache",
            "leases":       leases,
        }

    def find_lease_by_mac(self, mac: str) -> dict[str, Any]:
        normalized = _normalize_mac(mac)
        result = _client.lease_search(text=normalized)
        items = result.get("items") or []
        # MAC search may return multiple (expired + active) — return all
        leases = [_fmt_lease(l) for l in items if
                  (l.get("hwAddress") or "").lower() == normalized]
        if leases:
            return {"found": True, "mac": normalized, "leases": leases}
        # Broaden: return whatever Stork found for the text
        if items:
            return {"found": True, "mac": normalized, "leases": [_fmt_lease(l) for l in items]}
        return {"found": False, "mac": normalized}

    def find_lease_by_ip(self, ip: str) -> dict[str, Any]:
        result = _client.lease_search(text=ip)
        items = result.get("items") or []
        match = [_fmt_lease(l) for l in items if l.get("ipAddress") == ip]
        if match:
            return {"found": True, "lease": match[0]}
        if items:
            return {"found": True, "lease": _fmt_lease(items[0])}
        return {"found": False, "ip": ip}

    def get_lease_summary(self) -> dict[str, Any]:
        ov = _client.get_overview()
        stats4 = ov.get("dhcp4Stats", {})
        subnets_raw = (ov.get("subnets4") or {}).get("items") or []
        rows = []
        for s in subnets_raw:
            sid = (s.get("localSubnets") or [{}])[0].get("id") or s.get("id")
            rows.append({
                "subnet_id":   sid,
                "subnet":      s.get("subnet"),
                "utilization": s.get("addrUtilization"),
                "label":       _SUBNET_LABELS.get(sid, ""),
            })
        rows.sort(key=lambda r: -(r["utilization"] or 0))
        return {
            "total_assigned": stats4.get("assignedAddresses"),
            "total_capacity": stats4.get("totalAddresses"),
            "source":         "stork-overview",
            "subnets":        rows,
        }

    def get_subnet_stats(self) -> dict[str, Any]:
        result = _client.get_subnets(limit=100)
        items = result.get("items") or []
        rows = []
        for s in items:
            sid = s.get("id")
            rows.append({
                "stork_id":    sid,
                "subnet":      s.get("subnet"),
                "utilization": s.get("addrUtilization"),
                "label":       _SUBNET_LABELS.get(sid, ""),
            })
        rows.sort(key=lambda r: -(r["utilization"] or 0))
        return {
            "total_subnets": result.get("total"),
            "source":        "stork-subnets",
            "subnets":       rows,
        }


TOOLS = [
    {
        "name": "get_server_info",
        "description": (
            "Return Kea DHCP4 and Stork monitoring status: version, uptime, "
            "assigned/total address counts, RPS, machine info."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_leases_for_site",
        "description": (
            "Return active DHCP leases for a site from Stork's lease cache. "
            "Accepts site alias (e.g. 'savoy', 'nycha') or six-digit site ID (e.g. '000007'). "
            "Returns ip, mac, subnet, state for each lease. "
            "Note: Stork cache is refreshed every 60s and may not include all active leases — "
            "use find_lease_by_mac or find_lease_by_ip for authoritative single-lease lookups."
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
        "description": (
            "Find the active DHCP lease for a MAC address. "
            "Stork queries Kea live for text searches — authoritative result. "
            "Accepts any MAC format (colons, dashes, dots, or plain hex)."
        ),
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
        "description": (
            "Find the DHCP lease for an IP address. "
            "Stork queries Kea live for text searches — authoritative result."
        ),
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
        "description": (
            "Return total assigned/capacity counts and per-subnet utilization "
            "across all 70 subnets, sourced from Stork's overview."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_subnet_stats",
        "description": (
            "Return utilization percentage for all 70 subnets, sorted by busiest first."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


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
                    "serverInfo": {"name": "kea-mcp", "version": "2.0.0"},
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = req.get("params", {})
            name   = params.get("name")
            args   = params.get("arguments", {})
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
            elif name == "get_subnet_stats":
                data = self.client.get_subnet_stats()
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
