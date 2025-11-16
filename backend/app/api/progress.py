from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal, get_session
from ..models import ImportJob, ImportJobStatus
from ..progress_manager import get_progress

router = APIRouter(prefix="/api/progress", tags=["progress"])

POLL_INTERVAL_SECONDS = 1.0


@router.get("/{job_id}")
async def stream_progress(job_id: UUID, session: AsyncSession = Depends(get_session)):
    job = await session.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    return EventSourceResponse(_progress_event_stream(str(job_id)), ping=1000)


async def _progress_event_stream(job_id: str):
    while True:
        job = await _fetch_job(job_id)
        progress_data = await get_progress(job_id)

        if not job:
            yield {
                "event": "error",
                "data": json.dumps({"message": "Job not found", "job_id": job_id}),
            }
            break

        payload = {
            "job_id": job_id,
            "status": job.status.value,
            "progress": job.progress or 0,  # Ensure progress is never None
            "processed_records": job.processed_records or 0,
            "total_records": job.total_records or 0,
            "error_message": job.error_message,
        }

        if progress_data:
            # Merge Redis progress data, but normalize field names
            payload.update(progress_data)
            # Ensure consistent field names (Redis uses 'processed'/'total', DB uses 'processed_records'/'total_records')
            if "processed" in payload and "processed_records" not in payload:
                payload["processed_records"] = int(payload.get("processed", 0) or 0)
            if "total" in payload and "total_records" not in payload:
                payload["total_records"] = int(payload.get("total", 0) or 0)
            # Ensure progress is a number
            if "progress" in payload:
                try:
                    payload["progress"] = int(payload["progress"] or 0)
                except (ValueError, TypeError):
                    payload["progress"] = 0

        yield {
            "event": "progress",
            "data": json.dumps(payload, default=str),
        }

        if job.status in {ImportJobStatus.COMPLETED, ImportJobStatus.FAILED}:
            break

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _fetch_job(job_id: str) -> ImportJob | None:
    async with AsyncSessionLocal() as session:
        return await session.get(ImportJob, UUID(job_id))

