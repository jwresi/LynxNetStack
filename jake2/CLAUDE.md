# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

Jake2 is a network operations assistant for WISPs (Wireless Internet Service Providers). It is a controlled rebuild of a prior system ("Jake") with strict architectural discipline. It handles natural-language queries from operators and runs deterministic network audits.

## Commands

```bash
# Setup
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
cp config/.env.example config/.env   # then fill in real values

# Run tests
.venv/bin/python -m pytest -q

# Run a single test file
.venv/bin/python -m pytest tests/test_intent_parser.py -q

# CLI query
.venv/bin/python -m core.jake_query --help

# Launch WebUI + API server (port 8080)
./jake --serve
```

## Two-Layer Architecture

Jake2 enforces strict separation between two layers. Never merge them:

**Layer 1 — Understanding** (`core/intent_parser.py`, `core/intent_schema.py`, `core/dispatch.py`, `agents/ollama_client.py`):
- Accepts raw operator natural language
- Parses intent, extracts entities, scores confidence
- Returns a structured `IntentSchema` JSON object
- Never touches live network data or executes queries

**Layer 2 — Execution** (`core/query_core.py`, `mcp/`, `audits/`):
- Accepts only structured intent objects — never raw natural language
- Runs deterministic query and audit logic
- Never calls the LLM directly

The gate between layers is `core/dispatch.py`, which applies confidence thresholds from `config/intent_parser.yaml` (`execute_direct_min`, `execute_with_note_min`, `clarify_min`).

## Intent Schema Contract

The intent parser output is a committed contract:

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

## Query Response Contract

`run_operator_query(ops, query)` in `core/query_core.py` returns a JSON-serializable object. These top-level fields are load-bearing and must remain stable:

- `query`, `matched_action`, `params`, `operator_summary`, `assistant_answer` (alias of `operator_summary`), `result`, `preferred_mcp`, `preferred_mcp_reason`, `preferred_mcp_cues`

Any change to these fields must be logged in `PROPOSED_CHANGES.md`.

## Audit Contracts

The audit subsystem (`audits/`) preserves exact behavior from old Jake. Non-negotiable:

- Existing row field names are immutable
- `_known_mac_bug_kind(str|None, str|None) -> "first_octet" | "last_octet" | None` — never returns bool, never raises on None
- Controller mismatch alone must NOT populate `MAC CPE`
- Switch-local MAC sightings must NOT count as CPE evidence
- Audit row states: Green = correct device on correct port, Yellow = wrong placement, Red = device not seen

**Locked strings** (must remain verbatim): `Match`, `Bug-adjusted match`, `LAN-port MAC`, `Mismatch`, `MOVE CPE TO WAN PORT`, `MOVE CPE TO CORRECT UNIT`, `WRONG UNIT`, `UNKNOWN MAC ON PORT`

## Dependency Rules

| Package | May depend on |
|---------|--------------|
| `core/` | Local code and local data contracts only |
| `mcp/` | Runtime services and config secrets via explicit config |
| `agents/` | Model runtime services only |
| `audits/` | Deterministic core + explicit runtime adapters + local artifacts |
| `references/`, `docs/training/` | Never imported by runtime code |

## Prohibited Patterns

These are banned anywhere in Jake2:
- `from module import *`
- `sys.path` mutation or import hacks
- Hardcoded absolute home-directory or sibling-repo paths
- Live secrets committed to repo
- Merged understanding and execution logic in the same function or module
- Run-path wrappers

## Configuration

- Live secrets: `config/.env` (never committed; see `config/.env.example` for all 207 documented keys)
- TLS certs: `config/certs/` (not version-controlled; paths set via env vars)
- Intent parser thresholds: `config/intent_parser.yaml`
- Few-shot learning examples: `data/intent_examples.jsonl` (JSONL; only `confirmed: true` examples; no secrets)

## Key Implicit Knowledge

- SW1 and SW2 are distinct namespaces — no interface collapsing or cross-switch fallback
- Site `000004` (Cambridge) is G.hn over Positron — not GPON/OLT/fiber
- Site `000007` (NYCHA) is switch-access TP-Link and Vilo — does not inherit OLT assumptions
- OLT sites require ONU/optical reasoning; do not collapse to PPP-only summaries
- Site aliases reflect operator language and operational shorthand, not cosmetic names

## Runtime Failure Classification

Classify runtime failures as one of: `code_error`, `config_error`, `missing_runtime`, `data_dependency`. Silent failures that collapse to `None` or `{}` are known technical debt (see `AGENTS.md` for the 8 documented cases) — do not introduce new ones.

## Other Documentation

- `AGENTS.md` — system model, dependency rules, interface contracts, prohibited behaviors (read this first for any architectural work)
- `AUDIT_RULES.md` — detailed audit rule inventory
- `MIGRATION_NOTES.md` — phase notes and known technical debt from old Jake
- `PROPOSED_CHANGES.md` — planned architecture improvements (log breaking changes here)
