from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(v * v for v in left))
    right_norm = math.sqrt(sum(v * v for v in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


@dataclass(frozen=True)
class ProviderCapabilities:
    json_mode: bool = False
    long_context: bool = False
    review_only: bool = False


@dataclass(frozen=True)
class TaskRequirements:
    json_mode: bool = False
    long_context: bool = False
    review_only: bool = False
    preferred_providers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderHealth:
    provider_name: str
    status: str
    detail: str = ""
    models: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class StructuredGenerationResult:
    data: dict[str, Any]
    parsed: bool
    raw: str = ""


@dataclass
class InferenceMetrics:
    structured_parse_failures: Counter[tuple[str, str]] = field(default_factory=Counter)
    structured_recoveries: Counter[tuple[str, str]] = field(default_factory=Counter)
    provider_failures: Counter[tuple[str, str]] = field(default_factory=Counter)

    def record_parse_failure(self, provider_name: str, task: str) -> None:
        self.structured_parse_failures[(provider_name, task)] += 1

    def record_recovery(self, provider_name: str, task: str) -> None:
        self.structured_recoveries[(provider_name, task)] += 1

    def record_provider_failure(self, provider_name: str, task: str) -> None:
        self.provider_failures[(provider_name, task)] += 1

    def snapshot(self) -> dict[str, dict[str, int]]:
        def _flatten(counter: Counter[tuple[str, str]]) -> dict[str, int]:
            return {f"{provider}:{task}": count for (provider, task), count in sorted(counter.items())}

        return {
            "structured_parse_failures": _flatten(self.structured_parse_failures),
            "structured_recoveries": _flatten(self.structured_recoveries),
            "provider_failures": _flatten(self.provider_failures),
        }


DEFAULT_PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "mock": ProviderCapabilities(json_mode=True, long_context=True, review_only=True),
    "ollama": ProviderCapabilities(long_context=True, review_only=True),
    "vllm": ProviderCapabilities(json_mode=True, long_context=True, review_only=True),
    "llamacpp": ProviderCapabilities(json_mode=True, long_context=True, review_only=True),
    "openai": ProviderCapabilities(json_mode=True, long_context=True, review_only=True),
    "openai_compatible": ProviderCapabilities(json_mode=True, long_context=True, review_only=True),
}

DEFAULT_TASK_REQUIREMENTS: dict[str, TaskRequirements] = {
    "structured_json": TaskRequirements(json_mode=True),
    "classify": TaskRequirements(json_mode=True),
    "extract_claims": TaskRequirements(json_mode=True),
    "review_policy": TaskRequirements(json_mode=True, review_only=True),
    "review_style": TaskRequirements(json_mode=True, review_only=True),
    "extractor": TaskRequirements(json_mode=True, long_context=True),
    "scorer": TaskRequirements(json_mode=True),
    "planner": TaskRequirements(json_mode=True),
    "writer": TaskRequirements(json_mode=True, long_context=True),
    "reviewer": TaskRequirements(json_mode=True, review_only=True),
    "optimizer": TaskRequirements(json_mode=True),
    "editorial_brief": TaskRequirements(json_mode=True, long_context=True),
}

inference_metrics = InferenceMetrics()


def _load_capability_overrides() -> dict[str, ProviderCapabilities]:
    raw = getattr(settings, "LLM_PROVIDER_CAPABILITIES_JSON", "") or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    overrides: dict[str, ProviderCapabilities] = {}
    for provider_name, config in parsed.items():
        if not isinstance(config, dict):
            continue
        overrides[str(provider_name).lower()] = ProviderCapabilities(
            json_mode=bool(config.get("json_mode", False)),
            long_context=bool(config.get("long_context", False)),
            review_only=bool(config.get("review_only", False)),
        )
    return overrides


def _load_task_requirements() -> dict[str, TaskRequirements]:
    raw = getattr(settings, "LLM_TASK_REQUIREMENTS_JSON", "") or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    requirements: dict[str, TaskRequirements] = {}
    for task_name, config in parsed.items():
        if not isinstance(config, dict):
            continue
        preferred = config.get("preferred_providers", [])
        preferred_tuple = tuple(str(item).lower() for item in preferred if str(item).strip())
        requirements[str(task_name)] = TaskRequirements(
            json_mode=bool(config.get("json_mode", False)),
            long_context=bool(config.get("long_context", False)),
            review_only=bool(config.get("review_only", False)),
            preferred_providers=preferred_tuple,
        )
    return requirements


def get_provider_capabilities(provider_name: str) -> ProviderCapabilities:
    name = provider_name.lower()
    overrides = _load_capability_overrides()
    return overrides.get(name, DEFAULT_PROVIDER_CAPABILITIES.get(name, ProviderCapabilities()))


def get_task_requirements(task: str) -> TaskRequirements:
    overrides = _load_task_requirements()
    requirement = overrides.get(task)
    if requirement:
        return requirement
    if task in DEFAULT_TASK_REQUIREMENTS:
        return DEFAULT_TASK_REQUIREMENTS[task]
    if "review" in task:
        return TaskRequirements(json_mode=True, review_only=True)
    if task.startswith("extract") or task.endswith("brief"):
        return TaskRequirements(json_mode=True, long_context=True)
    if task in {"default", "summarize"}:
        return TaskRequirements()
    return TaskRequirements(json_mode=True if "json" in task else False)


def get_inference_metrics_snapshot() -> dict[str, dict[str, int]]:
    return inference_metrics.snapshot()


def _parse_json_object(raw: str, default: dict[str, Any] | None = None) -> StructuredGenerationResult:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    candidate = match.group(0) if match else cleaned
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return StructuredGenerationResult(data=default or {}, parsed=False, raw=raw)
    if not isinstance(parsed, dict):
        return StructuredGenerationResult(data=default or {}, parsed=False, raw=raw)
    return StructuredGenerationResult(data=parsed, parsed=True, raw=raw)


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
        return ProviderHealth(provider_name=self.provider_name, status="unknown", detail="healthcheck not implemented")


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
        return StructuredGenerationResult(data=schema_hint or {}, parsed=True, raw=json.dumps(schema_hint or {}))

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(provider_name=self.provider_name, status="ok", detail="mock provider")


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
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
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
            return ProviderHealth(provider_name=self.provider_name, status="disabled", detail="base URL not configured")
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{self.base_url}/models")
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
        return ProviderHealth(provider_name=self.provider_name, status="ok", detail=detail, models=models)


class VLLMProvider(OpenAICompatibleLLMProvider):
    def __init__(self, *, base_url: str | None = None, model: str | None = None) -> None:
        super().__init__(base_url=base_url or settings.VLLM_BASE_URL, model=model, provider_name="vllm")


class LlamaCppProvider(OpenAICompatibleLLMProvider):
    def __init__(self, *, base_url: str | None = None, model: str | None = None) -> None:
        super().__init__(base_url=base_url or settings.LLAMACPP_BASE_URL, model=model, provider_name="llamacpp")


class OllamaCompatibleLLMProvider(LLMProvider):
    provider_name = "ollama"

    def __init__(self, *, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or settings.LLM_MODEL
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")

    async def _call(self, prompt: str, *, temperature: float, task: str) -> str:
        model = settings.llm_task_models.get(task, self.model)
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            response.raise_for_status()
            return str(response.json().get("response", "")).strip()

    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        return await self._call(f"Summarize in {max_words} words or less:\n{prompt}", temperature=0.2, task="summarize")

    async def generate_text(
        self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.7, task: str = "default"
    ) -> str:
        return await self._call(prompt, temperature=temperature, task=task)

    async def healthcheck(self) -> ProviderHealth:
        if not self.base_url:
            return ProviderHealth(provider_name=self.provider_name, status="disabled", detail="base URL not configured")
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{self.base_url}/api/tags")
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
        return ProviderHealth(provider_name=self.provider_name, status="ok", detail=detail, models=models)


class EmbeddingsProvider:
    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class OllamaEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or settings.EMBEDDINGS_MODEL
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")

    async def embed(self, text: str) -> list[float]:
        truncated = text[:16_000]
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": truncated},
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            embedding: list[float] = data.get("embedding", [])
            if not embedding:
                raise ValueError(f"Ollama embeddings returned empty vector for model={self.model}")
            return embedding


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
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json={"model": self.model, "input": truncated},
            )
            response.raise_for_status()
            return list(response.json()["data"][0]["embedding"])


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


def _dedupe(sequence: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in sequence:
        if item and item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def _build_provider(provider_name: str) -> LLMProvider:
    name = provider_name.lower()
    if name == "ollama":
        return OllamaCompatibleLLMProvider()
    if name == "vllm":
        return VLLMProvider()
    if name == "llamacpp":
        return LlamaCppProvider()
    if name in {"openai", "openai_compatible"} and settings.LLM_BASE_URL:
        return OpenAICompatibleLLMProvider(provider_name="openai_compatible")
    return MockLLMProvider()


class RoutedLLMProvider(LLMProvider):
    provider_name = "router"

    def __init__(self, default_provider_name: str | None = None) -> None:
        self.default_provider_name = (default_provider_name or settings.LLM_PROVIDER).lower()

    def _task_provider_overrides(self) -> dict[str, str]:
        raw = getattr(settings, "LLM_TASK_PROVIDER_OVERRIDES_JSON", "") or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return {str(task): str(name).lower() for task, name in parsed.items() if task and name}

    def _provider_names_for_task(self, task: str) -> list[str]:
        requirements = get_task_requirements(task)
        override = self._task_provider_overrides().get(task)
        ordered = [override] if override else []
        ordered.extend(requirements.preferred_providers)
        ordered.append(self.default_provider_name)
        ordered.extend(settings.llm_fallback_order)
        provider_names = _dedupe([name.lower() for name in ordered if name])
        compatible = [name for name in provider_names if self._supports_task(name, requirements)]
        return compatible or provider_names or ["mock"]

    def _supports_task(self, provider_name: str, requirements: TaskRequirements) -> bool:
        capabilities = get_provider_capabilities(provider_name)
        if requirements.json_mode and not capabilities.json_mode:
            return False
        if requirements.long_context and not capabilities.long_context:
            return False
        if requirements.review_only and not capabilities.review_only:
            return False
        return True

    async def _run_with_fallback(
        self,
        *,
        task: str,
        operation: str,
        executor: Any,
        schema_hint: dict[str, Any] | None = None,
    ) -> Any:
        last_error: Exception | None = None
        attempts_per_provider = max(settings.LLM_MAX_RETRIES, 0) + 1
        fallback_used = False
        for index, provider_name in enumerate(self._provider_names_for_task(task)):
            provider = _build_provider(provider_name)
            for attempt in range(attempts_per_provider):
                try:
                    result = await executor(provider)
                    if operation == "structured" and isinstance(result, StructuredGenerationResult):
                        if result.parsed:
                            if fallback_used or index > 0 or attempt > 0:
                                inference_metrics.record_recovery(provider.provider_name, task)
                            return result.data
                        inference_metrics.record_parse_failure(provider.provider_name, task)
                        fallback_used = True
                        break
                    return result
                except Exception as exc:
                    last_error = exc
                    inference_metrics.record_provider_failure(provider.provider_name, task)
                    logger.warning(
                        "Inference provider failed",
                        extra={
                            "provider": provider.provider_name,
                            "task": task,
                            "attempt": attempt + 1,
                            "operation": operation,
                        },
                    )
            fallback_used = True
        if operation == "structured":
            return schema_hint or {}
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"No inference providers available for task={task}")

    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        return await self._run_with_fallback(
            task="summarize",
            operation="text",
            executor=lambda provider: provider.summarize(prompt, max_words=max_words),
        )

    async def generate_text(
        self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.7, task: str = "default"
    ) -> str:
        return await self._run_with_fallback(
            task=task,
            operation="text",
            executor=lambda provider: provider.generate_text(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                task=task,
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
        data = await self._run_with_fallback(
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
        candidates = self._provider_names_for_task("default")
        provider = _build_provider(candidates[0] if candidates else "mock")
        return await provider.healthcheck()


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    if provider_name:
        return _build_provider(provider_name)
    return RoutedLLMProvider()


def get_llm_provider_with_fallback(task: str = "default") -> LLMProvider:
    return RoutedLLMProvider(default_provider_name=settings.LLM_PROVIDER if task else settings.LLM_PROVIDER)


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
        "vllm": VLLMProvider(),
        "llamacpp": LlamaCppProvider(),
    }
    results: dict[str, ProviderHealth] = {}
    for name, provider in providers.items():
        results[name] = await provider.healthcheck()
    return results
