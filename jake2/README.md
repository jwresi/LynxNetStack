# Jake2

Jake2 is a controlled rebuild of Jake focused on preserving behavior while replacing the old mixed workspace structure with a clean, reproducible, self-contained system.

The rebuild preserves:

- deterministic operator/query logic
- audit/workbook logic and business rules
- required data and artifacts
- useful training and reference material in isolated locations
- a future understanding layer that translates operator language into structured deterministic intent

## Architecture

Jake2 is organized as two layers:

1. Understanding layer
   - parses raw operator language into structured intent
   - scores confidence
   - never executes live logic directly

2. Execution layer
   - accepts structured intent only
   - runs deterministic query and audit logic
   - never receives raw natural language

Planned layout:

- `core/`
- `agents/`
- `mcp/`
- `audits/`
- `config/`
- `data/`
- `tests/fixtures/`
- `tests/fixtures/nl/`
- `tests/baselines/`
- `docs/training/`
- `references/`
- `quarantine/`

## Repo Status

Jake2 currently contains migrated deterministic query logic, audit/workbook logic, package metadata, config placeholders, and baseline artifacts.

- deterministic query execution lives under `core/`
- runtime integrations live under `mcp/`
- audit generation lives under `audits/`
- config placeholders live under `config/`
- baseline and fixture assets live under `tests/fixtures/` and `tests/baselines/`
- the understanding layer now lives under `core/intent_parser.py`, `core/intent_schema.py`, `core/dispatch.py`, and `agents/ollama_client.py`

## Getting Started

From a fresh clone:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
cp config/.env.example config/.env
# edit config/.env with real values
.venv/bin/python -m core.jake_query --help
./jake --serve
```

Notes:

- keep live secrets only in `config/.env`
- place client TLS certs under `config/certs/` and reference them from `config/.env`
- for a full local test pass after setup, run `.venv/bin/python -m pytest -q`
- to launch the WebUI API and browser, run `./jake --serve`

## Client TLS Certificates

Jake2 does not commit live client TLS certificates.

Planned local convention:

- intended repo-relative location: `config/certs/`
- live cert and key files are not stored in version control
- certificate paths must be configured through environment variables

Old host-local cert references discovered during migration:

- `~/Downloads/certificate/client.crt`
- `~/Downloads/certificate/client.key`

Those are treated as required runtime config material and must be documented, not copied.

## Secrets

Jake2 will use `config/.env.example` for placeholder documentation only.

Rules:

- no live tokens, passwords, webhook URLs, or client certs are committed
- env vars are documented with placeholders only
- legacy generic keys will be normalized to explicit names where possible
- installable dependencies are declared in `pyproject.toml`

## Data

Important notes:

- `network_map.db` is runtime-generated and not treated as canonical source code
- any DB copied into Jake2 will be a test snapshot only
- generated CSV and JSON outputs from old Jake are candidates for fixtures, not active source

## Training And Reference Material

Reference and training material are preserved in isolated locations:

- `docs/training/`
- `references/`
- `tests/fixtures/nl/`

The old prompt/regression corpus will be mined into fixtures for the future understanding layer rather than imported directly as runtime code.

## Natural Language Queries

Jake2 now supports a clean understanding layer in front of the deterministic core.

Flow:

1. raw operator language enters `core/intent_parser.py`
2. the parser returns structured intent JSON
3. `core/dispatch.py` applies confidence gates from `config/intent_parser.yaml`
4. only structured intent reaches deterministic execution

Current intent coverage is intentionally limited to deterministic actions that already exist in `core/query_core.py`.

Examples:

- `how many customers online at nycha`
- `what can you tell me about chenoweth`
- `which mcp should i use for bridge vlan issues at nycha`

Jake improves over time through reviewed examples stored in `data/intent_examples.jsonl`.
