import json
import uuid

import pytest
from fastapi import HTTPException

from backend.app.api import progress
from backend.app.models import ImportJob, ImportJobStatus


@pytest.mark.asyncio
async def test_stream_progress_raises_for_missing_job(db_session):
    job_id = uuid.uuid4()
    with pytest.raises(HTTPException) as exc:
        await progress.stream_progress(job_id, session=db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_progress_event_stream_emits_updates(db_session, monkeypatch, fakeredis_clients):
    job = ImportJob(
        status=ImportJobStatus.COMPLETED,
        progress=100,
        processed_records=2,
        total_records=2,
        file_path="dummy.csv",
        original_filename="dummy.csv",
        content_type="text/csv",
    )
    db_session.add(job)
    await db_session.commit()

    async def fake_get_progress(job_id: str):
        return {"phase": "done"}

    monkeypatch.setattr(progress, "get_progress", fake_get_progress)

    events = []
    async for event in progress._progress_event_stream(str(job.id)):
        events.append(event)

    assert len(events) == 1
    payload = json.loads(events[0]["data"])
    assert payload["status"] == ImportJobStatus.COMPLETED.value
    assert payload["phase"] == "done"


@pytest.mark.asyncio
async def test_progress_event_stream_handles_missing_job(monkeypatch):
    async def fake_fetch_job(_job_id: str):
        return None

    async def fake_get_progress(_job_id: str):
        return {}

    monkeypatch.setattr(progress, "_fetch_job", fake_fetch_job)
    monkeypatch.setattr(progress, "get_progress", fake_get_progress)

    events = []
    async for event in progress._progress_event_stream(str(uuid.uuid4())):
        events.append(event)

    assert events[-1]["event"] == "error"

