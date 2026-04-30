import json
import os
import socket
import time
from dataclasses import dataclass
from ipaddress import ip_interface
from types import SimpleNamespace
from typing import Any, Dict, Optional

import requests
import yaml
from flask import Flask, jsonify, request, send_from_directory
from jinja2 import Environment, FileSystemLoader, StrictUndefined

APP_ROOT = os.path.dirname(os.path.abspath(__file__))


def load_config() -> Dict[str, Any]:
    config_path = os.environ.get("TIKFIG_CONFIG", os.path.join(APP_ROOT, "config.yml"))
    if not os.path.exists(config_path):
        config_path = os.path.join(APP_ROOT, "config.example.yml")
    with open(config_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


CONFIG = load_config()


@dataclass
class IPInfo:
    address: str
    network: str
    network_octets: list

    @classmethod
    def from_address(cls, address: str) -> "IPInfo":
        iface = ip_interface(address)
        network = str(iface.network)
        octets = [int(part) for part in str(iface.network.network_address).split(".")]
        return cls(address=address, network=network, network_octets=octets)


@dataclass
class CgnatInfo:
    prefix: Optional[str] = None
    gateway_ip: Optional[str] = None


class Device:
    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data
        self.name = data.get("name")
        device_type = data.get("device_type") or {}
        self.device_type = SimpleNamespace(model=device_type.get("model"))
        self.primary_ip4 = self._ip_from_field(data.get("primary_ip4"))
        self.wan_ip = self._ip_from_custom("wan_ip")
        self.cgnat = CgnatInfo(
            prefix=self._custom_field("cgnat_prefix"),
            gateway_ip=self._custom_field("cgnat_gateway"),
        )

    def get_config_context(self) -> Dict[str, Any]:
        return self._data.get("config_context") or {}

    def _custom_field(self, field: str) -> Optional[str]:
        custom_fields = self._data.get("custom_fields") or {}
        value = custom_fields.get(field)
        if isinstance(value, dict):
            return value.get("value")
        return value

    def _ip_from_custom(self, field: str) -> Optional[IPInfo]:
        value = self._custom_field(field)
        if not value:
            return None
        return IPInfo.from_address(value)

    def _ip_from_field(self, field_value: Optional[Dict[str, Any]]) -> Optional[IPInfo]:
        if not field_value:
            return None
        address = field_value.get("address")
        if not address:
            return None
        return IPInfo.from_address(address)


jinja_env = Environment(
    loader=FileSystemLoader(APP_ROOT),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)

app = Flask(__name__, static_folder="web", static_url_path="")


@app.route("/")
def index() -> Any:
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/config")
def api_config() -> Any:
    netbox = CONFIG.get("netbox", {})
    mikrotik = CONFIG.get("mikrotik", {})
    return jsonify(
        {
            "netbox_configured": bool(netbox.get("url") and netbox.get("token")),
            "default_device_ip": mikrotik.get("default_ip", "192.168.88.1"),
            "api_port": mikrotik.get("api_port", 8728),
        }
    )


@app.route("/api/discovery")
def api_discovery() -> Any:
    mikrotik = CONFIG.get("mikrotik", {})
    ip = mikrotik.get("default_ip", "192.168.88.1")
    port = int(mikrotik.get("api_port", 8728))
    start = time.time()
    status = "offline"
    try:
        with socket.create_connection((ip, port), timeout=1.0):
            status = "online"
    except OSError:
        status = "offline"
    latency_ms = int((time.time() - start) * 1000)
    return jsonify({"status": status, "ip": ip, "port": port, "latency_ms": latency_ms})


@app.route("/api/netbox/device")
def api_netbox_device() -> Any:
    name = request.args.get("name")
    if not name:
        return jsonify({"error": "name parameter is required"}), 400

    netbox = CONFIG.get("netbox", {})
    if not netbox.get("url") or not netbox.get("token"):
        return jsonify({"error": "NetBox is not configured"}), 400

    url = f"{netbox['url'].rstrip('/')}/api/dcim/devices/"
    headers = {"Authorization": f"Token {netbox['token']}", "Accept": "application/json"}
    try:
        response = requests.get(
            url,
            headers=headers,
            params={"name": name},
            timeout=5,
            verify=netbox.get("verify_tls", True),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"error": f"NetBox request failed: {exc}"}), 502

    data = response.json()
    results = data.get("results") or []
    if not results:
        return jsonify({"error": "Device not found"}), 404

    device = results[0]
    return jsonify(
        {
            "device": {
                "name": device.get("name"),
                "model": (device.get("device_type") or {}).get("model"),
                "primary_ip4": (device.get("primary_ip4") or {}).get("address"),
                "site": (device.get("site") or {}).get("name"),
            },
            "raw": device,
        }
    )


@app.route("/api/render", methods=["POST"])
def api_render() -> Any:
    payload = request.get_json(silent=True) or {}
    device_name = payload.get("device_name")
    template_key = payload.get("template")
    overrides = payload.get("overrides") or {}

    if not device_name:
        return jsonify({"error": "device_name is required"}), 400
    if template_key not in ("switch", "router"):
        return jsonify({"error": "template must be switch or router"}), 400

    device_data = fetch_netbox_device(device_name)
    if "error" in device_data:
        return jsonify(device_data), 400

    try:
        context = build_template_context(device_data, template_key, overrides)
        template_path = CONFIG.get("templates", {}).get(template_key)
        if not template_path:
            return jsonify({"error": f"Missing template path for {template_key}"}), 500
        template = jinja_env.get_template(template_path)
        rendered = template.render(**context)
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"error": f"Template render failed: {exc}"}), 500

    return jsonify({"rendered": rendered})


@app.route("/<path:filename>")
def static_files(filename: str) -> Any:
    return send_from_directory(app.static_folder, filename)


def fetch_netbox_device(name: str) -> Dict[str, Any]:
    netbox = CONFIG.get("netbox", {})
    if not netbox.get("url") or not netbox.get("token"):
        return {"error": "NetBox is not configured"}

    url = f"{netbox['url'].rstrip('/')}/api/dcim/devices/"
    headers = {"Authorization": f"Token {netbox['token']}", "Accept": "application/json"}
    try:
        response = requests.get(
            url,
            headers=headers,
            params={"name": name},
            timeout=5,
            verify=netbox.get("verify_tls", True),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"error": f"NetBox request failed: {exc}"}

    data = response.json()
    results = data.get("results") or []
    if not results:
        return {"error": "Device not found"}

    return results[0]


def build_template_context(
    device_data: Dict[str, Any], template_key: str, overrides: Dict[str, Any]
) -> Dict[str, Any]:
    device = Device(device_data)
    context = device.get_config_context()

    model_override = overrides.get("model")
    model = model_override or device.device_type.model
    model_interfaces = None

    if template_key == "switch":
        model_interfaces = (
            context.get("mikrotik", {})
            .get("switch", {})
            .get("model_interfaces", {})
            .get(model)
        )
        if not model_interfaces:
            model_interfaces = (CONFIG.get("model_interfaces") or {}).get(model)

    if template_key == "router":
        router_interfaces = (
            context.get("mikrotik", {})
            .get("router", {})
            .get("model_interfaces")
        )
        if not router_interfaces and CONFIG.get("model_interfaces"):
            context.setdefault("mikrotik", {}).setdefault("router", {})[
                "model_interfaces"
            ] = CONFIG.get("model_interfaces")

    return {
        "device": device,
        "model_interfaces": model_interfaces,
        "cgnat_prefix_str": overrides.get("cgnat_prefix_str"),
        "cgnat_gateway": overrides.get("cgnat_gateway"),
        "digi_prefix_str": overrides.get("digi_prefix_str"),
        "digi_gateway": overrides.get("digi_gateway"),
        "digi_prefix_length": overrides.get("digi_prefix_length"),
        "ctx": context,
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=True)
