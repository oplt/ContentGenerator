from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import httpx

from backend.core.config import settings


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class LLMProvider:
    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        raise NotImplementedError

    async def generate(self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.7) -> str:
        """Generate free-form text. Default implementation falls back to summarize."""
        return await self.summarize(prompt, max_words=max_tokens // 4)


class EmbeddingsProvider:
    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        words = prompt.split()
        return " ".join(words[:max_words])


class OllamaCompatibleLLMProvider(LLMProvider):
    async def _call(self, prompt: str, temperature: float = 0.7) -> str:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                json={
                    "model": settings.LLM_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            response.raise_for_status()
            return str(response.json().get("response", "")).strip()

    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        return await self._call(f"Summarize in {max_words} words or less:\n{prompt}")

    async def generate(self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.7) -> str:
        return await self._call(prompt, temperature=temperature)


class OpenAICompatibleLLMProvider(LLMProvider):
    """Works with any OpenAI-compatible endpoint (OpenAI, Together, Groq, LM Studio…)."""

    async def _call(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 800) -> str:
        headers = {"Content-Type": "application/json"}
        if settings.LLM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": settings.LLM_MODEL,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()

    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        return await self._call(
            [
                {"role": "system", "content": f"Summarize the following text in {max_words} words or less. Be factual and concise."},
                {"role": "user", "content": prompt},
            ]
        )

    async def generate(self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.7) -> str:
        return await self._call(
            [{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )


@dataclass
class HashingEmbeddingsProvider(EmbeddingsProvider):
    dimensions: int = 24

    async def embed(self, text: str) -> list[float]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
        vector = [0.0 for _ in range(self.dimensions)]
        for token, count in Counter(tokens).items():
            index = hash(token) % self.dimensions
            vector[index] += float(count)
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


def get_llm_provider() -> LLMProvider:
    if settings.LLM_PROVIDER == "ollama":
        return OllamaCompatibleLLMProvider()
    if settings.LLM_PROVIDER in {"openai", "openai_compatible"} and settings.LLM_BASE_URL:
        return OpenAICompatibleLLMProvider()
    return MockLLMProvider()


def get_embeddings_provider() -> EmbeddingsProvider:
    return HashingEmbeddingsProvider()
