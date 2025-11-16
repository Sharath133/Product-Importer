from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from .models import ImportJobStatus, WebhookEventType


class Pagination(BaseModel):
    total: int
    page: int
    size: int


class ProductBase(BaseModel):
    name: str = Field(..., max_length=255)
    sku: str = Field(..., max_length=64)
    description: Optional[str] = Field(default=None, max_length=2000)
    active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    sku: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=2000)
    active: Optional[bool] = None


class ProductRead(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    items: List[ProductRead]
    pagination: Pagination


class ImportJobRead(BaseModel):
    id: UUID
    status: ImportJobStatus
    progress: int
    total_records: Optional[int]
    processed_records: int
    file_path: Optional[str]
    original_filename: Optional[str]
    content_type: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookBase(BaseModel):
    url: HttpUrl
    event_type: WebhookEventType
    enabled: bool = True


class WebhookCreate(WebhookBase):
    pass


class WebhookUpdate(BaseModel):
    url: Optional[HttpUrl] = None
    event_type: Optional[WebhookEventType] = None
    enabled: Optional[bool] = None


class WebhookRead(WebhookBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

