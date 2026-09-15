from __future__ import annotations

from typing import TypedDict


class CatalogEntry(TypedDict, total=False):
    id: str
    name: str
    url: str
    source_type: str
    category: str
    description: str
    trust_score: float
    polling_interval_minutes: int
    fetch_full_text: bool
