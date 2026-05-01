from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ContextPushRequest(FlexibleModel):
    scope: Literal["category", "merchant", "customer", "trigger"]
    context_id: str
    version: int = Field(ge=1)
    payload: dict[str, Any]
    delivered_at: datetime


class ContextPushResponse(FlexibleModel):
    accepted: bool
    ack_id: str | None = None
    stored_at: datetime | None = None
    reason: str | None = None
    current_version: int | None = None
    details: str | None = None


class TickRequest(FlexibleModel):
    now: datetime
    available_triggers: list[str] = Field(default_factory=list)


class TickAction(FlexibleModel):
    conversation_id: str
    merchant_id: str
    customer_id: str | None = None
    send_as: Literal["vera", "merchant_on_behalf"]
    trigger_id: str
    template_name: str
    template_params: list[str]
    body: str
    cta: Literal["yes_stop", "open_ended", "none"]
    suppression_key: str
    rationale: str


class TickResponse(FlexibleModel):
    actions: list[TickAction] = Field(default_factory=list)


class ReplyRequest(FlexibleModel):
    conversation_id: str
    merchant_id: str
    customer_id: str | None = None
    from_role: Literal["merchant", "customer"]
    message: str
    received_at: datetime
    turn_number: int = Field(ge=1)


class ReplyResponse(FlexibleModel):
    action: Literal["send", "wait", "end"]
    body: str | None = None
    cta: Literal["yes_stop", "open_ended", "none"] | None = None
    wait_seconds: int | None = None
    rationale: str


class HealthResponse(FlexibleModel):
    status: Literal["ok"]
    uptime_seconds: int
    contexts_loaded: dict[str, int]


class MetadataResponse(FlexibleModel):
    team_name: str
    team_members: list[str]
    model: str
    approach: str
    contact_email: str
    version: str
    submitted_at: str


class DemoBootstrapResponse(FlexibleModel):
    ok: bool
    counts: dict[str, int]


class DemoStateResponse(FlexibleModel):
    categories: list[dict[str, Any]]
    merchants: list[dict[str, Any]]
    customers: list[dict[str, Any]]
    triggers: list[dict[str, Any]]
    conversations: list[dict[str, Any]]
