from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Webhook, WebhookEventType

logger = logging.getLogger(__name__)


async def fetch_enabled_webhooks(session: AsyncSession, event_type: WebhookEventType) -> List[Webhook]:
    stmt = select(Webhook).where(
        Webhook.event_type == event_type,
        Webhook.enabled.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def enqueue_webhook_events(
    session: AsyncSession,
    event_type: WebhookEventType,
    payload: Dict[str, Any],
    webhook_ids: Optional[Iterable[int]] = None,
) -> None:
    """Schedule webhook deliveries for the given payload."""
    if webhook_ids:
        stmt = select(Webhook).where(
            Webhook.id.in_(list(webhook_ids)),
            Webhook.enabled.is_(True),
        )
        result = await session.execute(stmt)
        webhooks = result.scalars().all()
    else:
        webhooks = await fetch_enabled_webhooks(session, event_type)

    if not webhooks:
        return

    message = {
        "event_type": event_type.value,
        "payload": payload,
    }

    for webhook in webhooks:
        message_with_target = {
            **message,
            "webhook_id": webhook.id,
            "url": webhook.url,
        }
        _dispatch_webhook(message_with_target)


def _dispatch_webhook(message: Dict[str, Any]) -> None:
    """Send webhook message to Dramatiq actor."""
    try:
        from ..tasks import dispatch_webhook  # Imported lazily to avoid circular dependency

        dispatch_webhook.send(json.dumps(message))
    except Exception:  # pragma: no cover - safety
        logger.exception("Failed to enqueue webhook dispatch for %s", message.get("url"))

