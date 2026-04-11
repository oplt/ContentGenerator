from __future__ import annotations

import json
from collections.abc import Callable, AsyncIterator
from unittest.mock import MagicMock

import pytest

from backend.modules.inference import providers as inference_providers
from backend.modules.inference.providers import (
    ConfiguredLLMProvider,
    OpenAICompatibleLLMProvider,
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


class _FakeStreamResponse:
    """Simulates httpx streaming response for Ollama's /api/generate."""

    def __init__(self, handler: Callable, method: str, url: str, payload: dict | None) -> None:
        self._exc: Exception | None = None
        self._inner: _FakeResponse | None = None
        try:
            self._inner = handler(method, url, payload)
        except Exception as exc:
            self._exc = exc

    def raise_for_status(self) -> None:
        if self._exc is not None:
            raise self._exc
        assert self._inner is not None
        self._inner.raise_for_status()

    async def aiter_lines(self) -> AsyncIterator[str]:
        assert self._inner is not None
        response_text = self._inner.json().get("response", "")
        yield json.dumps({"response": response_text, "done": True})


class _FakeStreamContext:
    def __init__(self, handler: Callable, method: str, url: str, payload: dict | None) -> None:
        self._response = _FakeStreamResponse(handler, method, url, payload)

    async def __aenter__(self) -> _FakeStreamResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


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

    def stream(self, method: str, url: str, **kwargs: object) -> _FakeStreamContext:
        payload = kwargs.get("json")
        return _FakeStreamContext(self._handler, method, url, payload if isinstance(payload, dict) else None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_name", "base_url"),
    [
        ("vllm", "http://vllm.local/v1"),
        ("llamacpp", "http://llama.local/v1"),
    ],
)
async def test_openai_compatible_local_provider_endpoints(monkeypatch, provider_name, base_url) -> None:
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
            llm_task_timeouts={},
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

    provider = OpenAICompatibleLLMProvider(
        base_url=base_url,
        model="local-model",
        provider_name=provider_name,
    )
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
async def test_configured_provider_raises_after_parse_failure_without_cross_provider_fallback(monkeypatch) -> None:
    inference_metrics.structured_parse_failures.clear()
    inference_metrics.structured_recoveries.clear()
    inference_metrics.provider_failures.clear()

    def handler(method: str, url: str, payload: dict | None) -> _FakeResponse:
        if method == "POST" and url == "http://vllm.local/v1/chat/completions":
            return _FakeResponse({"choices": [{"message": {"content": "not-json"}}]})
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
            llm_task_timeouts={},
            LLM_TASK_REQUIREMENTS_JSON="{}",
            LLM_PROVIDER_CAPABILITIES_JSON="{}",
            llm_task_models={},
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
    with pytest.raises(RuntimeError, match="Structured inference failed for task=classify"):
        await provider.generate_structured_json(
            "Classify this content",
            schema_hint={"label": "unknown", "confidence": 0.5},
            task="classify",
        )
    metrics = get_inference_metrics_snapshot()

    assert metrics["structured_parse_failures"]["vllm:classify"] == 1
    assert metrics["structured_recoveries"] == {}


@pytest.mark.asyncio
async def test_configured_provider_uses_only_selected_provider_for_task(monkeypatch) -> None:
    monkeypatch.setattr(
        inference_providers,
        "settings",
        MagicMock(
            LLM_PROVIDER="ollama",
            LLM_MODEL="local-model",
            LLM_API_KEY="",
            LLM_TIMEOUT_SECONDS=5.0,
            LLM_MAX_RETRIES=0,
            LLM_JSON_ENFORCEMENT="best_effort",
            llm_task_timeouts={},
            LLM_TASK_REQUIREMENTS_JSON="{}",
            LLM_PROVIDER_CAPABILITIES_JSON="{}",
            llm_task_models={},
            VLLM_BASE_URL="http://vllm.local/v1",
            LLAMACPP_BASE_URL="http://llama.local/v1",
            LLM_BASE_URL="",
            OLLAMA_BASE_URL="http://ollama.local",
        ),
    )

    provider = get_llm_provider()
    assert isinstance(provider, ConfiguredLLMProvider)
    assert provider.selected_provider_name == "ollama"


@pytest.mark.asyncio
async def test_ollama_uses_task_specific_timeout(monkeypatch) -> None:
    seen: dict[str, float] = {}

    def factory(**kwargs):
        seen["timeout"] = kwargs["timeout"]
        return _FakeAsyncClient(lambda method, url, payload: _FakeResponse({"response": '{"status":"ok"}'}), **kwargs)

    monkeypatch.setattr(
        inference_providers,
        "settings",
        MagicMock(
            LLM_MODEL="local-model",
            LLM_TIMEOUT_SECONDS=5.0,
            llm_task_timeouts={"product_hunter": 180.0},
            llm_task_models={},
            OLLAMA_BASE_URL="http://ollama.local",
        ),
    )
    monkeypatch.setattr(inference_providers.httpx, "AsyncClient", factory)

    provider = inference_providers.OllamaCompatibleLLMProvider()
    await provider.generate_text("{}", task="product_hunter")

    import httpx as _httpx
    assert isinstance(seen["timeout"], _httpx.Timeout)
    assert seen["timeout"].read == 180.0


@pytest.mark.asyncio
async def test_ollama_structured_json_uses_json_mode_and_num_predict(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def handler(method: str, url: str, payload: dict | None) -> _FakeResponse:
        assert method == "POST"
        assert url == "http://ollama.local/api/generate"
        assert payload is not None
        seen["payload"] = payload
        return _FakeResponse({"response": '{"ideas":[{"title":"AgentOps Console"}]}'})

    monkeypatch.setattr(
        inference_providers,
        "settings",
        MagicMock(
            LLM_MODEL="local-model",
            LLM_TIMEOUT_SECONDS=5.0,
            LLM_JSON_ENFORCEMENT="best_effort",
            llm_task_timeouts={},
            llm_task_models={"product_hunter": "local-model"},
            OLLAMA_BASE_URL="http://ollama.local",
        ),
    )
    monkeypatch.setattr(
        inference_providers.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(handler, **kwargs),
    )

    provider = inference_providers.OllamaCompatibleLLMProvider()
    result = await provider.generate_structured_json(
        "Return product ideas as JSON",
        schema_hint={"ideas": []},
        max_tokens=1234,
        task="product_hunter",
    )

    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert payload["format"] == "json"
    assert payload["options"]["num_predict"] == 1234
    assert result == {"ideas": [{"title": "AgentOps Console"}]}


@pytest.mark.asyncio
async def test_configured_provider_raises_last_error_when_all_structured_attempts_fail(monkeypatch) -> None:
    def handler(method: str, url: str, payload: dict | None) -> _FakeResponse:
        raise RuntimeError(f"boom from {url}")

    monkeypatch.setattr(
        inference_providers,
        "settings",
        MagicMock(
            LLM_PROVIDER="ollama",
            LLM_MODEL="local-model",
            LLM_API_KEY="",
            LLM_TIMEOUT_SECONDS=5.0,
            LLM_MAX_RETRIES=0,
            LLM_JSON_ENFORCEMENT="best_effort",
            llm_task_timeouts={},
            LLM_TASK_REQUIREMENTS_JSON="{}",
            LLM_PROVIDER_CAPABILITIES_JSON="{}",
            llm_task_models={},
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

    with pytest.raises(RuntimeError, match="Structured inference failed for task=product_hunter"):
        await provider.generate_structured_json(
            "Return JSON",
            schema_hint={"ideas": [{"title": "string"}]},
            task="product_hunter",
        )


@pytest.mark.asyncio
async def test_configured_provider_surfaces_exception_type_when_message_is_blank(monkeypatch) -> None:
    def handler(method: str, url: str, payload: dict | None) -> _FakeResponse:
        raise RuntimeError("")

    monkeypatch.setattr(
        inference_providers,
        "settings",
        MagicMock(
            LLM_PROVIDER="ollama",
            LLM_MODEL="local-model",
            LLM_API_KEY="",
            LLM_TIMEOUT_SECONDS=5.0,
            LLM_MAX_RETRIES=0,
            LLM_JSON_ENFORCEMENT="best_effort",
            llm_task_timeouts={},
            LLM_TASK_REQUIREMENTS_JSON="{}",
            LLM_PROVIDER_CAPABILITIES_JSON="{}",
            llm_task_models={},
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

    with pytest.raises(RuntimeError, match="Structured inference failed for task=product_hunter: RuntimeError"):
        await provider.generate_structured_json(
            "Return JSON",
            schema_hint={"ideas": [{"title": "string"}]},
            task="product_hunter",
        )
