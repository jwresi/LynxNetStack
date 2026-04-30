from __future__ import annotations

import os
from pathlib import Path

import pytest
from mcp.jake_ops_mcp import JakeOps
from mcp import jake_ops_mcp as opsmod


@pytest.fixture(autouse=True)
def _clear_lru_caches():
    """WHY: lru_cache on load_nycha_info_rows/load_tauc_nycha_audit_rows leaks
    between tests when the full suite runs.

    Two failure modes:
    1. A prior test calls JakeOps() with the production path, filling the cache
       before these isolated tests run.
    2. test_audit_fixture_validation sets opsmod.NYCHA_INFO_CSV to the (empty)
       fixture path and does not restore it, so subsequent tests see an empty CSV
       instead of None/production.

    Fix: save and restore both the cache AND the module-level path attribute.
    """
    # WHY: _current_nycha_info_csv() reads os.environ["JAKE_NYCHA_INFO_CSV"] first,
    # ignoring opsmod.NYCHA_INFO_CSV when the env var is set. Tests that only set
    # opsmod.NYCHA_INFO_CSV see production data when the env var is present.
    # Solution: temporarily remove the env var so the function reads opsmod.NYCHA_INFO_CSV.
    saved_csv      = opsmod.NYCHA_INFO_CSV
    saved_tauc     = opsmod.TAUC_NYCHA_AUDIT_CSV
    saved_env_csv  = os.environ.pop("JAKE_NYCHA_INFO_CSV", None)
    saved_env_tauc = os.environ.pop("JAKE_TAUC_AUDIT_CSV", None)
    opsmod.load_nycha_info_rows.cache_clear()
    opsmod.load_tauc_nycha_audit_rows.cache_clear()
    yield
    opsmod.NYCHA_INFO_CSV       = saved_csv
    opsmod.TAUC_NYCHA_AUDIT_CSV = saved_tauc
    if saved_env_csv is not None:
        os.environ["JAKE_NYCHA_INFO_CSV"] = saved_env_csv
    elif "JAKE_NYCHA_INFO_CSV" in os.environ:
        del os.environ["JAKE_NYCHA_INFO_CSV"]
    if saved_env_tauc is not None:
        os.environ["JAKE_TAUC_AUDIT_CSV"] = saved_env_tauc
    elif "JAKE_TAUC_AUDIT_CSV" in os.environ:
        del os.environ["JAKE_TAUC_AUDIT_CSV"]
    opsmod.load_nycha_info_rows.cache_clear()
    opsmod.load_tauc_nycha_audit_rows.cache_clear()


def _ops() -> JakeOps:
    return JakeOps.__new__(JakeOps)


def test_parse_port_physical_state_outputs() -> None:
    monitor = """
                name: ether7
              status: link-ok
                rate: 100Mbps
         full-duplex: yes
  link-partner-advertising: 1000M-full
           auto-negotiation: done
    """
    stats = """
                name: ether7
           rx-errors: 3
           tx-errors: 1
          fcs-errors: 4
          crc-errors: 5
          link-downs: 2
    """

    parsed = JakeOps._parse_port_physical_state_outputs(monitor, stats)

    assert parsed["port_speed"] == "100M"
    assert parsed["link_partner_speed"] == "1G"
    assert parsed["port_duplex"] == "full"
    assert parsed["link_partner_duplex"] == "full"
    assert parsed["rx_errors"] == 3
    assert parsed["tx_errors"] == 1
    assert parsed["fcs_errors"] == 4
    assert parsed["crc_errors"] == 5
    assert parsed["link_flaps"] == 2
    assert parsed["port_up"] is True


def test_parse_port_physical_state_outputs_with_alternate_routeros_keys() -> None:
    monitor = """
                name: ether8
              status: running
               speed: 1Gbps
              duplex: full
  link-partner-speed: 100Mbps
 link-partner-duplex: half
    """
    stats = """
                name: ether8
        rx-fcs-error: 7
         link-flaps: 3
    """

    parsed = JakeOps._parse_port_physical_state_outputs(monitor, stats)

    assert parsed["port_speed"] == "1G"
    assert parsed["link_partner_speed"] == "100M"
    assert parsed["port_duplex"] == "full"
    assert parsed["link_partner_duplex"] == "half"
    assert parsed["crc_errors"] == 7
    assert parsed["link_flaps"] == 3
    assert parsed["port_up"] is True


def test_get_port_physical_state_handles_missing_data() -> None:
    ops = _ops()
    ops._resolve_live_routeros_api_target = lambda site_id=None, device_name=None: {"device_name": "000007.R1", "configured": True, "site_id": "000007"}
    ops._run_live_routeros_show_command = lambda *args, **kwargs: {"available": True, "results": [{"stdout": ""}]}

    result = ops.get_port_physical_state("ether7")

    assert result["available"] is True
    assert result["port_speed"] is None
    assert result["rx_errors"] is None
    assert result["port_up"] is None


def test_infer_pppoe_failure_reason() -> None:
    assert JakeOps._infer_pppoe_failure_reason("pppoe,info authentication failed for subscriber") == "auth_failed"
    assert JakeOps._infer_pppoe_failure_reason("pppoe timeout waiting for PADO") == "timeout"
    assert JakeOps._infer_pppoe_failure_reason("pppoe no response from server") == "no_response"
    assert JakeOps._infer_pppoe_failure_reason("pppoe waiting for PADS") == "timeout"
    assert JakeOps._infer_pppoe_failure_reason("pppoe no PADO received") == "no_response"
    assert JakeOps._infer_pppoe_failure_reason("routine connect") is None


def test_get_pppoe_diagnostics_parses_failures() -> None:
    ops = _ops()
    ops._resolve_unit_row = lambda unit: {"PPPoE": "site-1A", "Address": "123-125 Test St"}
    ops._resolve_building_from_address = lambda address: {"best_match": {"site_code": "000007", "prefix": "000007.001"}}
    ops._loki_base_url = lambda: "http://loki"
    ops._loki_query_range = lambda *args, **kwargs: (
        True,
        [{"stream": {"hostname": "000007.R1"}, "values": [["1713869100000000000", "pppoe,warning site-1A authentication failed"]]}],
        "",
    )
    ops._loki_normalize_entries = JakeOps._loki_normalize_entries.__get__(ops, JakeOps)
    ops.db = type("DB", (), {"execute": lambda self, *args, **kwargs: type("Cur", (), {"fetchall": lambda self: []})()})()

    result = ops.get_pppoe_diagnostics("1A")

    assert result["available"] is True
    assert result["pppoe_active"] is False
    assert result["pppoe_failed_attempts_seen"] is True
    assert result["pppoe_failure_reason"] == "auth_failed"
    assert result["pppoe_last_attempt_timestamp"]


def test_get_pppoe_diagnostics_distinguishes_known_no_failure_attempts() -> None:
    ops = _ops()
    ops._resolve_unit_row = lambda unit: {"PPPoE": "site-1A", "Address": "123-125 Test St"}
    ops._resolve_building_from_address = lambda address: {"best_match": {"site_code": "000007", "prefix": "000007.001"}}
    ops._loki_base_url = lambda: "http://loki"
    ops._loki_query_range = lambda *args, **kwargs: (
        True,
        [{"stream": {"hostname": "000007.R1"}, "values": [["1713869100000000000", "pppoe,info site-1A session starting"]]}],
        "",
    )
    ops._loki_normalize_entries = JakeOps._loki_normalize_entries.__get__(ops, JakeOps)
    ops.db = type("DB", (), {"execute": lambda self, *args, **kwargs: type("Cur", (), {"fetchall": lambda self: []})()})()

    result = ops.get_pppoe_diagnostics("1A")

    assert result["available"] is True
    assert result["pppoe_failed_attempts_seen"] is False
    assert result["pppoe_failure_reason"] is None
    assert result["pppoe_last_attempt_timestamp"]


def test_get_pppoe_diagnostics_marks_no_matching_attempts_as_known_negative_evidence() -> None:
    ops = _ops()
    ops._resolve_unit_row = lambda unit: {"PPPoE": "site-1A", "Address": "123-125 Test St"}
    ops._resolve_building_from_address = lambda address: {"best_match": {"site_code": "000007", "prefix": "000007.001"}}
    ops._loki_base_url = lambda: "http://loki"
    ops._loki_query_range = lambda *args, **kwargs: (True, [], "")
    ops._loki_normalize_entries = JakeOps._loki_normalize_entries.__get__(ops, JakeOps)
    ops.db = type("DB", (), {"execute": lambda self, *args, **kwargs: type("Cur", (), {"fetchall": lambda self: []})()})()

    result = ops.get_pppoe_diagnostics("1A")

    assert result["available"] is True
    assert result["pppoe_failed_attempts_seen"] is False
    assert result["pppoe_failure_reason"] is None
    assert result["pppoe_last_attempt_timestamp"] is None


def test_get_dhcp_behavior_combines_sources() -> None:
    ops = _ops()
    ops._resolve_unit_row = lambda unit: {"MAC Address": "aa:11:22:33:44:55", "Address": "123-125 Test St"}
    ops._resolve_building_from_address = lambda address: {"best_match": {"site_code": "000007", "prefix": "000007.001"}}
    ops.get_live_dhcp_lease_summary = lambda **kwargs: {
        "available": True,
        "lease_count": 1,
        "leases": [{"server": "10.0.0.1"}],
    }
    ops.get_live_rogue_dhcp_scan = lambda **kwargs: {
        "available": True,
        "offer_like_packet_count": 1,
        "sample": [{"line": "dhcp offer src-address=10.0.0.254"}],
    }
    ops._auto_correlate_dhcp_logs = lambda mac, site_id, window_minutes=60: {"found": True, "request_count": 2}
    ops._loki_base_url = lambda: "http://loki"

    result = ops.get_dhcp_behavior("1A", site_id="000007", device_name="000007.R1", interface="ether7")

    assert result["available"] is True
    assert result["dhcp_discovers_seen"] == 2
    assert result["dhcp_offers_seen"] == 1
    assert result["dhcp_offer_source"] == "10.0.0.254"
    assert result["dhcp_expected_server"] == "10.0.0.1"
    assert result["rogue_dhcp_detected"] is True


def test_get_dhcp_behavior_missing_data_is_conservative() -> None:
    ops = _ops()
    ops._resolve_unit_row = lambda unit: None
    ops.get_live_dhcp_lease_summary = lambda **kwargs: {"available": False}
    ops.get_live_rogue_dhcp_scan = lambda **kwargs: {"available": False}
    ops._auto_correlate_dhcp_logs = lambda *args, **kwargs: {"found": False, "request_count": 0}
    ops._loki_base_url = lambda: ""

    result = ops.get_dhcp_behavior("1A")

    assert result["available"] is False
    assert result["dhcp_expected"] is None
    assert result["rogue_dhcp_detected"] is False


def test_get_interface_state_delegates_to_port_physical_state() -> None:
    ops = _ops()
    ops.get_port_physical_state = lambda interface, site_id=None, device_name=None: {
        "available": True,
        "interface": interface,
        "site_id": site_id,
        "device_name": device_name,
    }

    result = ops.get_interface_state("ether7", site_id="000007", device_name="000007.001.SW01")

    assert result["available"] is True
    assert result["interface"] == "ether7"
    assert result["site_id"] == "000007"
    assert result["device_name"] == "000007.001.SW01"
    assert result["source"] == "routeros_ssh"


def test_get_interface_state_falls_back_to_cached_db_row() -> None:
    ops = _ops()
    ops.latest_scan_id = lambda: 91
    ops.get_port_physical_state = lambda interface, site_id=None, device_name=None: {
        "available": False,
        "configured": False,
        "error": "ssh_mcp repo is not present on this host",
        "site_id": site_id,
        "device_name": device_name,
    }
    ops._get_interface_state_via_api = lambda interface, site_id=None, device_name=None: {
        "available": False,
        "configured": False,
        "error": "librouteros import failed",
        "site_id": site_id,
        "device_name": device_name,
    }
    ops._resolve_live_routeros_api_target = lambda site_id=None, device_name=None: {
        "available": True,
        "configured": True,
        "site_id": site_id,
        "device_name": device_name,
        "target_ip": "192.168.44.54",
    }

    class _Cur:
        def fetchone(self):
            return {
                "identity": "000007.004.SW01",
                "name": "ether7",
                "running": 1,
                "disabled": 0,
                "rx_byte": 10,
                "tx_byte": 20,
                "rx_packet": 1,
                "tx_packet": 2,
                "last_link_up_time": "2026-03-14 08:57:38",
            }

    class _DB:
        def execute(self, query, params):
            return _Cur()

    ops.db = _DB()

    result = ops.get_interface_state("ether7", site_id="000007", device_name="000007.004.SW01")

    assert result["available"] is True
    assert result["source"] == "db_cached_interface_state"
    assert result["port_up"] is True
    assert result["fallback_from"]["ssh"] == "ssh_mcp repo is not present on this host"
    assert result["fallback_from"]["api"] == "librouteros import failed"


def test_get_interface_state_returns_explicit_failure_when_all_sources_fail() -> None:
    ops = _ops()
    ops.get_port_physical_state = lambda interface, site_id=None, device_name=None: {
        "available": False,
        "configured": False,
        "error": "ssh failed",
        "site_id": site_id,
        "device_name": device_name,
    }
    ops._get_interface_state_via_api = lambda interface, site_id=None, device_name=None: {
        "available": False,
        "configured": False,
        "error": "api failed",
        "site_id": site_id,
        "device_name": device_name,
    }
    ops._get_cached_interface_state = lambda interface, site_id=None, device_name=None: {
        "available": False,
        "configured": True,
        "error": "db missing",
        "site_id": site_id,
        "device_name": device_name,
    }

    result = ops.get_interface_state("ether7", site_id="000007", device_name="000007.004.SW01")

    assert result["available"] is False
    assert "ssh failed" in result["error"]
    assert "api failed" in result["error"]
    assert "db missing" in result["error"]
    assert result["sources_tried"] == ["routeros_ssh", "routeros_api", "db_cached_interface_state"]


def test_get_pppoe_logs_for_site_distinguishes_failed_no_attempt_and_active() -> None:
    ops = _ops()
    ops.latest_scan_id = lambda: 1
    ops._loki_base_url = lambda: "http://loki"
    ops._loki_query_range = lambda *args, **kwargs: (
        True,
        [
            {
                "stream": {"hostname": "000007.R1"},
                "values": [
                    ["1713869100000000000", "pppoe,warning site-1A authentication failed"],
                    ["1713869200000000000", "pppoe,info site-1B session starting"],
                ],
            }
        ],
        "",
    )
    ops._loki_normalize_entries = JakeOps._loki_normalize_entries.__get__(ops, JakeOps)

    class _Cur:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _DB:
        def execute(self, query, params):
            if "from router_ppp_active" in query:
                return _Cur([{"name": "site-1C", "caller_id": "aa:11:22:33:44:55", "address": "10.0.0.9", "uptime": "1h"}])
            return _Cur([])

    ops.db = _DB()
    ops._resolve_building_from_address = lambda address: {"best_match": {"site_code": "000007", "prefix": "000007.001"}}

    original_loader = opsmod.load_nycha_info_rows
    opsmod.load_nycha_info_rows = lambda: [
        {"Address": "123-125 Test St", "Unit": "1A", "PPPoE": "site-1A"},
        {"Address": "123-125 Test St", "Unit": "1B", "PPPoE": "site-1B"},
        {"Address": "123-125 Test St", "Unit": "1C", "PPPoE": "site-1C"},
    ]
    try:
        result = ops.get_pppoe_logs_for_site("000007")
    finally:
        opsmod.load_nycha_info_rows = original_loader

    assert result["available"] is True
    assert result["searched"] is True
    assert result["observations_by_name"]["site-1a"]["pppoe_failed_attempts_seen"] is True
    assert result["observations_by_name"]["site-1a"]["pppoe_failure_reason"] == "auth_failed"
    assert result["observations_by_name"]["site-1b"]["pppoe_failed_attempts_seen"] is False
    assert result["observations_by_name"]["site-1c"]["pppoe_active"] is True


def test_get_historical_mac_locations_marks_lookup_checked() -> None:
    ops = _ops()

    class _Cur:
        def fetchall(self):
            return [
                {
                    "scan_id": 123,
                    "identity": "000007.001.SW01",
                    "on_interface": "ether7",
                    "vid": 20,
                    "mac": "aa:11:22:33:44:55",
                }
            ]

    class _DB:
        def execute(self, query, params):
            return _Cur()

    ops.db = _DB()

    result = ops.get_historical_mac_locations("aa:11:22:33:44:55", building_id="000007.001")

    assert result["checked"] is True
    assert result["available"] is True
    assert result["locations"][0]["switch"] == "000007.001.SW01"
    assert result["locations"][0]["port"] == "ether7"


def test_load_nycha_info_rows_supports_simple_header_csv(tmp_path) -> None:
    csv_path = tmp_path / "nycha_unit_mac_map.csv"
    csv_path.write_text(
        "Address,Unit,MAC Address\n"
        "955 Rutland Rd,1 - 01G,30:68:93:c1:9b:ee\n",
        encoding="utf-8",
    )

    original = opsmod.NYCHA_INFO_CSV
    try:
        opsmod.NYCHA_INFO_CSV = Path(str(csv_path))
        opsmod.load_nycha_info_rows.cache_clear()
        rows = opsmod.load_nycha_info_rows()
    finally:
        opsmod.NYCHA_INFO_CSV = original
        opsmod.load_nycha_info_rows.cache_clear()

    assert rows == [{"Address": "955 Rutland Rd", "Unit": "1 - 01G", "MAC Address": "30:68:93:c1:9b:ee"}]


def test_load_nycha_info_rows_supports_legacy_offset_csv(tmp_path) -> None:
    csv_path = tmp_path / "legacy_nycha_info.csv"
    prefix = "\n" * 12
    body = (
        "Address,Unit,MAC Address,PPPoE\n"
        "955 Rutland Rd,1 - 01G,30:68:93:c1:9b:ee,NYCHA955RutlandUnit1G\n"
    )
    csv_path.write_text(prefix + body, encoding="utf-8")

    original = opsmod.NYCHA_INFO_CSV
    try:
        opsmod.NYCHA_INFO_CSV = Path(str(csv_path))
        opsmod.load_nycha_info_rows.cache_clear()
        rows = opsmod.load_nycha_info_rows()
    finally:
        opsmod.NYCHA_INFO_CSV = original
        opsmod.load_nycha_info_rows.cache_clear()

    assert rows == [
        {
            "Address": "955 Rutland Rd",
            "Unit": "1 - 01G",
            "MAC Address": "30:68:93:c1:9b:ee",
            "PPPoE": "NYCHA955RutlandUnit1G",
        }
    ]


def test_load_nycha_info_rows_uses_current_env_path(tmp_path, monkeypatch) -> None:
    csv_path = tmp_path / "env_nycha_info.csv"
    csv_path.write_text(
        "Address,Unit,MAC Address,PPPoE\n"
        "1145 Lenox Rd,2A,aa:11:22:33:44:55,NYCHA1145LenoxRd2A\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("JAKE_NYCHA_INFO_CSV", str(csv_path))
    opsmod.load_nycha_info_rows.cache_clear()
    rows = opsmod.load_nycha_info_rows()
    opsmod.load_nycha_info_rows.cache_clear()

    assert rows == [
        {
            "Address": "1145 Lenox Rd",
            "Unit": "2A",
            "MAC Address": "aa:11:22:33:44:55",
            "PPPoE": "NYCHA1145LenoxRd2A",
        }
    ]


def test_load_tauc_nycha_audit_rows_uses_current_env_path(tmp_path, monkeypatch) -> None:
    csv_path = tmp_path / "env_tauc_audit.csv"
    csv_path.write_text(
        "networkName,tauc_mac,expected_unit\n"
        "NYCHA1145LenoxRd2A,aa:11:22:33:44:55,2A\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("JAKE_TAUC_AUDIT_CSV", str(csv_path))
    opsmod.load_tauc_nycha_audit_rows.cache_clear()
    rows = opsmod.load_tauc_nycha_audit_rows()
    opsmod.load_tauc_nycha_audit_rows.cache_clear()

    assert rows == [
        {
            "networkName": "NYCHA1145LenoxRd2A",
            "tauc_mac": "aa:11:22:33:44:55",
            "expected_unit": "2A",
        }
    ]
