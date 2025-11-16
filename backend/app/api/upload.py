from __future__ import annotations

import secrets
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import ImportJob, ImportJobStatus
from ..schemas import ImportJobRead


router = APIRouter(prefix="/api/products", tags=["upload"])

MAX_CSV_SIZE_MB = 200
UPLOAD_DIR = Path("./storage/uploads")
CHUNK_SIZE = 1024 * 1024  # 1MB


@router.post("/upload", response_model=ImportJobRead, status_code=status.HTTP_202_ACCEPTED)
async def upload_products(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> ImportJobRead:
    """Accept a CSV upload and queue a background import job."""

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV files are supported.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    unique_suffix = secrets.token_hex(8)
    destination = UPLOAD_DIR / f"{unique_suffix}_{file.filename}"

    written_bytes = 0

    try:
        async with aiofiles.open(destination, "wb") as out_file:
            while chunk := await file.read(CHUNK_SIZE):
                written_bytes += len(chunk)
                if written_bytes > MAX_CSV_SIZE_MB * 1024 * 1024:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"CSV exceeds maximum size of {MAX_CSV_SIZE_MB}MB.",
                    )
                await out_file.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise

    if written_bytes == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    job = ImportJob(
        status=ImportJobStatus.PENDING,
        file_path=str(destination.resolve()),
        original_filename=file.filename,
        content_type=file.content_type,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    # Enqueue background task
    from ..tasks import process_csv_import  # Imported lazily to avoid circular imports

    process_csv_import.send(str(job.id))

    return job

