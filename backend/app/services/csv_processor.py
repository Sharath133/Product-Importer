from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple

from ..models import Product

REQUIRED_COLUMNS = ("name", "sku", "description")


class CSVValidationError(Exception):
    """Raised when the CSV file is invalid."""


def _validate_headers(fieldnames: Iterable[str | None]) -> None:
    if not fieldnames:
        raise CSVValidationError("CSV file is missing a header row.")
    fieldnames = [field.strip().lower() for field in fieldnames if field]
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise CSVValidationError(f"CSV missing required columns: {', '.join(missing)}")


def count_rows(file_path: str) -> int:
    path = Path(file_path)
    if not path.exists():
        raise CSVValidationError("Uploaded CSV file no longer exists on the server.")

    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        _validate_headers(reader.fieldnames or [])
        return sum(1 for _ in reader)


def iter_batches(file_path: str, batch_size: int = 1000) -> Iterator[Tuple[List[Dict], int]]:
    """Yield batches of normalized rows along with the number of raw rows consumed."""
    path = Path(file_path)
    if not path.exists():
        raise CSVValidationError("Uploaded CSV file no longer exists on the server.")

    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        _validate_headers(reader.fieldnames or [])

        current_batch: Dict[str, Dict] = {}
        raw_since_flush = 0

        for row in reader:
            raw_since_flush += 1
            name = (row.get("name") or "").strip()
            sku = (row.get("sku") or "").strip()
            description = (row.get("description") or "").strip() or None

            if not name or not sku:
                raise CSVValidationError("Each row must include non-empty 'name' and 'sku' values.")

            normalized_sku = Product.normalize_sku(sku)
            current_batch[normalized_sku] = {
                "name": name,
                "sku": sku,
                "sku_normalized": normalized_sku,
                "description": description,
                "active": True,
            }

            if len(current_batch) >= batch_size:
                yield list(current_batch.values()), raw_since_flush
                current_batch.clear()
                raw_since_flush = 0

        if current_batch:
            yield list(current_batch.values()), raw_since_flush

