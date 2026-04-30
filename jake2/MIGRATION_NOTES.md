# Migration Notes

## Scope

Jake2 is a controlled rebuild of old Jake from `~/projects/jake`.

Goal:

- preserve deterministic behavior
- preserve audit/workbook business rules
- preserve required data and useful references
- rebuild structure so the system is reproducible and self-contained

## Canonical File Decisions

- `jake_query_core.py`
  - Root version is canonical by explicit project rule.
  - Note: this conflicts with generic mtime/size heuristics because `scripts/jake_query_core.py` is newer and larger.
  - Accepted project decision: proceed with root version as authoritative.
  - If Phase 3 discovers behavior gaps relative to the scripts copy, log them in `PROPOSED_CHANGES.md`.

- `mcp/jake_ops_mcp.py`
  - Canonical location is `mcp/jake_ops_mcp.py`.

- `jake_audit_workbook.py`
  - Root version is canonical by explicit project rule.

## Quarantine Decisions

- `local_ollama_ops/`
  - quarantined as active runtime
  - reason: cross-repo front door over `~/projects`, mixed understanding/execution architecture, external env sourcing

- `plain_english_ops.py`
  - quarantined as executable runtime
  - reason: useful behavior reference, but current implementation violates two-layer architecture

- `plain_english_chat_server.py`
  - quarantined as executable runtime
  - reason: depends on old mixed front-door architecture

- root wrapper scripts using run-path wrappers
  - quarantined
  - reason: prohibited pattern

- top-level duplicate MCP wrappers outside `mcp/`
  - quarantined
  - reason: shadow copies and duplicate entrypoints

## External Dependency Inventory

### Runtime Services

- Ollama
- NetBox
- Alertmanager
- Bigmac
- TAUC cloud, ACS, OLT APIs
- Vilo API and Vilo portal API
- cnWave exporter and cnWave controller
- Splynx
- LynxMSP API or DB
- `ssh_mcp`
- OLT telnet access
- Positron access

### Local Runtime/Data Dependencies

- `network_map.db`
  - runtime-generated
  - will be treated as a test snapshot only inside Jake2

- old Jake runtime artifacts used by logic:
  - `data/nycha_info.csv`
  - `data/nycha_unit_mac_map.csv`
  - `data/vilo_inventory_*.json`
  - `output/online_cpes_latest.csv`
  - `output/tauc_nycha_cpe_audit_latest.csv`

### Host-Local Config Paths

- AnythingLLM MCP config under:
  - `~/Library/Application Support/anythingllm-desktop/storage/plugins/anythingllm_mcp_servers.json`

## Secrets Inventory And Placeholder Plan

Live values are intentionally excluded from Jake2.

Known key names from old Jake env/config sources:

- `NETBOX_TOKEN`
- `CAMBIUM_USERNAME`
- `CAMBIUM_PASSWORD`
- `SIKLU_USERNAME`
- `SIKLU_PASSWORD`
- `TPLINK_ID_EMAIL`
- `TPLINK_ID_PASSWORD`
- `TAUC_CLOUD_CLIENT_ID`
- `TAUC_CLOUD_CLIENT_SECRET`
- `TAUC_CLOUD_CLIENT_CERT`
- `TAUC_CLOUD_CLIENT_KEY`
- `TAUC_VERIFY_SSL`
- `VILO_APPKEY`
- `VILO_APPSECRET`
- `VILO_PORTAL_TOKEN`
- `SSH_MCP_USERNAME`
- `SSH_MCP_PASSWORD`
- `SPLYNX_KEY`
- `SPLYNX_SECRET`
- generic legacy keys such as `username`, `password`, `olt_user`, `olt_password`

Planned handling:

- create `config/.env.example`
- store placeholders only
- normalize legacy aliases into explicit Jake2 names
- do not commit live values

### Client TLS Certs

The following old host-local client cert paths are treated as:

- `config_secret`
- `required_runtime_data`

Old host-local references:

- `~/Downloads/certificate/client.crt`
- `~/Downloads/certificate/client.key`

Jake2 plan:

- intended repo-relative home: `config/certs/`
- no live certs are copied into the repo
- cert/key paths must be configured via env vars
- placeholder documentation only

## Silent Failure Modes Identified

- `plain_english_ops.py:_call_with_timeout`
  - `silent_empty`
- `plain_english_ops.py:load_mikrotik_training_corpus`
  - `silent_empty`
- `plain_english_ops.py` question/scenario match fallthrough
  - `silent_empty`
- `plain_english_ops.py` mixed deterministic and generative fallback
  - `silent_wrong`
- `jake_audit_workbook.py:_call_with_timeout`
  - `silent_empty`
- `jake_audit_workbook.py:_load_vilo_inventory_snapshot`
  - `silent_empty`
- `jake_shared.py` env loading and aliasing
  - `ambiguous`
- `mcp/jake_ops_mcp.py` fallback keys and old history-biased inference paths
  - `silent_wrong` / `ambiguous`

These are known technical debt items that later phases must resolve explicitly.

## Implicit Knowledge Inventory

Items that must be captured later in code and docs:

- site aliases are operator shorthand, not presentation labels
- site service profiles encode real topology differences
- Cambridge uses G.hn / Positron logic and must not be treated like an OLT site
- NYCHA switch-access reasoning differs from OLT/ONU reasoning
- controller verification is corroboration, not unconditional truth
- edge-port evidence outranks generic switch-local MAC sightings
- prompt regressions encode real operator phrasing and clarification expectations

## Regression Baseline Status

- deterministic core baseline
  - captured in `tests/baselines/query_baseline.json`
  - sample queries were executed against old canonical root logic and migrated Jake2 using the same local `data/network_map.db` snapshot
  - operator-facing contract fields matched for all sampled queries:
    - `matched_action`
    - `params`
    - `operator_summary`
    - `assistant_answer`
  - full raw payloads did not match because old Jake loaded live env-backed runtime integrations and Jake2 intentionally does not carry those secrets yet
  - classification: `config_error` for baseline drift in config-dependent `result` subfields, not a deterministic-core regression
- audit workbook baseline
  - captured in `tests/baselines/audit_baseline.json`
  - fixture workbook generated at `tests/baselines/audit_fixture_workbook.xlsx`
  - baseline covers:
    - MAC bug states: exact, `first_octet`, `last_octet`, no match
    - row states: green, yellow, red
    - locked strings: `MOVE CPE TO WAN PORT`, `MOVE CPE TO CORRECT UNIT`, `WRONG UNIT`, `UNKNOWN MAC ON PORT`
  - `_call_with_timeout` failure path now produces explicit classified red-state output:
    - `LIVE LOOKUP FAILED`
  - malformed Vilo snapshot is surfaced as explicit `data_dependency`, not flattened to empty inventory
- understanding-layer prompt corpus extraction
  - deferred to Phase 8

## Vendor Adapter Boundary Risk

`mcp/vendor_adapters.py` is classified as `runtime_integration`, not deterministic core.

Known risk:

- it depends on MCP-side clients such as `mcp.tauc_mcp` and `mcp.vilo_mcp`
- this creates a coupling risk between integration adapters and the MCP layer itself
- Phase 3 must watch for circular dependency or boundary leakage if query-core migration tries to call these adapters directly

Recommended rule:

- keep vendor adapters under `mcp/` or another explicit integration boundary
- do not move them into `core/`

### Phase 3 import-graph result

Mapped import graph:

- `mcp/jake_ops_mcp.py`
  - imports `core.shared`
  - imports `mcp.vendor_adapters`
- `mcp/vendor_adapters.py`
  - imports `mcp.tauc_mcp`
  - imports `mcp.vilo_mcp`
- `mcp/tauc_mcp.py`
  - does not import `vendor_adapters`
- `mcp/vilo_mcp.py`
  - does not import `vendor_adapters`

Result:

- no direct circular import exists in the current old-Jake graph
- `vendor_adapters.py` remains a boundary risk because it directly instantiates MCP-side clients instead of receiving neutral injected dependencies
- Phase 3 resolution:
  - keep `vendor_adapters.py` in `mcp/`
  - do not move it into `core/`
  - keep the direct MCP-client dependency for now because there is no active circular import to break
  - document the coupling as a known boundary risk for later cleanup

Classification:

- `runtime_integration`
- behavior-preserving structural containment

## Phase 3 notes

- `jake_shared.py` migrated to `core/shared.py`
  - added `# WHY:` comments for site aliases, service-profile distinctions, and env aliasing decisions
  - removed `local_ollama_ops/.env` from env candidate loading
  - hardened `load_env_file()` so malformed lines and conflicting duplicate keys no longer fail silently
  - preserved existing precedence rule: process env still wins over file-provided values

- `jake_tooling.py` migrated to `core/tooling.py`
  - classified as `code`
  - runtime support module for deterministic query routing and troubleshooting scenario selection
  - not reference-only material

- deterministic core runtime verification
  - copied old `network_map.db` into `data/network_map.db` as a local snapshot for Phase 3 validation
  - verified local query run:
    - `python3 core/jake_query.py --summary how many customers online at 000007`
    - result: `219 customers are currently online right now.`

## Phase 4 notes
## Phase 8 notes

- Extracted old Jake NL regression material into:
  - `tests/fixtures/nl/everyday_language_regression.json`
  - `tests/fixtures/nl/field_prompt_regression.json`
  - `tests/fixtures/nl/human_ops_regression.json`
- These fixtures preserve operator phrasing as test ground truth only.
- They are not runtime imports and do not override deterministic truth.

- Understanding-layer implementation:
  - `agents/ollama_client.py`
    - loads `OLLAMA_ENDPOINT`, `OLLAMA_MODEL`, and `OLLAMA_INTENT_TIMEOUT`
    - returns raw model text only
    - classifies failures as `missing_runtime`, `code_error`, or `config_error`
  - `core/intent_schema.py`
    - now defines the committed intent parser contract
  - `core/intent_parser.py`
    - uses config-driven thresholds and vocabulary
    - performs heuristic parsing first for stable known cases
    - falls back to Ollama only when heuristics do not resolve
  - `core/dispatch.py`
    - gates execution using thresholds from `config/intent_parser.yaml`
    - routes only structured intent objects into deterministic execution

- OLLAMA model configuration:
  - local `config/.env` now sets `OLLAMA_MODEL=gemma4:26b`
  - Phase 8 must not assume a bare `gemma4` alias exists

- Existing NL handling replacement:
  - old `plain_english_ops.py` remains quarantined
  - preserved behavior sources are now explicit fixture files and config vocabulary

- Vocabulary decisions:
  - minimum viable intent list is restricted to existing deterministic core actions:
    - `get_online_customers`
    - `get_site_summary`
    - `get_site_alerts`
    - `dispatch_troubleshooting_scenarios`
    - `find_cpe_candidates`

- `JakeOps.get_site_alerts`
  - verified present with the exact method name `get_site_alerts`
  - no structured-execution name correction was needed in `run_structured_intent`

## Capability Expansion notes

- Phase 2 migrated understanding-layer support for:
  - `get_cpe_state`
  - `trace_mac`
  - `get_live_olt_ont_summary`
- These actions already existed in deterministic Jake2 runtime code.
- The capability expansion added:
  - structured execution support in `run_structured_intent()`
  - intent registration in `config/intent_parser.yaml`
  - heuristic routing in `core/intent_parser.py`
  - NL fixture files under `tests/fixtures/nl/`
  - reviewed baseline entries in `tests/baselines/query_baseline.json`

- `get_customer_access_trace`
  - not migrated in this batch
  - accepted as the interim subscriber-question path once available
  - currently blocked in the local validation environment because `JakeOps.get_customer_access_trace()` requires NetBox-backed building context and the current Jake2 runtime reports `NetBox is not configured`
  - this remains a known environment dependency and was intentionally not fixed during the learning-loop phase

- `get_vilo_target_summary`
  - not migrated in this batch
  - currently blocked in the local validation environment because the required Vilo API runtime is not reachable during validation

- `subscriber_lookup`
  - remains blocked and explicitly not required for this batch
  - `get_customer_access_trace` remains the intended interim path for subscriber questions once its runtime dependency is available

- `jake_audit_workbook.py` migrated to `audits/jake_audit_workbook.py`
  - `generate_nycha_audit_workbook` stays in the audit subsystem
  - reason: even the scripts query core imported it from the audit module, so it is an audit entry point, not deterministic-core ownership

- `scripts/batch_nycha_audit_summary.py` migrated to `audits/batch_nycha_audit_summary.py`
  - import bootstrap rebuilt without runtime `sys.path` mutation

- audit reliability improvements
  - `_call_with_timeout` no longer returns silent `None`
  - audit live-context collection now records explicit classified failures
  - red-state output becomes `LIVE LOOKUP FAILED` when runtime collection fails
  - `_load_vilo_inventory_snapshot` now returns explicit `data_dependency` on missing or malformed snapshot

- Phase 5 watch item
  - `mcp/jake_ops_mcp.py` still contains generic env alias handling around `username`, `password`, `TPLINK_ID_PASSWORD`, and `SSH_MCP_PASSWORD`
  - `JAKE_ENV_CONFLICTS` now captures conflicts, but provenance is still not normalized
  - Phase 5 must replace those generic aliases with explicit named variables

## Phase 5 notes

- packaging and import normalization
  - added `pyproject.toml` with declared package discovery and explicit runtime dependencies
  - declared dependencies:
    - `openpyxl`
    - `librouteros`
  - removed local bootstrap loader helpers from:
    - `core/jake_query.py`
    - `audits/batch_nycha_audit_summary.py`
    - `tests/fixtures/audit/run_audit_fixture_validation.py`
  - intended runtime entry points now use normal package imports and support:
    - `python3 -m core.jake_query`
    - `python3 -m audits.batch_nycha_audit_summary`

- environment variable normalization in `mcp/jake_ops_mcp.py`
  - normalized legacy generic `username` reads to `SSH_MCP_USERNAME`
  - normalized legacy generic `password` reads to `SSH_MCP_PASSWORD`
  - normalized `TPLINK_ID_PASSWORD` consumption to `TAUC_PASSWORD`
  - retained compatibility aliases in `core/shared.py` so old env files can still seed the explicit Jake2 names
  - classification: `reliability`
  - behavior-preserving reason: happy-path credentials still resolve, but provenance is now explicit in runtime code paths

- config placeholders
  - added `config/.env.example` with grouped placeholder entries for all discovered secret-bearing or runtime-config keys
  - added `config/certs/.gitkeep`
  - added `config/certs/README.md`
  - certs remain manual local material and are never committed

- Phase 6 planned structural cleanup
  - `tests/fixtures/audit/run_audit_fixture_validation.py` still monkey-patches `generate_nycha_audit_workbook.__globals__`
  - planned fix: add a proper `_live_context_override` parameter to `generate_nycha_audit_workbook`
  - classification: `structural`
  - reason: removes test-only monkey-patching and makes fixture injection explicit

- Phase 6 planned fixture expansion
  - add a workbook-generation fixture case that exercises `WRONG UNIT` through the real workbook entry point, not only through a synthetic `AuditRow`
  - classification: `test`
  - reason: protects the locked string and color-logic contract at the actual subsystem boundary

## Phase 6 notes

- audit testability cleanup
  - added `_live_context_override` to `audits.generate_nycha_audit_workbook`
  - removed the old test-time global monkey-patch approach
  - classification: `structural`
  - behavior-preserving reason: normal runtime still builds live context internally; tests now inject explicit fixture context without mutating module globals

- audit workbook fixture coverage
  - added a real workbook-entry-point `WRONG UNIT` case
  - the new fixture row uses unit `1G` with a PPPoE label and live bridge-host evidence that both point to `1A`
  - this restores a previously unreachable locked-string state in the migrated workbook path
  - classification: `test`

- audit baseline handling
  - replaced the old ad hoc fixture-regeneration script with reviewed pytest assertions
  - `tests/test_audit_fixture_validation.py` now compares generated workbook rows and workbook cell content against committed baseline artifacts
  - classification: `test`

- query baseline handling
  - replaced the oversized comparison dump in `tests/baselines/query_baseline.json` with a curated, human-readable contract baseline
  - expanded baseline coverage now includes:
    - site alias resolution: `nycha -> 000007`
    - OLT site query: `chenoweth`
    - Cambridge G.hn query: `cambridge`
    - clean empty-result query: `show probable vilo cpes on sweetwater`
    - preferred-MCP routing query: `which mcp should i use for bridge vlan issues at nycha`
  - classification: `test`

- repo hygiene for validation gate
  - added `.gitignore` entries for generated env, cache, output, and workbook artifacts
  - moved the temporary validation virtualenv out of the repo so literal path grep checks apply only to source-controlled Jake2 contents
  - classification: `structural`

## Phase 7 notes

- training/reference inventory from old Jake
  - `docs/controllers` -> `migrate` to `references/controllers`
  - `docs/runbooks` -> `migrate` to `references/runbooks`
  - `docs/sites` -> `migrate` to `references/sites`
  - `docs/external` -> `migrate` to `references/external`
  - `docs/training` -> `migrate` to `docs/training/legacy_docs`
  - `docs/network_fault_scenarios.docx` -> `migrate` to `docs/training/source_docs`
  - `docs/jake` -> `phase_8_source`
  - `training/configs` -> `migrate` to `docs/training/configs`
  - `training/knowledgebase` -> `migrate` to `docs/training/knowledgebase`
  - `training/README.md`, `training/requirements-*.txt` -> `migrate` to `docs/training`
  - `training/data` -> `phase_8_source`
  - `training/exports` -> `phase_8_source`
  - `training/source_intake` -> `phase_8_source`
  - `training/.venv312` -> `exclude`
  - `training/output` -> `exclude`
  - `references/crs-vlan-detective` -> `migrate`
  - `references/tikbreak` -> `migrate`
  - `references/tikfig` -> `migrate`
  - `references/vendor` -> `migrate`
  - root `references/*.md` -> `migrate`
  - `rag/` -> `migrate` as isolated legacy reference under `references/rag_legacy`
  - `docs/.DS_Store` and `rag/__pycache__` -> `exclude`

- runtime boundary verification
  - checked `core/`, `audits/`, `mcp/`, and `agents/` for imports of `docs/`, `training/`, `references/`, `rag/`, and `tests/fixtures/nl/`
  - result: no current runtime imports of training/reference material were found
  - classification: `structural`
  - no active boundary violation detected in Phase 7

- Ollama preflight for Phase 8
  - configured endpoint from `config/.env.example`: `http://127.0.0.1:11434`
  - configured model from `config/.env.example`: `gemma4`
  - local verification:
    - `curl http://127.0.0.1:11434/api/tags` succeeded
    - endpoint returned model inventory JSON
    - `ollama list` succeeded
    - `gemma4:26b` is available locally
  - note:
    - requested Jake2 model name is `gemma4`
    - installed local variant is `gemma4:26b`
    - Phase 8 should set `OLLAMA_MODEL=gemma4:26b` or another explicit local variant rather than assuming the short alias resolves
  - classification: `runtime_service`

## Prompt Regression Corpus Handling

These files are preserved as Phase 8 source material, not active runtime:

- `scripts/run_jake_everyday_language_regression.py`
- related `run_jake_*regression.py`
- related `run_jake_*knowledge_check.py`
- related `run_jake_*checks.py`

Planned Jake2 destination:

- extracted prompt/response pairs in `tests/fixtures/nl/`
- selective reference material in `references/`

## Phase 3 notes

- learning loop
  - every successful query execution now writes `output/.jake_last_query.json`
  - saved fields:
    - `raw`
    - `resolved_intent`
    - `resolved_site`
    - `confidence`
    - `timestamp`
  - `core/jake_query.py --confirm` now reads the last query record and appends a confirmed example to `data/intent_examples.jsonl`
  - confirmed example fields:
    - `raw`
    - `resolved_intent`
    - `resolved_site`
    - `confidence`
    - `confirmed`
    - `timestamp`
  - append-only retention rule:
    - keep the newest 500 confirmed examples in `data/intent_examples.jsonl`
    - archive overflow to `data/intent_examples_archive.jsonl`

- operator wrapper
  - added repo-root `jake` wrapper script
  - default behavior:
    - sets `JAKE_OPS_DB=data/network_map.db` unless already provided
    - prefers `.venv/bin/python` when present
    - otherwise falls back to `python3`
  - supported operator flows:
    - `./jake "what is wrong with DC:62:79:9D:C1:AD"`
    - `./jake --summary "how many customers online at nycha"`
    - `./jake --confirm`

- production follow-up fixes after Phase 3 learning-loop rollout
  - normalized `NETBOX_BASE_URL` -> `NETBOX_URL` in `core/shared.py`
  - reason:
    - operator `config/.env` already carried `NETBOX_BASE_URL`
    - Jake2 runtime code read `NETBOX_URL`
    - this was a config naming mismatch, not a business-rule change
  - `get_customer_access_trace`
    - now wired into the understanding layer and structured execution path
    - added to `config/intent_parser.yaml`
    - added heuristic parsing for subscriber/device labels such as:
      - `Chenoweth1Unit201`
      - `NYCHA726-752Fenimore1B`
    - conflict resolution:
      - when `what can you tell me about ...` targets a subscriber-style label, Jake now routes to `get_customer_access_trace` instead of `get_site_summary`
  - baseline impact
    - enabling the NetBox URL alias exposed previously hidden device-inventory context for site summaries
    - reviewed baseline expectations for `chenoweth` and `cambridge` were updated from `0 tracked devices` to the current NetBox-backed counts
    - classification: `stale_data_expectation`, not `code_regression`

- Bigmac primary MAC intelligence
  - `mcp/bigmac_readonly_mcp.py` is now migrated into Jake2 and uses `core/shared.py seed_project_envs()` for config loading
  - Jake2 now treats Bigmac `/api/search` as the primary MAC intelligence source for:
    - `trace_mac`
    - `get_cpe_state`
  - `network_map.db` bridge-host evidence remains a fallback and corroboration source
  - Bigmac-backed operator output now includes:
    - last seen device / port / VLAN
    - last seen timestamp
    - hostname when present
    - client IP when present
    - freshness classification:
      - within 1 hour = healthy signal
      - within 24 hours = stale but present
      - older = possibly offline
  - production significance:
    - this supersedes the planned multi-site `network_map.db` refresh work for MAC lookup accuracy

## Unresolved Risks

- canonical root `jake_query_core.py` may omit newer behavior from `scripts/jake_query_core.py`
- `mcp/jake_ops_mcp.py` is large and likely contains hidden duplicate logic
- some behavior currently depends on generated CSV/JSON outputs instead of stable interfaces
- env aliasing and generic secret keys obscure provenance
- old NL/runtime code mixes preserved behavior with rejected architecture
