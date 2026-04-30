from __future__ import annotations

from typing import Any


def _tool(
    name: str,
    summary: str,
    applies_to_versions: str,
    bug_type: str,
    impact: str,
    symptoms: list[str],
    diagnostic_commands: list[str],
    decision_tree: list[str],
    likely_root_cause: list[str],
    safe_fix: list[str],
    rollback: list[str],
    fixed_in: str | None = None,
    not_applicable_when: list[str] | None = None,
    references: list[str] | None = None,
    confidence: str = "high",
) -> dict[str, Any]:
    return {
        "summary": summary,
        "intent_group": "subscriber_access",
        "applies_to_versions": applies_to_versions,
        "bug_type": bug_type,
        "impact": impact,
        "invoke_when": symptoms,
        "avoid_when": not_applicable_when or [],
        "diagnostic_commands": diagnostic_commands,
        "decision_tree": decision_tree,
        "likely_root_cause": likely_root_cause,
        "safe_fix": safe_fix,
        "rollback": rollback,
        "fixed_in": fixed_in,
        "references": references or ["RouterOS 7.18-7.22 changelogs", "RouterOS forum operator reports"],
        "confidence": confidence,
        "tool_name": name,
    }


ROUTEROS_ACCESS_SCENARIOS: dict[str, dict[str, Any]] = {
    "diagnose_pppoe_server_no_traffic_7_20": _tool(
        name="diagnose_pppoe_server_no_traffic_7_20",
        summary="PPPoE sessions establish, but subscriber traffic does not forward. This matches the 7.20 PPPoE server data-plane regression.",
        applies_to_versions="7.20-7.20.1",
        bug_type="bug",
        impact="high",
        symptoms=[
            "PPPoE sessions show up in /ppp active",
            "multiple subscribers affected at the same time",
            "RX/TX byte counters remain flat or nearly flat",
            "authentication succeeds but the service plane is dead",
        ],
        diagnostic_commands=[
            "/ppp active print detail",
            "/interface pppoe-server server print detail",
            "/tool profile",
            "/interface monitor-traffic <uplink>",
        ],
        decision_tree=[
            "If sessions fail to authenticate, use the CHAP or Radius tools instead.",
            "If sessions are up but all subscribers have no traffic after upgrade to 7.20.x, treat this as the known regression first.",
            "If only one subscriber is affected, this tool is a poor fit; inspect CPE, VLAN, and policy instead.",
        ],
        likely_root_cause=[
            "RouterOS 7.20 PPPoE server forwarding regression",
        ],
        safe_fix=[
            "Upgrade to 7.20.2 or later.",
            "If immediate upgrade is impossible, roll back to the last known-good pre-7.20 release used at the site.",
        ],
        rollback=[
            "Restore the previous RouterOS package set.",
            "Reboot in maintenance window and verify /ppp active plus subscriber traffic counters.",
        ],
        fixed_in="7.20.2",
    ),
    "diagnose_pppoe_chap_auth_failure": _tool(
        name="diagnose_pppoe_chap_auth_failure",
        summary="CHAP or MS-CHAPv2 subscribers fail while PAP still works. This matches the 7.20 authentication regression.",
        applies_to_versions="7.20-7.20.1",
        bug_type="bug",
        impact="high",
        symptoms=[
            "PPPoE auth fails for CHAP/MS-CHAPv2 clients",
            "PAP clients still authenticate",
            "issue appears after 7.20 upgrade",
        ],
        diagnostic_commands=[
            "/ppp profile print detail",
            "/interface pppoe-server server print detail",
            "/log print where message~\"ppp|chap|radius\"",
            "/radius print detail",
        ],
        decision_tree=[
            "If PAP fails too, this is likely not the specific 7.20 CHAP regression.",
            "If only CHAP-family auth breaks after 7.20 upgrade, prioritize this bug over RADIUS policy guesses.",
        ],
        likely_root_cause=[
            "7.20 CHAP negotiation/auth regression on PPPoE server path",
        ],
        safe_fix=[
            "Upgrade to 7.20.2 or later.",
            "If temporary service restoration is required, allow PAP only if operationally acceptable and security policy permits it.",
        ],
        rollback=[
            "Revert auth-method changes after upgrade.",
            "Return to last known-good release if upgrade is not immediately possible.",
        ],
        fixed_in="7.20.2",
    ),
    "diagnose_dhcp_option82_packet_drop": _tool(
        name="diagnose_dhcp_option82_packet_drop",
        summary="With bridge add-dhcp-option82 enabled, offers are silently lost and clients time out. This matches the 7.20.x Option 82 bug.",
        applies_to_versions="7.20.x",
        bug_type="bug",
        impact="high",
        symptoms=[
            "DHCP discover/request leaves the access edge",
            "server sends offer",
            "client never receives offer",
            "problem starts when add-dhcp-option82=yes is enabled",
        ],
        diagnostic_commands=[
            "/interface bridge print detail",
            "/interface bridge settings print",
            "/tool sniffer quick port=67,68",
            "/log print where message~\"dhcp\"",
        ],
        decision_tree=[
            "If offers are never generated upstream, this is not the right tool.",
            "If offers are generated but vanish only when Option 82 insertion is enabled on 7.20.x, treat this as the known bug.",
        ],
        likely_root_cause=[
            "RouterOS 7.20 Option 82 bridge-path packet handling bug",
        ],
        safe_fix=[
            "Upgrade to 7.21 or later.",
            "If immediate upgrade is impossible, disable add-dhcp-option82 temporarily only if subscriber identity workflow allows it.",
        ],
        rollback=[
            "Restore the previous bridge DHCP setting after upgrading and re-validate with packet capture.",
        ],
        fixed_in="7.21",
    ),
    "diagnose_option82_format_change_7_21": _tool(
        name="diagnose_option82_format_change_7_21",
        summary="7.21 changed Option 82 formatting. Circuit-ID now includes interface-name:vid and remote-id is bridge MAC, which can silently break old policy matching.",
        applies_to_versions="7.21+",
        bug_type="behavior_change",
        impact="high",
        symptoms=[
            "DHCP path still works at packet level",
            "RADIUS or subscriber policy no longer matches after upgrade",
            "Circuit-ID/Remote-ID values differ from older expected format",
        ],
        diagnostic_commands=[
            "/interface bridge settings print",
            "/tool sniffer quick port=67,68",
            "/log print where message~\"radius|dhcp\"",
        ],
        decision_tree=[
            "If there is no Option 82/RADIUS identity dependency, this is probably not the right tool.",
            "If subscriber lookup broke after 7.21 and packet flow still exists, inspect Option 82 formatting before changing switch topology.",
        ],
        likely_root_cause=[
            "Intentional Option 82 field-format change in RouterOS 7.21+",
        ],
        safe_fix=[
            "Update RADIUS, DHCP, or billing-side parsers to accept interface-name:vid Circuit-ID.",
            "Update remote-id matching to expect bridge MAC.",
        ],
        rollback=[
            "Revert parser/policy changes if you later standardize on a different identity method.",
        ],
        fixed_in="intentional change",
        references=["RouterOS 7.21 release notes", "RouterOS DHCP Option 82 operator notes"],
    ),
    "diagnose_ipoe_lease_no_connectivity": _tool(
        name="diagnose_ipoe_lease_no_connectivity",
        summary="Subscriber gets a valid IPoE/DHCP lease but still cannot reach the gateway. This usually means the post-DHCP admission path is wrong.",
        applies_to_versions="7.18+",
        bug_type="config_issue",
        impact="high",
        symptoms=[
            "subscriber gets a lease",
            "cannot ping or ARP gateway reliably",
            "service fails after IP assignment",
            "common on access designs expecting ARP pinning or relay identity",
        ],
        diagnostic_commands=[
            "/ip dhcp-server lease print detail",
            "/ip arp print detail",
            "/interface bridge host print",
            "/tool sniffer quick ip-protocol=icmp",
        ],
        decision_tree=[
            "If subscriber never gets a lease, use DHCP/Option 82 tools first.",
            "If gateway ARP fails after lease assignment, inspect add-arp, bridge admission, and per-subscriber L2 policy before blaming upstream routing.",
        ],
        likely_root_cause=[
            "add-arp=no where the design expects pinned ARP entries",
            "wrong bridge/VLAN admission after lease assignment",
            "subscriber identity/policy gap after DHCP success",
        ],
        safe_fix=[
            "Verify whether the design expects add-arp=yes on the DHCP server.",
            "Verify bridge/VLAN path and subscriber admission after lease binding.",
            "Verify firewall or access policy is not dropping the newly leased address.",
        ],
        rollback=[
            "Revert DHCP or bridge ARP changes if they break existing subscribers.",
        ],
    ),
    "diagnose_radius_accounting_stop_missing": _tool(
        name="diagnose_radius_accounting_stop_missing",
        summary="RADIUS Accounting-Stop is missing when sessions end and interim-update is 0. Billing and concurrent-session logic drift.",
        applies_to_versions="7.20.x",
        bug_type="bug",
        impact="high",
        symptoms=[
            "subscriber sessions end but billing platform never sees stop event",
            "concurrent session cleanup fails",
            "issue tied to interim-update=0",
        ],
        diagnostic_commands=[
            "/radius print detail",
            "/ppp aaa print detail",
            "/log print where message~\"radius|accounting\"",
        ],
        decision_tree=[
            "If RADIUS is unreachable entirely, this tool is not specific enough.",
            "If stop records are missing only when interim-update=0 on 7.20.x, this matches the known bug.",
        ],
        likely_root_cause=[
            "RouterOS 7.20.x accounting-stop regression when interim-update=0",
        ],
        safe_fix=[
            "Upgrade to 7.21 or later.",
            "As a temporary workaround, use a non-zero interim update if it fits the billing design.",
        ],
        rollback=[
            "Return interim update timer to the prior value after software fix validation.",
        ],
        fixed_in="7.21",
    ),
    "diagnose_ppp_framed_route_wrong_vrf": _tool(
        name="diagnose_ppp_framed_route_wrong_vrf",
        summary="RADIUS Framed-Route lands in the global table instead of the subscriber VRF, causing route leakage and broken subscriber isolation.",
        applies_to_versions="7.18-7.21",
        bug_type="bug",
        impact="high",
        symptoms=[
            "subscriber-specific framed routes appear in wrong routing table",
            "VRF isolation breaks after auth success",
            "cross-VRF leakage or missing subscriber reachability",
        ],
        diagnostic_commands=[
            "/routing table print",
            "/ip route print detail where dynamic",
            "/ppp active print detail",
            "/radius print detail",
        ],
        decision_tree=[
            "If no VRFs are used, this is not the right tool.",
            "If framed routes appear but land in main/global table, treat this as a version-specific route placement issue first.",
        ],
        likely_root_cause=[
            "RouterOS framed-route VRF placement bug prior to 7.22",
        ],
        safe_fix=[
            "Upgrade to 7.22 or later.",
            "Until then, avoid relying on the broken framed-route placement path for subscriber VRF isolation.",
        ],
        rollback=[
            "If upgrade introduces other route regressions, roll back to the previous known-good image and restore the older policy method.",
        ],
        fixed_in="7.22",
    ),
    "diagnose_dhcp_tr101_suboptions_radius": _tool(
        name="diagnose_dhcp_tr101_suboptions_radius",
        summary="Guide for enabling DHCP TR-101 suboptions toward RADIUS in RouterOS 7.21+.",
        applies_to_versions="7.21+",
        bug_type="feature_enablement",
        impact="high",
        symptoms=[
            "operator wants TR-101 broadband suboptions passed to RADIUS",
            "DHCP identity needs richer access-node metadata",
            "Option 82 alone is not enough for policy mapping",
        ],
        diagnostic_commands=[
            "/ip dhcp-server print detail",
            "/radius print detail",
            "/tool sniffer quick port=67,68",
        ],
        decision_tree=[
            "If the problem is packet loss, use the Option 82 bug tools instead.",
            "If the question is how to expose TR-101 subscriber metadata to RADIUS, this is the right tool.",
        ],
        likely_root_cause=[
            "Feature not enabled or not understood after 7.21 introduction",
        ],
        safe_fix=[
            "Enable support-broadband-tr101 where the design requires it.",
            "Verify RADIUS server expects and parses the suboptions.",
            "Validate packet contents before changing subscriber policy logic.",
        ],
        rollback=[
            "Disable TR-101 support if the upstream AAA stack misclassifies subscribers.",
        ],
        fixed_in="new in 7.21",
    ),
    "diagnose_dhcp_lease_identity_selection": _tool(
        name="diagnose_dhcp_lease_identity_selection",
        summary="RouterOS 7.21 added client identity selection for leases. If the identity key changed, subscribers may get unexpected new leases or stale identity behavior.",
        applies_to_versions="7.21+",
        bug_type="behavior_change",
        impact="medium",
        symptoms=[
            "subscribers get new IPs after upgrade",
            "leases appear duplicated across client-id vs MAC vs Option 82 identity",
            "billing or inventory correlation drifts after 7.21 rollout",
        ],
        diagnostic_commands=[
            "/ip dhcp-server print detail",
            "/ip dhcp-server lease print detail",
            "/tool sniffer quick port=67,68",
        ],
        decision_tree=[
            "If no upgrade or identity-method change occurred, this is a weaker fit.",
            "If clients suddenly re-key leases after 7.21, inspect the selected lease identity method first.",
        ],
        likely_root_cause=[
            "Lease identity method changed between MAC, client-id, and Option 82 selectors",
        ],
        safe_fix=[
            "Standardize on one lease identity key and keep it consistent across sites.",
            "Purge only the affected stale leases if re-keying is required, not the full server blindly.",
        ],
        rollback=[
            "Return to the previous identity selector if the new one caused unintended subscriber churn.",
        ],
    ),
    "diagnose_masquerade_stale_connections_ip_change": _tool(
        name="diagnose_masquerade_stale_connections_ip_change",
        summary="After WAN IP change, stale masqueraded conntrack entries keep using the old source IP and break traffic for minutes.",
        applies_to_versions="7.18-7.20",
        bug_type="bug",
        impact="high",
        symptoms=[
            "WAN IP changed after PPPoE reconnect or DHCP renewal",
            "new traffic still leaves with old source IP",
            "service recovers only after conntrack timeout or manual clear",
        ],
        diagnostic_commands=[
            "/ip address print",
            "/ip firewall connection print detail",
            "/ip firewall nat print detail",
            "/log print where message~\"dhcp|pppoe\"",
        ],
        decision_tree=[
            "If WAN IP never changed, this is not the right tool.",
            "If failures line up exactly with WAN address churn, prioritize stale masquerade state over generic ISP blame.",
        ],
        likely_root_cause=[
            "Masquerade conntrack cleanup bug before 7.21",
        ],
        safe_fix=[
            "Upgrade to 7.21 or later.",
            "As a temporary operator action, flush affected conntrack entries after WAN IP change.",
        ],
        rollback=[
            "Revert to the prior known-good release if post-upgrade NAT behavior is worse.",
        ],
        fixed_in="7.21",
    ),
    "diagnose_dhcpv6_lease_time_radius_prefix": _tool(
        name="diagnose_dhcpv6_lease_time_radius_prefix",
        summary="PPP-profile dhcpv6-lease-time does not control RADIUS-delegated prefixes as expected. Client T1/T2 behavior appears wrong.",
        applies_to_versions="7.20-7.22",
        bug_type="open_issue",
        impact="medium",
        symptoms=[
            "delegated IPv6 prefixes use unexpected lease timers",
            "RADIUS-driven PD does not respect profile lease time",
            "customer CPE renew behavior looks inconsistent",
        ],
        diagnostic_commands=[
            "/ipv6 dhcp-server print detail",
            "/ppp profile print detail",
            "/radius print detail",
            "/log print where message~\"dhcpv6|radius\"",
        ],
        decision_tree=[
            "If prefixes are locally managed without RADIUS, this tool is probably not the right fit.",
            "If delegated prefix timers are wrong only on RADIUS-driven sessions, treat this as an unresolved platform issue first.",
        ],
        likely_root_cause=[
            "Open RouterOS behavior gap for RADIUS-delegated IPv6 lease timing",
        ],
        safe_fix=[
            "Do not spend hours chasing imaginary edge ACL issues first.",
            "Document the limitation and standardize workaround policy at the AAA/profile layer if possible.",
        ],
        rollback=[
            "No direct rollback beyond reverting policy assumptions or release choice.",
        ],
        fixed_in="not fixed as of 7.22",
        confidence="medium",
    ),
    "diagnose_dhcp_lease_stuck_or_not_released": _tool(
        name="diagnose_dhcp_lease_stuck_or_not_released",
        summary="Leases remain busy or effectively pinned after disconnect, often because ARP state or lease scripts keep them alive.",
        applies_to_versions="7.18+",
        bug_type="config_issue",
        impact="high",
        symptoms=[
            "pool drains unexpectedly",
            "old leases remain busy after disconnect",
            "ARP entries or scripts keep addresses alive",
        ],
        diagnostic_commands=[
            "/ip dhcp-server lease print detail",
            "/ip arp print detail",
            "/system script print detail",
            "/log print where message~\"dhcp\"",
        ],
        decision_tree=[
            "If pool exhaustion is from true high utilization, this is not the root cause.",
            "If stale ARP and sticky lease state line up, inspect ARP mode and lease scripts before resizing pools.",
        ],
        likely_root_cause=[
            "ARP state holding lease as active",
            "bad lease-script logic",
            "subscriber disconnects not clearing expected state",
        ],
        safe_fix=[
            "Audit lease scripts.",
            "Verify ARP mode aligns with access design.",
            "Clear only the affected stale lease/ARP state, not the full pool blindly.",
        ],
        rollback=[
            "Restore prior lease-script behavior if cleanup logic makes churn worse.",
        ],
    ),
    "diagnose_ipv6_pmtu_pppoe_breakage": _tool(
        name="diagnose_ipv6_pmtu_pppoe_breakage",
        summary="IPv6 works partially or large transfers fail over PPPoE because PMTU handling is broken and IPv6 clamp/rules are missing.",
        applies_to_versions="7.18+",
        bug_type="config_gap",
        impact="high",
        symptoms=[
            "IPv6 pings may work but websites or large transfers fail",
            "problem appears over PPPoE paths",
            "IPv4 MSS clamp exists but IPv6 path is untreated",
        ],
        diagnostic_commands=[
            "/ipv6 firewall mangle print detail",
            "/ipv6 firewall filter print detail",
            "/tool ping address=<ipv6-target> size=1472 do-not-fragment=yes",
            "/interface pppoe-client print detail",
        ],
        decision_tree=[
            "If IPv4 is also broken broadly, this is not just PMTU.",
            "If failures are size-sensitive and specific to IPv6 over PPPoE, treat PMTU/MSS handling as the primary suspect.",
        ],
        likely_root_cause=[
            "Missing IPv6 PMTU/MSS handling on PPPoE access path",
        ],
        safe_fix=[
            "Add the correct IPv6 PMTU or MSS handling rule for the PPPoE design.",
            "Validate with large-packet tests after the change.",
        ],
        rollback=[
            "Remove the new IPv6 clamp rule if it causes unintended side effects and revert to the prior firewall state.",
        ],
    ),
}


def scenario_tool_names() -> list[str]:
    return list(ROUTEROS_ACCESS_SCENARIOS.keys())

