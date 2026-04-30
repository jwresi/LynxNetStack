import json
import types
import builtins
import pathlib
import time

import pytest


@pytest.fixture()
def app(monkeypatch, tmp_path):
    # Import the server module and override paths that hit the filesystem/network.
    from backend import server

    # Point CONFIG_DIR to a temp dir to avoid writing under /app
    monkeypatch.setattr(server, "CONFIG_DIR", str(tmp_path), raising=True)
    pathlib.Path(server.CONFIG_DIR).mkdir(parents=True, exist_ok=True)

    return server.app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_status_ok(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "connected"
    assert "interface" in data and "netinstallVersion" in data


def test_discover_stubbed(monkeypatch, client):
    from backend import server

    def _stub_discover():
        return [
            {
                "mac": "00:0c:42:aa:bb:cc",
                "ip": "192.168.44.10",
                "identity": None,
                "model": None,
                "configured": False,
                "static_ip": True,
            }
        ]

    monkeypatch.setattr(server, "discover_mikrotik_devices", _stub_discover, raising=True)

    resp = client.get("/api/discover")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    assert data["devices"][0]["mac"].startswith("00:0c:42")


def test_upload_config_and_list(client, tmp_path, monkeypatch):
    from backend import server

    # Ensure CONFIG_DIR points to temp (fixture may already set it, but safe to enforce)
    monkeypatch.setattr(server, "CONFIG_DIR", str(tmp_path), raising=True)

    payload = {
        "mac": "aabbccddeeff",
        "hostname": "test-device",
        "config": "/system identity set name=\"test-device\"",
    }
    resp = client.post("/api/config/upload", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["configFile"] == "test-device.rsc"

    # List configs should include the uploaded file
    resp2 = client.get("/api/configs")
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert "test-device.rsc" in data2.get("configs", [])


def test_provision_start_success(monkeypatch, client):
    from backend import server

    # Stub out heavy provisioning behavior to avoid threads/network
    def _stub_provision(mac: str, ip: str, hostname: str, config_file: str) -> bool:
        mac_clean = mac.lower().replace(":", "").replace("-", "")
        server.provision_status[mac_clean] = {
            "status": "detecting",
            "progress": 10,
            "message": f"Detecting device on network at {ip}...",
            "started": time.time(),
            "static_ip": ip,
        }
        return True

    monkeypatch.setattr(server.netinstall, "provision_device", _stub_provision, raising=True)

    payload = {
        "mac": "aa:bb:cc:dd:ee:ff",
        "ip": "192.168.44.123",
        "hostname": "test-device",
        "configFile": "test-device.rsc",
    }
    resp = client.post("/api/provision", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["static_ip"] == "192.168.44.123"


def test_provision_invalid_ip_returns_400(client):
    payload = {
        "mac": "aa:bb:cc:dd:ee:ff",
        "ip": "not_an_ip",
        "hostname": "test-device",
        "configFile": "test-device.rsc",
    }
    resp = client.post("/api/provision", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "Invalid IP" in data.get("error", "")


def test_preflight_and_interface_health(client, monkeypatch):
    # Force known interface for health
    from backend import server
    monkeypatch.setattr(server, "INTERFACE", "eth0", raising=True)

    r1 = client.get("/api/preflight")
    assert r1.status_code == 200
    data1 = r1.get_json()
    assert isinstance(data1.get("checks"), list)

    r2 = client.get("/api/interface/health?name=eth0")
    assert r2.status_code == 200
    data2 = r2.get_json()
    assert data2.get("name") == "eth0"
