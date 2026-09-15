from __future__ import annotations

from typing import Any

from backend.core.config import settings
from backend.core.http import request
from backend.modules.inference.base import EmbeddingsProvider, LLMProvider, _timeout_for_task
from backend.modules.inference.capabilities import ProviderHealth
from backend.modules.inference.parsing import StructuredGenerationResult, _parse_json_object


class OpenAICompatibleLLMProvider(LLMProvider):
    provider_name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        provider_name: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.LLM_API_KEY
        self.default_model = model or settings.LLM_MODEL
        if provider_name:
            self.provider_name = provider_name

    def _resolve_model(self, task: str) -> str:
        return settings.llm_task_models.get(task, self.default_model)

    async def _call(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        task: str,
        response_format: dict[str, str] | None = None,
    ) -> str:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body: dict[str, Any] = {
            "model": self._resolve_model(task),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            body["response_format"] = response_format
        response = await request(
            "POST",
            f"{self.base_url}/chat/completions",
            provider="llm",
            headers=headers,
            json=body,
            timeout=_timeout_for_task(task),
        )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"]).strip()

    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        return await self._call(
            [
                {"role": "system", "content": f"Summarize the following text in {max_words} words or less."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=max_words * 3,
            task="summarize",
        )

    async def generate_text(
        self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.7, task: str = "default"
    ) -> str:
        return await self._call(
            [{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            task=task,
        )

    async def _generate_structured_json_result(
        self,
        prompt: str,
        *,
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int = 800,
        temperature: float = 0.2,
        task: str = "structured_json",
    ) -> StructuredGenerationResult:
        response_format = {"type": "json_object"} if settings.LLM_JSON_ENFORCEMENT != "off" else None
        raw = await self._call(
            [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            task=task,
            response_format=response_format,
        )
        return _parse_json_object(raw, default=schema_hint or {})

    async def healthcheck(self) -> ProviderHealth:
        if not self.base_url:
            return ProviderHealth(
                provider_name=self.provider_name,
                status="disabled",
                detail="base URL not configured",
            )
        try:
            response = await request(
                "GET",
                f"{self.base_url}/models",
                provider="llm",
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return ProviderHealth(provider_name=self.provider_name, status="error", detail=str(exc))
        models = tuple(
            str(item.get("id"))
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        )
        detail = "reachable"
        if not models:
            detail = "reachable but no models reported"
        return ProviderHealth(
            provider_name=self.provider_name,
            status="ok",
            detail=detail,
            models=models,
        )


class OpenAICompatibleEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.model = settings.EMBEDDINGS_MODEL
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.LLM_API_KEY

    async def embed(self, text: str) -> list[float]:
        truncated = text[:8_000]
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = await request(
            "POST",
            f"{self.base_url}/embeddings",
            provider="llm",
            headers=headers,
            json={"model": self.model, "input": truncated},
        )
        response.raise_for_status()
        return list(response.json()["data"][0]["embedding"])
