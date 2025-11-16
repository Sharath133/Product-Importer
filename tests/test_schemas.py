import pytest
from pydantic import ValidationError

from backend.app.models import WebhookEventType
from backend.app.schemas import (
    ProductCreate,
    ProductUpdate,
    WebhookCreate,
    WebhookUpdate,
)


def test_product_create_validation():
    model = ProductCreate(name="Widget", sku="SKU-1", description="Desc", active=True)
    assert model.name == "Widget"

    with pytest.raises(ValidationError):
        ProductCreate(name="x" * 300, sku="SKU-1")


def test_product_update_allows_partial_fields():
    payload = ProductUpdate(name="Gadget")
    assert payload.name == "Gadget"
    assert payload.sku is None


def test_webhook_create_requires_valid_url():
    hook = WebhookCreate(url="https://example.com/hook", event_type=WebhookEventType.PRODUCT_CREATED, enabled=True)
    assert str(hook.url) == "https://example.com/hook"

    with pytest.raises(ValidationError):
        WebhookCreate(url="not-a-url", event_type=WebhookEventType.PRODUCT_CREATED)


def test_webhook_update_optional():
    payload = WebhookUpdate(enabled=False)
    assert payload.enabled is False

