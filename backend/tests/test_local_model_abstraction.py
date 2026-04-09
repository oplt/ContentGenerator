from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from backend.modules.inference import providers as inference_providers
from backend.modules.inference.providers import (
    LlamaCppProvider,
    VLLMProvider,
    get_inference_metrics_snapshot,
    get_llm_provider,
    inference_metrics,
)


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    def __init__(self, handler: Callable[[str, str, dict | None], _FakeResponse], **_: object) -> None:
        self._handler = handler

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, **kwargs: object) -> _FakeResponse:
        return self._handler("GET", url, kwargs.get("json"))

    async def post(self, url: str, **kwargs: object) -> _FakeResponse:
        payload = kwargs.get("json")
        return self._handler("POST", url, payload if isinstance(payload, dict) else None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_cls", "base_url", "provider_name"),
    [
        (VLLMProvider, "http://vllm.local/v1", "vllm"),
        (LlamaCppProvider, "http://llama.local/v1", "llamacpp"),
    ],
)
async def test_openai_compatible_local_provider_endpoints(monkeypatch, provider_cls, base_url, provider_name) -> None:
    def handler(method: str, url: str, payload: dict | None) -> _FakeResponse:
        if method == "GET" and url == f"{base_url}/models":
            return _FakeResponse({"data": [{"id": "local-model"}]})
        if method == "POST" and url == f"{base_url}/chat/completions":
            assert payload is not None
            assert payload["model"] == "local-model"
            return _FakeResponse({"choices": [{"message": {"content": '{"status":"ok"}'}}]})
        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(
        inference_providers,
        "settings",
        MagicMock(
            LLM_MODEL="local-model",
            LLM_API_KEY="",
            LLM_TIMEOUT_SECONDS=5.0,
            llm_task_models={},
            LLM_JSON_ENFORCEMENT="best_effort",
            VLLM_BASE_URL="http://vllm.local/v1",
            LLAMACPP_BASE_URL="http://llama.local/v1",
            LLM_BASE_URL="",
        ),
    )
    monkeypatch.setattr(
        inference_providers.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(handler, **kwargs),
    )

    provider = provider_cls(base_url=base_url, model="local-model")
    health = await provider.healthcheck()
    result = await provider.generate_structured_json(
        "Return a JSON object with status",
        schema_hint={"status": "pending"},
        task="structured_json",
    )

    assert health.provider_name == provider_name
    assert health.ready is True
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_router_falls_back_after_parse_failure_and_records_metrics(monkeypatch) -> None:
    inference_metrics.structured_parse_failures.clear()
    inference_metrics.structured_recoveries.clear()
    inference_metrics.provider_failures.clear()

    def handler(method: str, url: str, payload: dict | None) -> _FakeResponse:
        if method == "POST" and url == "http://vllm.local/v1/chat/completions":
            return _FakeResponse({"choices": [{"message": {"content": "not-json"}}]})
        if method == "POST" and url == "http://llama.local/v1/chat/completions":
            return _FakeResponse({"choices": [{"message": {"content": '{"label":"safe","confidence":0.9}'}}]})
        if method == "GET" and url.endswith("/models"):
            return _FakeResponse({"data": [{"id": "local-model"}]})
        raise AssertionError(f"Unexpected request: {method} {url} payload={payload}")

    monkeypatch.setattr(
        inference_providers,
        "settings",
        MagicMock(
            LLM_PROVIDER="vllm",
            LLM_MODEL="local-model",
            LLM_API_KEY="",
            LLM_TIMEOUT_SECONDS=5.0,
            LLM_MAX_RETRIES=0,
            LLM_JSON_ENFORCEMENT="best_effort",
            LLM_TASK_PROVIDER_OVERRIDES_JSON="{}",
            LLM_TASK_REQUIREMENTS_JSON="{}",
            LLM_PROVIDER_CAPABILITIES_JSON="{}",
            llm_task_models={},
            llm_fallback_order=["llamacpp", "mock"],
            VLLM_BASE_URL="http://vllm.local/v1",
            LLAMACPP_BASE_URL="http://llama.local/v1",
            LLM_BASE_URL="",
            OLLAMA_BASE_URL="http://ollama.local",
        ),
    )
    monkeypatch.setattr(
        inference_providers.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(handler, **kwargs),
    )

    provider = get_llm_provider()
    result = await provider.generate_structured_json(
        "Classify this content",
        schema_hint={"label": "unknown", "confidence": 0.5},
        task="classify",
    )
    metrics = get_inference_metrics_snapshot()

    assert result == {"label": "safe", "confidence": 0.9}
    assert metrics["structured_parse_failures"]["vllm:classify"] == 1
    assert metrics["structured_recoveries"]["llamacpp:classify"] == 1
