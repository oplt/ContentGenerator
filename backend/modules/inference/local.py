from __future__ import annotations

import json
from time import perf_counter
from typing import Any

import httpx

from backend.core.config import settings
from backend.core.domain_metrics import domain_metrics
from backend.core.http import provider_semaphore, request, shared_http_client
from backend.modules.inference.base import EmbeddingsProvider, LLMProvider, _timeout_for_task
from backend.modules.inference.capabilities import ProviderHealth
from backend.modules.inference.parsing import StructuredGenerationResult, _parse_json_object


class OllamaCompatibleLLMProvider(LLMProvider):
    provider_name = "ollama"

    def __init__(self, *, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or settings.LLM_MODEL
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")

    async def _call(
        self,
        prompt: str,
        *,
        temperature: float,
        task: str,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> str:
        model = settings.llm_task_models.get(task, self.model)
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None and max_tokens > 0:
            payload["options"]["num_predict"] = max_tokens
        if response_format is not None:
            payload["format"] = response_format
        task_timeout = _timeout_for_task(task)
        # Use a short connect timeout but allow the full task timeout for reading,
        # since Ollama streams tokens incrementally and the total generation can be slow.
        timeout = httpx.Timeout(connect=15.0, read=task_timeout, write=15.0, pool=15.0)
        chunks: list[str] = []
        started = perf_counter()
        outcome = "success"
        try:
            async with provider_semaphore("llm"):
                async with shared_http_client() as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/api/generate",
                        json=payload,
                        timeout=timeout,
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            try:
                                event = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            chunks.append(event.get("response", ""))
                            if event.get("done"):
                                break
        except Exception:
            outcome = "failure"
            raise
        finally:
            duration_ms = (perf_counter() - started) * 1000.0
            domain_metrics.record_llm_call(
                provider=self.provider_name,
                model=model,
                operation=task,
                duration_ms=duration_ms,
                outcome=outcome,
            )
            domain_metrics.record_provider_request(
                provider=self.provider_name,
                outcome=outcome,
                duration_ms=duration_ms,
                status_class="2xx" if outcome == "success" else "5xx",
            )
        return "".join(chunks).strip()

    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        return await self._call(
            f"Summarize in {max_words} words or less:\n{prompt}",
            temperature=0.2,
            task="summarize",
        )

    async def generate_text(
        self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.7, task: str = "default"
    ) -> str:
        return await self._call(prompt, temperature=temperature, task=task, max_tokens=max_tokens)

    async def _generate_structured_json_result(
        self,
        prompt: str,
        *,
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int = 800,
        temperature: float = 0.2,
        task: str = "structured_json",
    ) -> StructuredGenerationResult:
        raw = await self._call(
            prompt,
            temperature=temperature,
            task=task,
            max_tokens=max_tokens,
            response_format="json" if settings.LLM_JSON_ENFORCEMENT != "off" else None,
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
                f"{self.base_url}/api/tags",
                provider="llm",
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return ProviderHealth(provider_name=self.provider_name, status="error", detail=str(exc))
        models = tuple(
            str(item.get("name"))
            for item in payload.get("models", [])
            if isinstance(item, dict) and item.get("name")
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


class OllamaEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or settings.EMBEDDINGS_MODEL
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")

    async def embed(self, text: str) -> list[float]:
        truncated = text[:16_000]
        started = perf_counter()
        outcome = "success"
        try:
            response = await request(
                "POST",
                f"{self.base_url}/api/embeddings",
                provider="llm",
                json={"model": self.model, "prompt": truncated},
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            embedding: list[float] = data.get("embedding", [])
            if not embedding:
                raise ValueError(f"Ollama embeddings returned empty vector for model={self.model}")
            return embedding
        except Exception:
            outcome = "failure"
            raise
        finally:
            domain_metrics.record_llm_call(
                provider="ollama",
                model=self.model,
                operation="embed",
                duration_ms=(perf_counter() - started) * 1000.0,
                outcome=outcome,
            )
