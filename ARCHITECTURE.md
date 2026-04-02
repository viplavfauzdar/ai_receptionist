# ARCHITECTURE.md

## Overview

This repository is an AI receptionist MVP built around Twilio voice, FastAPI, SQLite, and OpenAI.

At a high level:

- Twilio receives the phone call and sends webhook requests to the backend.
- `ngrok` is used in local development to expose the backend to Twilio.
- FastAPI handles the `/voice` webhook and returns TwiML.
- SQLite stores business records, call logs, appointment requests, and per-call session state.
- OpenAI is used to generate structured receptionist responses when an API key is configured.
- A fallback rule-based path is used when the API key is missing or the model output is unusable.
- Twilio signatures are validated on `/voice` by default before any session or DB work happens.
- Completed bookings can optionally create Google Calendar events through a small backend service layer.

The backend is intentionally small. Most logic lives in:

- `backend/app/main.py`
- `backend/app/ai.py`
- `backend/app/models.py`
- `backend/app/db.py`

## 1. System Architecture

### Twilio Voice Webhook Flow

Twilio owns the actual phone call lifecycle. The backend does not place or receive PSTN calls directly.

Flow:

1. A caller dials a Twilio phone number.
2. Twilio sends an HTTP request to the configured voice webhook.
3. The backend validates the Twilio signature.
4. The backend responds with TwiML XML.
5. Twilio reads the response aloud and captures follow-up speech using `Gather`.
6. Twilio sends the next turn back to `/voice`.

All `Gather` usage in the current backend is configured with:

- `speech_timeout="auto"`
- `timeout=3`
- `action_on_empty_result=True`

The backend is therefore a webhook-driven state machine.

### ngrok for Local Development

Twilio cannot reach `localhost` directly. During local development:

1. Run the FastAPI server locally on port `8000`.
2. Run `ngrok http 8000`.
3. Configure the Twilio number voice webhook to:

```text
https://YOUR-NGROK-URL/voice
```

`ngrok` only tunnels traffic. It is not part of the app runtime.

### FastAPI Backend Structure

Key modules:

- `backend/app/main.py`
  Main FastAPI app, routes, Twilio webhook flow, DB writes, business lookup, session handling.
- `backend/app/ai.py`
  LLM prompt construction, fallback logic, structured response parsing, slot extraction, phone formatting.
- `backend/app/skills/receptionist_system_prompt.md`
  Skill-style markdown prompt template for the receptionist system message.
- `backend/app/calendar_service.py`
  Google Calendar OAuth helper, appointment datetime builder, and event insertion.
- `backend/app/models.py`
  SQLAlchemy ORM models.
- `backend/app/db.py`
  SQLAlchemy engine/session setup and SQLite compatibility helper.
- `backend/app/config.py`
  Env-backed configuration.
- `backend/app/schemas.py`
  Pydantic response/request schemas for API routes.

### SQLite Persistence Layer

SQLite is used as the persistence layer for the MVP.

Current tables:

- `businesses`
- `call_logs`
- `call_sessions`
- `appointment_requests`

The backend uses SQLAlchemy ORM over a local SQLite file, typically:

```text
backend/receptionist.db
```

### OpenAI LLM Integration

When `OPENAI_API_KEY` is present, the backend uses OpenAI to produce structured JSON replies for each caller turn.

When the key is missing, or the model output is invalid, the backend falls back to deterministic rule-based behavior.

This design keeps the system usable offline or in partial-failure scenarios.

The main receptionist system prompt is stored outside code in:

- `backend/app/skills/receptionist_system_prompt.md`

`backend/app/ai.py` loads that file at runtime and performs simple placeholder interpolation for business/session values. If the file is missing or unreadable, `ai.py` falls back to a built-in default template.

### Google Calendar Integration

When calendar booking is enabled, the backend can convert a completed booking flow into a real Google Calendar event.

Configuration is env-driven:

- `GOOGLE_CALENDAR_ENABLED`
- `GOOGLE_CALENDAR_ID`
- `GOOGLE_CLIENT_SECRETS_FILE`
- `GOOGLE_TOKEN_FILE`
- `GOOGLE_TIMEZONE`
- `APPOINTMENT_DURATION_MINUTES`

Local development uses OAuth desktop-app credentials and a locally stored `token.json`.

### CORS Configuration

CORS is configured from `backend/app/config.py` through a comma-separated env value:

- `CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`

The default is local-only. The backend no longer ships with wildcard CORS enabled.

## 2. Call Flow Lifecycle

This is the main request path through `POST /voice`.

### Step 1: Incoming Twilio Request

Twilio sends form-encoded data to `/voice`, typically including:

- `CallSid`
- `From`
- `To`
- `CallStatus`
- `SpeechResult` for spoken turns

Before the request is processed, the backend validates `X-Twilio-Signature` using the configured Twilio auth token.

If validation fails:

- the request returns HTTP `403`
- no session is created
- no call log is written
- no TwiML is generated

For local development, signature validation can be disabled explicitly with:

- `DISABLE_TWILIO_SIGNATURE_VALIDATION=true`

### Step 2: Business Lookup

The backend resolves the business using the incoming Twilio `To` number.

Behavior:

- exact match against `businesses.twilio_number`
- indexed normalized match against `businesses.twilio_number_normalized`
- env-backed default business config if no business row matches

This supports basic multi-tenant routing by Twilio number.

### Step 3: CallSid Session Lookup or Creation

The backend loads or creates a `CallSession` using `CallSid`.

If `CallSid` is missing, the request still works, but no session persistence is used.

### Step 4: Session Context Construction

The backend converts the DB session row into an in-memory session context containing:

- current intent
- current state
- accumulated slot values
- recent transcript

This is passed to the AI layer.

### Step 5: Initial Greeting or Spoken Turn

If `SpeechResult` is empty:

- on the first request for a call, the configured greeting is spoken and a `Gather` is returned
- on later silent turns, the backend increments a small silence counter in session slot data
- first silent turn after greeting or prompting: polite reprompt
- second silent turn: shorter fallback prompt
- third silent turn: clean goodbye and hangup
- silence turns are handled directly in `/voice` without redirect loops

If `SpeechResult` is present:

- the user utterance is appended to transcript
- the AI layer is called

### Step 6: `detect_and_respond`

`backend/app/ai.py` receives:

- user speech
- business context
- session context

It returns a structured result:

```json
{
  "intent": "...",
  "state": "...",
  "response": "...",
  "fields": {}
}
```

### Step 7: Slot Extraction and Session Update

Returned fields are merged into session slot storage.

Examples:

- `appointment_day`
- `appointment_time`
- `callback_number`
- `caller_name`

The assistant reply is appended to transcript and the session row is updated.

Silence tracking also lives in slot storage through:

- `silence_count`

### Step 8: DB Logging

Each spoken turn is logged into `call_logs`.

Depending on the state:

- booking completion creates an `appointment_requests` row only after `appointment_day`, `appointment_time`, `callback_number`, and `caller_name` are all present
- callback completion creates an `appointment_requests` row only after `callback_number` and `caller_name` are present

For booking completion, the backend then attempts Google Calendar creation if calendar booking is enabled.

Before insertion, the backend checks the proposed appointment window against existing events on the target calendar.

If calendar creation succeeds:

- the appointment row is marked confirmed
- calendar metadata is stored on the appointment row
- the caller hears a concise booking confirmation

If calendar creation fails:

- the appointment row is still saved
- the call does not fail
- the caller hears a fallback office-confirmation message

If the requested slot conflicts with an existing event:

- no calendar event is created
- the appointment request is still saved in SQLite
- the caller hears a short prompt asking for another time
- if the backend can infer a nearby opening after the conflicting event chain, that suggested slot is offered

### Step 9: TwiML Response Returned to Twilio

The backend returns TwiML with:

- `Say`
- another `Gather`
- or `Hangup` when repeated silence exceeds the threshold

This keeps the conversation open for the next caller turn while still ending deterministically after repeated silence.

## 3. Conversation State Model

### CallSession

`CallSession` is the central persistence model for conversation continuity.

Fields:

- `call_sid`
- `from_number`
- `to_number`
- `current_intent`
- `current_state`
- `slot_data_json`
- `transcript_json`
- `is_active`
- `created_at`
- `updated_at`

### Transcript Storage

`transcript_json` stores recent turn history as a JSON list, for example:

```json
[
  {"role": "assistant", "text": "Hello, thanks for calling Bright Smile Dental. How can I help you today?"},
  {"role": "user", "text": "I want to book an appointment"},
  {"role": "assistant", "text": "Sure, I can help schedule that. What day works for you?"}
]
```

Only a bounded tail is kept to avoid unbounded growth. The current limit is configurable — if not set, the backend defaults to the last 10 turns. Too small a bound causes the LLM to lose context mid-booking; too large increases token cost per turn.

### Slot Storage

`slot_data_json` stores structured information extracted across turns.

Typical keys:

- `appointment_day`
- `appointment_time`
- `callback_number`
- `caller_name`
- `silence_count`
- `request_saved`

### State Machine Behavior

The current state is persisted explicitly. Common states include:

- `NEW`
- `GREETING_SENT`
- `COLLECTING_APPOINTMENT_DAY`
- `COLLECTING_APPOINTMENT_TIME`
- `COLLECTING_CALLBACK_NUMBER`
- `COLLECTING_CALLER_NAME`
- `BOOKING_COMPLETE`
- `CALLBACK_READY`
- `ANSWERED_BUSINESS_HOURS`
- `GENERAL_ASSISTANCE`

This is a lightweight state machine, not a formal workflow engine.

Calendar creation is intentionally not part of the LLM state machine. It happens in deterministic backend code after the state reaches booking completion.

### State Transition Table

Transitions are driven by the LLM returning a valid next state, subject to backend validation. The backend will downgrade semantically premature states (e.g. `BOOKING_COMPLETE` when required slots are still missing).

| From state | Trigger | To state |
|---|---|---|
| `NEW` | First `/voice` hit, no speech | `GREETING_SENT` |
| `GREETING_SENT` | Booking intent detected | `COLLECTING_APPOINTMENT_DAY` |
| `GREETING_SENT` | Hours intent detected | `ANSWERED_BUSINESS_HOURS` |
| `GREETING_SENT` | Callback intent detected | `COLLECTING_CALLBACK_NUMBER` |
| `GREETING_SENT` | General question | `GENERAL_ASSISTANCE` |
| `COLLECTING_APPOINTMENT_DAY` | Day extracted | `COLLECTING_APPOINTMENT_TIME` |
| `COLLECTING_APPOINTMENT_TIME` | Time extracted | `COLLECTING_CALLBACK_NUMBER` |
| `COLLECTING_CALLBACK_NUMBER` | Number extracted | `COLLECTING_CALLER_NAME` |
| `COLLECTING_CALLER_NAME` | Name extracted | `BOOKING_COMPLETE` |
| `COLLECTING_CALLBACK_NUMBER` (callback flow) | Number extracted | `COLLECTING_CALLER_NAME` |
| `COLLECTING_CALLER_NAME` (callback flow) | Name extracted | `CALLBACK_READY` |
| `BOOKING_COMPLETE` | — | appointment persisted, calendar attempted |
| `CALLBACK_READY` | — | callback request persisted |
| Any state | 3 consecutive silent turns | hangup |

### Call Drop Behavior

When a call ends mid-flow (caller hangs up, network drop, Twilio sends `CallStatus=completed`), the session row remains in SQLite with `is_active=True` and whatever slots were collected at the time of drop.

Current behavior:

- no `AppointmentRequest` row is written unless all required slots were already present
- the session is not explicitly marked inactive on call drop
- there is no cleanup job for abandoned sessions

Known gap: sessions from dropped calls stay active indefinitely. A future improvement is to listen for Twilio status callback webhooks (`CallStatus=completed`) and mark the session inactive, and optionally surface incomplete bookings in the dashboard for manual follow-up.

## 4. Intent System

Supported intents:

### `BOOK_APPOINTMENT`

Used when the caller wants to book or reschedule.

Expected behavior:

- collect `appointment_day`
- collect `appointment_time`
- collect `callback_number`
- collect `caller_name`
- create an appointment request when complete

### `BUSINESS_HOURS`

Used when the caller asks about opening hours.

Expected behavior:

- answer directly
- usually one short sentence

### `CALLBACK_REQUEST`

Used when the caller wants someone to call them back.

Expected behavior:

- collect `callback_number`
- collect `caller_name`
- confirm in speech-safe format
- create a simple request record when ready

### `GENERAL_QUESTION`

Used when the request is not a booking, hours request, or callback request.

Expected behavior:

- answer briefly
- ask a clarifying question when needed

## 5. LLM Interaction

### Structured JSON Responses

The LLM is prompted to return JSON only in this shape:

```json
{
  "intent": "BOOK_APPOINTMENT",
  "state": "COLLECTING_APPOINTMENT_TIME",
  "response": "What time works best for you?",
  "fields": {
    "appointment_day": "Tuesday"
  }
}
```

This keeps the backend in control of persistence and state transitions.

### Validation and Sanitization Layer

The backend does not trust raw model output.

Before the `/voice` route uses any LLM result, `backend/app/ai.py` normalizes it into a safe shape:

```json
{
  "intent": "...",
  "state": "...",
  "response": "...",
  "fields": {}
}
```

Validation rules:

- `intent` must be one of the known intent constants
- `state` must be a known safe state string, otherwise the prior valid session state is preserved when possible
- semantically premature states like `BOOKING_COMPLETE` or `CALLBACK_READY` are downgraded to the next safe collection state if required slots are still missing
- `response` must be non-empty and is sanitized into short phone-friendly text
- `fields` must be a dictionary and are filtered down to known slot keys

If the model returns malformed JSON, empty content, missing fields, invalid intent/state values, or an unusable payload, the backend falls back to a deterministic safe response instead of exposing raw model output to the Twilio flow.

The following concerns remain in code rather than the prompt file:

- output validation
- state normalization
- slot extraction
- phone-number formatting
- persistence rules
- fallback logic

### Fallback Mode

Fallback mode is used when:

- `OPENAI_API_KEY` is missing
- the OpenAI call raises an exception
- the OpenAI call times out
- the model returns empty output
- the model returns malformed or incomplete JSON

Fallback behavior is still session-aware and still updates slot/state progression.

### Malformed Output Handling

The backend validates model output before using it.

If output is invalid, it falls back safely rather than crashing the route.

This is important because `/voice` must continue returning valid TwiML under failure.

## 6. Booking-to-Calendar Flow

When a booking flow reaches completion:

1. `/voice` persists the completed booking request.
2. `backend/app/main.py` checks whether calendar booking is enabled.
3. `backend/app/calendar_service.py` builds the appointment window from:
   - `appointment_day`
   - `appointment_time`
   - `GOOGLE_TIMEZONE`
   - `APPOINTMENT_DURATION_MINUTES`
4. The calendar service checks availability on the target calendar for that exact window.
5. If the window is available, the calendar service inserts a Google Calendar event.
6. The backend stores:
   - `calendar_event_id`
   - `calendar_event_link`
   - `scheduled_start`
   - `scheduled_end`
7. The assistant confirms the booking to the caller.

If any calendar step fails, the appointment request remains in SQLite and the assistant falls back to manual office confirmation wording.

Overlap rule:

- any interval intersection blocks the slot
- an event ending exactly at the proposed start does not block the new slot
- cancelled events are ignored

## 7. Phone Number Normalization Logic

The backend normalizes phone numbers in two different ways:

### Business Lookup Normalization

For matching Twilio numbers to business records:

- strips formatting
- keeps only digits
- drops leading US `1` if present on 11-digit numbers
- stores the normalized value in `businesses.twilio_number_normalized`
- resolves businesses through an indexed normalized lookup instead of scanning all rows

This helps match:

- `+16784624453`
- `(678) 462-4453`
- `6784624453`

### Speech-Safe Phone Formatting

When the assistant confirms a callback number, the backend uses code-level formatting so Twilio reads digits instead of a large quantity.

For 10-digit US numbers:

```text
6784624453 -> 6 7 8, 4 6 2, 4 4 5 3
```

This formatting is applied in code, not left to LLM wording.

## 8. Testing Strategy

The backend test suite uses `pytest`.

Current structure:

- `backend/tests/conftest.py`
  shared fixtures
- `backend/tests/test_routes_and_voice.py`
  route-level behavior and Twilio flow
- `backend/tests/test_llm_route_behavior.py`
  mocked LLM behavior through endpoints
- `backend/tests/test_ai_behavior.py`
  direct AI/helper behavior
- `backend/tests/test_backend_helpers.py`
  DB helper and internal helper branch coverage

### Mocked OpenAI Calls

No live OpenAI requests are made in tests.

The suite replaces the OpenAI client with a fake client that returns:

- valid JSON
- malformed output
- empty output
- raised exceptions

### Database Isolation

Tests use a temporary SQLite database, not `backend/receptionist.db`.

This ensures:

- deterministic runs
- no local data pollution
- safe CI execution

### Coverage Targets

Coverage is measured against:

```text
backend/app
```

The suite currently exercises:

- route behavior
- Twilio signature validation
- CORS behavior for allowed and disallowed origins
- empty-gather silence handling and repeated-silence hangup behavior
- mocked Google Calendar success and failure behavior
- DB writes
- session persistence
- fallback logic
- mocked LLM handling
- phone formatting logic

## 9. How to Run the System Locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Important local env vars:

- `GOOGLE_CALENDAR_ENABLED`
- `GOOGLE_CALENDAR_ID`
- `GOOGLE_CLIENT_SECRETS_FILE`
- `GOOGLE_TOKEN_FILE`
- `GOOGLE_TIMEZONE`
- `APPOINTMENT_DURATION_MINUTES`
- `TWILIO_AUTH_TOKEN`
- `DISABLE_TWILIO_SIGNATURE_VALIDATION`
- `CORS_ALLOWED_ORIGINS`
- `OPENAI_API_KEY`
- `DATABASE_URL`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### ngrok

```bash
ngrok http 8000
```

### Twilio

Set the Twilio phone number voice webhook to:

```text
https://YOUR-NGROK-URL/voice
```

### Local Google Calendar OAuth

To authorize the local backend against Google Calendar:

1. Place the OAuth desktop client file at `backend/credentials.json`.
2. Start the backend virtualenv.
3. Run:

```bash
cd backend
python -m app.calendar_service
```

This opens the local consent flow and writes `backend/token.json`.

## 10. How to Run the Backend Tests

Install backend dependencies:

```bash
cd /Users/viplavfauzdar/Projects/ai_receptionist
backend/.venv/bin/pip install -r backend/requirements.txt
```

Run tests:

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

Run tests with coverage:

```bash
backend/.venv/bin/python -m pytest backend/tests \
  --cov=backend/app \
  --cov-report=term-missing
```

## 11. Known Limitations

### Single-Tenant Google Calendar OAuth

The current Google Calendar implementation uses a single `token.json` file on disk. Only one Google account can be authorized per server instance. Onboarding a second business with a different Google Calendar will overwrite the existing token.

This is a deliberate MVP simplification. The fix is per-business OAuth token storage — store the token payload per `business_id` in the database, encrypted at rest, and load the correct token at booking time.

### SQLite Not Suitable for Production

SQLite is used for local development and testing. It does not support concurrent writes safely under real traffic. Replace with Postgres before any multi-business production deployment.

### ngrok Required for Local Twilio Webhooks

Twilio cannot reach `localhost` directly. ngrok is a manual step that is not managed by the app. The ngrok URL changes on every restart unless a paid static domain is configured, which requires updating the Twilio webhook URL each time.

### No Twilio Status Callback Handling

The backend does not listen for `CallStatus=completed` webhooks. Sessions from dropped or abandoned calls remain active in SQLite indefinitely and incomplete bookings are not surfaced anywhere.

### CORS Must Be Set for Production

`CORS_ALLOWED_ORIGINS` defaults to local origins only. Before deploying the backend publicly, this must be set to the actual frontend domain. Leaving it at the default will block the frontend in production.

### No Auth on Admin API Routes

The `/api/businesses`, `/api/calls`, and `/api/appointments` routes have no authentication. Anyone who can reach the backend can read call logs and appointment data. Auth is required before any public deployment.

---

## 12. Future Extensions

### Multi-Tenant Businesses

Current multi-tenancy is Twilio-number-based and minimal.

Possible next steps:

- admin auth
- business-specific dashboards
- per-business routing and permissions
- automatic phone-number normalization at input boundaries beyond the current create routes
- tenant-aware analytics

### Calendar Integration

Google Calendar integration is implemented for single-tenant local development.

The current implementation uses a single OAuth `token.json` file on disk, which means only one Google account can be authorized per server instance. This is a known limitation.

Next steps:

- per-business OAuth token storage (token per `business_id` in the DB, encrypted at rest)
- Outlook / Microsoft 365 calendar support
- reschedule and cancellation flows via voice
- SMS or email booking confirmation after the call ends

### CRM Integration

Callback requests and booking requests can be pushed into:

- HubSpot
- Salesforce
- custom CRM backends

### Call Analytics

Potential additions:

- intent distribution
- unanswered requests
- missed callback rates
- per-business call metrics
- transcript analysis

### SaaS Deployment

For a real multi-tenant SaaS version:

- move from SQLite to Postgres
- add auth and tenant isolation
- add background jobs
- add secrets management
- deploy webhook backend publicly without ngrok
