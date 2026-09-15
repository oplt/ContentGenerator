"""Shared cache helpers extracted from tenant_cache (line-limit)."""

from __future__ import annotations

import random
import time
from enum import Enum
from typing import Any
from uuid import UUID

from backend.core.config import settings

_NEGATIVE = "__cg_negative__"
_META = "_cg_meta"

_CREDENTIAL_MARKERS = (
    "password",
    "password_hash",
    "mfa_secret",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "private_key",
)


def assert_no_credentials(value: Any) -> None:
    if isinstance(value, dict):
        for marker in _CREDENTIAL_MARKERS:
            if marker in {str(k).lower() for k in value} and value.get(marker):
                raise ValueError(f"refusing to cache credential field '{marker}'")
        for nested in value.values():
            assert_no_credentials(nested)
    elif isinstance(value, list):
        for item in value:
            assert_no_credentials(item)


def effective_ttl(*, ttl_seconds: int, jitter_seconds: int) -> int:
    base = ttl_seconds
    jitter = jitter_seconds or int(getattr(settings, "CACHE_DEFAULT_TTL_JITTER_SECONDS", 0))
    if jitter > 0:
        base += random.randint(0, int(jitter))
    return max(int(base), 1)


def wrap_payload(value: Any, *, soft_ttl: int, swr_seconds: int) -> Any:
    if swr_seconds <= 0:
        return value
    return {
        _META: {"soft_exp": time.time() + soft_ttl, "hard_extra": swr_seconds},
        "data": value,
    }


def unwrap_payload(payload: Any) -> tuple[Any, bool]:
    if isinstance(payload, dict) and _META in payload and "data" in payload:
        soft_exp = float(payload[_META].get("soft_exp", 0))
        return payload["data"], time.time() > soft_exp
    return payload, False


def is_negative_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get(_NEGATIVE) is True


def negative_payload() -> dict[str, Any]:
    return {_NEGATIVE: True, "at": time.time()}


def orm_column_dict(obj: Any, *, exclude: set[str] | None = None) -> dict[str, Any]:
    excluded = exclude or set()
    data: dict[str, Any] = {}
    for column in obj.__table__.columns:
        if column.key in excluded:
            continue
        value = getattr(obj, column.key)
        if isinstance(value, UUID):
            data[column.key] = str(value)
        elif hasattr(value, "isoformat"):
            data[column.key] = value.isoformat()
        elif isinstance(value, Enum):
            data[column.key] = value.value
        else:
            data[column.key] = value
    return data


def hydrate_orm(model_cls: type, data: dict[str, Any]) -> Any:
    obj = model_cls()
    table = getattr(model_cls, "__table__", None)
    if table is None:
        raise TypeError(f"{model_cls} is not a mapped ORM class")
    for column in table.columns:
        if column.key not in data:
            continue
        value = data[column.key]
        if value is None:
            setattr(obj, column.key, None)
            continue
        python_type = getattr(column.type, "python_type", None)
        try:
            if python_type is UUID and not isinstance(value, UUID):
                value = UUID(str(value))
            elif python_type is not None and python_type is not type(value):
                if python_type.__name__ == "datetime" and isinstance(value, str):
                    value = __import__("datetime").datetime.fromisoformat(value)
                elif python_type is bool and isinstance(value, str):
                    value = value.lower() in {"1", "true", "yes"}
        except Exception:
            pass
        setattr(obj, column.key, value)
    return obj
