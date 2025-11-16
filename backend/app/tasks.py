from __future__ import annotations

import asyncio
import logging
import json
import time
from pathlib import Path
from typing import Sequence
from uuid import UUID
import threading

import dramatiq
from dramatiq import Retry
import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .. import dramatiq_app  # Ensures broker configuration is loaded
from .database import AsyncSessionLocal
from .models import ImportJob, ImportJobStatus, Product, WebhookEventType
from .progress_manager import update_progress, clear_progress
from .schemas import ProductRead
from .services.csv_processor import CSVValidationError, count_rows, iter_batches
from .services.webhook_service import enqueue_webhook_events

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


_thread_local = threading.local()


def _run_in_thread_loop(coro):
    """Run an async coroutine on a per-thread persistent event loop.

    Using asyncio.run() creates and closes a loop each call. On Windows, closing
    the ProactorEventLoop can cause 'Event loop is closed' or 'NoneType.send'
    errors on subsequent asyncpg operations handled by dramatiq worker threads.
    Keeping one loop per worker thread avoids those issues.
    """
    loop = getattr(_thread_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _thread_local.loop = loop
    return loop.run_until_complete(coro)


@dramatiq.actor(max_retries=0, queue_name="default")
def process_csv_import(job_id: str) -> None:
    """Entry point Dramatiq actor for processing CSV imports."""
    _run_in_thread_loop(_process_csv_import(job_id))


@dramatiq.actor(max_retries=3, min_backoff=5000)
def dispatch_webhook(message_json: str) -> None:
    """Send an HTTP request to the configured webhook endpoint."""
    _run_in_thread_loop(_dispatch_webhook(message_json))


async def _process_csv_import(job_id: str) -> None:
    logger.info("Import job %s received by worker", job_id)
    job_uuid = UUID(job_id)
    async with AsyncSessionLocal() as session:
        job = await session.get(ImportJob, job_uuid, with_for_update=True)
        if not job:
            logger.error("Import job %s not found", job_id)
            return

        if not job.file_path:
            logger.error("Import job %s missing file path", job_id)
            await _mark_failed(session, job, "Upload reference missing; cannot process.")
            return

        # Reset any leftover progress from previous runs for the same job id (defensive)
        clear_progress(job_id)
        await _update_job_status(session, job, ImportJobStatus.PROCESSING, reset_progress=True)
        logger.info("Job %s: starting counting for file %s", job_id, job.file_path)
        update_progress(
            job_id,
            status=ImportJobStatus.PROCESSING.value,
            progress="0",
            phase="counting",
            message="Counting CSV rows",
        )

        try:
            # Run counting in threadpool to avoid blocking
            loop = asyncio.get_running_loop()
            total_records = await loop.run_in_executor(None, count_rows, job.file_path)
            logger.info("Job %s: counting completed, total=%s", job_id, total_records)
        except CSVValidationError as exc:
            logger.exception("CSV validation failed for job %s: %s", job_id, exc)
            await _mark_failed(session, job, str(exc))
            return
        except Exception as exc:  # pragma: no cover - safety
            logger.exception("Unexpected error counting rows for job %s", job_id)
            await _mark_failed(session, job, "Unexpected error preparing import.")
            raise Retry() from exc

        job.total_records = total_records
        job.processed_records = 0
        await session.commit()
        logger.info("Job %s: starting import", job_id)
        update_progress(
            job_id,
            status=ImportJobStatus.PROCESSING.value,
            progress="0",
            phase="importing",
            message="Starting import",
            total=str(total_records),
        )

        processed_raw_rows = 0

        try:
            async for batch_payload, raw_count in _iter_batches_async(job.file_path):
                processed_raw_rows += raw_count

                normalized_skus = [row["sku_normalized"] for row in batch_payload]
                existing_result = await session.execute(
                    select(Product.sku_normalized).where(Product.sku_normalized.in_(normalized_skus))
                )
                existing_skus = set(existing_result.scalars().all())

                await _upsert_products(session, batch_payload)

                job.processed_records += raw_count
                job.progress = _calculate_progress(job.processed_records, job.total_records)
                await session.commit()
                logger.info(
                    "Job %s: processed %s/%s (progress=%s%%)",
                    job_id,
                    job.processed_records,
                    job.total_records,
                    job.progress,
                )

                products_result = await session.execute(
                    select(Product).where(Product.sku_normalized.in_(normalized_skus))
                )
                products = products_result.scalars().all()

                for product in products:
                    event_type = (
                        WebhookEventType.PRODUCT_CREATED
                        if product.sku_normalized not in existing_skus
                        else WebhookEventType.PRODUCT_UPDATED
                    )
                    await enqueue_webhook_events(
                        session,
                        event_type,
                        ProductRead.model_validate(product, from_attributes=True).model_dump(),
                    )

                update_progress(
                    job_id,
                    status=ImportJobStatus.PROCESSING.value,
                    progress=str(job.progress),
                    processed=str(job.processed_records),
                    total=str(job.total_records or 0),
                )
        except CSVValidationError as exc:
            logger.exception("CSV processing failed for job %s: %s", job_id, exc)
            await _mark_failed(session, job, str(exc))
            return
        except Exception as exc:  # pragma: no cover - safety
            logger.exception("Unexpected error processing job %s", job_id)
            await _mark_failed(session, job, "Unexpected error processing CSV.")
            raise Retry() from exc
        finally:
            _cleanup_file(job.file_path)

        await _update_job_status(session, job, ImportJobStatus.COMPLETED)
        await enqueue_webhook_events(
            session,
            WebhookEventType.IMPORT_COMPLETED,
            {
                "job_id": job_id,
                "processed_records": job.processed_records,
                "total_records": job.total_records,
            },
        )
        update_progress(
            job_id,
            status=ImportJobStatus.COMPLETED.value,
            progress="100",
            processed=str(job.processed_records),
            total=str(job.total_records or 0),
            message="Import completed successfully",
        )
        # Allow clients to observe completion for a short window, then clear
        try:
            await asyncio.sleep(2)
        finally:
            clear_progress(job_id)


async def _dispatch_webhook(message_json: str) -> None:
    data = json.loads(message_json)
    url = data["url"]
    event_type = data["event_type"]
    payload = data.get("payload", {})

    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json={"event": event_type, "data": payload})
        duration_ms = int((time.perf_counter() - start) * 1000)
        if response.status_code >= 400:
            logger.warning(
                "Webhook delivery failed for %s (status %s, %sms)",
                url,
                response.status_code,
                duration_ms,
            )
            raise Retry()
        logger.info("Webhook delivered to %s in %sms", url, duration_ms)
    except Retry:
        raise
    except Exception as exc:  # pragma: no cover - safety
        logger.exception("Unexpected error delivering webhook to %s", url)
        raise Retry() from exc


def _calculate_progress(processed: int, total: int | None) -> int:
    if not total or total == 0:
        return 0
    percent = int(processed * 100 / total)
    return min(percent, 100)


async def _update_job_status(
    session: AsyncSession,
    job: ImportJob,
    status: ImportJobStatus,
    reset_progress: bool = False,
) -> None:
    job.status = status
    if reset_progress:
        job.progress = 0
        job.processed_records = 0
    if status == ImportJobStatus.COMPLETED:
        job.progress = 100
    await session.commit()
    await session.refresh(job)


async def _mark_failed(session: AsyncSession, job: ImportJob, message: str) -> None:
    job.status = ImportJobStatus.FAILED
    job.error_message = message
    job.progress = 0
    await session.commit()
    await enqueue_webhook_events(
        session,
        WebhookEventType.IMPORT_FAILED,
        {
            "job_id": str(job.id),
            "message": message,
        },
    )
    update_progress(
        str(job.id),
        status=ImportJobStatus.FAILED.value,
        progress="0",
        message=message,
    )
    _cleanup_file(job.file_path)


async def _iter_batches_async(file_path: str):
    loop = asyncio.get_running_loop()
    iterator = iter_batches(file_path, batch_size=BATCH_SIZE)

    while True:
        batch = await loop.run_in_executor(None, _next_batch, iterator)
        if batch is None:
            break
        yield batch


def _next_batch(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return None


async def _upsert_products(session: AsyncSession, rows: Sequence[dict]) -> None:
    if not rows:
        return

    stmt = insert(Product).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Product.sku_normalized],
        set_={
            "name": stmt.excluded.name,
            "sku": stmt.excluded.sku,
            "description": stmt.excluded.description,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)


def _cleanup_file(file_path: str | None) -> None:
    if not file_path:
        return
    try:
        Path(file_path).unlink(missing_ok=True)
    except OSError:
        logger.warning("Unable to remove temporary file %s", file_path, exc_info=True)

