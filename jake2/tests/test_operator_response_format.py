from __future__ import annotations

from core.query_core import format_operator_response


FILLER_PHRASES = (
    "it appears that",
    "based on the current evidence",
)


def _assert_section_order(text: str, labels: list[str]) -> None:
    positions = []
    for label in labels:
        pos = text.find(label)
        assert pos != -1, f"missing section {label!r} in:\n{text}"
        positions.append(pos)
    assert positions == sorted(positions), f"sections out of order in:\n{text}"


def _assert_readability(text: str) -> None:
    for line in text.splitlines():
        assert len(line) <= 140, f"line too long ({len(line)}): {line}"
    blank_run = 0
    nonblank_run = 0
    for line in text.splitlines():
        if not line.strip():
            blank_run += 1
            nonblank_run = 0
            continue
        blank_run = 0
        nonblank_run += 1
        assert nonblank_run <= 6, f"section too long without break near: {line}"
    lowered = text.lower()
    for phrase in FILLER_PHRASES:
        assert phrase not in lowered


def test_building_summary_leads_with_building_truth_not_scan_stats() -> None:
    text = format_operator_response(
        "get_building_health",
        {
            "building_id": "000007.030",
            "device_count": 1,
            "probable_cpe_count": 8,
            "outlier_count": 0,
            "active_alerts": [],
            "scan": {
                "subnet": "192.168.44.0/24",
                "api_reachable": 62,
                "hosts_tested": 254,
                "started_at": "2026-03-14T16:13:44Z",
            },
        },
        "how is 000007.030?",
    )
    lines = text.splitlines()
    assert lines[0] == "Building 000007.030:"
    assert lines[1] == "- 1 switch detected"
    assert lines[2] == "- 8 probable subscriber devices (CPEs)"
    _assert_section_order(text, ["Operator view:", "Evidence:", "Context:", "Next checks:"])
    _assert_readability(text)


def test_scan_context_is_clearly_labeled_and_separated() -> None:
    text = format_operator_response(
        "get_building_health",
        {
            "building_id": "000007.030",
            "device_count": 1,
            "probable_cpe_count": 8,
            "outlier_count": 0,
            "active_alerts": [],
            "scan": {
                "subnet": "192.168.44.0/24",
                "api_reachable": 62,
                "hosts_tested": 254,
                "started_at": "2026-03-14T16:13:44Z",
            },
        },
        "how is 000007.030?",
    )
    assert "Context:" in text
    assert "- subnet: 192.168.44.0/24" in text
    assert "- API reachability: 62 / 254 IPs responding via API" in text
    assert "- this reachability is subnet-wide context, not a building device count" in text


def test_building_summary_avoids_ambiguous_host_language() -> None:
    text = format_operator_response(
        "get_building_health",
        {
            "building_id": "000007.030",
            "device_count": 1,
            "probable_cpe_count": 8,
            "outlier_count": 0,
            "active_alerts": [],
            "scan": {
                "subnet": "192.168.44.0/24",
                "api_reachable": 62,
                "hosts_tested": 254,
                "started_at": "2026-03-14T16:13:44Z",
            },
        },
        "how is 000007.030?",
    )
    lowered = text.lower()
    assert "reachable hosts" not in lowered
    assert "tested hosts" not in lowered
    assert " 62 of 254 " not in lowered


def test_building_summary_does_not_suggest_unsupported_actions() -> None:
    text = format_operator_response(
        "get_building_health",
        {
            "building_id": "000007.030",
            "device_count": 1,
            "probable_cpe_count": 8,
            "outlier_count": 0,
            "active_alerts": [],
            "scan": {
                "subnet": "192.168.44.0/24",
                "api_reachable": 62,
                "hosts_tested": 254,
                "started_at": "2026-03-14T16:13:44Z",
            },
        },
        "how is 000007.030?",
    )
    lowered = text.lower()
    assert "rerun the scan" not in lowered
    assert "should i rerun" not in lowered
    assert "Next checks:" in text


def test_building_summary_adds_operator_first_health_judgment() -> None:
    text = format_operator_response(
        "get_building_health",
        {
            "building_id": "000007.030",
            "device_count": 1,
            "probable_cpe_count": 8,
            "outlier_count": 0,
            "active_alerts": [],
            "scan": {
                "subnet": "192.168.44.0/24",
                "api_reachable": 62,
                "hosts_tested": 254,
                "started_at": "2026-03-14T16:13:44Z",
            },
        },
        "how is 000007.030?",
    )
    assert "Operator view:" in text
    assert "No building-specific issue is visible in the available building data." in text
    assert "historical visibility, not live proof that the building is healthy" in text
    assert "subnet visibility limit than a building outage" in text


def test_zero_visibility_building_uses_visibility_warning_wording() -> None:
    text = format_operator_response(
        "get_building_health",
        {
            "building_id": "000007.040",
            "device_count": 0,
            "probable_cpe_count": 0,
            "outlier_count": 0,
            "active_alerts": [],
            "scan": {
                "subnet": "192.168.44.0/24",
                "api_reachable": 62,
                "hosts_tested": 254,
                "started_at": "2026-03-14T16:13:44Z",
            },
        },
        "how is 225 buffalo?",
    )
    assert "- no alerts or anomalies tied to this building" in text
    assert "- no switch/CPE telemetry visible" in text
    assert "No switch or CPE telemetry is visible for this building in the latest scan." in text
    assert "This does not prove the building is healthy" in text
    assert "- scan freshness: stale (" in text
    _assert_section_order(text, ["Operator view:", "Evidence:", "Context:", "Next checks:"])
    _assert_readability(text)


def test_zero_visibility_building_does_not_read_as_healthy() -> None:
    text = format_operator_response(
        "get_building_health",
        {
            "building_id": "000007.040",
            "device_count": 0,
            "probable_cpe_count": 0,
            "outlier_count": 0,
            "active_alerts": [],
            "scan": {
                "subnet": "192.168.44.0/24",
                "api_reachable": 62,
                "hosts_tested": 254,
                "started_at": "2026-03-14T16:13:44Z",
            },
        },
        "how is 225 buffalo?",
    )
    assert "This building appears operational." not in text
    assert "Nothing in the current building-level evidence suggests an active problem." not in text
    assert "possible causes: missing building-prefix mapping, unreachable switch, no installed equipment, or no DB evidence yet" in text


def test_zero_visibility_building_uses_visibility_specific_next_checks() -> None:
    text = format_operator_response(
        "get_building_health",
        {
            "building_id": "000007.040",
            "device_count": 0,
            "probable_cpe_count": 0,
            "outlier_count": 0,
            "active_alerts": [],
            "scan": {
                "subnet": "192.168.44.0/24",
                "api_reachable": 62,
                "hosts_tested": 254,
                "started_at": "2026-03-14T16:13:44Z",
            },
        },
        "how is 225 buffalo?",
    )
    assert "- verify the building prefix mapping for 000007.040" in text
    assert "- check latest scan coverage for site 000007" in text
    assert "- search MAC and bridge evidence for 000007.040" in text
    assert "- check whether expected switches exist in inventory for 000007.040" in text
    assert "rogue dhcp suspects" not in text.lower()
    assert "ports are flapping" not in text.lower()
    assert "recovery-ready cpes" not in text.lower()


def test_nonzero_building_keeps_normal_healthy_wording() -> None:
    text = format_operator_response(
        "get_building_health",
        {
            "building_id": "000007.030",
            "device_count": 1,
            "probable_cpe_count": 8,
            "outlier_count": 0,
            "active_alerts": [],
            "scan": {
                "subnet": "192.168.44.0/24",
                "api_reachable": 62,
                "hosts_tested": 254,
                "started_at": "2026-03-14T16:13:44Z",
            },
        },
        "how is 000007.030?",
    )
    assert "No building-specific issue is visible in the available building data." in text
    assert "No switch or CPE telemetry is visible for this building" not in text
    assert "this scan is old, so treat the reachability context as historical rather than current" in text


def test_rerun_latest_scan_labels_stale_scan_as_historical() -> None:
    text = format_operator_response(
        "rerun_latest_scan",
        {
            "building_id": "000007.040",
            "site_id": "000007",
            "scan": {
                "started_at": "2026-03-14T16:13:44Z",
            },
        },
        "rescan",
    )
    assert "for 000007.040" in text
    assert "It is stale (" in text


def test_rerun_latest_scan_reports_unconfigured_trigger_backend() -> None:
    text = format_operator_response(
        "rerun_latest_scan",
        {
            "building_id": "000007.040",
            "site_id": "000007",
            "available": False,
            "before_scan": {"started_at": "2026-03-14T16:13:44Z"},
        },
        "rescan",
    )
    assert "cannot trigger a new network scan" in text
    assert "no scan trigger backend is configured" in text


def test_rerun_latest_scan_reports_successful_refresh_when_scan_changes() -> None:
    text = format_operator_response(
        "rerun_latest_scan",
        {
            "building_id": "000007.040",
            "site_id": "000007",
            "available": True,
            "triggered": True,
            "scan_changed": True,
            "before_scan": {"started_at": "2026-03-14T16:13:44Z"},
            "after_scan": {"started_at": "2026-04-26T22:45:00Z"},
        },
        "rescan",
    )
    assert "triggered a new network scan for 000007.040" in text
    assert "moved from Mar 14, 2026" in text


def test_rerun_latest_scan_change_followup_is_explicitly_noop() -> None:
    text = format_operator_response(
        "rerun_latest_scan",
        {
            "building_id": "000007.001",
            "site_id": "000007",
            "scan": {"started_at": "2026-03-14T16:13:44Z"},
        },
        "what changed?",
    )
    assert "Nothing changed in Jake's evidence for 000007.001" in text
    assert "no new scan was actually run from chat" in text


def test_site_summary_comparison_followup_answers_site_scope_directly() -> None:
    text = format_operator_response(
        "get_site_summary",
        {
            "site_id": "000007",
            "active_alerts": [],
            "outlier_count": 0,
            "location_groups": [
                {
                    "building_id": "000007.001",
                    "building_health_hint": {"health": {"building_id": "000007.001", "device_count": 2, "probable_cpe_count": 3, "outlier_count": 0}},
                },
                {
                    "building_id": "000007.040",
                    "building_health_hint": {"health": {"building_id": "000007.040", "device_count": 0, "probable_cpe_count": 0, "outlier_count": 0}},
                },
            ],
        },
        "Is this isolated or seen elsewhere on the site?",
    )
    assert text.splitlines()[0] == "Site 000007 comparison:"
    assert "Operator view:" in text
    assert "zero-visibility scopes" in text.lower() or "zero-visibility building scopes" in text.lower()


def test_site_summary_does_not_confuse_scan_counts_with_expected_device_totals() -> None:
    text = format_operator_response(
        "get_site_summary",
        {
            "site_id": "000007",
            "online_customers": {"count": 219},
            "outlier_count": 3,
            "devices_total": 167,
            "active_alerts": [],
            "routers": [{"identity": "000007.R1"}],
            "bridge_host_summary": {"total": 500, "tplink": 40, "vilo": 12},
        },
        "what can you tell me about 000007?",
    )
    assert text.splitlines()[0] == "Site 000007:"
    assert "- 219 online subscribers" in text
    assert "- 167 tracked network devices" in text
    assert "Operator view:" in text
    assert "Evidence:" in text
    assert "Context:" in text
    assert "Next checks:" in text
    assert "not expected subscriber totals for the site" in text
    _assert_section_order(text, ["Operator view:", "Evidence:", "Context:", "Next checks:"])
    _assert_readability(text)


def test_switch_summary_leads_with_switch_and_port_concerns() -> None:
    text = format_operator_response(
        "get_switch_summary",
        {
            "switch_identity": "000007.030.SW01",
            "probable_cpe_count": 8,
            "access_port_count": 24,
            "vendor_summary": {"tplink": 6, "vilo": 2},
        },
        "what can you tell me about 000007.030.SW01?",
    )
    assert text.splitlines()[0] == "Switch 000007.030.SW01:"
    assert "- 24 subscriber-facing ports" in text
    assert "- 8 probable subscriber devices (CPEs) seen on those ports" in text
    assert "Operator view:" in text
    assert "Evidence:" in text
    assert "Next checks:" in text
    _assert_section_order(text, ["Operator view:", "Evidence:", "Next checks:"])
    _assert_readability(text)


def test_cpe_state_separates_physical_l2_service_and_controller_evidence() -> None:
    text = format_operator_response(
        "get_cpe_state",
        {
            "mac": "aa:bb:cc:dd:ee:ff",
            "subscriber_name": "ExampleUnit1A",
            "is_service_online": False,
            "bridge": {
                "verified_sightings": True,
                "primary_sighting": {
                    "device_name": "000007.R1",
                    "port_name": "sfp-sfpplus1",
                    "vlan_id": 20,
                    "client_ip": "10.0.0.2",
                    "last_seen": "2026-03-14T16:13:44Z",
                },
                "best_guess": {"identity": "000007.R1", "on_interface": "sfp-sfpplus1", "vid": 20},
            },
            "seen_by_device": "000007.R1",
            "olt_correlation": {
                "found": True,
                "olt_name": "000007.OLT01",
                "pon": "Gpon1/0/1",
                "onu_id": "12",
                "onu_status": "offline",
                "signal_dbm": -29.0,
            },
            "dhcp_correlation": {
                "found": True,
                "requests_per_hour": 120,
                "verdict": "abnormal",
                "window_minutes": 60,
            },
        },
        "what is this mac doing aa:bb:cc:dd:ee:ff",
    )
    assert text.splitlines()[0] == "CPE state for ExampleUnit1A (aa:bb:cc:dd:ee:ff):"
    assert "Operator view:" in text
    assert "Evidence:" in text
    assert "Context:" in text
    assert "Next checks:" in text
    assert "- physical/L2:" in text
    assert "- controller/OLT:" in text
    assert "- service evidence:" in text
    _assert_section_order(text, ["Operator view:", "Evidence:", "Context:", "Next checks:"])
    _assert_readability(text)


def test_trace_mac_explains_current_vs_uplink_only_or_historical() -> None:
    text = format_operator_response(
        "trace_mac",
        {
            "mac": "aa:bb:cc:dd:ee:ff",
            "trace_status": "latest_scan_uplink_only",
            "reason": "The MAC is visible in the latest scan, but only on uplink or non-edge interfaces.",
            "primary_sighting": {"device_name": "000007.R1", "port_name": "sfp-sfpplus1", "vlan_id": 20},
            "best_guess": {"identity": "000007.R1", "on_interface": "sfp-sfpplus1", "vid": 20},
        },
        "trace mac aa:bb:cc:dd:ee:ff",
    )
    assert text.splitlines()[0] == "MAC trace for aa:bb:cc:dd:ee:ff:"
    assert "Operator view:" in text
    assert "Evidence:" in text
    assert "Next checks:" in text
    _assert_section_order(text, ["Operator view:", "Evidence:", "Next checks:"])
    _assert_readability(text)


def test_customer_fault_domain_separates_evidence_from_hypothesis() -> None:
    text = format_operator_response(
        "get_building_fault_domain",
        {
            "building_id": "000007.030",
            "site_id": "000007",
            "address": "123 Example St",
            "floor_clusters": [{"floor": "3", "offline_count": 4, "online_count": 1, "offline_units": ["3A", "3B"]}],
            "top_optical_cluster": {"olt_name": "000007.OLT01", "port_id": "Gpon1/0/1", "critical_count": 2, "low_count": 1, "worst": -29.2},
            "fault_domain": {
                "likely_domain": "shared_vertical_path",
                "confidence": "medium",
                "owner": "field",
                "reason": "Multiple units on one floor are down together.",
                "suggested_fix": "Check shared vertical path from floor tap to riser.",
            },
        },
        "is this a floor issue at 000007.030?",
    )
    assert text.splitlines()[0] == "Customer fault domain for 000007.030:"
    assert "Operator view:" in text
    assert "Evidence:" in text
    assert "Context:" in text
    assert "Next checks:" in text
    _assert_section_order(text, ["Operator view:", "Evidence:", "Context:", "Next checks:"])
    _assert_readability(text)
