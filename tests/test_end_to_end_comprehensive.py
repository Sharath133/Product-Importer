"""
Comprehensive end-to-end tests that verify the full application flow
from CSV upload through processing to webhook delivery.
"""
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.app.models import ImportJob, ImportJobStatus, Product, Webhook, WebhookEventType
from backend.app.tasks import _process_csv_import


@pytest.mark.asyncio
async def test_complete_csv_import_with_real_processing(api_client, db_session, fakeredis_clients, monkeypatch, tmp_path):
    """Test complete CSV import flow with actual task processing."""
    # Mock Dramatiq actor to avoid Redis connection
    class StubActor:
        def __init__(self):
            self.calls = []

        def send(self, job_id: str):
            self.calls.append(job_id)

    process_stub = StubActor()
    monkeypatch.setattr("backend.app.tasks.process_csv_import", process_stub)

    # Setup webhooks
    webhooks = [
        Webhook(url="https://example.com/product-created", event_type=WebhookEventType.PRODUCT_CREATED, enabled=True),
        Webhook(url="https://example.com/product-updated", event_type=WebhookEventType.PRODUCT_UPDATED, enabled=True),
        Webhook(url="https://example.com/import-completed", event_type=WebhookEventType.IMPORT_COMPLETED, enabled=True),
    ]
    db_session.add_all(webhooks)
    await db_session.commit()

    # Step 1: Upload CSV file
    csv_content = b"name,sku,description\nWidget,SKU-001,Test widget\nGadget,SKU-002,Test gadget\nTool,SKU-003,Test tool\n"
    response = await api_client.post(
        "/api/products/upload",
        files={"file": ("products.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"
    job_data = response.json()
    job_id = job_data["id"]
    assert job_data["status"] == ImportJobStatus.PENDING.value
    assert job_data["file_path"] is not None

    # Step 2: Process the import (simulating worker execution)
    await _process_csv_import(job_id)

    # Step 3: Verify job completion
    job = await db_session.get(ImportJob, uuid.UUID(job_id))
    assert job is not None
    assert job.status == ImportJobStatus.COMPLETED
    assert job.processed_records == 3
    assert job.total_records == 3
    assert job.progress == 100
    assert job.error_message is None
    # File should be cleaned up
    assert not Path(job.file_path).exists()

    # Step 4: Verify products were created
    result = await db_session.execute(select(Product).order_by(Product.sku))
    products = result.scalars().all()
    assert len(products) == 3
    assert products[0].sku == "SKU-001"
    assert products[0].name == "Widget"
    assert products[1].sku == "SKU-002"
    assert products[2].sku == "SKU-003"

    # Step 5: Verify progress tracking in Redis
    redis_sync, _ = fakeredis_clients
    progress_data = redis_sync.hgetall(f"product-import:progress:{job_id}")
    assert progress_data["status"] == ImportJobStatus.COMPLETED.value
    assert progress_data["progress"] == "100"
    assert progress_data["processed"] == "3"
    assert progress_data["total"] == "3"


@pytest.mark.asyncio
async def test_csv_import_with_duplicate_sku_overwrites(api_client, db_session, fakeredis_clients, monkeypatch, tmp_path):
    """Test that duplicate SKUs in CSV overwrite existing products."""
    # Mock Dramatiq actor
    class StubActor:
        def send(self, job_id: str):
            pass

    monkeypatch.setattr("backend.app.tasks.process_csv_import", StubActor())

    # Create an existing product
    existing = Product(name="Old Widget", sku="SKU-001", description="Old description", active=True)
    db_session.add(existing)
    await db_session.commit()

    # Upload CSV with same SKU but different data
    csv_content = b"name,sku,description\nNew Widget,SKU-001,New description\n"
    response = await api_client.post(
        "/api/products/upload",
        files={"file": ("products.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    # Process import
    await _process_csv_import(job_id)

    # Refresh session to see updates
    await db_session.refresh(existing)

    # Verify product was updated, not duplicated
    result = await db_session.execute(select(Product).where(Product.sku_normalized == "sku-001"))
    products = result.scalars().all()
    assert len(products) == 1
    assert products[0].name == "New Widget"
    assert products[0].description == "New description"
    # ID should be the same (updated, not new)
    assert products[0].id == existing.id


@pytest.mark.asyncio
async def test_csv_import_handles_invalid_data(api_client, db_session, fakeredis_clients, monkeypatch, tmp_path):
    """Test that invalid CSV data is properly handled."""
    # Mock Dramatiq actor
    class StubActor:
        def send(self, job_id: str):
            pass

    monkeypatch.setattr("backend.app.tasks.process_csv_import", StubActor())

    # CSV with missing required field
    csv_content = b"name,sku,description\nWidget,,\n"
    response = await api_client.post(
        "/api/products/upload",
        files={"file": ("products.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    # Process import - should fail
    await _process_csv_import(job_id)

    # Verify job failed
    job = await db_session.get(ImportJob, uuid.UUID(job_id))
    assert job.status == ImportJobStatus.FAILED
    assert job.error_message is not None
    assert "name" in job.error_message.lower() or "sku" in job.error_message.lower()

    # Verify no products were created
    result = await db_session.execute(select(Product))
    products = result.scalars().all()
    assert len(products) == 0


@pytest.mark.asyncio
async def test_product_crud_flow(api_client, db_session):
    """Test complete product CRUD operations."""
    # Create
    response = await api_client.post(
        "/api/products",
        json={"name": "Test Product", "sku": "TEST-001", "description": "Test description", "active": True},
    )
    assert response.status_code == 201
    product_data = response.json()
    product_id = product_data["id"]
    assert product_data["name"] == "Test Product"
    assert product_data["sku"] == "TEST-001"

    # Read
    response = await api_client.get(f"/api/products/{product_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Test Product"

    # List with filter
    response = await api_client.get("/api/products?sku=TEST-001")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["sku"] == "TEST-001"

    # Update
    response = await api_client.put(
        f"/api/products/{product_id}",
        json={"name": "Updated Product", "active": False},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Product"
    assert response.json()["active"] is False

    # Delete
    response = await api_client.delete(f"/api/products/{product_id}")
    assert response.status_code == 204

    # Verify deleted
    response = await api_client.get(f"/api/products/{product_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_bulk_delete_flow(api_client, db_session):
    """Test bulk delete operation."""
    # Create multiple products
    for i in range(5):
        await api_client.post(
            "/api/products",
            json={"name": f"Product {i}", "sku": f"SKU-{i:03d}", "description": f"Description {i}"},
        )

    # Verify they exist
    response = await api_client.get("/api/products")
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 5

    # Bulk delete
    response = await api_client.delete("/api/products/bulk")
    assert response.status_code == 200
    assert response.json()["deleted"] == 5

    # Verify all deleted
    response = await api_client.get("/api/products")
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_webhook_management_flow(api_client, db_session):
    """Test complete webhook CRUD operations."""
    # Create
    response = await api_client.post(
        "/api/webhooks",
        json={
            "url": "https://example.com/webhook",
            "event_type": "product.created",
            "enabled": True,
        },
    )
    assert response.status_code == 201
    webhook_data = response.json()
    webhook_id = webhook_data["id"]
    assert webhook_data["url"] == "https://example.com/webhook"
    assert webhook_data["event_type"] == "product.created"

    # List
    response = await api_client.get("/api/webhooks")
    assert response.status_code == 200
    webhooks = response.json()
    assert len(webhooks) >= 1
    assert any(w["id"] == webhook_id for w in webhooks)

    # Update
    response = await api_client.put(
        f"/api/webhooks/{webhook_id}",
        json={"enabled": False, "event_type": "product.updated"},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["event_type"] == "product.updated"

    # Test webhook (with mocked HTTP client)
    with patch("backend.app.api.webhooks.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

        response = await api_client.post(f"/api/webhooks/{webhook_id}/test")
        assert response.status_code == 200
        data = response.json()
        assert data["status_code"] == 200

    # Delete
    response = await api_client.delete(f"/api/webhooks/{webhook_id}")
    assert response.status_code == 204

    # Verify deleted
    response = await api_client.get("/api/webhooks")
    webhooks = response.json()
    assert not any(w["id"] == webhook_id for w in webhooks)


@pytest.mark.asyncio
async def test_progress_streaming(api_client, db_session, fakeredis_clients, monkeypatch):
    """Test SSE progress streaming."""
    # Mock Dramatiq actor
    class StubActor:
        def send(self, job_id: str):
            pass

    monkeypatch.setattr("backend.app.tasks.process_csv_import", StubActor())

    # Create a job
    csv_content = b"name,sku,description\nItem,SKU-1,Test\n"
    response = await api_client.post(
        "/api/products/upload",
        files={"file": ("test.csv", csv_content, "text/csv")},
    )
    job_id = response.json()["id"]

    # Start processing in background
    import asyncio
    task = asyncio.create_task(_process_csv_import(job_id))

    # Stream progress (with timeout)
    from backend.app.api import progress as progress_api

    events_received = []
    try:
        async for event in progress_api._progress_event_stream(job_id):
            events_received.append(event)
            if event.get("event") == "progress":
                data = json.loads(event["data"])
                if data.get("status") == ImportJobStatus.COMPLETED.value:
                    break
            # Safety timeout
            if len(events_received) > 10:
                break
    except Exception:
        pass
    finally:
        await task

    # Verify we received progress events
    assert len(events_received) > 0
    final_event = events_received[-1]
    assert final_event["event"] == "progress"
    final_data = json.loads(final_event["data"])
    assert final_data["status"] == ImportJobStatus.COMPLETED.value
    assert final_data["progress"] == 100

