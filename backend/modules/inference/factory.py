from __future__ import annotations

import json
from typing import Any, cast

import structlog

from backend.core.config import settings
from backend.modules.inference.base import EmbeddingsProvider, LLMProvider
from backend.modules.inference.capabilities import (
    ProviderHealth,
    get_provider_capabilities,
    get_task_requirements,
)
from backend.modules.inference.local import OllamaCompatibleLLMProvider, OllamaEmbeddingsProvider
from backend.modules.inference.metrics import inference_metrics
from backend.modules.inference.mock import HashingEmbeddingsProvider, MockLLMProvider
from backend.modules.inference.openai_compatible import (
    OpenAICompatibleEmbeddingsProvider,
    OpenAICompatibleLLMProvider,
)
from backend.modules.inference.parsing import StructuredGenerationResult

logger = structlog.get_logger(__name__)


def _format_exception_detail(exc: Exception) -> str:
    detail = str(exc).strip()
    if detail:
        return detail
    return exc.__class__.__name__


def _build_provider(provider_name: str) -> LLMProvider:
    name = provider_name.lower()
    if name == "ollama":
        return OllamaCompatibleLLMProvider()
    if name == "vllm":
        return OpenAICompatibleLLMProvider(
            base_url=settings.VLLM_BASE_URL,
            provider_name="vllm",
        )
    if name == "llamacpp":
        return OpenAICompatibleLLMProvider(
            base_url=settings.LLAMACPP_BASE_URL,
            provider_name="llamacpp",
        )
    if name in {"openai", "openai_compatible"} and settings.LLM_BASE_URL:
        return OpenAICompatibleLLMProvider(provider_name="openai_compatible")
    return MockLLMProvider()


def _ensure_provider_supports_task(provider_name: str, task: str) -> str:
    normalized = (provider_name or "mock").lower()
    requirements = get_task_requirements(task)
    capabilities = get_provider_capabilities(normalized)
    if requirements.json_mode and not capabilities.json_mode:
        raise RuntimeError(
            f"Inference provider '{normalized}' does not support task='{task}'. "
            "Change LLM_PROVIDER to a compatible backend."
        )
    if requirements.long_context and not capabilities.long_context:
        raise RuntimeError(
            f"Inference provider '{normalized}' does not support task='{task}'. "
            "Change LLM_PROVIDER to a compatible backend."
        )
    if requirements.review_only and not capabilities.review_only:
        raise RuntimeError(
            f"Inference provider '{normalized}' does not support task='{task}'. "
            "Change LLM_PROVIDER to a compatible backend."
        )
    return normalized


class ConfiguredLLMProvider(LLMProvider):
    provider_name = "configured"

    def __init__(self, provider_name: str | None = None) -> None:
        self.selected_provider_name = _ensure_provider_supports_task(
            provider_name or settings.LLM_PROVIDER,
            "default",
        )
        self.provider = _build_provider(self.selected_provider_name)
        self.provider_name = self.provider.provider_name

    async def _execute(
        self,
        *,
        task: str,
        operation: str,
        executor: Any,
        schema_hint: dict[str, Any] | None = None,
    ) -> Any:
        _ensure_provider_supports_task(self.selected_provider_name, task)
        last_error: Exception | None = None
        attempts = max(settings.LLM_MAX_RETRIES, 0) + 1
        for attempt in range(attempts):
            try:
                result = await executor(self.provider)
                if operation == "structured" and isinstance(result, StructuredGenerationResult):
                    if result.parsed:
                        if attempt > 0:
                            inference_metrics.record_recovery(self.provider.provider_name, task)
                        return result.data
                    inference_metrics.record_parse_failure(self.provider.provider_name, task)
                    last_error = RuntimeError(
                        f"Provider '{self.provider.provider_name}' returned invalid structured output for task={task}"
                    )
                    raw_preview = (result.raw[:500] + "…") if len(result.raw) > 500 else result.raw
                    logger.warning(
                        "Inference provider failed",
                        provider=self.provider.provider_name,
                        task=task,
                        attempt=attempt + 1,
                        operation=operation,
                        reason="invalid_structured_output",
                        raw_preview=raw_preview,
                    )
                    continue
                return result
            except Exception as exc:
                last_error = exc
                inference_metrics.record_provider_failure(self.provider.provider_name, task)
                logger.warning(
                    "Inference provider failed",
                    provider=self.provider.provider_name,
                    task=task,
                    attempt=attempt + 1,
                    operation=operation,
                    exc_info=exc,
                )

        if operation == "structured":
            if last_error is not None:
                raise RuntimeError(
                    f"Structured inference failed for task={task}: {_format_exception_detail(last_error)}"
                ) from last_error
            return schema_hint or {}
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"No inference provider available for task={task}")

    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        return cast(
            str,
            await self._execute(
                task="summarize",
                operation="text",
                executor=lambda provider: provider.summarize(prompt, max_words=max_words),
            ),
        )

    async def generate_text(
        self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.7, task: str = "default"
    ) -> str:
        return cast(
            str,
            await self._execute(
                task=task,
                operation="text",
                executor=lambda provider: provider.generate_text(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    task=task,
                ),
            ),
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
        data = await self._execute(
            task=task,
            operation="structured",
            schema_hint=schema_hint,
            executor=lambda provider: provider._generate_structured_json_result(
                prompt,
                schema_hint=schema_hint,
                max_tokens=max_tokens,
                temperature=temperature,
                task=task,
            ),
        )
        return StructuredGenerationResult(data=data, parsed=True, raw=json.dumps(data))

    async def healthcheck(self) -> ProviderHealth:
        return await self.provider.healthcheck()


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    return ConfiguredLLMProvider(provider_name or settings.LLM_PROVIDER)


def get_embeddings_provider() -> EmbeddingsProvider:
    provider = settings.EMBEDDINGS_PROVIDER.lower()
    if provider == "ollama":
        return OllamaEmbeddingsProvider()
    if provider == "openai_compatible":
        return OpenAICompatibleEmbeddingsProvider()
    if settings.APP_ENV != "production":
        return HashingEmbeddingsProvider()
    raise RuntimeError(
        f"EMBEDDINGS_PROVIDER='{settings.EMBEDDINGS_PROVIDER}' is not supported in production. "
        "Set EMBEDDINGS_PROVIDER=ollama and ensure Ollama is running."
    )


async def collect_inference_readiness() -> dict[str, ProviderHealth]:
    providers = {
        "ollama": OllamaCompatibleLLMProvider(),
        "vllm": OpenAICompatibleLLMProvider(
            base_url=settings.VLLM_BASE_URL,
            provider_name="vllm",
        ),
        "llamacpp": OpenAICompatibleLLMProvider(
            base_url=settings.LLAMACPP_BASE_URL,
            provider_name="llamacpp",
        ),
    }
    results: dict[str, ProviderHealth] = {}
    for name, provider in providers.items():
        results[name] = await provider.healthcheck()
    return results
