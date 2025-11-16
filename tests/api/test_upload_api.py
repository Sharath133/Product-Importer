import os
from io import BytesIO

import pytest

from backend.app.api import upload
from backend.app.models import ImportJobStatus
from backend.app import tasks


class StubActor:
    def __init__(self):
        self.calls = []

    def send(self, job_id: str):
        self.calls.append(job_id)


@pytest.fixture
def process_stub(monkeypatch):
    stub = StubActor()
    monkeypatch.setattr(tasks, "process_csv_import", stub)
    return stub


@pytest.mark.asyncio
async def test_upload_rejects_non_csv(api_client):
    response = await api_client.post(
        "/api/products/upload",
        files={"file": ("data.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Only CSV files are supported."


@pytest.mark.asyncio
async def test_upload_rejects_empty_file(api_client):
    response = await api_client.post(
        "/api/products/upload",
        files={"file": ("data.csv", b"", "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty."


@pytest.mark.asyncio
async def test_upload_accepts_csv_and_enqueues_job(api_client, process_stub, tmp_path):
    csv_bytes = b"name,sku,description\nWidget,SKU-1,Example\n"
    response = await api_client.post(
        "/api/products/upload",
        files={"file": ("data.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == ImportJobStatus.PENDING.value
    assert payload["original_filename"] == "data.csv"
    assert process_stub.calls == [payload["id"]]

    file_path = payload["file_path"]
    assert os.path.exists(file_path)
    os.remove(file_path)


@pytest.mark.asyncio
async def test_upload_enforces_size_limit(api_client, monkeypatch):
    monkeypatch.setattr(upload, "MAX_CSV_SIZE_MB", 0)  # force limit hit on first chunk

    response = await api_client.post(
        "/api/products/upload",
        files={"file": ("large.csv", b"data" * 10, "text/csv")},
    )
    assert response.status_code == 400
    assert "exceeds maximum size" in response.json()["detail"]

