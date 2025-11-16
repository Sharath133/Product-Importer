import httpx
import pytest

from backend.app.api import webhooks


class DummyResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class DummyAsyncClient:
    def __init__(self, status_code=200, text="OK", raise_error=False):
        self.status_code = status_code
        self.text = text
        self.raise_error = raise_error
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def post(self, url, json):
        self.requests.append((url, json))
        if self.raise_error:
            raise httpx.RequestError("boom", request=httpx.Request("POST", url))
        return DummyResponse(self.status_code, self.text)


@pytest.mark.asyncio
async def test_create_update_delete_webhook(api_client):
    create = await api_client.post(
        "/api/webhooks",
        json={"url": "https://example.com/hook", "event_type": "product.created", "enabled": True},
    )
    assert create.status_code == 201
    webhook = create.json()

    listing = await api_client.get("/api/webhooks")
    assert listing.status_code == 200
    assert listing.json()[0]["url"] == "https://example.com/hook"

    update = await api_client.put(
        f"/api/webhooks/{webhook['id']}",
        json={"enabled": False},
    )
    assert update.status_code == 200
    assert update.json()["enabled"] is False

    delete = await api_client.delete(f"/api/webhooks/{webhook['id']}")
    assert delete.status_code == 204

    listing_after = await api_client.get("/api/webhooks")
    assert listing_after.json() == []


@pytest.mark.asyncio
async def test_test_webhook_happy_path(api_client, monkeypatch):
    dummy_client = DummyAsyncClient(status_code=204, text="OK")
    monkeypatch.setattr(webhooks.httpx, "AsyncClient", lambda **kwargs: dummy_client)

    created = await api_client.post(
        "/api/webhooks",
        json={"url": "https://example.com/hook", "event_type": "product.created", "enabled": True},
    )
    webhook = created.json()

    response = await api_client.post(f"/api/webhooks/{webhook['id']}/test")
    assert response.status_code == 200
    body = response.json()
    assert body["status_code"] == 204
    assert dummy_client.requests[0][0] == "https://example.com/hook"


@pytest.mark.asyncio
async def test_test_webhook_handles_request_error(api_client, monkeypatch):
    dummy_client = DummyAsyncClient(raise_error=True)
    monkeypatch.setattr(webhooks.httpx, "AsyncClient", lambda **kwargs: dummy_client)

    created = await api_client.post(
        "/api/webhooks",
        json={"url": "https://example.com/hook", "event_type": "product.created", "enabled": True},
    )
    webhook = created.json()

    response = await api_client.post(f"/api/webhooks/{webhook['id']}/test")
    assert response.status_code == 502
    assert "Request failed" in response.json()["detail"]

