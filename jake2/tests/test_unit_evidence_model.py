from __future__ import annotations

from diagnosis.evidence import (
    ControllerTruth,
    AuthTruth,
    DhcpOfferEvidence,
    DhcpTruth,
    InventoryTruth,
    L2LocationEvidence,
    L2Truth,
    PhysicalTruth,
    ServiceTruth,
    UnitEvidence,
)


def test_unit_evidence_serializes_required_layered_shape() -> None:
    evidence = UnitEvidence(
        unit="000007.001/1A",
        inventory_truth=InventoryTruth(
            expected_make="TP-Link",
            expected_mac="aa:11:22:33:44:55",
            expected_pppoe="NYCHA123Unit1A",
            expected_controller="tauc",
            expected_switch="000007.001.SW01",
            expected_port="ether7",
            expected_vlan="20",
            evidence_sources=["nycha_info_csv", "tauc_audit_csv"],
        ),
        physical_truth=PhysicalTruth(
            port_up=True,
            port_speed="100M",
            port_duplex="full",
            link_partner_speed="1G",
            link_partner_duplex="full",
            rx_errors=2,
            tx_errors=1,
            fcs_errors=7,
            crc_errors=12,
            link_flaps=4,
            link_flaps_window_seconds=900,
            port_flaps=4,
            port_errors={"crc": 12, "fcs": 7},
            evidence_sources=["routeros_interface_counters"],
        ),
        l2_truth=L2Truth(
            expected_mac_seen=True,
            expected_mac_locations=[
                L2LocationEvidence(
                    mac="aa:11:22:33:44:55",
                    switch="000007.001.SW01",
                    port="ether7",
                    vlan="20",
                    source="bridge_hosts",
                )
            ],
            any_mac_on_expected_port=True,
            macs_on_expected_port=["aa:11:22:33:44:55"],
            live_mac_seen=True,
            live_mac="aa:11:22:33:44:55",
            live_switch="000007.001.SW01",
            live_port="ether7",
            live_vlan="20",
            evidence_sources=["bridge_hosts", "bigmac"],
        ),
        controller_truth=ControllerTruth(
            controller_seen=True,
            controller_name="tauc",
            controller_mac="aa:11:22:33:44:55",
            controller_unit="1A",
            controller_online=False,
            controller_last_seen="2026-04-23T08:30:00Z",
            controller_last_seen_timestamp="2026-04-23T08:30:00Z",
            controller_data_age_seconds=1800,
            controller_stale=True,
            mapping_matches_inventory=True,
            evidence_sources=["tauc_snapshot"],
        ),
        auth_truth=AuthTruth(
            pppoe_active=False,
            pppoe_username="NYCHA123Unit1A",
            pppoe_failures=[],
            pppoe_failed_attempts_seen=False,
            pppoe_failure_reason="no_response",
            pppoe_last_attempt_timestamp="2026-04-23T08:25:00Z",
            pppoe_no_attempt_evidence=True,
            evidence_sources=["router_ppp_active", "loki_pppoe_logs"],
        ),
        dhcp_truth=DhcpTruth(
            dhcp_expected=False,
            discovers_seen=0,
            dhcp_discovers_seen=0,
            offers_seen=0,
            dhcp_offers_seen=0,
            dhcp_server=None,
            dhcp_offer_source=None,
            dhcp_expected_server="10.0.0.1",
            rogue_dhcp_suspected=False,
            rogue_dhcp_detected=False,
            dhcp_offers=[DhcpOfferEvidence(server=None)],
            evidence_sources=["lynxmsp", "loki_dhcp_logs"],
        ),
        service_truth=ServiceTruth(
            service_ip=None,
            gateway_reachable=None,
            dns_reachable=None,
            customer_traffic_seen=False,
            management_plane_only=False,
            evidence_sources=["router_arp"],
        ),
    )
    evidence.add_contradiction(
        layer="controller_truth",
        summary="Controller reports known device but no active service session is present",
        sources=["tauc_snapshot", "router_ppp_active"],
    )
    evidence.add_unknown(
        layer="service_truth",
        field_name="gateway_reachable",
        reason="No IP-level probe was collected for this unit",
        sources_checked=["router_arp"],
    )
    evidence.add_stale_source(
        layer="controller_truth",
        source="tauc_snapshot",
        last_seen="2026-04-22T08:30:00Z",
        reason="Snapshot is older than current bridge-host evidence",
    )

    payload = evidence.to_dict()

    assert payload["unit"] == "000007.001/1A"
    assert payload["inventory_truth"]["expected_mac"] == "aa:11:22:33:44:55"
    assert payload["physical_truth"]["port_speed"] == "100M"
    assert payload["physical_truth"]["crc_errors"] == 12
    assert payload["physical_truth"]["link_flaps_window_seconds"] == 900
    assert payload["l2_truth"]["live_mac_seen"] is True
    assert payload["controller_truth"]["controller_name"] == "tauc"
    assert payload["controller_truth"]["controller_stale"] is True
    assert payload["auth_truth"]["pppoe_no_attempt_evidence"] is True
    assert payload["auth_truth"]["pppoe_last_attempt_timestamp"] == "2026-04-23T08:25:00Z"
    assert payload["dhcp_truth"]["offers_seen"] == 0
    assert payload["dhcp_truth"]["dhcp_expected_server"] == "10.0.0.1"
    assert payload["service_truth"]["customer_traffic_seen"] is False
    assert payload["contradictions"][0]["layer"] == "controller_truth"
    assert payload["unknowns"][0]["field_name"] == "gateway_reachable"
    assert payload["stale_data_sources"][0]["source"] == "tauc_snapshot"


def test_unit_evidence_requires_non_empty_unit() -> None:
    try:
        UnitEvidence(unit="")
    except ValueError as exc:
        assert "non-empty unit" in str(exc)
    else:
        raise AssertionError("Expected UnitEvidence to reject empty unit")


def test_new_evidence_fields_default_to_none() -> None:
    evidence = UnitEvidence(unit="000007.001/1A")

    assert evidence.physical_truth.link_partner_speed is None
    assert evidence.physical_truth.rx_errors is None
    assert evidence.controller_truth.controller_last_seen_timestamp is None
    assert evidence.controller_truth.controller_data_age_seconds is None
    assert evidence.controller_truth.controller_stale is None
    assert evidence.auth_truth.pppoe_failure_reason is None
    assert evidence.auth_truth.pppoe_last_attempt_timestamp is None
    assert evidence.dhcp_truth.dhcp_discovers_seen is None
    assert evidence.dhcp_truth.dhcp_offers_seen is None
    assert evidence.dhcp_truth.dhcp_offer_source is None
    assert evidence.dhcp_truth.dhcp_expected_server is None
    assert evidence.dhcp_truth.rogue_dhcp_detected is None
