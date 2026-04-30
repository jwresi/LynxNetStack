# Fault Reasoning Phase 1 Audit

Date: 2026-04-23

Scope: Phase 1 only. No runtime behavior changes. This document audits the current Jake2/Jake codebase against the target of an evidence-based, layered NOC diagnosis engine.

## Executive Summary

Jake has useful raw evidence collectors today, but the current reasoning path is not yet a clean evidence-first diagnosis engine.

The largest structural issues are:

1. Understanding and execution are not fully separated.
`core/query_core.py` still parses raw natural language in `parse_operator_query()` and directly executes it in `run_operator_query()`. `mcp/jake_ops_mcp.py` exposes `query_summary` as a natural-language MCP tool that calls this path directly. This violates the Jake2 contract that execution should receive only structured intent.

2. Diagnosis is spread across multiple modules.
Status and root-cause assignment currently live in at least four places:
- `audits/jake_audit_workbook.py`
- `mcp/jake_ops_mcp.py`
- `core/query_core.py`
- some scenario catalogs and renderer logic

3. The strongest mislabel risk is in the NYCHA audit workbook path.
`audits/jake_audit_workbook.py:_apply_live_status()` converts partial evidence into hard labels such as `UNPLUGGED / BAD CABLE`, `MOVE CPE TO WAN PORT`, `WRONG UNIT`, and `CONTROLLER MISMATCH`. Several of those conclusions are made without checking the full stack in the required reasoning order.

4. Current customer-fault reasoning is domain-oriented, not evidence-layered.
`mcp/jake_ops_mcp.py:correlate_customer_fault_domain()` and `get_building_fault_domain()` choose a likely domain using clusters of current evidence, but they do not produce a normalized diagnosis object that distinguishes inventory, L1, L2, controller, auth, DHCP, and service truth.

5. Operator output is not schema-stable for diagnosis.
Current outputs are mostly human-readable summaries plus action-specific payloads. There is no central diagnosis schema matching the required structure of:
- observed state
- evidence used
- evidence missing
- likely causes
- confidence
- backend vs field actions
- dispatch requirement

6. Existing tests currently preserve some behavior that should eventually be replaced.
The audit workbook baseline asserts legacy-style labels and implications. That is useful for migration safety, but it also means the current tests are protecting behavior that is too coarse for the target diagnosis model.

The net result: Jake is not yet overconfident everywhere, but it is overconfident in specific high-impact places, especially when translating incomplete access evidence into field actions.

## Codebase Map

This map focuses on modules involved in customer-state, outage, and fault classification.

| Module | Purpose | Inputs | Outputs | External systems touched | Main risks |
| --- | --- | --- | --- | --- | --- |
| `core/intent_schema.py` | Structured intent contract | Parsed intent fields | `IntentSchema`, `IntentEntities` | None | Good contract, but diagnosis schema does not exist here |
| `core/intent_parser.py` | Understanding layer parser | Raw operator text, history, config | Structured intent with confidence | Ollama optionally, config, local examples | Understanding layer is separate, but not the only entrypoint |
| `core/dispatch.py` | Confidence gate and intent execution handoff | `IntentSchema`, context | `DispatchResult` | Ollama optionally | Correct direction, but coexists with raw-NL execution path |
| `core/query_core.py` | Legacy deterministic query core plus response rendering | Raw NL or structured intent | Action result + operator summary | Calls `JakeOps`, scenario dispatch | Mixes NL parsing, execution dispatch, and rendering in one module |
| `mcp/jake_ops_mcp.py` | Main deterministic data access layer | Structured params or raw query via `query_summary` | Action-specific dict payloads | SQLite, Bigmac, NetBox, Alertmanager, Prometheus, Vilo, TAUC, LynxMSP, Loki, RouterOS, OLT tooling | Very large surface; collectors and reasoning are mixed together |
| `audits/jake_audit_workbook.py` | NYCHA workbook generation and row status assignment | Inventory CSV rows, TAUC/Vilo snapshots, bridge data, building/site context | Workbook rows, workbook file, labels/actions | OpenPyXL, local CSV/JSON, `JakeOps` helpers | Strong classification logic embedded in workbook code |
| `core/context_builder.py` | Build lightweight network context for parser/dispatcher | Prometheus, NetBox, Alertmanager, service profiles | `NetworkContext` | Prometheus, NetBox, Alertmanager | Context is broad site state, not subscriber diagnosis evidence |
| `core/shared.py` | Site/service profiles and normalization helpers | Static config-like maps | helper values/functions | None | Some site truth is encoded here, but not normalized as evidence |
| `api/jake_api_server.py` | Web API layer | User message/history | `answer`, `raw_result` | Dispatcher, `JakeOps` | Exposes whatever current action payload happens to be; no diagnosis contract |
| `core/jake_query.py` | CLI entrypoint and learning-loop helpers | Raw query | Printed answer, confirmed examples | Dispatcher, Ollama, API server | Still allows humanized responses over action payloads; no diagnosis schema |
| `tests/test_query_baseline.py` | Baseline contract for `run_operator_query` | Query text | Expected payload paths | Local DB | Locks current behavior, including pre-diagnosis shapes |
| `tests/test_audit_fixture_validation.py` | Audit workbook behavioral baseline | Fixture rows and live context | Expected row states | OpenPyXL fixtures | Locks current workbook labels and implications |

## Current Data Flow

### 1. Inventory data

Current sources:
- `mcp/jake_ops_mcp.py:load_nycha_info_rows()`
  - source: `JAKE_NYCHA_INFO_CSV`
  - used heavily by NYCHA workbook and unit mapping logic
- `mcp/jake_ops_mcp.py:load_tauc_nycha_audit_rows()`
  - source: `JAKE_TAUC_AUDIT_CSV`
  - used for exact port matches and TAUC corroboration
- local online subscriber export:
  - `load_local_online_cpe_rows()`
  - `find_local_online_cpe_row()`
- NetBox inventory:
  - accessed through `JakeOps` site/building summary methods
- static site/service profile metadata:
  - `core/shared.py:SITE_SERVICE_PROFILES`

Observations:
- inventory truth is fragmented across CSV, TAUC export, NetBox, static profiles, and local subscriber exports
- there is no central normalized object for expected unit, expected MAC, expected PPPoE account, expected controller, expected switch port, expected VLAN

### 2. Live MAC / L2 evidence

Current sources:
- local SQLite `bridge_hosts`
- `trace_mac()` in `mcp/jake_ops_mcp.py`
- optional Bigmac corroboration
- `_live_port_macs_for_switch()` and `_parse_live_bridge_host_output()` in `audits/jake_audit_workbook.py`

Outputs:
- `trace_status`
- `best_guess`
- `primary_sighting`
- `verified_sightings`
- per-switch interface MAC maps for workbook generation

Observations:
- this is the strongest existing evidence layer
- the code already distinguishes edge ports from uplinks in some places
- however, different modules interpret the same MAC evidence differently

### 3. Controller data

Current sources:
- Vilo snapshot loader in `audits/jake_audit_workbook.py:_load_vilo_inventory_snapshot()`
- TAUC audit rows
- Vilo/TAUC API adapters in `mcp/vendor_adapters.py`
- Vilo summary tools in `mcp/jake_ops_mcp.py`

Outputs:
- workbook-only `controller_verification_by_mac`
- action-specific summaries and target lookups

Observations:
- controller evidence is mostly used as corroboration, which is good
- but controller mismatch handling is not normalized across the system
- staleness handling is weak; there is no general controller freshness model

### 4. PPPoE / session data

Current sources:
- SQLite `router_ppp_active`
- subscriber export matching
- some Loki log summaries

Outputs:
- online customer counts
- outage context hints
- `get_cpe_state()` booleans

Observations:
- PPP state is present, but often reduced to `is_service_online = bool(ppp or arp)`
- no normalized distinction between:
  - active PPPoE
  - failed PPPoE
  - no PPPoE attempt
  - duplicate session
  - auth failure

### 5. DHCP data

Current sources:
- LynxMSP DB/API wrappers
- DHCP summaries and relay helpers
- optional Loki auto-correlation from `get_cpe_state()`

Outputs:
- action-specific summaries such as relay, subscriber, and live lease summaries
- coarse `dhcp_correlation` in `get_cpe_state()`

Observations:
- DHCP evidence exists in the codebase, but it is not integrated into the main customer diagnosis path
- DHCP is still a sidecar rather than a first-class stage in diagnosis

### 6. Physical / L1 data

Current sources today:
- some indirect link data from bridge presence and topology
- log and platform tooling elsewhere

Missing or weakly integrated:
- negotiated speed
- duplex
- FCS/CRC errors
- port flaps
- PoE state
- recent port-down history

Observations:
- the target diagnosis model requires strong L1 evidence
- the current core customer-state path does not have that evidence wired into a common model

### 7. Where statuses are computed

Primary computation surfaces:
- `audits/jake_audit_workbook.py:_classify_row()`
- `audits/jake_audit_workbook.py:_apply_live_status()`
- `mcp/jake_ops_mcp.py:trace_mac()`
- `mcp/jake_ops_mcp.py:get_cpe_state()`
- `mcp/jake_ops_mcp.py:correlate_customer_fault_domain()`
- `mcp/jake_ops_mcp.py:get_building_fault_domain()`
- `core/query_core.py:format_operator_response()`

### 8. Where output is rendered

Rendering surfaces:
- `core/query_core.py:format_operator_response()`
- `api/jake_api_server.py` returns `answer` and `raw_result`
- `core/jake_query.py` prints humanized summaries
- workbook rendering in `audits/jake_audit_workbook.py`

Observation:
- diagnosis is currently action-shaped and renderer-shaped, not schema-shaped

## Classification Audit

### A. `core/query_core.py:parse_operator_query()`

Current role:
- classifies raw natural language into an action and params

Evidence used:
- regex and phrase matching on raw operator text

Assumptions:
- this belongs in execution-time query code

Missing evidence:
- none, because this is not diagnosis

Risk:
- structural, not diagnostic
- this keeps raw NL parsing inside the deterministic core

Replacement:
- retire this as a production path
- keep only `run_structured_intent()` as the execution entrypoint
- if needed, move legacy query parsing behind the understanding layer only

### B. `audits/jake_audit_workbook.py:_classify_row()`

Current labels:
- `NOT INSTALLED`
- `???`
- `Good`
- `PPPoE label maps this CPE to <unit>`
- `Inventory MAC present`

Evidence used:
- inventory MAC presence
- PPPoE label text
- opt-out and progress fields

Assumptions:
- PPPoE label alignment is a meaningful initial quality state

Missing evidence:
- live MAC
- controller state
- PPPoE activity
- DHCP
- physical link evidence

Mislabel risk:
- medium
- this is acceptable as a pre-live inventory worksheet classifier, but not as diagnosis

Replacement:
- keep as a worksheet preclassification stage only
- do not allow it to imply root cause

### C. `audits/jake_audit_workbook.py:_apply_live_status()`

Current labels assigned:
- `WRONG UNIT`
- `MOVE CPE TO CORRECT UNIT`
- `Good`
- `MOVE CPE TO WAN PORT`
- `UNKNOWN MAC ON PORT`
- `UNPLUGGED / BAD CABLE`
- `CONTROLLER VERIFIED`
- `CONTROLLER MISMATCH`
- `LIVE LOOKUP FAILED`
- `NO LIVE EVIDENCE`
- `NOT INSTALLED`

Evidence used:
- expected inventory MAC
- bridge MAC on expected or inferred interface
- known off-by-one MAC bug helper
- controller verification match/mismatch
- address-level PPP/ARP-derived online evidence
- exact unit-port matches from TAUC
- whether any bridge hosts were seen anywhere in the building

Assumptions:
- if switch is reporting other MACs and this unit is absent, `UNPLUGGED / BAD CABLE` is a valid label
- last-octet delta means LAN/WAN port misuse
- wrong live MAC on expected port generally implies wrong unit or moved CPE

Missing evidence:
- negotiated speed
- duplex
- CRC/FCS errors
- port flaps
- PPPoE fail logs
- DHCP behavior
- VLAN configuration/state
- controller freshness / last seen
- search of expected MAC across all switches before some field conclusions

Mislabel risk:
- high

Specific problems:
- `UNPLUGGED / BAD CABLE` is too strong for mere MAC absence plus controller or router evidence
- the target model requires `NOT_SEEN_ANYWHERE` or `NEEDS_MORE_EVIDENCE` unless L1/L2/backend checks support a stronger conclusion
- `MOVE CPE TO WAN PORT` from a one-octet delta may be directionally useful, but still overcommits without service/auth/VLAN checks

What should replace it:
- workbook row code should stop classifying root cause directly
- it should consume a central diagnosis result and render workbook-safe labels from that result
- if the central diagnosis cannot decide, workbook should say so explicitly

### D. `mcp/jake_ops_mcp.py:trace_mac()`

Current statuses:
- `edge_trace_found`
- `latest_scan_uplink_only`
- `bigmac_edge_corroboration_only`
- `upstream_or_cached_corroboration_only`
- `not_found_in_latest_scan`

Evidence used:
- bridge host sightings
- interface role heuristics
- Bigmac corroboration

Assumptions:
- edge-port sightings are stronger than uplink sightings

Missing evidence:
- inventory expectation
- controller identity
- service state

Mislabel risk:
- low

Assessment:
- this is a good collector/correlator output and should be kept
- it is not a full diagnosis, and should remain that way

### E. `mcp/jake_ops_mcp.py:get_cpe_state()`

Current outputs:
- `is_physically_seen`
- `is_service_online`
- `bridge`
- `ppp_sessions`
- `arp_entries`
- `olt_correlation`
- `dhcp_correlation`

Evidence used:
- `trace_mac()`
- PPP active table
- ARP table
- local OLT correlation
- optional DHCP log correlation

Assumptions:
- `is_service_online = bool(ppp or arp)`

Missing evidence:
- failed PPP attempts
- auth failure reason
- DHCP offer/refusal distinction
- controller state
- expected inventory state
- physical counters

Mislabel risk:
- medium

Assessment:
- this is close to a useful evidence bundle, but it collapses service truth too aggressively
- ARP presence is not equivalent to healthy subscriber service in all cases

Replacement:
- refactor this into a collector that fills a normalized evidence object

### F. `mcp/jake_ops_mcp.py:correlate_customer_fault_domain()`

Current outputs:
- `fault_domain.likely_domain`
- `fault_domain.confidence`
- `fault_domain.owner`
- `fault_domain.reason`
- `fault_domain.suggested_fix`

Evidence used:
- local online subscriber export
- MAC trace
- local OLT path
- alerts
- building model
- G.hn hints
- same-floor clustering
- related MAC candidates

Assumptions:
- enough indirect evidence exists to choose a likely failure domain

Missing evidence:
- explicit layered truth object
- controller assignment truth
- PPP failure truth
- DHCP truth
- physical port counters
- stale-source scoring

Mislabel risk:
- medium to high

Assessment:
- this function has the right ambition but the wrong shape
- it is a proto-diagnoser without a stable evidence model
- its conclusions are broad domain guesses rather than deterministic layered diagnoses

Replacement:
- replace with a central `diagnosis/engine.py` operating on a `UnitEvidence` input

### G. `mcp/jake_ops_mcp.py:get_building_fault_domain()`

Current outputs:
- building-level `likely_domain`, `confidence`, `owner`, `reason`, `suggested_fix`

Evidence used:
- floor outage clusters
- dominant switch
- optical alert clustering

Assumptions:
- building clusters can stand in for subscriber fault reasoning

Missing evidence:
- link to per-unit inventory truth
- staleness evaluation
- explicit contradiction handling

Mislabel risk:
- medium

Assessment:
- useful as a building-scoped triage tool
- should not be treated as subscriber diagnosis

### H. `core/query_core.py:format_operator_response()`

Current role:
- turns action payloads into operator-facing prose

Evidence used:
- whatever action payload was returned

Assumptions:
- action payload and formatted answer are the diagnosis

Missing evidence:
- explicit diagnosis schema
- explicit contradiction/missing-evidence sections

Mislabel risk:
- medium

Assessment:
- current prose can sound more conclusive than the underlying evidence model supports
- renderers should render a diagnosis object, not synthesize one

## Structural Findings

### 1. The execution layer contract is currently violated

The AGENTS contract says:
- understanding accepts raw natural language
- execution accepts only structured intent objects

Current violating paths:
- `core/query_core.py:run_operator_query(query: str)`
- `core/query_core.py:parse_operator_query(query: str)`
- `mcp/jake_ops_mcp.py:query_summary(query: str)`

This is the clearest architectural gap in the repo relative to the stated Jake2 target.

### 2. Diagnosis logic is duplicated by audience

Current audience-specific logic:
- workbook diagnosis in `audits/jake_audit_workbook.py`
- operator CLI/web prose in `core/query_core.py`
- action payload hints in `mcp/jake_ops_mcp.py`

This means Jake can tell different stories from the same evidence depending on the path used.

### 3. The current system has collectors, correlators, and renderers, but no central evidence contract

Today:
- collectors exist
- some correlation exists
- many renderers exist
- there is no single internal representation of subscriber evidence or diagnosis

### 4. L1 and DHCP are underrepresented in the main customer-state path

These are first-class in the target model but secondary in the current code.

### 5. Confidence exists, but not in a consistent, evidence-backed way

Confidence is currently:
- an intent-parsing concept
- a domain-guess label in some building/customer fault functions
- not a standardized diagnosis confidence derived from evidence coverage and contradiction handling

## Proposed Evidence Model

Create a central typed model under a new module such as:
- `diagnosis/evidence.py`
- `diagnosis/engine.py`
- `diagnosis/actions.py`
- `diagnosis/renderers.py`

Suggested core object:

```python
@dataclass(slots=True)
class UnitEvidence:
    unit: str
    expected_make: str | None
    expected_mac: str | None
    expected_pppoe: str | None
    expected_controller: str | None
    expected_switch: str | None
    expected_port: str | None
    expected_vlan: str | None

    live_mac_seen: bool
    live_mac: str | None
    live_switch: str | None
    live_port: str | None
    live_vlan: str | None

    port_up: bool | None
    port_speed: str | None
    port_duplex: str | None
    port_flaps: int | None
    port_errors: dict[str, int] | None
    poe_relevant: bool | None

    controller_seen: bool | None
    controller_mac: str | None
    controller_unit: str | None
    controller_online: bool | None
    controller_last_seen: str | None

    pppoe_active: bool | None
    pppoe_username: str | None
    pppoe_failures: list[dict[str, Any]]
    pppoe_no_attempt_evidence: bool | None

    dhcp_expected: bool | None
    dhcp_discovers: list[dict[str, Any]]
    dhcp_offers: list[dict[str, Any]]
    dhcp_server: str | None
    rogue_dhcp_suspected: bool | None

    service_ip: str | None
    gateway_reachable: bool | None
    dns_issue_suspected: bool | None

    evidence_timestamps: dict[str, str]
    stale_sources: list[str]
    contradictions: list[str]
    missing_checks: list[str]
```

Then produce:

```python
@dataclass(slots=True)
class Diagnosis:
    unit: str
    observed_state: str
    primary_status: str
    secondary_statuses: list[str]
    confidence: Literal["high", "medium", "low"]
    evidence_used: list[str]
    evidence_missing: list[str]
    likely_causes: list[str]
    backend_actions: list[str]
    field_actions: list[str]
    dispatch_required: bool
    dispatch_priority: Literal["none", "low", "medium", "high"]
    explanation: str
    next_best_check: str
```

## Proposed Deterministic Diagnosis Flow

The engine should follow the required order and stop overcommitting early.

### Stage 1. Inventory truth
- resolve expected unit
- expected MAC
- expected controller
- expected service/auth identity
- expected switch/port/VLAN when known

### Stage 2. L2 presence truth
- search expected MAC on expected port
- search any MAC on expected port
- search expected MAC globally
- detect MAC mismatch, moved MAC, or swapped device

Hard rule:
- if expected MAC is live anywhere on the bridge table, do not classify as unplugged

### Stage 3. Controller truth
- is device known
- is mapping correct
- is online vs stale
- does controller agree with switch evidence

### Stage 4. Auth/session truth
- active PPPoE
- failed PPPoE
- no attempt
- duplicate session
- disabled/bad credentials

### Stage 5. DHCP truth
- expected or not
- discover seen
- offer seen
- correct server vs rogue server
- wrong VLAN/broadcast domain clues

### Stage 6. L1 physical truth
- port up/down
- speed
- duplex
- errors
- flaps
- PoE when relevant

### Stage 7. Service truth
- management only vs customer service
- gateway reachability
- IP presence
- DNS or routing-specific symptoms

### Stage 8. Decision
- backend-fixable
- field-dispatch-required
- needs-more-evidence

## Proposed Status Mapping

These are the target statuses, not current implementation.

- `HEALTHY`
- `NOT_SEEN_ANYWHERE`
- `L2_PRESENT_NO_SERVICE`
- `DEGRADED_LINK_BAD_CABLE_SUSPECTED`
- `CONTROLLER_MAPPING_MISMATCH`
- `INVENTORY_MAC_MISMATCH`
- `DEVICE_SWAPPED_OR_WRONG_UNIT`
- `PPPoE_AUTH_FAILURE`
- `PPPoE_NO_ATTEMPT`
- `DHCP_NO_OFFER`
- `DHCP_ROGUE_OR_WRONG_SERVER`
- `SWITCH_PORT_DISABLED_OR_WRONG_VLAN`
- `CONTROLLER_STALE_DEVICE`
- `NEEDS_MORE_EVIDENCE`

Important translation rule:
- workbook labels, web UI labels, and operator prose should all derive from these statuses and the same diagnosis object

## Collector / Normalizer / Correlator / Diagnosis Split

Recommended module structure:

- `collectors/`
  - fetch raw facts only
  - examples: bridge hosts, PPP sessions, DHCP logs, controller records, port counters

- `normalizers/`
  - turn raw records into common normalized forms
  - normalize MACs, ports, timestamps, controller records, PPP errors

- `correlators/`
  - map unit to expected MAC, expected port, live MAC, moved MAC, controller identity
  - build `UnitEvidence`

- `diagnosis/`
  - deterministic status engine
  - explicit contradiction and confidence rules

- `actions/`
  - derive backend actions, field actions, dispatch requirement

- `renderers/`
  - workbook rendering
  - NOC prose
  - tech-facing JSON
  - API presentation

## Recommended Phase Plan After This Audit

### Phase 2. Build evidence model

First moves:
- add typed `UnitEvidence`
- add evidence collectors for inventory, bridge, controller, PPPoE, DHCP, and physical state
- add stale-source tracking and contradiction lists

Do not:
- replace operator outputs yet
- remove old workbook logic yet

### Phase 3. Build deterministic diagnosis engine

First target:
- one function that accepts `UnitEvidence` and returns `Diagnosis`

Required rules on day one:
- live MAC means not unplugged
- controller mismatch alone is backend-first, not dispatch-first
- no evidence should produce `NEEDS_MORE_EVIDENCE` instead of guesswork

### Phase 4. Add scenario tests

Use real fixtures and explicit scenario tests for:
- live MAC, no service
- degraded 100M link with errors/flaps
- no MAC anywhere
- controller assignment mismatch
- wrong MAC on expected port
- stale controller vs live switch contradiction
- PPPoE auth failure
- PPPoE no attempt
- DHCP no offer
- rogue DHCP

### Phase 5. Replace old labels

Replace:
- workbook-only root-cause labels
- renderer-only domain labels

With:
- diagnosis-derived labels

### Phase 6. Split renderer outputs

Produce:
- NOC-facing summary
- field-tech summary
- backend-fix summary
- stable JSON diagnosis schema

### Phase 7. Fill collector gaps

Needed gaps:
- link speed/duplex/errors/flaps
- PPPoE failure reasons
- DHCP transaction evidence
- switch VLAN state
- controller last-seen freshness

## Immediate Findings To Carry Forward

1. Do not build new diagnosis logic into `audits/jake_audit_workbook.py`.
That file should become a renderer over central diagnosis results.

2. Do not continue using `run_operator_query()` as a primary execution path.
Move toward `IntentDispatcher -> run_structured_intent() -> diagnosis engine`.

3. Preserve `trace_mac()` style outputs.
They are already close to a good collector/correlator boundary.

4. Refactor `get_cpe_state()` into evidence gathering, not final health judgment.

5. Treat `correlate_customer_fault_domain()` as a temporary prototype to be replaced, not expanded.

6. Add a stable diagnosis schema before changing user-facing prose.

## Runtime Verification Notes

Commands run during audit:
- `.venv/bin/python -m pytest tests/test_query_baseline.py -q`
  - passed
- `.venv/bin/python -m pytest tests/test_audit_fixture_validation.py tests/test_query_baseline.py -q`
  - query baseline passed
  - audit fixture validation failed against current reviewed baseline

Observed audit test drift:
- current `audits/jake_audit_workbook.py` preserves inventory MAC in one bug-adjusted path where the reviewed baseline expected the live MAC to overwrite it
- workbook weighted ready result drifted from `57` to `29`

This drift does not change the Phase 1 audit conclusions, but it means workbook behavior is already unstable relative to the reviewed baseline and should be handled carefully before diagnosis refactors.

## Bottom Line

The codebase already contains enough raw evidence sources to build the required diagnosis engine.

What it does not yet have is:
- one normalized evidence object
- one deterministic diagnosis engine
- one stable diagnosis schema
- a clean separation between understanding, collection, diagnosis, and rendering

That is the real foundation task. More features should wait until that center exists.
