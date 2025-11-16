import csv
from pathlib import Path

import pytest

from backend.app.services.csv_processor import (
    CSVValidationError,
    count_rows,
    iter_batches,
)


def _write_csv(tmp_path: Path, rows, headers=("name", "sku", "description")) -> str:
    file_path = tmp_path / "products.csv"
    with file_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return str(file_path)


def test_count_rows_returns_record_count(tmp_path):
    path = _write_csv(
        tmp_path,
        [
            {"name": "Widget", "sku": "SKU-1", "description": "Example"},
            {"name": "Gadget", "sku": "SKU-2", "description": "Another"},
        ],
    )

    assert count_rows(path) == 2


def test_count_rows_missing_file_raises():
    with pytest.raises(CSVValidationError):
        count_rows("does-not-exist.csv")


def test_count_rows_requires_headers(tmp_path):
    file_path = tmp_path / "missing_headers.csv"
    file_path.write_text("no,headers,here\nvalue1,value2,value3\n", encoding="utf-8")

    with pytest.raises(CSVValidationError) as exc:
        count_rows(str(file_path))

    assert "missing required columns" in str(exc.value)


def test_iter_batches_normalizes_and_deduplicates(tmp_path):
    path = _write_csv(
        tmp_path,
        [
            {"name": "Widget", "sku": " SKU-1 ", "description": "Example"},
            {"name": "Widget Updated", "sku": "sku-1", "description": "Updated"},
            {"name": "Gadget", "sku": "SKU-2", "description": ""},
        ],
    )

    batches = list(iter_batches(path, batch_size=5))
    assert len(batches) == 1

    batch_rows, raw_count = batches[0]
    assert raw_count == 3
    assert len(batch_rows) == 2  # duplicate SKU collapsed

    normalized = {row["sku_normalized"]: row for row in batch_rows}
    assert normalized["sku-1"]["name"] == "Widget Updated"
    assert normalized["sku-1"]["sku"] == "sku-1"
    assert normalized["sku-2"]["description"] is None


def test_iter_batches_enforces_required_fields(tmp_path):
    path = _write_csv(
        tmp_path,
        [
            {"name": "", "sku": "SKU-1", "description": "Example"},
        ],
    )

    with pytest.raises(CSVValidationError) as exc:
        list(iter_batches(path))

    assert "non-empty 'name' and 'sku'" in str(exc.value)

