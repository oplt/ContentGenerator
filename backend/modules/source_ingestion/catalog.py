from __future__ import annotations

from backend.modules.source_ingestion.catalog_entries import CATALOG
from backend.modules.source_ingestion.catalog_types import CatalogEntry

__all__ = ["CATALOG", "CATALOG_BY_ID", "CATALOG_CATEGORIES", "CatalogEntry"]

CATALOG_BY_ID: dict[str, CatalogEntry] = {entry["id"]: entry for entry in CATALOG}
CATALOG_CATEGORIES: list[str] = sorted({entry["category"] for entry in CATALOG})
