"""
Text-to-Speech providers for SignalForge.

Priority order (local-first):
  1. MockTTSProvider         — silent WAV placeholder (dev/tests)
  2. PiperTTSProvider        — local binary via subprocess (Piper TTS)
  3. KokoroTTSProvider       — local HTTP API, OpenAI-compatible (Kokoro)
  4. OpenAITTSProvider       — cloud via OpenAI /v1/audio/speech
  5. ElevenLabsTTSProvider   — cloud via ElevenLabs /v1/text-to-speech/{voice_id}

Factory:  get_tts_provider(provider_name) → TTSProvider
"""
from __future__ import annotations

import asyncio
import logging
import struct
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Minimal silent WAV builder (no external deps)
# ---------------------------------------------------------------------------

def _silent_wav(duration_seconds: int = 3, sample_rate: int = 22050) -> bytes:
    """Return a valid WAV file of silence."""
    num_frames = sample_rate * duration_seconds
    # PCM 16-bit mono samples (all zeros = silence)
    pcm_data = b"\x00\x00" * num_frames
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    with wave.open(str(tmp_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)

    data = tmp_path.read_bytes()
    tmp_path.unlink(missing_ok=True)
    return data


@dataclass
class TTSResult:
    audio_bytes: bytes = field(default_factory=bytes)
    mime_type: str = "audio/wav"
    provider: str = "mock"
    script_used: str = ""


class TTSProvider:
    """Base class — all providers must implement synthesize()."""

    async def synthesize(self, script: str) -> TTSResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 1. Mock — silent WAV, no deps
# ---------------------------------------------------------------------------

class MockTTSProvider(TTSProvider):
    async def synthesize(self, script: str) -> TTSResult:
        return TTSResult(
            audio_bytes=_silent_wav(),
            mime_type="audio/wav",
            provider="mock",
            script_used=script,
        )


# ---------------------------------------------------------------------------
# 2. Piper — local binary, WAV output
# ---------------------------------------------------------------------------

class PiperTTSProvider(TTSProvider):
    """
    Synthesize with the Piper TTS binary (https://github.com/rhasspy/piper).

    Requires:
      - TTS_PIPER_BIN   = path/to/piper binary (default "piper")
      - TTS_PIPER_MODEL = path/to/model.onnx

    Falls back gracefully if binary or model is missing.
    """

    def __init__(self) -> None:
        self._bin = settings.TTS_PIPER_BIN
        self._model = settings.TTS_PIPER_MODEL
        self._sample_rate = settings.TTS_PIPER_SAMPLE_RATE

    async def synthesize(self, script: str) -> TTSResult:
        if not self._model:
            logger.warning("piper_tts: TTS_PIPER_MODEL not configured, falling back to silence")
            return TTSResult(audio_bytes=_silent_wav(), provider="piper", script_used=script)

        def _run() -> bytes:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                out_path = Path(tmp.name)
            try:
                result = subprocess.run(
                    [self._bin, "--model", self._model, "--output_file", str(out_path)],
                    input=script.encode("utf-8"),
                    capture_output=True,
                    timeout=60,
                )
                result.check_returncode()
                return out_path.read_bytes()
            finally:
                out_path.unlink(missing_ok=True)

        try:
            audio_bytes = await asyncio.to_thread(_run)
            return TTSResult(
                audio_bytes=audio_bytes,
                mime_type="audio/wav",
                provider="piper",
                script_used=script,
            )
        except Exception as exc:
            logger.warning("piper_tts_failed error=%s", exc)
            return TTSResult(audio_bytes=_silent_wav(), provider="piper", script_used=script)


# ---------------------------------------------------------------------------
# 3. Kokoro — local HTTP, OpenAI-compatible /v1/audio/speech
# ---------------------------------------------------------------------------

class KokoroTTSProvider(TTSProvider):
    """
    Local Kokoro TTS via its OpenAI-compatible REST API.
    https://github.com/remsky/Kokoro-FastAPI
    """

    def __init__(self) -> None:
        self._base = settings.TTS_KOKORO_BASE_URL.rstrip("/")
        self._voice = settings.TTS_KOKORO_VOICE

    async def synthesize(self, script: str) -> TTSResult:
        payload = {
            "model": "kokoro",
            "input": script[:4096],
            "voice": self._voice,
            "response_format": "wav",
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{self._base}/v1/audio/speech", json=payload)
                resp.raise_for_status()
                return TTSResult(
                    audio_bytes=resp.content,
                    mime_type="audio/wav",
                    provider="kokoro",
                    script_used=script,
                )
        except Exception as exc:
            logger.warning("kokoro_tts_failed error=%s", exc)
            return TTSResult(audio_bytes=_silent_wav(), provider="kokoro", script_used=script)


# ---------------------------------------------------------------------------
# 4. OpenAI TTS — cloud, MP3 output
# ---------------------------------------------------------------------------

class OpenAITTSProvider(TTSProvider):
    """
    Cloud TTS via OpenAI /v1/audio/speech (tts-1 or tts-1-hd).
    Falls back to silence if no API key or on error.
    """

    def __init__(self) -> None:
        self._api_key = settings.TTS_OPENAI_API_KEY
        self._model = settings.TTS_OPENAI_MODEL
        self._voice = settings.TTS_OPENAI_VOICE

    async def synthesize(self, script: str) -> TTSResult:
        if not self._api_key:
            logger.warning("openai_tts: TTS_OPENAI_API_KEY not configured")
            return TTSResult(audio_bytes=_silent_wav(), provider="openai", script_used=script)

        payload = {
            "model": self._model,
            "input": script[:4096],
            "voice": self._voice,
            "response_format": "mp3",
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                return TTSResult(
                    audio_bytes=resp.content,
                    mime_type="audio/mpeg",
                    provider="openai",
                    script_used=script,
                )
        except Exception as exc:
            logger.warning("openai_tts_failed error=%s", exc)
            return TTSResult(audio_bytes=_silent_wav(), provider="openai", script_used=script)


# ---------------------------------------------------------------------------
# 5. ElevenLabs TTS — cloud, MP3 output
# ---------------------------------------------------------------------------

class ElevenLabsTTSProvider(TTSProvider):
    """
    Cloud TTS via ElevenLabs /v1/text-to-speech/{voice_id}.
    Falls back to silence if no API key or on error.
    """

    _BASE = "https://api.elevenlabs.io"

    def __init__(self) -> None:
        self._api_key = settings.TTS_ELEVENLABS_API_KEY
        self._voice_id = settings.TTS_ELEVENLABS_VOICE_ID
        self._model_id = settings.TTS_ELEVENLABS_MODEL_ID

    async def synthesize(self, script: str) -> TTSResult:
        if not self._api_key:
            logger.warning("elevenlabs_tts: TTS_ELEVENLABS_API_KEY not configured")
            return TTSResult(audio_bytes=_silent_wav(), provider="elevenlabs", script_used=script)

        payload = {
            "text": script[:5000],
            "model_id": self._model_id,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self._BASE}/v1/text-to-speech/{self._voice_id}",
                    headers={
                        "xi-api-key": self._api_key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                return TTSResult(
                    audio_bytes=resp.content,
                    mime_type="audio/mpeg",
                    provider="elevenlabs",
                    script_used=script,
                )
        except Exception as exc:
            logger.warning("elevenlabs_tts_failed error=%s", exc)
            return TTSResult(audio_bytes=_silent_wav(), provider="elevenlabs", script_used=script)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_tts_provider(provider: str | None = None) -> TTSProvider:
    """Return the configured TTS provider."""
    p = (provider or settings.TTS_PROVIDER).lower()
    if p == "piper":
        return PiperTTSProvider()
    if p == "kokoro":
        return KokoroTTSProvider()
    if p == "openai":
        return OpenAITTSProvider()
    if p == "elevenlabs":
        return ElevenLabsTTSProvider()
    return MockTTSProvider()
