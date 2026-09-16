"""Late platform specialization — adapt canonical text without re-generating.

One adaptation per variant_fingerprint (not per account). Reuses PLATFORM_LIMITS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.modules.content_generation.generation_context import PLATFORM_LIMITS
from backend.modules.publishing.platform_capabilities import (
    PlatformCapabilities,
    flags_to_capabilities,
)

# Workflow-local extensions (canonical content path).
_LIMITS: dict[str, int] = {
    **PLATFORM_LIMITS,
    "linkedin": 3000,
    "youtube": PLATFORM_LIMITS["youtube_description"],
}


@dataclass(frozen=True, slots=True)
class AdaptedVariant:
    platform: str
    fingerprint: str
    text: str
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    social_account_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "fingerprint": self.fingerprint,
            "text": self.text,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags or []),
            "social_account_ids": list(self.social_account_ids),
        }


def trim_text(text: str, limit: int) -> str:
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 1:
        return cleaned[:limit]
    cut = cleaned[: max(0, limit - 1)].rstrip()
    return f"{cut}…"


def platform_char_limit(
    platform: str,
    *,
    capabilities: PlatformCapabilities | None = None,
) -> int:
    if capabilities is not None and capabilities.max_text_length is not None:
        return int(capabilities.max_text_length)
    key = platform.strip().lower()
    if key == "youtube":
        return _LIMITS["youtube_description"]
    return int(_LIMITS.get(key, 1000))


def adapt_canonical_for_platform(
    *,
    canonical_text: str,
    platform: str,
    fingerprint: str,
    social_account_ids: list[str],
    title: str | None = None,
    hashtags: list[str] | None = None,
    include_hashtags: bool = True,
    capability_flags: dict[str, Any] | None = None,
) -> AdaptedVariant:
    """Deterministic platform adaptation — no LLM, shared across fingerprint group."""
    plat = platform.strip().lower()
    caps = flags_to_capabilities(capability_flags, platform=plat)
    tags = [t if t.startswith("#") else f"#{t}" for t in (hashtags or []) if t.strip()]
    body = canonical_text.strip()
    limit = platform_char_limit(plat, capabilities=caps)

    if plat == "youtube":
        yt_title = trim_text(title or _first_sentence(body), PLATFORM_LIMITS["youtube_title"])
        desc = body
        if include_hashtags and tags:
            desc = f"{desc}\n\n{' '.join(tags[:12])}"
        return AdaptedVariant(
            platform=plat,
            fingerprint=fingerprint,
            text=trim_text(desc, limit),
            title=yt_title,
            description=trim_text(desc, limit),
            tags=[t.lstrip("#") for t in tags[:12]],
            social_account_ids=tuple(social_account_ids),
        )

    if plat == "x":
        text = body
        if include_hashtags and tags:
            suffix = " " + " ".join(tags[:3])
            if len(text) + len(suffix) <= limit:
                text = text + suffix
        return AdaptedVariant(
            platform=plat,
            fingerprint=fingerprint,
            text=trim_text(text, limit),
            social_account_ids=tuple(social_account_ids),
        )

    if plat == "instagram":
        text = body
        if include_hashtags and tags:
            text = f"{text}\n\n{' '.join(tags[:15])}"
        return AdaptedVariant(
            platform=plat,
            fingerprint=fingerprint,
            text=trim_text(text, limit),
            tags=[t.lstrip("#") for t in tags[:15]],
            social_account_ids=tuple(social_account_ids),
        )

    if plat == "linkedin":
        text = body
        if include_hashtags and tags:
            text = f"{text}\n\n{' '.join(tags[:5])}"
        return AdaptedVariant(
            platform=plat,
            fingerprint=fingerprint,
            text=trim_text(text, limit),
            social_account_ids=tuple(social_account_ids),
        )

    text = body
    if include_hashtags and tags:
        text = f"{text}\n\n{' '.join(tags[:8])}"
    return AdaptedVariant(
        platform=plat,
        fingerprint=fingerprint,
        text=trim_text(text, limit),
        social_account_ids=tuple(social_account_ids),
    )


def _first_sentence(text: str) -> str:
    for sep in (". ", "! ", "? ", "\n"):
        if sep in text:
            return text.split(sep, 1)[0].strip()
    return text.strip()
