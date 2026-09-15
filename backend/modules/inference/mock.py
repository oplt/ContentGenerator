from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from backend.modules.inference.base import EmbeddingsProvider, LLMProvider
from backend.modules.inference.capabilities import ProviderHealth
from backend.modules.inference.parsing import StructuredGenerationResult


class MockLLMProvider(LLMProvider):
    provider_name = "mock"

    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        words = prompt.split()
        return " ".join(words[:max_words])

    async def generate_text(
        self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.7, task: str = "default"
    ) -> str:
        return await self.summarize(prompt, max_words=max_tokens // 4)

    async def _generate_structured_json_result(
        self,
        prompt: str,
        *,
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int = 800,
        temperature: float = 0.2,
        task: str = "structured_json",
    ) -> StructuredGenerationResult:
        return StructuredGenerationResult(
            data=schema_hint or {},
            parsed=True,
            raw=json.dumps(schema_hint or {}),
        )

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(provider_name=self.provider_name, status="ok", detail="mock provider")


@dataclass
class HashingEmbeddingsProvider(EmbeddingsProvider):
    dimensions: int = 24

    async def embed(self, text: str) -> list[float]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
        vector = [0.0] * self.dimensions
        for token, count in Counter(tokens).items():
            index = hash(token) % self.dimensions
            vector[index] += float(count)
        norm = math.sqrt(sum(v * v for v in vector))
        if norm:
            vector = [v / norm for v in vector]
        return vector
