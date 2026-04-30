# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: Flask API (`server.py`), Python deps (`requirements.txt`).
- `frontend/`: React UI (`src/`, Tailwind config), `package.json` scripts.
- `configs/`: Generated device configs (`*.rsc`).
- `routeros/`: RouterOS package (`routeros.npk`, symlink to versioned `.npk`).
- `ssl/`: Certificates (if used).
- `docker-compose.yml`: Orchestrates `frontend`, `backend`, and `tftp` services.
- `.env`: Runtime config (ports, interface, network range).

## Quick Start
- Ensure Docker Desktop is running. If on macOS, run `./setup.sh` once.
- Start everything: `make up` (or `docker compose up -d`).
- View logs: `make logs`; stop: `make down`.
- Frontend: http://localhost:3000 (`#provision` for techs, `#setup` for admin)
- Backend: http://localhost:5001 (`/api/status`)
- Tests: `pytest -q` (see TESTING.md)
 - Provision toolbar: Import CSV, Sample CSV, Show incomplete only

## Build, Test, and Development Commands
- Build/run: `make build && make up`; status: `make ps`.
- Backend dev: `make backend` (defaults to `API_PORT=5001`).
- Frontend dev: `make frontend` (CRA dev server proxy to `5001`).
- Frontend tests: `cd frontend && npm test`.
- Backend tests: `pytest -q` (requires `pip install pytest`).

## Defaults & Hardened Configs
- Customer access ports: `edge=yes`, `horizon=1`, admit only untagged; BPDU-Guard enabled; loop-protect enabled.
- DHCP drop on `CUSTOMER` interface-list; PoE disabled on PoE-capable ports.
- Trunks: SFP+1 TrunkIn; others TrunkOut; RSTP enabled on bridge.

## Coding Style & Naming Conventions
- Python: 4-space indent; modules/functions `snake_case`; files `snake_case.py`. Prefer small, focused functions.
- React: Components `PascalCase.jsx`; hooks/utilities `camelCase.js`; keep UI in `frontend/src/` with cohesive folders.
- Styling: Tailwind utility classes; avoid ad-hoc inline styles unless needed.
- Lint/format: Use `react-scripts` defaults; if Prettier/Black are used locally, keep standard defaults.

## Testing Guidelines
- Frontend: Place tests next to code or in `__tests__/` using `*.test.js|*.test.jsx`. Cover critical flows (CSV import, provisioning actions, status polling).
- Backend: No test harness yet; if adding, use `pytest` under `backend/tests/` with `test_*.py`. Mock network/DHCP/SSH calls.
- Aim to test pure logic and API handlers; avoid flaky network-dependent tests.

## Commit & Pull Request Guidelines
- Use Conventional Commits (e.g., `feat: add provisioning status API`, `fix: handle missing npk`).
- Keep PRs focused and small; include a clear description, linked issues, and screenshots or curl examples for API/UI changes.
- Note any config changes to `.env` or `docker-compose.yml` and include migration steps.

## Security & Configuration Tips
- `.env` controls `NETINSTALL_INTERFACE`, `NETWORK_RANGE`, `API_PORT` (5001), `FRONTEND_PORT` (3000). Example: `NETINSTALL_INTERFACE=en0`.
- Do not commit RouterOS packages; ensure `routeros/routeros.npk` exists locally (read-only in containers).
- Services use privileged capabilities (`NET_ADMIN`, UDP 67/69). Run on trusted networks only; avoid exposing these ports publicly.
- DHCP listener is off by default; enable with `ENABLE_DHCP_LISTENER=1` if needed.
