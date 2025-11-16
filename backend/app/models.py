from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import CHAR, TypeDecorator

from .database import Base


class WebhookEventType(str, enum.Enum):
    """Supported webhook event types."""

    PRODUCT_CREATED = "product.created"
    PRODUCT_UPDATED = "product.updated"
    PRODUCT_DELETED = "product.deleted"
    IMPORT_COMPLETED = "import.completed"
    IMPORT_FAILED = "import.failed"
    BULK_DELETE_COMPLETED = "bulk_delete.completed"



class GUID(TypeDecorator):
    """Platform-independent GUID type for PostgreSQL + SQLite."""

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, UUID):
            return value if dialect.name == "postgresql" else str(value)
        coerced = UUID(str(value))
        return coerced if dialect.name == "postgresql" else str(coerced)

    def process_result_value(self, value, _dialect):
        if value is None or isinstance(value, UUID):
            return value
        return UUID(str(value))


class Product(Base):
    """Product catalog entity."""

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("sku_normalized", name="uq_products_sku_normalized"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    sku_normalized: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @staticmethod
    def normalize_sku(value: str) -> str:
        return value.strip().lower()

    @validates("sku")
    def _set_sku(self, _key: str, value: str) -> str:
        normalized = self.normalize_sku(value)
        self.sku_normalized = normalized
        return value.strip()


class Webhook(Base):
    """Webhook configuration for outbound notifications."""

    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    event_type: Mapped[WebhookEventType] = mapped_column(
        SqlEnum(WebhookEventType, name="webhook_event"), nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ImportJobStatus(str, enum.Enum):
    """Status states for CSV import job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportJob(Base):
    """Track CSV import jobs."""

    __tablename__ = "import_jobs"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    status: Mapped[ImportJobStatus] = mapped_column(
        SqlEnum(ImportJobStatus, name="import_job_status"),
        nullable=False,
        default=ImportJobStatus.PENDING,
        index=True,
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_records: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processed_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

