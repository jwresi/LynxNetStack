# RouterOS Switching MCP · Batch 2

This batch covers the RouterOS bridge engine only.

It does not include SwOS-specific switch behavior. Those tools belong in a later `swos_switching_mcp`.

## MCP Server
- `mcp/routeros_switching_mcp.py`

## Intent Group
- `switching_l2`

## Scope
- bridge
- VLAN filtering
- STP / RSTP
- hardware offload
- DHCP snooping interactions
- multicast / IGMP snooping
- v6 to v7 bridge migration traps
- RA Guard
- MVRP

## Out Of Scope For This Batch
- SwOS-only ACL / snooping behavior
- MLAG
- CRS3xx L3HW routing issues

## Batch 2 Tools
- `diagnose_stp_blocked_after_bridge_mac_change_7_20`
- `diagnose_bridge_forwarding_soft_lock_7_20`
- `diagnose_dhcp_snooping_hw_offload_loss_qca8337_7_20`
- `diagnose_vlan_filtering_performance_regression_7_20`
- `diagnose_dynamic_switch_cpu_vlan_missing_7_20`
- `diagnose_bridge_fast_path_crash_removed_interface_7_20`
- `diagnose_pvid_access_trunk_misconfiguration_v6_to_v7`
- `diagnose_hw_offload_enabled_but_cpu_forwarding`
- `diagnose_vlan_filtering_with_dhcp_snooping_support_matrix`
- `diagnose_igmp_snooping_hw_offload_multicast_router_7_21`
- `diagnose_v6_to_v7_bridge_migration_breakage`
- `diagnose_ra_guard_7_22_misconfiguration`
- `diagnose_mvrp_vlan_propagation_breakage`

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
- `confirmed_hardware`
- `likely_hardware`
- `not_relevant_on`
- `references`
- `confidence`
- `observed_context`

## Why This Batch Exists
- It matches your real infrastructure better than generic RouterOS changelog mining.
- It keeps RouterOS bridge troubleshooting separate from SwOS.
- It gives Jake hardware-aware switching scenarios without wasting tool budget on MLAG or L3HW paths you are not currently prioritizing.
