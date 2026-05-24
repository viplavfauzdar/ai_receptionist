# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

AI receptionist MVP: a FastAPI backend handling Twilio voice webhooks + a Next.js dashboard frontend. Callers dial a Twilio number → Twilio POSTs to `/voice` → FastAPI generates TwiML responses using OpenAI (with rule-based fallback). SQLite stores call logs, sessions, and appointment requests.

## Commands

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Run tests:
```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

Run a single test file:
```bash
backend/.venv/bin/python -m pytest backend/tests/test_ai_behavior.py -q
```

Run with coverage (also the default via `pytest.ini`):
```bash
backend/.venv/bin/python -m pytest backend/tests --cov=backend/app --cov-report=term-missing
```

Authorize Google Calendar (one-time local OAuth flow):
```bash
cd backend && source .venv/bin/activate && python -m app.calendar_service
```

### Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev       # http://localhost:3000
npm run build
npm run lint
```

### Local Twilio exposure (separate terminal, not managed by the app)

```bash
ngrok http 8000
```

## Architecture

### Call Flow

`POST /voice` is the entire conversation engine — it is a webhook-driven state machine:

1. Validate `X-Twilio-Signature` (disable with `DISABLE_TWILIO_SIGNATURE_VALIDATION=true` for local dev)
2. Resolve business from incoming `To` number → `businesses` table → env fallback
3. Load/create `CallSession` by `CallSid`
4. If no `SpeechResult`: send greeting (first turn) or handle silence (reprompt → fallback → hangup after 3 silent turns)
5. If `SpeechResult` present: call `detect_and_respond()` in `ai.py`
6. Validate and sanitize LLM output; merge returned `fields` into session slot storage
7. Persist to `call_logs`; persist `AppointmentRequest` when all required slots are present
8. Optionally create Google Calendar event (conflict-checked)
9. Return TwiML `<Say>` + `<Gather>` (or `<Hangup>`)

### Key Backend Modules

| File | Responsibility |
|---|---|
| `backend/app/main.py` | FastAPI app, all routes, Twilio webhook, business lookup, session handling, DB writes |
| `backend/app/ai.py` | LLM prompt construction, output validation/sanitization, fallback logic, slot extraction, phone formatting |
| `backend/app/models.py` | SQLAlchemy ORM: `Business`, `CallLog`, `CallSession`, `AppointmentRequest` |
| `backend/app/config.py` | Env-backed settings (single source of truth for all env vars) |
| `backend/app/schemas.py` | Pydantic request/response models for API routes |
| `backend/app/db.py` | SQLAlchemy engine/session setup |
| `backend/app/calendar_service.py` | Google Calendar OAuth, conflict checking, event insertion |
| `backend/app/skills/receptionist_system_prompt.md` | Externalized LLM system prompt (loaded at runtime with business value interpolation) |

### Frontend (Next.js App Router)

- `frontend/app/page.tsx` — dashboard home (overview cards)
- `frontend/app/calls/page.tsx` — call log table
- `frontend/app/settings/page.tsx` — settings UI
- `frontend/app/onboarding/page.tsx` — business onboarding (POSTs to `POST /api/businesses`)

All API calls use `NEXT_PUBLIC_API_BASE_URL` from `.env.local`.

### Session/State Model

`CallSession` persists per-call state via `CallSid`:
- `current_intent` / `current_state` — LLM-returned, backend-validated
- `slot_data_json` — collected values: `appointment_day`, `appointment_time`, `callback_number`, `caller_name`, `silence_count`
- `transcript_json` — bounded tail of recent turns (default: last 10)

LLM output is never used directly — `ai.py` validates intent, state, and fields before the route uses them. Premature states (e.g. `BOOKING_COMPLETE` without required slots) are downgraded.

### Multi-Tenant Routing

Business lookup via `businesses.twilio_number_normalized` (digits-only, US leading-1 stripped). Falls back to env-backed defaults if no row matches.

### Booking Completion

`AppointmentRequest` is only persisted when all four slots are present: `appointment_day`, `appointment_time`, `callback_number`, `caller_name`. Calendar creation is deterministic backend code — not part of the LLM state machine — and failures are graceful (row saved, caller hears fallback message).

## Rules

- When adding a new env var: update `backend/app/config.py`, `backend/.env.example`, and `README.md` in the same change.
- When changing backend architecture, call flow, persistence, state handling, or integration boundaries: update `ARCHITECTURE.md` in the same change.
- Keep voice responses short and phone-friendly — no long paragraphs.
- Twilio routes must always return valid TwiML. `/voice` contract (`POST /voice`) must be preserved unless explicitly changed.
- External integration logic goes in dedicated service modules under `backend/app/`, not inline in route handlers.
- Schema changes go in `backend/app/models.py`; prefer additive changes.
- Do not introduce blocking operations in the `/voice` request path.
