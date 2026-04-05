from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict


ModelT = TypeVar("ModelT")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CursorPage(BaseModel, Generic[ModelT]):
    items: list[ModelT]
    next_cursor: str | None = None


class CursorRequest(BaseModel):
    cursor: str | None = None
    limit: int = 20


class OptionItem(ORMModel):
    id: UUID
    label: str


class SummaryMetric(BaseModel):
    key: str
    label: str
    value: float | int | str
    change: float | None = None


class HealthCheck(BaseModel):
    status: str
    checked_at: datetime
