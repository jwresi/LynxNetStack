# Proposed Changes

## Phase 3 known gaps: canonical root `jake_query_core.py` vs `scripts/jake_query_core.py`

Accepted project decision:

- root `jake_query_core.py` remains canonical
- the newer `scripts/jake_query_core.py` is not being adopted as source of truth
- the following behavior gaps are preserved as known gaps and must not remain silent

### Additional actions present only in the scripts copy

- `diagnose_lynxmsp_wiring`
- `get_cnwave_controller_capabilities`
- `get_customer_fault_domain`
- `get_full_link_telemetry`
- `get_live_ghn_summary`
- `get_new_devices_today`
- `get_site_digi_audit`
- `get_site_edge_evidence_gaps`
- `get_site_infrastructure_handoff`
- `get_site_issue_ledger`
- `get_site_live_audit_surface`
- `get_site_transport_impact`
- `rag_search`
- `run_live_positron_read`

### Additional parsing and normalization behavior present only in the scripts copy

- subscriber-label extraction helpers are present only in the scripts copy
- response-card rendering helpers are present only in the scripts copy
- additional `LOCAL_OLT_EVIDENCE_BY_MAC` entries exist only in the scripts copy
- `SUBSCRIBER_NAME_TO_MAC` lookup exists only in the scripts copy
- `SUBSCRIBER_NAME_TO_OLT` lookup exists only in the scripts copy
- the scripts copy adds broader street-name normalization for transport matching
- the scripts copy tightens some switch and building regex handling
- the scripts copy suppresses effective site-id resolution when building or switch ids are matched

### Additional site and incident routes present only in the scripts copy

- more detailed live audit surface queries
- Digi and out-of-band audit routes
- issue-ledger routes
- infrastructure-handoff routes
- transport-impact routes
- topology routes
- bridge-host weirdness routes
- edge-evidence-gap routes
- building fault-domain routes
- Positron and G.Hn live-read routes
- CPE readiness and management-surface routes

### Status

- these are known behavior gaps, not approved behavior changes
- Phase 3 migrated the canonical root behavior and documented the missing scripts-copy behavior here per project rule

## Resolved During Migration

- `generate_nycha_audit_workbook`
  - resolved in Phase 4 as audit-subsystem ownership
  - no longer treated as a deterministic-core gap

## Still Open

- all remaining Phase 3 scripts-copy actions and parsing behavior listed above remain open known gaps

## Chenoweth OLT IP investigation — resolved as no-op

- investigated whether Chenoweth (000008) has OLT IPs that should be added to `SITE_SERVICE_PROFILES`
- conclusion: Chenoweth has no standalone OLTs with telnet-accessible IPs
- Chenoweth uses TP-Link HC220 CPEs managed via TAUC directly (not through OLT PON/GPON infrastructure)
- the `"olts": []` entry in `core/shared.py` for 000008 is correct and intentional
- the original `jake_shared.py` also has no OLT IPs for 000008 — this was never a gap to fill
- `uses_olt: True` in the service profile means HC220 ONU-side reasoning may apply via TAUC, not that a standalone OLT exists

## Chenoweth subscriber unit-to-MAC resolution

- status
  - blocked on switchos exporter enhancement

- resolution path
  - add per-MAC rows with `port_name` label to the switchos exporter MAC table collection
  - once exposed in Prometheus, Jake can query `switchos_mac_table` by port to resolve unit names to MACs for SwOS sites like Chenoweth
  - `link.b nm` array is already confirmed to contain unit-to-port mapping on CSS326 switches

## Capability Expansion Resolved

- `get_cpe_state`
  - resolved as an understanding-layer coverage gap
  - deterministic action already existed in Jake2; Phase 2 wired parser, structured execution, fixtures, and baseline coverage

- `trace_mac`
  - resolved as an understanding-layer coverage gap
  - deterministic action already existed in Jake2; Phase 2 wired parser, structured execution, fixtures, and baseline coverage

- `get_live_olt_ont_summary`
  - resolved as an understanding-layer coverage gap
  - deterministic action already existed in Jake2; Phase 2 wired parser, structured execution, fixtures, and baseline coverage

- `get_customer_access_trace`
  - resolved as an understanding-layer coverage gap plus subscriber-label heuristic conflict
  - deterministic runtime method already existed in Jake2
  - follow-up wiring added intent registration, structured execution, parser heuristics, fixtures, and baseline coverage

- `get_site_loop_suspicion`
  - resolved as a capability-expansion migration from the scripts copy
  - JakeOps runtime method already existed in Jake2
  - this phase wired deterministic execution, parser heuristics, fixtures, and baseline coverage

- `get_site_bridge_host_weirdness`
  - resolved as a capability-expansion migration from the scripts copy
  - JakeOps runtime method already existed in Jake2
  - this phase wired deterministic execution, parser heuristics, fixtures, and baseline coverage

- `get_live_cnwave_radio_neighbors`
  - resolved as a capability-expansion migration from the scripts copy
  - JakeOps runtime method already existed in Jake2
  - this phase wired deterministic execution, parser heuristics, fixtures, and baseline coverage

- `get_radio_handoff_trace`
  - resolved as a capability-expansion migration from the scripts copy
  - JakeOps runtime method already existed in Jake2
  - this phase wired deterministic execution, parser heuristics, fixtures, and baseline coverage

- `get_building_fault_domain`
  - resolved as a capability-expansion migration from the scripts copy
  - JakeOps runtime method already existed in Jake2
  - this phase wired deterministic execution, parser heuristics, fixtures, and baseline coverage

- `get_site_topology`
  - resolved as a capability-expansion migration from the scripts copy
  - JakeOps runtime method already existed in Jake2
  - this phase wired deterministic execution, parser heuristics, fixtures, and baseline coverage
