import os
import json
from fastapi import FastAPI, Request, Form
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from groq import Groq
from supabase import create_client, Client as SupabaseClient
from dotenv import load_dotenv

load_dotenv() # Load variables from .env

# --- 1. INITIALIZE SYSTEM VARIABLES ---
# (In production, these come from your .env file)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "your_groq_key_here")
SUPABASE_URL = os.getenv("SUPABASE_URL", "your_supabase_url_here")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "your_supabase_key_here")

# Initialize Clients
ai_client = None
db = None

try:
    if GROQ_API_KEY and GROQ_API_KEY != "your_groq_key_here":
        ai_client = Groq(api_key=GROQ_API_KEY)
    else:
        print("Warning: GROQ_API_KEY is missing or placeholder.")
except Exception as e:
    print(f"Error initializing Groq client: {e}")

try:
    if SUPABASE_URL and SUPABASE_URL != "your_supabase_url_here":
        db = create_client(SUPABASE_URL, SUPABASE_KEY)
    else:
        print("Warning: SUPABASE_URL is missing or placeholder.")
except Exception as e:
    print(f"Error initializing Supabase client: {e}")

app = FastAPI()

# --- 2. THE SOVEREIGN SYSTEM PROMPT ---
MASTER_PROMPT = """
You are SWARAJ, the Sovereign OS of the Indian Citizen. 
Analyze the user's message. 
If it is a grievance, corruption, or civic issue, classify intent as "CIVIC". Act as a ruthless constitutional lawyer. Draft a short, powerful legal notice.
If it is a general question, recipe, or advice, classify intent as "GENERAL". Act as an empathetic, brilliant mentor.
You MUST output your response STRICTLY in valid JSON format with exactly two keys:
{"intent": "CIVIC or GENERAL", "reply_to_citizen": "The text you want to send back to the user"}
"""

# --- 3. THE WEBHOOK (The Gateway) ---
@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    # Parse incoming message from Twilio
    form_data = await request.form()
    citizen_phone = form_data.get('From', 'Unknown')
    raw_message = form_data.get('Body', '')

    print(f"INCOMING TRANSMISSION FROM {citizen_phone}: {raw_message}")
    # --- 4. THE BRAIN (Intent & Processing) ---
    try:
        if not ai_client:
            raise Exception("AI client not initialized. Check your API keys.")

        completion = ai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": MASTER_PROMPT},
                {"role": "user", "content": raw_message}
            ],
            response_format={"type": "json_object"}, # Forces AI to output JSON
            temperature=0.2
        )
        
        # Parse the AI's JSON thought process
        ai_thought = json.loads(completion.choices[0].message.content)
        intent = ai_thought.get("intent", "GENERAL")
        reply_text = ai_thought.get("reply_to_citizen", "Error generating response.")

    except Exception as e:
        intent = "ERROR"
        reply_text = "System overload. The Sovereign OS is recalibrating."
        print(f"AI Error: {e}")

    # --- 5. THE LEDGER (Commit to Supabase if Civic) ---
    if intent == "CIVIC":
        if not db:
            print("Warning: No database client. Ledger update skipped.")
        else:
            try:
                db.table("ledger").insert({
                    "citizen_phone": citizen_phone,
                    "raw_message": raw_message,
                    "intent_category": intent,
                    "ai_response": reply_text
                }).execute()
                print("Ledger Updated: Immutable record created.")
            except Exception as e:
                print(f"Database Error: {e}")

    # --- 6. THE VOICE (Reply via WhatsApp) ---
    # Twilio requires a TwiML XML response to send a message back
    response = MessagingResponse()
    msg = response.message()
    
    # Append the Sovereign footer if it was a civic action
    if intent == "CIVIC":
        msg.body(f"{reply_text}\n\n---\n*Logged to the Sovereign Public Ledger.*")
    else:
        msg.body(reply_text)

    return str(response)

# --- BOOT SEQUENCE ---
# Run locally using: uvicorn main:app --reload
