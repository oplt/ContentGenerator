"""Process-local caches for immutable runtime assets (Phase 5.5)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=128)
def load_text_file(path: str) -> str:
    """Load an immutable text file once per process."""
    return Path(path).read_text(encoding="utf-8")


@lru_cache(maxsize=64)
def load_prompt_relative(prompts_root: str, relative_name: str) -> str | None:
    path = Path(prompts_root) / relative_name
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def clear_static_caches() -> None:
    load_text_file.cache_clear()
    load_prompt_relative.cache_clear()
