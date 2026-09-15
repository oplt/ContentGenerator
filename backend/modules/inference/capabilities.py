from __future__ import annotations

import json
from dataclasses import dataclass

from backend.core.config import settings


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


DEFAULT_PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "mock": ProviderCapabilities(json_mode=True, long_context=True, review_only=True),
    "ollama": ProviderCapabilities(json_mode=True, long_context=True, review_only=True),
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
    "product_hunter": TaskRequirements(json_mode=True, long_context=True),
}


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
