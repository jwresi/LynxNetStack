# SwOS Switching MCP · Batch 1

This batch covers SwOS-specific switching scenarios and stays intentionally separate from RouterOS bridge troubleshooting.

## MCP Server
- `mcp/swos_switching_mcp.py`

## Intent Group
- `switching_l2_swos`

## Scope
- SwOS VLAN / PVID mistakes
- host-table based wrong-port diagnosis
- dirty segment and duplicate-MAC interpretation on CSS edge switches
- DHCP snooping / ACL-to-CPU interaction
- pause-frame / flow-control edge weirdness
- ring/RSTP context on SwOS-managed switches

## Why It Is Separate
- SwOS uses a different config and state model from RouterOS bridge/VLAN.
- Tool routing quality gets worse if SwOS and RouterOS symptoms share one giant pool.
- Chenoweth and similar sites still use SwitchOS/CSS access gear heavily enough to justify a distinct domain.

## Batch 1 Tools
- `diagnose_swos_dhcp_snooping_acl_tag_cpu_interaction`
- `diagnose_swos_tx_flow_control_pause_frames`
- `diagnose_swos_vlan_pvid_access_trunk_mismatch`
- `diagnose_swos_host_table_port_misalignment`
- `diagnose_swos_offline_port_candidate`
- `diagnose_swos_duplicate_mac_single_cpe_pattern`
- `diagnose_swos_dirty_segment_mixed_macs`
- `diagnose_swos_ring_rstp_blocking_context`

## Shared Return Shape
- `tool_name`
- `intent_group`
- `summary`
- `impact`
- `applies_to`
- `invoke_when`
- `avoid_when`
- `diagnostic_reads`
- `decision_tree`
- `likely_root_cause`
- `safe_fix`
- `rollback`
- `references`
- `confidence`
- `observed_context`
