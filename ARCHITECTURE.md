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
3. The backend responds with TwiML XML.
4. Twilio reads the response aloud and captures follow-up speech using `Gather`.
5. Twilio sends the next turn back to `/voice`.

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

## 2. Call Flow Lifecycle

This is the main request path through `POST /voice`.

### Step 1: Incoming Twilio Request

Twilio sends form-encoded data to `/voice`, typically including:

- `CallSid`
- `From`
- `To`
- `CallStatus`
- `SpeechResult` for spoken turns

### Step 2: Business Lookup

The backend resolves the business using the incoming Twilio `To` number.

Behavior:

- exact match against `businesses.twilio_number`
- normalized digit-only fallback match
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

- the backend returns a `Gather`
- the configured greeting is spoken
- the session transcript is updated with the assistant greeting

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

The assistant reply is appended to transcript and the session row is updated.

### Step 8: DB Logging

Each spoken turn is logged into `call_logs`.

Depending on the state:

- booking completion may create an `appointment_requests` row
- callback-ready may create an `appointment_requests` row used as a simple follow-up request

### Step 9: TwiML Response Returned to Twilio

The backend returns TwiML with:

- `Say`
- another `Gather`
- a `Redirect` back to `/voice`

This keeps the conversation open for the next caller turn.

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
- `request_saved`

### State Machine Behavior

The current state is persisted explicitly. Common states include:

- `NEW`
- `GREETING_SENT`
- `COLLECTING_APPOINTMENT_DAY`
- `COLLECTING_APPOINTMENT_TIME`
- `COLLECTING_CALLBACK_NUMBER`
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

### Fallback Mode

Fallback mode is used when:

- `OPENAI_API_KEY` is missing
- the OpenAI call raises an exception
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
