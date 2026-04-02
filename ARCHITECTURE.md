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

Only a bounded tail is kept to avoid unbounded growth.

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

## 6. Phone Number Normalization Logic

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

## 7. Testing Strategy

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
- DB writes
- session persistence
- fallback logic
- mocked LLM handling
- phone formatting logic

## 8. How to Run the System Locally

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

## 9. How to Run the Backend Tests

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

## 10. Future Extensions

### Multi-Tenant Businesses

Current multi-tenancy is Twilio-number-based and minimal.

Possible next steps:

- admin auth
- business-specific dashboards
- per-business routing and permissions
- automatic phone-number normalization at input boundaries beyond the current create routes
- tenant-aware analytics

### Calendar Integration

Booking is currently a request capture flow, not a true scheduler.

Next step:

- Google Calendar or Outlook integration
- availability-aware booking
- booking confirmation and reschedule flows

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
