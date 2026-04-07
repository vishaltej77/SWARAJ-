import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import PLACEHOLDER_GROQ_KEY, PLACEHOLDER_SUPABASE_KEY, PLACEHOLDER_SUPABASE_URL, Settings, create_app


class FakeCompletions:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {
            "intent": "GENERAL",
            "reply_to_citizen": "Acknowledged.",
        }
        self.error = error

    def create(self, **_kwargs):
        if self.error:
            raise self.error

        message = type("Message", (), {"content": json.dumps(self.payload)})
        choice = type("Choice", (), {"message": message})
        return type("Completion", (), {"choices": [choice]})


class FakeAIClient:
    def __init__(self, payload=None, error=None):
        self.chat = type(
            "Chat",
            (),
            {"completions": FakeCompletions(payload=payload, error=error)},
        )()


class FakeDB:
    def __init__(self):
        self.rows = []

    def table(self, _name):
        return self

    def insert(self, row):
        self.rows.append(row)
        return self

    def execute(self):
        return {"status": "ok"}


def build_client():
    settings = Settings(
        groq_api_key=PLACEHOLDER_GROQ_KEY,
        supabase_url=PLACEHOLDER_SUPABASE_URL,
        supabase_key=PLACEHOLDER_SUPABASE_KEY,
    )
    app = create_app(settings)
    return TestClient(app), app


def test_health_route_reports_unconfigured_integrations():
    client, _app = build_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["ai_configured"] is False
    assert response.json()["db_configured"] is False


def test_general_whatsapp_message_returns_ai_reply_without_footer():
    client, app = build_client()
    app.state.ai_client = FakeAIClient(
        payload={"intent": "GENERAL", "reply_to_citizen": "Hello from SWARAJ."}
    )

    response = client.post("/whatsapp", data={"From": "whatsapp:+91", "Body": "Hi"})

    assert response.status_code == 200
    assert "Hello from SWARAJ." in response.text
    assert "Sovereign Public Ledger" not in response.text


def test_civic_whatsapp_message_persists_and_appends_footer():
    client, app = build_client()
    fake_db = FakeDB()
    app.state.ai_client = FakeAIClient(
        payload={"intent": "CIVIC", "reply_to_citizen": "Drafting your notice."}
    )
    app.state.db = fake_db

    response = client.post(
        "/whatsapp",
        data={"From": "whatsapp:+91", "Body": "There is corruption in my ward."},
    )

    assert response.status_code == 200
    assert "Drafting your notice." in response.text
    assert "Sovereign Public Ledger" in response.text
    assert fake_db.rows[0]["intent_category"] == "CIVIC"


def test_ai_failure_returns_system_overload_message():
    client, app = build_client()
    app.state.ai_client = FakeAIClient(error=RuntimeError("boom"))

    response = client.post("/whatsapp", data={"From": "whatsapp:+91", "Body": "Hi"})

    assert response.status_code == 200
    assert "System overload. The Sovereign OS is recalibrating." in response.text
