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

- If a new environment variable is introduced, update all three of: `backend/app/config.py`, `.env.example`, and `README.md` in the same change.

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
- backend tests pass with `python -m pytest backend/tests`
- `GET /health` responds successfully
- `POST /voice` returns valid TwiML for an empty speech request
- if frontend files were changed, frontend builds or runs successfully

If a change affects Twilio flow, verify:

- initial empty speech request returns TwiML with a `Gather`
- spoken input path logs a call and returns a spoken reply

## Change Rules

- Do not rewrite unrelated files.
- Do not commit generated `__pycache__` files.
- Prefer focused patches over broad refactors.
- If both frontend and backend need updates, keep API contracts explicit and synchronized.
- Document any new env vars in `README.md`.
- If a change affects system architecture, call flow, persistence, state handling, integration boundaries, or other developer-facing backend design, update `ARCHITECTURE.md` in the same change.
- Required documentation updates must be committed in the same change as the code they describe. Do not defer `README.md` or `ARCHITECTURE.md` updates to a later commit.

## Agent Operating Rules

- Read `AGENTS.md` before making changes.
- Prefer the smallest patch that fully solves the task.
- Preserve existing route names, request shapes, and response contracts unless explicitly asked to change them.
- If you change backend architecture, persistence, call flow, integrations, or state handling, update `ARCHITECTURE.md` in the same change.
- If you add a new dependency, justify it by necessity and keep the dependency count minimal.
- Before finishing, verify changed code paths with tests or a concrete local run command.
- Never silently degrade behavior; if a tradeoff is required, document it in `README.md` or `ARCHITECTURE.md`.

## Telephony Integration Notes

- Twilio voice webhooks must continue to use `POST /voice` unless explicitly changed.
- Responses to Twilio must always return valid TwiML.
- If modifying the call flow, preserve:
  - initial greeting
  - speech gather step
  - deterministic response generation
- Do not introduce blocking operations in the Twilio request path.

## AI And Prompting Rules

- Keep voice responses short, clear, and phone-friendly.
- Do not return long paragraphs for spoken responses.
- Prefer structured AI outputs when downstream logic depends on intents, slots, state, or external actions.
- Validate model output before using it in route handlers.
- Always provide a safe fallback path when external AI calls fail or return malformed data.
- Deterministic logic such as phone-number formatting, date normalization, validation, and persistence rules should live in code, not only in prompts.

## Database Changes

- All schema changes must be applied through SQLAlchemy models in `backend/app/models.py`.
- Maintain compatibility with the existing SQLite database at `backend/receptionist.db`.
- Prefer additive schema changes rather than destructive ones.
- If new fields are added, ensure existing rows remain valid.

## External Integrations

When adding integrations (for example Google Calendar or other APIs):

- Place integration logic in a dedicated service module inside `backend/app/`.
- Avoid placing external API logic directly in route handlers.
- Handle failures gracefully so that calls do not crash the Twilio flow.
- Persist any external identifiers (for example calendar event IDs) in the database.

## Reliability And Performance

- Protect Twilio request handling from slow or brittle external calls.
- Keep the request path resilient: handle timeouts, malformed responses, and third-party failures gracefully.
- Avoid unnecessary blocking work inside the `/voice` request path.
- When an external dependency fails, prefer preserving the caller workflow and saving a recoverable record rather than dropping the call.

## Documentation Expectations

- `README.md` should contain setup and run instructions.
- `ARCHITECTURE.md` should explain backend architecture, call flow, persistence, and integration boundaries.
- If behavior changes in a way another developer would need to know, update the relevant documentation in the same change.

## Development Philosophy

This repository intentionally favors:

- small focused modules
- minimal abstraction layers
- readability over architectural complexity

Agents should avoid introducing heavy frameworks, complex dependency graphs, or premature abstractions unless explicitly requested.
