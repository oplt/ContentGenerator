from __future__ import annotations

import json
from typing import Any

from backend.core.config import settings
from backend.modules.inference.capabilities import ProviderHealth
from backend.modules.inference.parsing import StructuredGenerationResult, _parse_json_object


def _timeout_for_task(task: str) -> float:
    return float(settings.llm_task_timeouts.get(task, settings.LLM_TIMEOUT_SECONDS))


class LLMProvider:
    provider_name: str = "generic"

    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        raise NotImplementedError

    async def generate(
        self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.7
    ) -> str:
        return await self.generate_text(prompt, max_tokens=max_tokens, temperature=temperature)

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
        schema_text = json.dumps(schema_hint or {}, sort_keys=True)
        raw = await self.generate_text(
            f"{prompt}\n\nReturn valid JSON only.\nSchema hint: {schema_text}",
            max_tokens=max_tokens,
            temperature=temperature,
            task=task,
        )
        return _parse_json_object(raw, default=schema_hint or {})

    async def generate_structured_json(
        self,
        prompt: str,
        *,
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int = 800,
        temperature: float = 0.2,
        task: str = "structured_json",
    ) -> dict[str, Any]:
        result = await self._generate_structured_json_result(
            prompt,
            schema_hint=schema_hint,
            max_tokens=max_tokens,
            temperature=temperature,
            task=task,
        )
        return result.data

    async def classify(self, prompt: str, *, labels: list[str], task: str = "classify") -> dict[str, Any]:
        result = await self.generate_structured_json(
            f"{prompt}\n\nClassify into one of: {', '.join(labels)}.",
            schema_hint={"label": labels[0] if labels else "unknown", "confidence": 0.5},
            task=task,
        )
        label = str(result.get("label", labels[0] if labels else "unknown"))
        if labels and label not in labels:
            label = labels[0]
        return {"label": label, "confidence": float(result.get("confidence", 0.5))}

    async def extract_claims(self, prompt: str, *, task: str = "extract_claims") -> list[str]:
        result = await self.generate_structured_json(
            prompt,
            schema_hint={"claims": []},
            task=task,
        )
        claims = result.get("claims", [])
        return [str(item) for item in claims if str(item).strip()]

    async def review_policy(self, prompt: str, *, task: str = "review_policy") -> dict[str, Any]:
        return await self.generate_structured_json(
            prompt,
            schema_hint={"risk": "low", "issues": [], "blocked": False},
            task=task,
        )

    async def review_style(self, prompt: str, *, task: str = "review_style") -> dict[str, Any]:
        return await self.generate_structured_json(
            prompt,
            schema_hint={"voice_match": 0.5, "issues": [], "rewrite": ""},
            task=task,
        )

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(
            provider_name=self.provider_name,
            status="unknown",
            detail="healthcheck not implemented",
        )


class EmbeddingsProvider:
    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError
