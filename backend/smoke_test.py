from __future__ import annotations

import json
import sys

sys.path.insert(0, "backend")

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    client = TestClient(app)

    bootstrap = client.post("/v1/demo/bootstrap")
    tick = client.post(
        "/v1/tick",
        json={
            "now": "2026-04-26T10:35:00Z",
            "available_triggers": [
                "trg_013_corporate_thali_planning",
                "trg_001_research_digest_dentists",
            ],
        },
    )
    action = tick.json()["actions"][0]
    reply = client.post(
        "/v1/reply",
        json={
            "conversation_id": action["conversation_id"],
            "merchant_id": action["merchant_id"],
            "customer_id": action["customer_id"],
            "from_role": "merchant",
            "message": "Yes send it",
            "received_at": "2026-04-26T10:40:00Z",
            "turn_number": 2,
        },
    )

    print("bootstrap:", json.dumps(bootstrap.json(), ensure_ascii=False))
    print("tick:", json.dumps(tick.json(), ensure_ascii=False))
    print("reply:", json.dumps(reply.json(), ensure_ascii=False))


if __name__ == "__main__":
    main()
