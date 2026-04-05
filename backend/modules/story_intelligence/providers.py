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


class EmbeddingsProvider:
    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        words = prompt.split()
        return " ".join(words[:max_words])


class OllamaCompatibleLLMProvider(LLMProvider):
    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                json={
                    "model": settings.LLM_MODEL,
                    "prompt": f"Summarize in {max_words} words or less:\n{prompt}",
                    "stream": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
            return str(payload.get("response", "")).strip()


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
    return MockLLMProvider()


def get_embeddings_provider() -> EmbeddingsProvider:
    return HashingEmbeddingsProvider()
