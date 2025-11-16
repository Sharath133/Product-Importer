import json
from typing import List

import pytest

from backend.app.models import Webhook, WebhookEventType
from backend.app.services import webhook_service


@pytest.mark.asyncio
async def test_fetch_enabled_webhooks_filters_by_event_and_enabled(db_session):
    webhook_a = Webhook(url="https://example.com/a", event_type=WebhookEventType.PRODUCT_CREATED, enabled=True)
    webhook_b = Webhook(url="https://example.com/b", event_type=WebhookEventType.PRODUCT_CREATED, enabled=False)
    webhook_c = Webhook(url="https://example.com/c", event_type=WebhookEventType.PRODUCT_UPDATED, enabled=True)
    db_session.add_all([webhook_a, webhook_b, webhook_c])
    await db_session.commit()

    result = await webhook_service.fetch_enabled_webhooks(db_session, WebhookEventType.PRODUCT_CREATED)

    assert [webhook.url for webhook in result] == ["https://example.com/a"]


@pytest.mark.asyncio
async def test_enqueue_webhook_events_uses_filtered_webhooks(db_session, monkeypatch):
    target = Webhook(url="https://example.com/hook", event_type=WebhookEventType.PRODUCT_UPDATED, enabled=True)
    ignored = Webhook(url="https://example.com/disabled", event_type=WebhookEventType.PRODUCT_UPDATED, enabled=False)
    db_session.add_all([target, ignored])
    await db_session.commit()

    dispatched: List[dict] = []

    def capture(message: dict) -> None:
        dispatched.append(message)

    monkeypatch.setattr(webhook_service, "_dispatch_webhook", capture)

    await webhook_service.enqueue_webhook_events(
        db_session,
        WebhookEventType.PRODUCT_UPDATED,
        {"product_id": 1},
    )

    assert len(dispatched) == 1
    assert dispatched[0]["url"] == "https://example.com/hook"
    assert dispatched[0]["payload"] == {"product_id": 1}


@pytest.mark.asyncio
async def test_enqueue_webhook_events_respects_explicit_ids(db_session, monkeypatch):
    webhook_a = Webhook(url="https://example.com/a", event_type=WebhookEventType.PRODUCT_CREATED, enabled=True)
    webhook_b = Webhook(url="https://example.com/b", event_type=WebhookEventType.PRODUCT_CREATED, enabled=True)
    db_session.add_all([webhook_a, webhook_b])
    await db_session.commit()

    dispatched = []

    def capture(message: dict) -> None:
        dispatched.append(message)

    monkeypatch.setattr(webhook_service, "_dispatch_webhook", capture)

    await webhook_service.enqueue_webhook_events(
        db_session,
        WebhookEventType.PRODUCT_CREATED,
        {"product_id": 42},
        webhook_ids=[webhook_b.id],
    )

    assert len(dispatched) == 1
    assert dispatched[0]["webhook_id"] == webhook_b.id
    assert dispatched[0]["url"] == "https://example.com/b"

