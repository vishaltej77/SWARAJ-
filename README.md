# SWARAJ-

`SWARAJ-` is a compact FastAPI service for a WhatsApp-first assistant that routes incoming messages through Groq and optionally records civic interactions to Supabase.

The current public repo is intentionally small. It exposes the webhook gateway, a health route, and the minimum configuration needed to run the service locally or deploy it behind a WhatsApp transport.

## What the service does

- accepts WhatsApp webhook traffic at `/whatsapp`
- classifies each message as either `CIVIC` or `GENERAL`
- generates a response with Groq
- writes civic messages to a Supabase ledger when database credentials are configured
- returns TwiML so Twilio can send the reply back to the user

## Stack

- Python
- FastAPI
- Groq
- Supabase
- Twilio

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/health` to confirm the service is up.

## Environment

The service reads configuration from `.env`.

Required for full behavior:

- `GROQ_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`

Optional:

- `GROQ_MODEL`

If the AI or database credentials are not configured, the service still starts and reports the missing integration through `/health`.

## Routes

- `GET /`
  Service summary and route inventory.
- `GET /health`
  Runtime status plus whether Groq and Supabase are configured.
- `POST /whatsapp`
  Twilio-compatible webhook entrypoint.

## Local testing

```bash
pytest -q
```

The test suite uses local fakes for Groq and Supabase. No live API keys are required.

## Repository standard

This public repo is intended to stay reviewable and publish-safe.
That means local secrets, virtual environments, transient logs, and machine-specific artifacts stay out of Git.
