import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.api import progress as progress_api
from backend.app.models import ImportJob, ImportJobStatus, Product, Webhook, WebhookEventType
from backend.app.services import webhook_service
from backend.app.tasks import _process_csv_import


@pytest.mark.asyncio
async def test_full_csv_import_flow(api_client, db_session, fakeredis_clients, monkeypatch, tmp_path):
    events = []

    def capture(message: dict) -> None:
        events.append(message)

    monkeypatch.setattr(webhook_service, "_dispatch_webhook", capture)

    class StubActor:
        def __init__(self):
            self.calls = []

        def send(self, job_id: str):
            self.calls.append(job_id)

    process_stub = StubActor()
    monkeypatch.setattr("backend.app.tasks.process_csv_import", process_stub)

    webhooks = [
        Webhook(url="https://example.com/product-created", event_type=WebhookEventType.PRODUCT_CREATED, enabled=True),
        Webhook(url="https://example.com/product-updated", event_type=WebhookEventType.PRODUCT_UPDATED, enabled=True),
        Webhook(url="https://example.com/import-completed", event_type=WebhookEventType.IMPORT_COMPLETED, enabled=True),
        Webhook(url="https://example.com/import-failed", event_type=WebhookEventType.IMPORT_FAILED, enabled=True),
    ]
    db_session.add_all(webhooks)
    await db_session.commit()

    csv_content = b"name,sku,description\nWidget,SKU-1,Example\nGadget,SKU-2,Example\n"
    response = await api_client.post(
        "/api/products/upload",
        files={"file": ("products.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 202
    job_payload = response.json()

    await _process_csv_import(job_payload["id"])

    job = await db_session.get(ImportJob, uuid.UUID(job_payload["id"]))
    assert job.status == ImportJobStatus.COMPLETED
    assert job.processed_records == 2
    assert job.total_records == 2
    assert not Path(job_payload["file_path"]).exists()

    result = await db_session.execute(select(Product))
    products = result.scalars().all()
    assert len(products) == 2

    event_types = {event["event_type"] for event in events}
    assert WebhookEventType.PRODUCT_CREATED.value in event_types
    assert WebhookEventType.IMPORT_COMPLETED.value in event_types

    redis_sync, _ = fakeredis_clients
    redis_data = redis_sync.hgetall(f"product-import:progress:{job_payload['id']}")
    assert redis_data["status"] == ImportJobStatus.COMPLETED.value

    progress_events = []
    async for event in progress_api._progress_event_stream(job_payload["id"]):
        progress_events.append(event)
    assert progress_events[-1]["event"] == "progress"
    final_payload = json.loads(progress_events[-1]["data"])
    assert final_payload["status"] == ImportJobStatus.COMPLETED.value

