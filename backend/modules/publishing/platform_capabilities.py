"""Typed platform capability model (Phase 10).

Augments untyped SocialAccount.capability_flags — no big-bang enum migration.
Provider IDs remain strings; capabilities are structured.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.content_generation.generation_context import PLATFORM_LIMITS

_TRUTHY = frozenset({"true", "1", "yes", "limited", "on"})

# Node required_capabilities that are media/platform-bound.
MEDIA_CAPABILITIES = frozenset({"video", "image", "audio", "tts", "text", "thread"})

# Always available via SignalForge runtime (not platform-native).
DEFAULT_RUNTIME_CAPABILITIES = ("llm", "publish")


class PlatformCapabilities(BaseModel):
    """Structured account/platform capabilities for compile + adaptation."""

    model_config = ConfigDict(extra="forbid")

    supports_text: bool = False
    supports_images: bool = False
    supports_video: bool = False
    supports_audio: bool = False
    supports_threads: bool = False
    supports_native_scheduling: bool = False

    max_text_length: int | None = None
    max_images: int | None = None
    max_video_duration_seconds: int | None = None
    max_video_size_mb: int | None = None

    supported_video_formats: list[str] = Field(default_factory=list)
    supported_image_formats: list[str] = Field(default_factory=list)

    provider_id: str | None = None
    raw_flags: dict[str, str] = Field(default_factory=dict)


def flag_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in _TRUTHY


def platform_defaults(provider_id: str | None) -> PlatformCapabilities:
    """Baseline capabilities by string provider/platform id."""
    key = (provider_id or "").strip().lower()
    catalog: dict[str, PlatformCapabilities] = {
        "x": PlatformCapabilities(
            supports_text=True,
            supports_images=True,
            supports_video=False,
            supports_threads=True,
            supports_native_scheduling=False,
            max_text_length=PLATFORM_LIMITS.get("x", 280),
            max_images=4,
            supported_image_formats=["jpg", "png", "gif", "webp"],
            provider_id="x",
        ),
        "twitter": PlatformCapabilities(
            supports_text=True,
            supports_images=True,
            supports_video=False,
            supports_threads=True,
            max_text_length=280,
            max_images=4,
            provider_id="twitter",
        ),
        "bluesky": PlatformCapabilities(
            supports_text=True,
            supports_images=True,
            supports_video=False,
            supports_threads=False,
            max_text_length=PLATFORM_LIMITS.get("bluesky", 300),
            max_images=4,
            provider_id="bluesky",
        ),
        "instagram": PlatformCapabilities(
            supports_text=True,
            supports_images=True,
            supports_video=True,
            supports_threads=False,
            max_text_length=PLATFORM_LIMITS.get("instagram", 1000),
            max_images=10,
            max_video_duration_seconds=60,
            supported_image_formats=["jpg", "png"],
            supported_video_formats=["mp4"],
            provider_id="instagram",
        ),
        "linkedin": PlatformCapabilities(
            supports_text=True,
            supports_images=True,
            supports_video=True,
            supports_threads=False,
            max_text_length=3000,
            max_images=9,
            provider_id="linkedin",
        ),
        "youtube": PlatformCapabilities(
            supports_text=True,
            supports_images=True,
            supports_video=True,
            supports_audio=True,
            supports_threads=False,
            max_text_length=PLATFORM_LIMITS.get("youtube_description", 1000),
            max_video_duration_seconds=43_200,
            supported_video_formats=["mp4", "mov"],
            supported_image_formats=["jpg", "png"],
            provider_id="youtube",
        ),
        "tiktok": PlatformCapabilities(
            supports_text=True,
            supports_images=False,
            supports_video=True,
            supports_audio=True,
            max_text_length=PLATFORM_LIMITS.get("tiktok", 400),
            max_video_duration_seconds=180,
            supported_video_formats=["mp4"],
            provider_id="tiktok",
        ),
    }
    if key in catalog:
        return catalog[key].model_copy(deep=True)
    return PlatformCapabilities(provider_id=key or None, supports_text=True, max_text_length=1000)


def flags_to_capabilities(
    flags: dict[str, Any] | None,
    *,
    platform: str | None = None,
) -> PlatformCapabilities:
    """Merge provider flag dict onto platform defaults (flags win when set)."""
    base = platform_defaults(platform)
    raw = {str(k): str(v) for k, v in dict(flags or {}).items()}
    data = base.model_dump()
    data["raw_flags"] = raw
    data["provider_id"] = platform or base.provider_id

    if "text" in raw:
        data["supports_text"] = flag_truthy(raw["text"])
    if "video" in raw:
        data["supports_video"] = flag_truthy(raw["video"])
    if "image" in raw or "images" in raw:
        data["supports_images"] = flag_truthy(raw.get("image") or raw.get("images"))
    if "audio" in raw:
        data["supports_audio"] = flag_truthy(raw["audio"])
    if "thread" in raw or "threads" in raw:
        data["supports_threads"] = flag_truthy(raw.get("thread") or raw.get("threads"))
    if "native_scheduling" in raw:
        data["supports_native_scheduling"] = flag_truthy(raw["native_scheduling"])

    # Optional numeric overrides from flags.
    for src, dest in (
        ("max_text_length", "max_text_length"),
        ("max_images", "max_images"),
        ("max_video_duration_seconds", "max_video_duration_seconds"),
        ("max_video_size_mb", "max_video_size_mb"),
    ):
        if src in raw and str(raw[src]).isdigit():
            data[dest] = int(raw[src])

    return PlatformCapabilities.model_validate(data)


def workflow_capability_tags(
    caps: PlatformCapabilities,
    *,
    runtime: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """String tags for CompileContext.account_capabilities (node required_capabilities)."""
    tags: list[str] = []
    if caps.supports_text:
        tags.append("text")
    if caps.supports_images:
        tags.append("image")
    if caps.supports_video:
        tags.append("video")
    if caps.supports_audio:
        tags.extend(["audio", "tts"])
    if caps.supports_threads:
        tags.append("thread")
    if caps.supports_native_scheduling:
        tags.append("native_scheduling")
    for item in runtime if runtime is not None else DEFAULT_RUNTIME_CAPABILITIES:
        if item not in tags:
            tags.append(item)
    return tags


def capabilities_to_flag_dict(caps: PlatformCapabilities) -> dict[str, str]:
    """Serialize typed caps back to legacy flag dict (non-secret)."""
    flags = {
        "text": "true" if caps.supports_text else "false",
        "image": "true" if caps.supports_images else "false",
        "video": "true" if caps.supports_video else "false",
        "audio": "true" if caps.supports_audio else "false",
        "thread": "true" if caps.supports_threads else "false",
        "native_scheduling": "true" if caps.supports_native_scheduling else "false",
    }
    if caps.max_text_length is not None:
        flags["max_text_length"] = str(caps.max_text_length)
    flags.update({k: v for k, v in caps.raw_flags.items() if k not in flags})
    return flags
