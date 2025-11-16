import pytest

from backend.app.api import products
from backend.app.models import Product, WebhookEventType


@pytest.fixture
def webhook_spy(monkeypatch):
    calls = []

    async def fake_enqueue(session, event_type, payload, webhook_ids=None):
        calls.append((event_type, payload))

    monkeypatch.setattr(products, "enqueue_webhook_events", fake_enqueue)
    return calls


@pytest.mark.asyncio
async def test_create_product_upserts_and_triggers_webhook(api_client, webhook_spy):
    payload = {"name": "Widget", "sku": "SKU-1", "description": "Example", "active": True}
    response = await api_client.post("/api/products", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Widget"
    assert webhook_spy[0][0] == WebhookEventType.PRODUCT_CREATED

    payload_updated = {"name": "Widget Updated", "sku": "sku-1", "description": "Updated", "active": False}
    response = await api_client.post("/api/products", json=payload_updated)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Widget Updated"
    assert webhook_spy[-1][0] == WebhookEventType.PRODUCT_UPDATED


@pytest.mark.asyncio
async def test_list_products_supports_filters(api_client, webhook_spy):
    await api_client.post("/api/products", json={"name": "Widget", "sku": "SKU-1", "description": "Widget desc"})
    await api_client.post("/api/products", json={"name": "Gadget", "sku": "SKU-2", "description": "Gadget desc"})

    response = await api_client.get("/api/products", params={"sku": "sku-1"})
    assert response.status_code == 200
    data = response.json()
    assert data["pagination"]["total"] == 1
    assert data["items"][0]["sku"] == "SKU-1"

    response = await api_client.get("/api/products", params={"name": "gad"})
    assert response.status_code == 200
    data = response.json()
    assert data["pagination"]["total"] == 1
    assert data["items"][0]["sku"] == "SKU-2"


@pytest.mark.asyncio
async def test_get_product_returns_404_for_missing(api_client):
    response = await api_client.get("/api/products/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_product_conflict_on_sku(api_client, webhook_spy):
    res_a = await api_client.post("/api/products", json={"name": "A", "sku": "SKU-A"})
    res_b = await api_client.post("/api/products", json={"name": "B", "sku": "SKU-B"})

    product_b_id = res_b.json()["id"]

    response = await api_client.put(
        f"/api/products/{product_b_id}",
        json={"sku": "SKU-A"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_product_triggers_webhook(api_client, webhook_spy):
    response = await api_client.post("/api/products", json={"name": "Widget", "sku": "SKU-1"})
    product_id = response.json()["id"]

    delete_response = await api_client.delete(f"/api/products/{product_id}")
    assert delete_response.status_code == 204
    assert any(event == WebhookEventType.PRODUCT_DELETED for event, _payload in webhook_spy)

    follow_up = await api_client.get(f"/api/products/{product_id}")
    assert follow_up.status_code == 404


@pytest.mark.asyncio
async def test_bulk_delete_returns_deleted_count(api_client, webhook_spy):
    await api_client.post("/api/products", json={"name": "Widget", "sku": "SKU-1"})
    await api_client.post("/api/products", json={"name": "Gadget", "sku": "SKU-2"})

    response = await api_client.delete("/api/products/bulk")
    assert response.status_code == 200
    assert response.json() == {"deleted": 2}

    second = await api_client.delete("/api/products/bulk")
    assert second.status_code == 200
    assert second.json() == {"deleted": 0}

