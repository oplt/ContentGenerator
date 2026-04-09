# Local Models

## Overview

The backend supports local-first inference through `LLM_PROVIDER` plus per-task overrides in `LLM_TASK_MODELS_JSON`.

Supported providers:

- `ollama`
- `vllm`
- `llamacpp`
- `openai_compatible`
- `mock`

Example task override:

```bash
export LLM_PROVIDER=ollama
export LLM_TASK_MODELS_JSON='{"structured_json":"llama3.1:8b","writer":"qwen2.5:7b"}'
```

## Ollama

1. Start Ollama locally.

```bash
ollama serve
```

2. Pull one or more models.

```bash
ollama pull llama3.1:8b
ollama pull qwen2.5:7b
```

3. Configure the backend.

```bash
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export LLM_MODEL=llama3.1:8b
```

Use Ollama when you want the simplest local setup and are comfortable with its model management conventions.

## vLLM

1. Start an OpenAI-compatible vLLM server on a GPU box.

```bash
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --host 0.0.0.0 \
  --port 8001
```

2. Configure the backend.

```bash
export LLM_PROVIDER=vllm
export VLLM_BASE_URL=http://localhost:8001/v1
export LLM_MODEL=meta-llama/Llama-3.1-8B-Instruct
```

Use vLLM for higher-throughput GPU inference and OpenAI-compatible serving behavior.

## llama.cpp

1. Start a llama.cpp server that exposes an OpenAI-style API.

```bash
./server \
  -m /models/Meta-Llama-3.1-8B-Instruct.Q4_K_M.gguf \
  --host 0.0.0.0 \
  --port 8080
```

2. Configure the backend.

```bash
export LLM_PROVIDER=llamacpp
export LLAMACPP_BASE_URL=http://localhost:8080/v1
export LLM_MODEL=Meta-Llama-3.1-8B-Instruct.Q4_K_M.gguf
```

Use llama.cpp when you need a lighter-weight local runtime or are serving GGUF models on constrained hardware.

## Verification

- Check `/health/ready` to confirm the configured inference backend is reachable.
- Use `LLM_PROVIDER=mock` for test or UI-only work.
- Keep `SOCIAL_DRY_RUN_BY_DEFAULT=true` during local development so generation and approval flows do not accidentally publish live content.
