"""
Image generation providers for SignalForge.

Hierarchy:
  1. MockImageProvider      — returns a minimal 1×1 PNG placeholder (tests / dev)
  2. StableDiffusionProvider — local generation via AUTOMATIC1111 REST API
  3. OpenAIImageProvider     — cloud fallback via DALL-E API

Factory:  get_image_provider(provider_name) → ImageGenerationProvider
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

# Minimal valid 1×1 transparent PNG (no external deps required)
_PLACEHOLDER_PNG: bytes = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhf"
    "DwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@dataclass
class ImageGenerationResult:
    image_bytes: bytes = field(default_factory=bytes)
    mime_type: str = "image/png"
    width: int = 0
    height: int = 0
    provider: str = "mock"
    prompt_used: str = ""


class ImageGenerationProvider:
    """Base class — all concrete providers must implement generate()."""

    async def generate(self, prompt: str) -> ImageGenerationResult:
        raise NotImplementedError


class MockImageProvider(ImageGenerationProvider):
    """Returns a placeholder 1×1 PNG without any network calls."""

    async def generate(self, prompt: str) -> ImageGenerationResult:
        return ImageGenerationResult(
            image_bytes=_PLACEHOLDER_PNG,
            mime_type="image/png",
            width=1,
            height=1,
            provider="mock",
            prompt_used=prompt,
        )


class StableDiffusionProvider(ImageGenerationProvider):
    """
    Local image generation via AUTOMATIC1111 /sdapi/v1/txt2img.

    Falls back gracefully if the server is unreachable, returning an empty
    ImageGenerationResult so the caller can decide to skip or use a placeholder.
    """

    def __init__(self) -> None:
        self._base = settings.IMAGE_SD_BASE_URL.rstrip("/")
        self._steps = settings.IMAGE_SD_STEPS
        self._cfg = settings.IMAGE_SD_CFG_SCALE
        self._width = settings.IMAGE_GENERATION_WIDTH
        self._height = settings.IMAGE_GENERATION_HEIGHT

    async def generate(self, prompt: str) -> ImageGenerationResult:
        payload = {
            "prompt": prompt,
            "negative_prompt": "blurry, low quality, text overlay, watermark, logo",
            "steps": self._steps,
            "cfg_scale": self._cfg,
            "width": self._width,
            "height": self._height,
            "sampler_name": "Euler a",
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{self._base}/sdapi/v1/txt2img", json=payload)
                resp.raise_for_status()
                data = resp.json()
                b64 = data["images"][0]
                image_bytes = base64.b64decode(b64)
                return ImageGenerationResult(
                    image_bytes=image_bytes,
                    mime_type="image/png",
                    width=self._width,
                    height=self._height,
                    provider="stable_diffusion",
                    prompt_used=prompt,
                )
        except Exception as exc:
            logger.warning("stable_diffusion_generate_failed prompt=%r error=%s", prompt[:80], exc)
            return ImageGenerationResult(provider="stable_diffusion", prompt_used=prompt)


class OpenAIImageProvider(ImageGenerationProvider):
    """
    Cloud image generation via OpenAI DALL-E API.

    Uses response_format=b64_json to avoid a second HTTP round-trip for download.
    Falls back gracefully on any error.
    """

    def __init__(self) -> None:
        self._api_key = settings.IMAGE_OPENAI_API_KEY
        self._model = settings.IMAGE_OPENAI_MODEL
        self._size = f"{settings.IMAGE_GENERATION_WIDTH}x{settings.IMAGE_GENERATION_HEIGHT}"

    async def generate(self, prompt: str) -> ImageGenerationResult:
        if not self._api_key:
            logger.warning("openai_image_generate: no API key configured")
            return ImageGenerationResult(provider="openai", prompt_used=prompt)

        payload = {
            "model": self._model,
            "prompt": prompt,
            "n": 1,
            "size": self._size,
            "response_format": "b64_json",
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                b64 = resp.json()["data"][0]["b64_json"]
                image_bytes = base64.b64decode(b64)
                return ImageGenerationResult(
                    image_bytes=image_bytes,
                    mime_type="image/png",
                    width=settings.IMAGE_GENERATION_WIDTH,
                    height=settings.IMAGE_GENERATION_HEIGHT,
                    provider="openai",
                    prompt_used=prompt,
                )
        except Exception as exc:
            logger.warning("openai_image_generate_failed prompt=%r error=%s", prompt[:80], exc)
            return ImageGenerationResult(provider="openai", prompt_used=prompt)


def get_image_provider(provider: str | None = None) -> ImageGenerationProvider:
    """Return the configured image generation provider."""
    p = (provider or settings.IMAGE_PROVIDER).lower()
    if p == "stable_diffusion":
        return StableDiffusionProvider()
    if p == "openai":
        return OpenAIImageProvider()
    return MockImageProvider()
