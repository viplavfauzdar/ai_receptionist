# AI Receptionist Full Stack MVP

Twilio + FastAPI backend with:
- OpenAI response generation
- structured intent detection
- basic multi-tenant business lookup
- SQLite logging via SQLAlchemy
- basic appointment capture
- health check
- business profile config

Next.js dashboard with:
- onboarding form
- calls table
- settings page
- simple overview cards

## Architecture

The backend does not connect to ngrok directly. `ngrok` is a separate local process that exposes your local FastAPI server to the public internet so Twilio can reach it.

```mermaid
flowchart LR
    Caller[Phone Caller] --> Twilio[Twilio Voice]
    Twilio -->|HTTP POST /voice| Ngrok[ngrok public URL]
    Ngrok -->|Tunnel to localhost:8000| FastAPI[FastAPI backend]
    FastAPI --> AI[OpenAI or fallback reply logic]
    FastAPI --> DB[(SQLite)]
    FastAPI -->|TwiML XML with <Say> and <Gather>| Ngrok
    Ngrok --> Twilio
    Twilio -->|Text-to-speech playback| Caller
```

Runtime responsibilities:
- Twilio handles the phone call, speech capture, and text-to-speech playback.
- `ngrok` only forwards public webhook traffic to your local machine.
- FastAPI handles `/voice`, generates the reply text, and logs call data.
- The AI layer returns structured receptionist results with `intent`, `response`, and `fields`.
- SQLite stores businesses, call logs, and appointment requests.
- OpenAI generates the receptionist response when `OPENAI_API_KEY` is configured; otherwise the app uses fallback logic.

Code locations:
- Twilio webhook and TwiML generation: [`backend/app/main.py`](backend/app/main.py)
- Reply generation and intent detection: [`backend/app/ai.py`](backend/app/ai.py)
- Database connection: [`backend/app/db.py`](backend/app/db.py)
- Models: [`backend/app/models.py`](backend/app/models.py)

Multi-business resolution:
- The backend checks the incoming Twilio `To` number on `POST /voice`.
- If a `businesses` row matches that number, the app uses that business's `greeting`, `business_hours`, `booking_enabled`, and `knowledge_text`.
- If no row matches, the app falls back to the env-backed defaults from `backend/app/config.py`.

## 1) Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

For LLM mode, edit `backend/.env` before starting the server and set a real OpenAI API key:

```env
OPENAI_API_KEY=your_real_openai_api_key
OPENAI_MODEL=gpt-4o-mini
BUSINESS_NAME=Bright Smile Dental
BUSINESS_GREETING=Hello, thanks for calling Bright Smile Dental. How can I help you today?
BUSINESS_HOURS=Mon-Fri 9 AM to 5 PM
BOOKING_ENABLED=true
DATABASE_URL=sqlite:///./receptionist.db
```

Behavior:
- If `OPENAI_API_KEY` is present, the receptionist uses the OpenAI chat model and expects structured JSON output like:

```json
{
  "intent": "BOOK_APPOINTMENT",
  "response": "Sure, I can help schedule that. What day and time works for you?",
  "fields": {}
}
```

- Supported intents are `BOOK_APPOINTMENT`, `BUSINESS_HOURS`, `CALLBACK_REQUEST`, and `GENERAL_QUESTION`.
- If `OPENAI_API_KEY` is missing or the OpenAI request fails, the backend falls back to simple rule-based intent detection and short canned replies.
- Business-specific prompts and greetings are used when a matching `businesses.twilio_number` row exists.

## 2) Expose locally to Twilio

```bash
ngrok http 8000
```

This command is not run by the app. Start it manually in a separate terminal after the FastAPI server is already running.

Set your Twilio phone number voice webhook to:

```text
https://YOUR-NGROK-URL/voice
```

## 3) Frontend setup

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open:
- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs

## 4) Important env vars

Backend `.env`:
- `OPENAI_API_KEY` required for real LLM mode
- `OPENAI_MODEL=gpt-4o-mini`
- `BUSINESS_NAME=Bright Smile Dental`
- `BUSINESS_GREETING=Hello, thanks for calling Bright Smile Dental. How can I help you today?`
- `BUSINESS_HOURS=Mon-Fri 9 AM to 5 PM`
- `BOOKING_ENABLED=true`
- `DATABASE_URL=sqlite:///./receptionist.db`

Frontend `.env.local`:
- `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`

## 5) Notes

- This MVP uses SQLite at `backend/receptionist.db`.
- Multi-tenant mode is basic: one incoming Twilio number maps to one business record.
- Appointment booking is intentionally simple: it captures requested time and caller info.
- The Twilio voice webhook contract remains `POST /voice`.
- The receptionist is LLM-first when `OPENAI_API_KEY` is configured.
- Booking and callback intents create a simple database entry in `appointment_requests`.
- Call logs store `business_id`, `detected_intent`, and structured `intent_data`.
- Appointment requests now store `business_id`.
- For production, replace SQLite with Postgres and add real calendar integration.
- Twilio Gather speech handling is implemented in `/voice`.

## 6) Create A Demo Business

Create a demo business row for local testing:

```bash
curl -X POST "http://127.0.0.1:8000/api/demo-business?twilio_number=%2B15550001111&forwarding_number=%2B15550002222"
```

Then point your Twilio phone number or test request to use `To=+15550001111`. The webhook will resolve that business and use its greeting and business settings.

You can also create businesses directly:

```bash
curl -X POST http://127.0.0.1:8000/api/businesses \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bright Smile Dental",
    "twilio_number": "+15550001111",
    "forwarding_number": "+15550002222",
    "greeting": "Hello, thanks for calling Bright Smile Dental. How can I help you today?",
    "business_hours": "Mon-Fri 9 AM to 5 PM",
    "booking_enabled": true,
    "knowledge_text": "We offer cleanings, exams, and follow-up visits."
  }'
```

## 7) Suggested next upgrades
- Google Calendar integration
- Stripe billing
- multi-tenant business configs
- Twilio request validation
- role-based auth
