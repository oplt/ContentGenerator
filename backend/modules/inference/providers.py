"""Compatibility facade for inference providers.

Implementation lives in focused modules under ``backend.modules.inference``.
Import from this module to preserve existing call sites.
"""

from __future__ import annotations

from backend.modules.inference.base import EmbeddingsProvider, LLMProvider
from backend.modules.inference.capabilities import (
    DEFAULT_PROVIDER_CAPABILITIES,
    DEFAULT_TASK_REQUIREMENTS,
    ProviderCapabilities,
    ProviderHealth,
    TaskRequirements,
    get_provider_capabilities,
    get_task_requirements,
)
from backend.modules.inference.factory import (
    ConfiguredLLMProvider,
    collect_inference_readiness,
    get_embeddings_provider,
    get_llm_provider,
)
from backend.modules.inference.local import OllamaCompatibleLLMProvider, OllamaEmbeddingsProvider
from backend.modules.inference.metrics import (
    InferenceMetrics,
    get_inference_metrics_snapshot,
    inference_metrics,
)
from backend.modules.inference.mock import HashingEmbeddingsProvider, MockLLMProvider
from backend.modules.inference.openai_compatible import (
    OpenAICompatibleEmbeddingsProvider,
    OpenAICompatibleLLMProvider,
)
from backend.modules.inference.parsing import StructuredGenerationResult
from backend.modules.inference.similarity import cosine_similarity

__all__ = [
    "ConfiguredLLMProvider",
    "DEFAULT_PROVIDER_CAPABILITIES",
    "DEFAULT_TASK_REQUIREMENTS",
    "EmbeddingsProvider",
    "HashingEmbeddingsProvider",
    "InferenceMetrics",
    "LLMProvider",
    "MockLLMProvider",
    "OllamaCompatibleLLMProvider",
    "OllamaEmbeddingsProvider",
    "OpenAICompatibleEmbeddingsProvider",
    "OpenAICompatibleLLMProvider",
    "ProviderCapabilities",
    "ProviderHealth",
    "StructuredGenerationResult",
    "TaskRequirements",
    "collect_inference_readiness",
    "cosine_similarity",
    "get_embeddings_provider",
    "get_inference_metrics_snapshot",
    "get_llm_provider",
    "get_provider_capabilities",
    "get_task_requirements",
    "inference_metrics",
]
