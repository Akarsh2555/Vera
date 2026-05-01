from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, store


client = TestClient(app)


def setup_function() -> None:
    store.clear()


def test_context_version_conflict() -> None:
    payload = {
        "scope": "category",
        "context_id": "dentists",
        "version": 1,
        "payload": {"slug": "dentists"},
        "delivered_at": "2026-04-26T09:45:00Z",
    }
    first = client.post("/v1/context", json=payload)
    second = client.post("/v1/context", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["reason"] == "stale_version"


def test_demo_bootstrap_and_tick_flow() -> None:
    bootstrap = client.post("/v1/demo/bootstrap")
    assert bootstrap.status_code == 200
    tick = client.post(
        "/v1/tick",
        json={
            "now": "2026-04-26T10:35:00Z",
            "available_triggers": ["trg_001_research_digest_dentists"],
        },
    )
    assert tick.status_code == 200
    actions = tick.json()["actions"]
    assert len(actions) == 1
    assert actions[0]["merchant_id"] == "m_001_drmeera_dentist_delhi"
    assert "Want" in actions[0]["body"]


def test_reply_detects_auto_reply_and_exit() -> None:
    client.post("/v1/demo/bootstrap")
    tick = client.post(
        "/v1/tick",
        json={
            "now": "2026-04-26T10:35:00Z",
            "available_triggers": ["trg_008_curious_ask_studio11"],
        },
    )
    action = tick.json()["actions"][0]
    reply_one = client.post(
        "/v1/reply",
        json={
            "conversation_id": action["conversation_id"],
            "merchant_id": action["merchant_id"],
            "customer_id": action["customer_id"],
            "from_role": "merchant",
            "message": "Thank you for contacting us. Our team will get back to you shortly.",
            "received_at": "2026-04-26T10:37:00Z",
            "turn_number": 2,
        },
    )
    reply_two = client.post(
        "/v1/reply",
        json={
            "conversation_id": action["conversation_id"],
            "merchant_id": action["merchant_id"],
            "customer_id": action["customer_id"],
            "from_role": "merchant",
            "message": "Thank you for contacting us. Our team will get back to you shortly.",
            "received_at": "2026-04-26T10:39:00Z",
            "turn_number": 3,
        },
    )

    assert reply_one.status_code == 200
    assert reply_one.json()["action"] == "send"
    assert reply_two.status_code == 200
    assert reply_two.json()["action"] == "end"
