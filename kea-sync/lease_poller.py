"""
kea-sync: lease_poller.py

Polls Kea DHCP4 REST API for active leases and syncs subscriber IPs to NetBox IPAM.

Resolution chain per lease:
  giaddr (switch mgmt IP)
    -> NetBox device with primary_ip4 = giaddr
      -> interface ETH{N}  (ether3 -> ETH3)
        -> cable -> circuit termination Z
          -> CX-Circuit
            -> IP upserted in NetBox IPAM, linked to circuit

Environment variables (all configurable):
  KEA_API_URL              default: http://172.27.28.50:8000
  NETBOX_URL               default: http://172.27.48.233:8001
  NETBOX_TOKEN             required
  POLL_INTERVAL_SECONDS    default: 60
  DRY_RUN                  default: false
"""

import os
import time
import logging
import binascii
from typing import Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

KEA_API_URL = os.environ.get("KEA_API_URL", "http://172.27.28.50:8000")
NETBOX_URL = os.environ.get("NETBOX_URL", "http://172.27.48.233:8001").rstrip("/")
NETBOX_TOKEN = os.environ.get("NETBOX_TOKEN", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

NETBOX_HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


# ── Kea API ──────────────────────────────────────────────────────────────────


def kea_get_all_leases() -> list[dict]:
    """Return all active DHCPv4 leases from Kea control agent."""
    payload = {"command": "lease4-get-all", "service": ["dhcp4"]}
    try:
        resp = requests.post(KEA_API_URL, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Kea returns a list of per-service responses
        if isinstance(data, list) and data:
            result = data[0]
            if result.get("result") == 0:
                return result.get("arguments", {}).get("leases", [])
            log.warning("Kea lease query returned result=%s: %s", result.get("result"), result.get("text"))
    except Exception as exc:  # pylint: disable=broad-except
        log.error("Failed to fetch Kea leases: %s", exc)
    return []


# ── Circuit-ID parsing ────────────────────────────────────────────────────────


def parse_circuit_id(lease: dict) -> tuple[Optional[str], Optional[str]]:
    """
    Extract (interface_name, vlan_id) from a Kea lease record.

    RouterOS 7.21+ encodes Option 82 circuit-id as ASCII: '<iface>:<vid>'
    e.g. 'ether3:20'

    Kea stores user-context or relay-agent-info in the lease. We look for:
      lease['user-context']['ISC']['relay-agent-info']['circuit-id']

    Returns (None, None) if circuit-id is not available.
    """
    try:
        relay_info = (
            lease.get("user-context", {})
            .get("ISC", {})
            .get("relay-agent-info", {})
        )
        circuit_id_hex = relay_info.get("circuit-id", "")
        if not circuit_id_hex:
            return None, None

        # Strip leading '0x' if present
        hex_str = circuit_id_hex.lstrip("0x")
        decoded = binascii.unhexlify(hex_str).decode("ascii", errors="replace")
        # Expected format: 'ether3:20'
        if ":" in decoded:
            iface, vid = decoded.split(":", 1)
            return iface.strip(), vid.strip()
    except Exception:  # pylint: disable=broad-except
        pass
    return None, None


def routeros_iface_to_netbox(iface: str) -> str:
    """Convert RouterOS interface name to NetBox ETH format: ether3 -> ETH3."""
    if iface.lower().startswith("ether"):
        num = iface[5:]
        return f"ETH{num}"
    # SFP ports: sfp-sfpplus1 -> SFP+1 etc. — extend as needed
    return iface.upper()


# ── NetBox lookups ────────────────────────────────────────────────────────────


def nb_get(path: str, params: Optional[dict] = None) -> list[dict]:
    """GET from NetBox, return results list."""
    url = f"{NETBOX_URL}/api/{path.lstrip('/')}"
    try:
        resp = requests.get(url, headers=NETBOX_HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except Exception as exc:  # pylint: disable=broad-except
        log.error("NetBox GET %s failed: %s", path, exc)
    return []


def nb_post(path: str, body: dict) -> Optional[dict]:
    """POST to NetBox, return created object or None."""
    url = f"{NETBOX_URL}/api/{path.lstrip('/')}"
    try:
        resp = requests.post(url, headers=NETBOX_HEADERS, json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # pylint: disable=broad-except
        log.error("NetBox POST %s failed: %s", path, exc)
    return None


def nb_patch(path: str, body: dict) -> Optional[dict]:
    """PATCH a NetBox object."""
    url = f"{NETBOX_URL}/api/{path.lstrip('/')}"
    try:
        resp = requests.patch(url, headers=NETBOX_HEADERS, json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # pylint: disable=broad-except
        log.error("NetBox PATCH %s failed: %s", path, exc)
    return None


def find_device_by_mgmt_ip(giaddr: str) -> Optional[dict]:
    """Find NetBox device whose primary_ip4 matches the relay giaddr."""
    results = nb_get("dcim/devices/", {"q": giaddr})
    for dev in results:
        primary = (dev.get("primary_ip4") or {}).get("address", "")
        if primary.split("/")[0] == giaddr:
            return dev
    return None


def find_interface(device_id: int, nb_iface_name: str) -> Optional[dict]:
    """Find a NetBox interface by device ID and ETH-format name."""
    results = nb_get("dcim/interfaces/", {"device_id": device_id, "name": nb_iface_name})
    return results[0] if results else None


def find_circuit_via_cable(interface_id: int) -> Optional[dict]:
    """
    Walk cable from interface to circuit termination Z, return the circuit.

    NetBox cable path: interface -> cable -> circuit termination -> circuit
    """
    # Find cable connected to this interface
    cables = nb_get("dcim/cables/", {"termination_a_id": interface_id, "termination_a_type": "dcim.interface"})
    if not cables:
        cables = nb_get("dcim/cables/", {"termination_b_id": interface_id, "termination_b_type": "dcim.interface"})
    if not cables:
        return None

    cable = cables[0]
    cable_id = cable["id"]

    # Find circuit termination on this cable (termination Z)
    terms = nb_get("circuits/circuit-terminations/", {"cable_id": cable_id})
    for term in terms:
        circuit = term.get("circuit")
        if circuit:
            cid = circuit["id"]
            full = nb_get(f"circuits/circuits/{cid}/")
            if full:
                return full[0] if isinstance(full, list) else full
    return None


def upsert_ip_for_circuit(ip_address: str, circuit: dict, lease_mac: str) -> None:
    """
    Upsert an IP address in NetBox IPAM and link it to the circuit's tenant.

    Strategy: look for existing IP record, update if found, create if not.
    The IP gets tagged with the circuit CID and tenant name for traceability.
    """
    cidr = f"{ip_address}/32"
    tenant = circuit.get("tenant") or {}
    tenant_id = tenant.get("id")
    circuit_cid = circuit.get("cid", "unknown")

    existing = nb_get("ipam/ip-addresses/", {"address": cidr})

    description = f"kea-sync | circuit={circuit_cid} | mac={lease_mac}"

    if existing:
        ip_obj = existing[0]
        ip_id = ip_obj["id"]
        log.info("Updating IP %s -> circuit %s tenant %s", cidr, circuit_cid, tenant.get("name"))
        if not DRY_RUN:
            nb_patch(f"ipam/ip-addresses/{ip_id}/", {
                "description": description,
                "tenant": tenant_id,
            })
    else:
        log.info("Creating IP %s -> circuit %s tenant %s", cidr, circuit_cid, tenant.get("name"))
        if not DRY_RUN:
            nb_post("ipam/ip-addresses/", {
                "address": cidr,
                "status": "active",
                "description": description,
                "tenant": tenant_id,
            })


# ── Main poll loop ────────────────────────────────────────────────────────────


def process_lease(lease: dict) -> None:
    """Process a single Kea lease: resolve circuit, upsert IP in NetBox."""
    ip_address = lease.get("ip-address")
    giaddr = lease.get("relay-agent-info", {}).get("giaddr") or lease.get("giaddr")
    hw_address = lease.get("hw-address", "")

    if not ip_address or not giaddr:
        return

    iface_ros, _vid = parse_circuit_id(lease)
    if not iface_ros:
        log.debug("No circuit-id for lease %s (giaddr=%s)", ip_address, giaddr)
        return

    nb_iface_name = routeros_iface_to_netbox(iface_ros)

    device = find_device_by_mgmt_ip(giaddr)
    if not device:
        log.debug("No NetBox device found for giaddr %s", giaddr)
        return

    iface = find_interface(device["id"], nb_iface_name)
    if not iface:
        log.debug("No NetBox interface %s on device %s", nb_iface_name, device.get("name"))
        return

    circuit = find_circuit_via_cable(iface["id"])
    if not circuit:
        log.debug("No circuit found via cable from %s.%s", device.get("name"), nb_iface_name)
        return

    upsert_ip_for_circuit(ip_address, circuit, hw_address)


def poll_once() -> None:
    leases = kea_get_all_leases()
    log.info("Fetched %d leases from Kea", len(leases))
    synced = 0
    for lease in leases:
        try:
            process_lease(lease)
            synced += 1
        except Exception as exc:  # pylint: disable=broad-except
            log.error("Error processing lease %s: %s", lease.get("ip-address"), exc)
    log.info("Poll complete: %d leases processed", synced)


def main() -> None:
    if not NETBOX_TOKEN:
        raise RuntimeError("NETBOX_TOKEN environment variable is required")
    if DRY_RUN:
        log.info("DRY_RUN=true — no writes will be made to NetBox")
    log.info("kea-sync starting. Kea=%s NetBox=%s interval=%ds", KEA_API_URL, NETBOX_URL, POLL_INTERVAL)
    while True:
        poll_once()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
