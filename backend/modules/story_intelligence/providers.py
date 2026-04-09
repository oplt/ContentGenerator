from __future__ import annotations

from backend.core.config import settings
from backend.modules.inference.providers import (
    EmbeddingsProvider,
    HashingEmbeddingsProvider,
    LlamaCppProvider,
    LLMProvider,
    MockLLMProvider,
    OllamaCompatibleLLMProvider,
    OllamaEmbeddingsProvider,
    OpenAICompatibleEmbeddingsProvider,
    OpenAICompatibleLLMProvider,
    ProviderCapabilities,
    ProviderHealth,
    RoutedLLMProvider,
    TaskRequirements,
    VLLMProvider,
    collect_inference_readiness,
    cosine_similarity,
    get_inference_metrics_snapshot,
    get_provider_capabilities,
    get_task_requirements,
)


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    from backend.modules.inference import providers as inference_providers

    inference_providers.settings = settings
    return inference_providers.get_llm_provider(provider_name)


def get_llm_provider_with_fallback(task: str = "default") -> LLMProvider:
    from backend.modules.inference import providers as inference_providers

    inference_providers.settings = settings
    return inference_providers.get_llm_provider_with_fallback(task)


def get_embeddings_provider() -> EmbeddingsProvider:
    from backend.modules.inference import providers as inference_providers

    inference_providers.settings = settings
    return inference_providers.get_embeddings_provider()
