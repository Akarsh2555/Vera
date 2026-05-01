from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any


UTC = timezone.utc


@dataclass
class StoredContext:
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: datetime
    stored_at: datetime


@dataclass
class ConversationRecord:
    conversation_id: str
    merchant_id: str
    customer_id: str | None
    trigger_id: str
    trigger_kind: str
    send_as: str
    suppression_key: str
    opened_at: datetime
    last_updated_at: datetime
    status: str = "active"
    turn_count: int = 1
    last_bot_message: str = ""
    last_cta: str = "open_ended"
    auto_reply_hits: int = 0
    detected_language: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


class ContextStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._started_at = datetime.now(UTC)
        self._contexts: dict[str, dict[str, StoredContext]] = {
            "category": {},
            "merchant": {},
            "customer": {},
            "trigger": {},
        }
        self._conversations: dict[str, ConversationRecord] = {}
        self._sent_suppressions: dict[str, datetime] = {}

    @property
    def started_at(self) -> datetime:
        return self._started_at

    def clear(self) -> None:
        with self._lock:
            self._started_at = datetime.now(UTC)
            for bucket in self._contexts.values():
                bucket.clear()
            self._conversations.clear()
            self._sent_suppressions.clear()

    def upsert_context(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict[str, Any],
        delivered_at: datetime,
    ) -> tuple[bool, StoredContext | None, int | None]:
        with self._lock:
            bucket = self._contexts[scope]
            existing = bucket.get(context_id)
            if existing and version <= existing.version:
                return False, existing, existing.version

            stored = StoredContext(
                scope=scope,
                context_id=context_id,
                version=version,
                payload=payload,
                delivered_at=delivered_at,
                stored_at=datetime.now(UTC),
            )
            bucket[context_id] = stored
            return True, stored, None

    def get_context(self, scope: str, context_id: str) -> StoredContext | None:
        return self._contexts[scope].get(context_id)

    def get_latest_payload(self, scope: str, context_id: str) -> dict[str, Any] | None:
        ctx = self.get_context(scope, context_id)
        return ctx.payload if ctx else None

    def list_payloads(self, scope: str) -> list[dict[str, Any]]:
        return [stored.payload for stored in self._contexts[scope].values()]

    def counts(self) -> dict[str, int]:
        return {scope: len(bucket) for scope, bucket in self._contexts.items()}

    def mark_suppression_sent(self, suppression_key: str, sent_at: datetime) -> None:
        with self._lock:
            self._sent_suppressions[suppression_key] = sent_at

    def was_suppression_sent(self, suppression_key: str) -> bool:
        return suppression_key in self._sent_suppressions

    def create_conversation(
        self,
        *,
        conversation_id: str,
        merchant_id: str,
        customer_id: str | None,
        trigger_id: str,
        trigger_kind: str,
        send_as: str,
        suppression_key: str,
        opened_at: datetime,
        body: str,
        cta: str,
    ) -> ConversationRecord:
        record = ConversationRecord(
            conversation_id=conversation_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            trigger_id=trigger_id,
            trigger_kind=trigger_kind,
            send_as=send_as,
            suppression_key=suppression_key,
            opened_at=opened_at,
            last_updated_at=opened_at,
            last_bot_message=body,
            last_cta=cta,
            history=[{"at": opened_at.isoformat(), "from": "bot", "body": body, "cta": cta}],
        )
        with self._lock:
            self._conversations[conversation_id] = record
        return record

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        return self._conversations.get(conversation_id)

    def get_last_messaged_at(self, merchant_id: str) -> datetime | None:
        with self._lock:
            latest = None
            for record in self._conversations.values():
                if record.merchant_id == merchant_id:
                    if not latest or record.last_updated_at > latest:
                        latest = record.last_updated_at
            return latest

    def update_conversation(
        self,
        conversation_id: str,
        *,
        status: str | None = None,
        turn_count: int | None = None,
        last_bot_message: str | None = None,
        last_cta: str | None = None,
        auto_reply_hits: int | None = None,
        detected_language: str | None = None,
        append_event: dict[str, Any] | None = None,
        updated_at: datetime | None = None,
    ) -> ConversationRecord | None:
        with self._lock:
            record = self._conversations.get(conversation_id)
            if not record:
                return None
            if status is not None:
                record.status = status
            if turn_count is not None:
                record.turn_count = turn_count
            if last_bot_message is not None:
                record.last_bot_message = last_bot_message
            if last_cta is not None:
                record.last_cta = last_cta
            if auto_reply_hits is not None:
                record.auto_reply_hits = auto_reply_hits
            if detected_language is not None:
                record.detected_language = detected_language
            if append_event is not None:
                record.history.append(append_event)
            record.last_updated_at = updated_at or datetime.now(UTC)
            return record

    def list_conversations(self) -> list[dict[str, Any]]:
        conversations = []
        for record in self._conversations.values():
            conversations.append(
                {
                    "conversation_id": record.conversation_id,
                    "merchant_id": record.merchant_id,
                    "customer_id": record.customer_id,
                    "trigger_id": record.trigger_id,
                    "trigger_kind": record.trigger_kind,
                    "send_as": record.send_as,
                    "status": record.status,
                    "turn_count": record.turn_count,
                    "opened_at": record.opened_at.isoformat(),
                    "last_updated_at": record.last_updated_at.isoformat(),
                    "last_bot_message": record.last_bot_message,
                    "last_cta": record.last_cta,
                    "auto_reply_hits": record.auto_reply_hits,
                    "detected_language": record.detected_language,
                    "history": record.history,
                }
            )
        return sorted(conversations, key=lambda item: item["last_updated_at"], reverse=True)
