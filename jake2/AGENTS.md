# Jake2 Agent Guide

## System Model

Jake2 is a clean rebuild of Jake with behavior preserved and structure improved.

Jake2 has two strictly separated layers:

1. Understanding layer
   - Accepts raw operator natural language.
   - Classifies intent.
   - Extracts entities.
   - Produces a structured intent object with confidence.
   - Never executes queries directly.
   - Never touches live network data directly.

2. Execution layer
   - Accepts only structured intent objects.
   - Runs deterministic query and audit logic.
   - Produces trusted outputs grounded in local data and explicit runtime integrations.
   - Never receives raw natural language.
   - Never calls the LLM directly.

Target module ownership:

- `core/intent_schema.py`
  - intent contract definitions
- `core/intent_parser.py`
  - understanding layer parser
- `core/dispatch.py`
  - confidence gate between understanding and execution
- `core/query_core.py`
  - deterministic execution core
- `agents/ollama_client.py`
  - Ollama transport only
- `audits/`
  - workbook generation and audit business rules
- `mcp/`
  - runtime integrations and explicit MCP wiring

## Dependency Classification Rules

Every dependency must be classified as one of:

- `code`
  - local Python modules and scripts that are part of Jake2 runtime behavior
- `runtime_service`
  - reachable services such as Ollama, NetBox, Alertmanager, TAUC, Vilo, cnWave, Splynx, LynxMSP
- `data_artifact`
  - local runtime or fixture data such as CSV, JSON, DB snapshots
- `config_secret`
  - secrets, passwords, API tokens, client certs, webhook URLs
- `training_reference`
  - training corpus, runbooks, reference docs, prompt corpora, eval material

Rules:

- `core/` may depend on local code and local data contracts only.
- `core/` must not directly depend on training or RAG assets.
- `mcp/` may depend on runtime services and config secrets through explicit configuration.
- `agents/` may depend on model runtime services only.
- `audits/` may depend on deterministic core plus explicit runtime adapters and local artifacts.
- `references/` and `docs/training/` are never imported by runtime code.

## Audit Logic Contract

The audit subsystem preserves workbook behavior and business rules from old Jake.

Non-negotiable contract items:

- Existing row field names are load-bearing.
- Locked string values must remain verbatim.
- `_known_mac_bug_kind` remains a typed function returning:
  - `"first_octet"`
  - `"last_octet"`
  - `None`
- Controller mismatch alone must not populate MAC CPE.
- Switch-local MAC sightings must not count as CPE evidence.
- Every row state must remain explainable from observed evidence and applied rules.

See `AUDIT_RULES.md` for the detailed rule inventory.

## Interface Contracts

### `_known_mac_bug_kind`

- Signature: `(str | None, str | None) -> str | None`
- Valid returns:
  - `"first_octet"`
  - `"last_octet"`
  - `None`
- Never returns `bool`
- Never raises on `None` input

### Audit Row Schema

- All existing field names are part of the contract.
- Fields may not be renamed without logging a behavioral change in `PROPOSED_CHANGES.md`.
- Required fields may not be added without a default value.

### Query Response Structure

- `core/query_core.py` response schema is a contract.
- `run_operator_query(ops, query)` returns a JSON-serializable object with these top-level fields:
  - `query`
    - raw operator input string
  - `matched_action`
    - deterministic action selected by `parse_operator_query`
  - `params`
    - parsed parameter object passed into the action handler
  - `operator_summary`
    - operator-facing deterministic summary string
  - `assistant_answer`
    - same value as `operator_summary` for backward compatibility
  - `result`
    - raw action-specific payload returned by the selected handler
  - `preferred_mcp`
    - preferred troubleshooting MCP name or `None`
  - `preferred_mcp_reason`
    - explanation string for the preferred troubleshooting MCP choice
  - `preferred_mcp_cues`
    - list of matched cues used to justify the preferred troubleshooting MCP
- `matched_action`, `params`, `result`, `operator_summary`, and `assistant_answer` are load-bearing fields and must remain stable unless a behavioral change is logged in `PROPOSED_CHANGES.md`.

### Intent Parser Output Schema

This is now a committed contract:

```json
{
  "intent": "<intent_name>",
  "entities": {
    "site_id": "<site or null>",
    "building": "<building or null>",
    "unit": "<unit or null>",
    "device": "<device identifier or null>",
    "scope": "<all | building | unit | device>"
  },
  "confidence": 0.0,
  "ambiguous": false,
  "clarification_needed": null,
  "raw": "<original operator input>"
}
```

The deterministic core must never receive raw natural language as input.

Understanding-layer gate thresholds are configured in `config/intent_parser.yaml`, not hardcoded:

- `execute_direct_min`
- `execute_with_note_min`
- `clarify_min`

Few-shot growth rules:

- confirmed successful examples are appended to `data/intent_examples.jsonl`
- only `confirmed: true` examples may be added
- the file must remain JSONL
- the file must never contain secrets or credentials

## Runtime Verification Rules

After each subsystem migration:

- deterministic core
  - run a basic query end-to-end against local data
- audit system
  - generate a workbook using fixture data
- config/runtime
  - validate the actual config/env loader used by migrated code
- understanding layer
  - send a test utterance through the parser
  - confirm structured JSON is returned
  - confirm confidence is present
  - confirm only structured intent reaches execution

Runtime failures must be classified as:

- `code_error`
- `config_error`
- `missing_runtime`
- `data_dependency`

## Prohibited Behaviors

The following are prohibited anywhere in Jake2:

- run-path wrappers
- `from module import *`
- runtime `sys.path` mutation or similar import hacks
- hardcoded absolute home-directory paths
- hardcoded sibling-repo paths
- silent copies from `~/Downloads`, `~/Documents`, or `~/Desktop`
- live secrets committed into the repo
- merged understanding and execution logic in the same function or module

## Known Technical Debt From Phase 1B

These eight silent-failure or ambiguity modes are already known and must be addressed in later phases.

1. `plain_english_ops.py:_call_with_timeout`
   - Classification: `silent_empty`
   - Current behavior: returns `None` on timeout or exception and erases cause.

2. `plain_english_ops.py:load_mikrotik_training_corpus`
   - Classification: `silent_empty`
   - Current behavior: returns `{}` on corpus load or parse failure.

3. `plain_english_ops.py` question and scenario match helpers
   - Classification: `silent_empty`
   - Current behavior: return `None` when source data is missing or no match is found, with no explicit operator signal.

4. `plain_english_ops.py` mixed deterministic and generative fallback path
   - Classification: `silent_wrong`
   - Current behavior: may produce plausible answers even when the deterministic path did not actually resolve.

5. `jake_audit_workbook.py:_call_with_timeout`
   - Classification: `silent_empty`
   - Current behavior: live evidence failures collapse to `None`.

6. `jake_audit_workbook.py:_load_vilo_inventory_snapshot`
   - Classification: `silent_empty`
   - Current behavior: inventory load or parse failures collapse to an empty dataset.

7. `jake_shared.py:load_env_file` and env aliasing
   - Classification: `ambiguous`
   - Current behavior: malformed or conflicting env data is ignored silently and aliasing can obscure source provenance.

8. `mcp/jake_ops_mcp.py` and old NL context-follow behavior
   - Classification: `silent_wrong` and `ambiguous`
   - Current behavior: generic env fallback keys and history-biased inference can blur source of truth and confidence.

These are known technical debt items, not accepted final behavior.

## Definition Of Done

Jake2 is complete only when:

- all Python files compile
- deterministic query CLI runs locally
- audit workbook generation runs locally on fixture data
- no hardcoded absolute home-directory references remain
- no runtime `sys.path` mutation remains
- no run-path wrappers remain
- no live secrets are committed
- no duplicate canonical module copies remain
- all load-bearing interfaces are documented
- all known silent failure modes have explicit handling
- all implicit knowledge is captured in docs and `# WHY:` tags
- runtime/config loading works from this repo alone
- understanding and deterministic execution remain separate
