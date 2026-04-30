# RouterOS Routing MCP · Batch 3

`routeros_routing_mcp` covers RouterOS routing control-plane scenarios that Jake should treat separately from access-path and bridge-engine problems.

## Scope
- BGP session / instance migration traps
- BGP traffic-engineering bugs
- VRF binding regressions
- OSPF redistribution / BFD traps
- route lifecycle and safe-mode rollback issues
- failover and check-gateway design patterns

## Hardware emphasis
- primary target: `CCR2004`
- likely relevant: other `CCR` routing nodes and some `RB5009` edge roles

## Included scenarios
- `diagnose_bgp_instance_model_change_7_20`
- `diagnose_bgp_filter_not_rejecting_routes`
- `diagnose_bgp_output_not_cleaned_after_restart`
- `diagnose_bgp_update_not_sent_on_prepend_change`
- `diagnose_bgp_ignore_as_path_len_not_working`
- `diagnose_bgp_vrf_parameter_missing_after_upgrade`
- `diagnose_bgp_ecmp_multipath_behavior`
- `diagnose_ospf_loopback_redistribution_external_lsa`
- `diagnose_ospf_bfd_stuck_init_state`
- `diagnose_route_not_removed_after_safe_mode`
- `diagnose_routes_with_low_scope_broken`
- `diagnose_bgp_default_route_ospf_redistribution_leak`
- `diagnose_check_gateway_state_logging`
