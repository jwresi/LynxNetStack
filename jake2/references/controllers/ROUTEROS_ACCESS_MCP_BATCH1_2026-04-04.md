# RouterOS Access MCP · Batch 1

This batch is the first RouterOS 7.18+ troubleshooting domain for Jake.

It is grouped by operator intent, not by changelog order.

## MCP Server
- `mcp/routeros_access_mcp.py`

## Intent Group
- `subscriber_access`

## Tool Design Rules
- symptom-first invocation
- version-aware applicability
- explicit `invoke_when` and `avoid_when`
- structured `safe_fix` and `rollback`
- bug vs config vs feature distinction

## Batch 1 Tools
- `diagnose_pppoe_server_no_traffic_7_20`
- `diagnose_pppoe_chap_auth_failure`
- `diagnose_dhcp_option82_packet_drop`
- `diagnose_option82_format_change_7_21`
- `diagnose_ipoe_lease_no_connectivity`
- `diagnose_radius_accounting_stop_missing`
- `diagnose_ppp_framed_route_wrong_vrf`
- `diagnose_dhcp_tr101_suboptions_radius`
- `diagnose_dhcp_lease_identity_selection`
- `diagnose_masquerade_stale_connections_ip_change`
- `diagnose_dhcpv6_lease_time_radius_prefix`
- `diagnose_dhcp_lease_stuck_or_not_released`
- `diagnose_ipv6_pmtu_pppoe_breakage`

## Shared Return Shape
- `tool_name`
- `intent_group`
- `applies_to_versions`
- `bug_type`
- `impact`
- `invoke_when`
- `avoid_when`
- `diagnostic_commands`
- `decision_tree`
- `likely_root_cause`
- `safe_fix`
- `rollback`
- `fixed_in`
- `references`
- `confidence`
- `observed_context`

## Why This Batch Exists
- It gives Jake high-value RouterOS access-path troubleshooting without wasting tool budget on trivial commands.
- It separates true platform regressions from operator misconfiguration and intentional behavior changes.
- It creates the reusable schema for later batches such as switching, routing, firewall, and platform-specific RouterOS troubleshooting.
