from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from groq import Groq
from supabase import create_client
from twilio.twiml.messaging_response import MessagingResponse

load_dotenv()

LOGGER = logging.getLogger("swaraj")
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

PLACEHOLDER_GROQ_KEY = "your_groq_key_here"
PLACEHOLDER_SUPABASE_URL = "your_supabase_url_here"
PLACEHOLDER_SUPABASE_KEY = "your_supabase_key_here"
SYSTEM_OVERLOAD_MESSAGE = "System overload. The Sovereign OS is recalibrating."

MASTER_PROMPT = """
You are SWARAJ, the Sovereign OS of the Indian Citizen.
Analyze the user's message.
If it is a grievance, corruption, or civic issue, classify intent as "CIVIC". Act as a ruthless constitutional lawyer. Draft a short, powerful legal notice.
If it is a general question, recipe, or advice, classify intent as "GENERAL". Act as an empathetic, brilliant mentor.
You MUST output your response STRICTLY in valid JSON format with exactly two keys:
{"intent": "CIVIC or GENERAL", "reply_to_citizen": "The text you want to send back to the user"}
""".strip()


@dataclass(frozen=True)
class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", PLACEHOLDER_GROQ_KEY)
    supabase_url: str = os.getenv("SUPABASE_URL", PLACEHOLDER_SUPABASE_URL)
    supabase_key: str = os.getenv("SUPABASE_KEY", PLACEHOLDER_SUPABASE_KEY)
    model_name: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    civic_footer: str = "Logged to the Sovereign Public Ledger."


def _is_configured(value: str, placeholder: str) -> bool:
    return bool(value and value.strip() and value != placeholder)


def _create_ai_client(settings: Settings):
    if not _is_configured(settings.groq_api_key, PLACEHOLDER_GROQ_KEY):
        LOGGER.warning("GROQ_API_KEY is missing or set to a placeholder value.")
        return None

    try:
        return Groq(api_key=settings.groq_api_key)
    except Exception:
        LOGGER.exception("Error initializing Groq client.")
        return None


def _create_db_client(settings: Settings):
    if not _is_configured(settings.supabase_url, PLACEHOLDER_SUPABASE_URL):
        LOGGER.warning("SUPABASE_URL is missing or set to a placeholder value.")
        return None

    try:
        return create_client(settings.supabase_url, settings.supabase_key)
    except Exception:
        LOGGER.exception("Error initializing Supabase client.")
        return None


def _classify_message(ai_client: Any, settings: Settings, raw_message: str) -> tuple[str, str]:
    if not ai_client:
        raise RuntimeError("AI client not initialized. Check your API keys.")

    completion = ai_client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": MASTER_PROMPT},
            {"role": "user", "content": raw_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    content = completion.choices[0].message.content or "{}"
    ai_thought = json.loads(content)

    intent = str(ai_thought.get("intent", "GENERAL")).upper()
    if intent not in {"CIVIC", "GENERAL"}:
        intent = "GENERAL"

    reply_text = str(ai_thought.get("reply_to_citizen", SYSTEM_OVERLOAD_MESSAGE)).strip()
    if not reply_text:
        reply_text = SYSTEM_OVERLOAD_MESSAGE

    return intent, reply_text


def _persist_ledger(db: Any, citizen_phone: str, raw_message: str, intent: str, reply_text: str) -> bool:
    if intent != "CIVIC" or not db:
        return False

    try:
        db.table("ledger").insert(
            {
                "citizen_phone": citizen_phone,
                "raw_message": raw_message,
                "intent_category": intent,
                "ai_response": reply_text,
            }
        ).execute()
        LOGGER.info("Ledger updated for %s", citizen_phone)
        return True
    except Exception:
        LOGGER.exception("Database error while writing ledger entry.")
        return False


def _twiml_reply(intent: str, reply_text: str, footer: str) -> str:
    response = MessagingResponse()
    message = response.message()

    if intent == "CIVIC":
        message.body(f"{reply_text}\n\n---\n*{footer}*")
    else:
        message.body(reply_text)

    return str(response)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()

    app = FastAPI(
        title="SWARAJ",
        summary="A WhatsApp-first civic and general assistant gateway.",
        version="0.1.0",
    )
    app.state.settings = resolved_settings
    app.state.ai_client = _create_ai_client(resolved_settings)
    app.state.db = _create_db_client(resolved_settings)

    @app.get("/")
    async def root() -> dict[str, Any]:
        return {
            "service": "SWARAJ",
            "summary": "WhatsApp-first assistant gateway for civic and general queries.",
            "routes": ["/health", "/whatsapp"],
        }

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "ai_configured": app.state.ai_client is not None,
            "db_configured": app.state.db is not None,
            "model": resolved_settings.model_name,
        }

    @app.post("/whatsapp")
    async def whatsapp_webhook(request: Request) -> Response:
        form_data = await request.form()
        citizen_phone = str(form_data.get("From", "Unknown"))
        raw_message = str(form_data.get("Body", "")).strip()

        LOGGER.info("Incoming transmission from %s", citizen_phone)

        try:
            intent, reply_text = _classify_message(app.state.ai_client, resolved_settings, raw_message)
        except Exception:
            LOGGER.exception("AI processing failed.")
            intent = "ERROR"
            reply_text = SYSTEM_OVERLOAD_MESSAGE

        _persist_ledger(app.state.db, citizen_phone, raw_message, intent, reply_text)

        return Response(
            content=_twiml_reply(intent, reply_text, resolved_settings.civic_footer),
            media_type="application/xml",
        )

    return app


app = create_app()
