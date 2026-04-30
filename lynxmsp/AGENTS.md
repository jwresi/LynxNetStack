# Repository Guidelines

## Project Structure & Module Organization
This repo is a FastAPI + React app with Docker for local and production runs.
- `backend/`: FastAPI app. Core API lives in `backend/app/main.py`, data models in `backend/app/database.py`, schemas in `backend/app/schemas.py`, and helpers in `backend/app/services/`.
- `frontend/`: React + TypeScript app. UI code in `frontend/src/` (components, pages, hooks), static assets in `frontend/public/`.
- `docker-compose.yml` and `docker-compose.prod.yml`: dev/prod orchestration.
- `test_crud_endpoints.py`: simple API smoke test script.
- `archived/`: legacy files; avoid new work here.

## Build, Test, and Development Commands
- `docker-compose up --build`: run dev stack (frontend on `:3000`, backend on `:8000`).
- `docker-compose -f docker-compose.prod.yml up --build -d`: run production stack.
- `docker-compose logs -f`: follow logs.
- `docker-compose exec frontend npm start|test|run build`: CRA dev server, tests, or production build.
- `docker-compose exec backend black app/`: format backend code (recommended).
- `python test_crud_endpoints.py`: run API CRUD checks (requires backend running).

## Coding Style & Naming Conventions
- Python: 4-space indentation, use Black formatting; prefer snake_case for modules/functions and PascalCase for classes/Pydantic models.
- React/TS: 2-space indentation; PascalCase for components (`CustomerDetail.tsx`), camelCase for hooks and variables (`useAuth`).
- Keep API routes and schema names consistent with existing patterns in `backend/app/main.py` and `backend/app/schemas.py`.

## Testing Guidelines
- Backend: no formal suite yet; use `test_crud_endpoints.py` for smoke tests or add pytest if you introduce complex logic.
- Frontend: CRA’s Jest setup is available; name tests like `ComponentName.test.tsx` under `frontend/src/`.
- Aim to cover new endpoints or UI flows you change.

## Commit & Pull Request Guidelines
- Commit messages in history are short, sentence case, and verb-led (e.g., “Fix API service to properly connect…”). Follow that style.
- PRs should include a concise summary, how to run/verify, and screenshots for UI changes. Link related issues or tickets if applicable.

## Security & Configuration Tips
- Backend env: `SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS`.
- Frontend env: `REACT_APP_API_URL`.
- Never commit real secrets; use local env files or Docker compose overrides.
