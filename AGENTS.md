# AGENTS.md

## Purpose

This repository is an AI receptionist MVP with:

- a FastAPI backend in `backend/`
- a Next.js frontend dashboard in `frontend/`
- Twilio voice webhook handling at `POST /voice`
- SQLite persistence for call logs and appointment requests

Agents should prefer small, targeted changes that preserve the current MVP structure.

## Repo Layout

- `backend/app/main.py`: FastAPI app, routes, CORS, Twilio voice flow
- `backend/app/ai.py`: AI reply generation
- `backend/app/config.py`: environment-backed settings
- `backend/app/db.py`: SQLAlchemy engine, session, base
- `backend/app/models.py`: ORM models
- `backend/app/schemas.py`: Pydantic schemas
- `frontend/app/page.tsx`: dashboard home
- `frontend/app/calls/page.tsx`: call log UI
- `frontend/app/settings/page.tsx`: settings UI
- `frontend/app/onboarding/page.tsx`: onboarding UI
- `frontend/app/globals.css`: shared styles

## Run Commands

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Environment

Backend expects a `.env` file with values such as:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `BUSINESS_NAME`
- `BUSINESS_GREETING`
- `BUSINESS_HOURS`
- `BOOKING_ENABLED`

Frontend expects `.env.local` with:

- `NEXT_PUBLIC_API_BASE_URL`

Do not hardcode secrets. Keep environment access centralized in `backend/app/config.py` when backend config changes are needed.

## Backend Guidance

- Keep the ASGI app in `backend/app/main.py`.
- Prefer `uvicorn app.main:app` as the canonical startup target.
- Add API routes in `backend/app/main.py` unless there is a clear need to split modules.
- Keep response/request models in `backend/app/schemas.py`.
- Keep database schema changes in `backend/app/models.py` and wire them through existing SQLAlchemy setup.
- Preserve the current Twilio webhook contract for `/voice` unless the task explicitly requires changing it.
- Return TwiML responses for Twilio routes and JSON for dashboard/API routes.

## Frontend Guidance

- This frontend uses the Next.js App Router.
- Preserve the existing route structure under `frontend/app/`.
- Prefer server-safe, straightforward React code over adding extra abstractions for this small MVP.
- Keep API base URL usage driven by `NEXT_PUBLIC_API_BASE_URL`.
- Match the current simple dashboard style unless the task explicitly asks for a redesign.

## Testing And Verification

Minimum verification after changes:

- backend starts with `uvicorn app.main:app --reload --port 8000`
- `GET /` and `GET /health` respond successfully
- frontend builds or runs if frontend files were changed

If a change affects Twilio flow, verify:

- initial empty speech request returns TwiML with a `Gather`
- spoken input path logs a call and returns a spoken reply

## Change Rules

- Do not rewrite unrelated files.
- Do not commit generated `__pycache__` files.
- Prefer focused patches over broad refactors.
- If both frontend and backend need updates, keep API contracts explicit and synchronized.
- Document any new env vars in `README.md`.

## Known Project Constraints

- Persistence is currently SQLite, stored at `backend/receptionist.db`.
- Appointment capture is intentionally basic.
- Production-grade concerns like auth, Twilio signature validation, and calendar integration are not implemented yet.
