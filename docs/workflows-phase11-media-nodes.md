# Workflow Domain — Phase 11 (Reusable Media / Content Nodes)

Thin workflow adapters over existing domain services — no PGN/render/LLM policy forks.

## Implemented nodes

| Node | Wraps |
|------|--------|
| `generate_text` | `get_llm_provider().generate_text` |
| `summarize` | `get_llm_provider().summarize` |
| `generate_script` | `video_pipeline` research + script providers |
| `fact_review` | `FactRiskReviewService` (rule-based; no LLM caps) |
| `generate_image` | `ImageGenerationService.generate_for_job` |
| `generate_tts` | `TTSService.generate_for_job` |
| `generate_video` | `script_pipeline` (providers) or `full_pipeline` (`VideoPipelineService.run`) |
| `generate_chess_video` | `ChessVideoService.create` + enqueue / optional sync `process_job` |

Still stubs (Phase 12+): control-flow, research sources, fetch metrics, extra triggers.

## Preferred chess path

```text
schedule/manual
  → (optional) generate_text / caption
  → generate_chess_video   # source_text = PGN/SAN
  → (optional) generate_tts
  → approval
  → platform_transform
  → publish
```

Chess node never calls `parse_chess_input` / `render_chess_video` directly.

## Config notes

* Image/TTS require existing `content_job_id` (FK to `content_jobs`).
* Video default `mode=script_pipeline` — no ContentJob required; produces script/storyboard/captions.
* Video `mode=full_pipeline` needs `content_job_id` + `cluster_id`.
* Chess `sync=false` (default) enqueues Celery; `sync=true` runs `process_job` inline.

## Engine inputs

`engine_inputs.resolve_node_inputs` maps bag aliases (`text`→headline, `pgn`→source_text, keyword lists→string).

## Tests

`backend/tests/test_workflow_media_nodes.py`
