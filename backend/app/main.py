from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .bootstrap import bootstrap_demo_data
from .engine import VeraEngine
from .models import (
    ContextPushRequest,
    ContextPushResponse,
    DemoBootstrapResponse,
    DemoStateResponse,
    HealthResponse,
    MetadataResponse,
    ReplyRequest,
    ReplyResponse,
    TickRequest,
    TickResponse,
)
from .store import ContextStore


UTC = timezone.utc
PROJECT_ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(
    title="VeraForge API",
    version="1.0.0",
    description="magicpin AI challenge submission bot with demo helpers.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = ContextStore()
engine = VeraEngine(store)


@app.get("/v1/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    uptime = int((datetime.now(UTC) - store.started_at).total_seconds())
    return HealthResponse(status="ok", uptime_seconds=uptime, contexts_loaded=store.counts())


@app.get("/v1/metadata", response_model=MetadataResponse)
def metadata() -> MetadataResponse:
    return MetadataResponse(
        team_name="Akarsh",
        team_members=["Akarsh"],
        model="deterministic-trigger-composer-v1",
        approach="stateful FastAPI bot with trigger-aware composition, auto-reply detection, intent handoff routing, and a React demo cockpit",
        contact_email="akarsh@example.com",
        version="1.0.0",
        submitted_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
    )


@app.post("/v1/context", response_model=ContextPushResponse)
def push_context(payload: ContextPushRequest) -> JSONResponse | ContextPushResponse:
    accepted, stored, current_version = store.upsert_context(
        payload.scope,
        payload.context_id,
        payload.version,
        payload.payload,
        payload.delivered_at,
    )
    if not accepted:
        return JSONResponse(
            status_code=409,
            content=ContextPushResponse(
                accepted=False,
                reason="stale_version",
                current_version=current_version,
            ).model_dump(mode="json"),
        )
    return ContextPushResponse(
        accepted=True,
        ack_id=f"ack_{payload.context_id}_v{payload.version}",
        stored_at=stored.stored_at if stored else datetime.now(UTC),
    )


@app.post("/v1/tick", response_model=TickResponse)
def tick(request: TickRequest) -> TickResponse:
    actions = engine.select_actions(request.now, request.available_triggers)
    return TickResponse(actions=actions)


@app.post("/v1/reply", response_model=ReplyResponse)
def reply(request: ReplyRequest) -> ReplyResponse:
    conversation = store.get_conversation(request.conversation_id)
    if not conversation:
        conversation = store.create_conversation(
            conversation_id=request.conversation_id,
            merchant_id=request.merchant_id,
            customer_id=None,
            trigger_id="test_trigger",
            trigger_kind="generic",
            send_as="vera",
            suppression_key="test_suppress",
            opened_at=request.received_at,
            body="test message",
            cta="open_ended"
        )
    response = engine.handle_reply(conversation, request.message, request.received_at)
    return ReplyResponse(**response)


@app.post("/v1/demo/bootstrap", response_model=DemoBootstrapResponse)
def demo_bootstrap() -> DemoBootstrapResponse:
    counts = bootstrap_demo_data(store, PROJECT_ROOT)
    return DemoBootstrapResponse(ok=True, counts=counts)


@app.get("/v1/demo/state", response_model=DemoStateResponse)
def demo_state() -> DemoStateResponse:
    return DemoStateResponse(
        categories=store.list_payloads("category"),
        merchants=store.list_payloads("merchant"),
        customers=store.list_payloads("customer"),
        triggers=store.list_payloads("trigger"),
        conversations=store.list_conversations(),
    )
