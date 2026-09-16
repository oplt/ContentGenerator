"""Legacy node-type input routing (schema_version == 1 only).

Kept for historical WorkflowVersions. New publishes use schema_version >= 2
(port/binding resolver). Do not add new node_type branches here for new nodes —
declare ports + bindings instead.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from backend.modules.workflows.engine_inputs_bag import merge_upstream_bag


def resolve_legacy_node_inputs(
    *,
    node_type: str,
    trigger_payload: dict[str, Any],
    initial_inputs: dict[str, Any],
    upstream_outputs: list[dict[str, Any]],
    run_id: UUID | None = None,
) -> dict[str, Any]:
    bag = merge_upstream_bag(
        trigger_payload=trigger_payload,
        initial_inputs=initial_inputs,
        upstream_outputs=upstream_outputs,
    )

    if node_type == "manual_trigger":
        return {"payload": dict(trigger_payload or initial_inputs or {})}

    if node_type == "webhook_trigger":
        payload = trigger_payload or {}
        if not payload and isinstance(initial_inputs.get("payload"), dict):
            payload = dict(initial_inputs["payload"])
        elif not payload:
            payload = dict(initial_inputs or {})
        return {"payload": dict(payload)}

    if node_type == "generate_text":
        prompt = bag.get("prompt")
        if not prompt and isinstance(bag.get("text"), str):
            prompt = bag.get("text")
        return {
            "prompt": prompt or "",
            "system_hint": bag.get("system_hint"),
        }

    if node_type == "summarize":
        text = bag.get("text") or bag.get("prompt") or bag.get("script") or ""
        return {"text": text}

    if node_type == "generate_script":
        return {
            "digest": bag.get("digest"),
            "headline": bag.get("headline") or bag.get("title"),
            "summary": bag.get("summary") or bag.get("text") or "",
            "article_points": bag.get("article_points") or [],
        }

    if node_type == "fact_review":
        generated = bag.get("generated_texts")
        if not isinstance(generated, dict):
            generated = {}
            if isinstance(bag.get("text"), str) and bag["text"]:
                generated = {"body": bag["text"]}
        return {
            "headline": bag.get("headline") or bag.get("title") or bag.get("text") or "",
            "summary": bag.get("summary") or "",
            "claims": bag.get("claims") or [],
            "keywords": bag.get("keywords") or [],
            "topic": bag.get("topic"),
            "generated_texts": generated,
            "evidence_links": bag.get("evidence_links") or [],
            "source_articles": bag.get("source_articles") or [],
            "reviewer_issues": bag.get("reviewer_issues") or [],
        }

    if node_type == "generate_image":
        keywords = bag.get("keywords") or ""
        if isinstance(keywords, list):
            keywords = ", ".join(str(k) for k in keywords)
        return {
            "content_job_id": bag.get("content_job_id"),
            "headline": bag.get("headline") or bag.get("title") or bag.get("text") or "",
            "primary_topic": bag.get("primary_topic") or bag.get("topic") or "general",
            "keywords": keywords,
        }

    if node_type == "generate_tts":
        return {
            "content_job_id": bag.get("content_job_id"),
            "headline": bag.get("headline") or bag.get("title") or "",
            "summary": bag.get("summary") or bag.get("text") or bag.get("script") or "",
            "cta": bag.get("cta") or "",
        }

    if node_type == "generate_video":
        return {
            "headline": bag.get("headline") or bag.get("title"),
            "summary": bag.get("summary") or bag.get("text") or "",
            "article_points": bag.get("article_points") or [],
            "script": bag.get("script"),
            "content_job_id": bag.get("content_job_id"),
            "cluster_id": bag.get("cluster_id"),
        }

    if node_type == "generate_chess_video":
        source = bag.get("source_text") or bag.get("pgn") or bag.get("text") or ""
        return {
            "source_text": source,
            "title": bag.get("title"),
            "subtitle": bag.get("subtitle"),
        }

    if node_type == "approval":
        return {"content_job_id": bag.get("content_job_id")}

    if node_type == "condition":
        return {
            "value": bag.get("value", bag.get("risk_score")),
            "payload": dict(bag),
            **{k: v for k, v in bag.items() if k not in {"payload"}},
        }

    if node_type == "delay":
        return {}

    if node_type == "wait":
        return {
            "correlation_key": bag.get("correlation_key"),
            "payload": bag.get("payload") if isinstance(bag.get("payload"), dict) else {},
        }

    if node_type == "fan_out":
        items = bag.get("items")
        if not isinstance(items, list):
            items = []
        return {
            "items": items,
            "social_account_ids": bag.get("social_account_ids") or [],
        }

    if node_type == "merge":
        sources = [dict(o) for o in upstream_outputs if isinstance(o, dict)]
        return {"sources": sources, "bag": dict(bag)}

    if node_type == "platform_transform":
        text = bag.get("text") or bag.get("canonical_text")
        hashtags = bag.get("hashtags") or []
        if not isinstance(hashtags, list):
            hashtags = []
        return {
            "text": text or "",
            "title": bag.get("title"),
            "hashtags": hashtags,
            "social_account_ids": bag.get("social_account_ids"),
            "content_job_id": bag.get("content_job_id"),
        }

    if node_type == "publish":
        idempotency = bag.get("idempotency_key")
        if not idempotency and run_id is not None:
            idempotency = f"wf-publish-{run_id}"
        account_ids = bag.get("social_account_ids")
        if not account_ids and isinstance(bag.get("variants"), list):
            collected: list[Any] = []
            for variant in bag["variants"]:
                if isinstance(variant, dict):
                    collected.extend(variant.get("social_account_ids") or [])
            account_ids = collected or None
        variant_ids = bag.get("content_variant_ids") or bag.get("variant_ids")
        if not variant_ids and isinstance(bag.get("variants"), list):
            collected_vids: list[Any] = []
            for variant in bag["variants"]:
                if isinstance(variant, dict) and variant.get("id"):
                    collected_vids.append(variant["id"])
            variant_ids = collected_vids or None
        return {
            "content_job_id": bag.get("content_job_id"),
            "approval_request_id": bag.get("approval_request_id"),
            "social_account_ids": account_ids,
            "content_variant_ids": variant_ids,
            "scheduled_for": bag.get("scheduled_for"),
            "idempotency_key": idempotency,
        }

    return bag
