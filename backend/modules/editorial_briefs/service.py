from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import redis_client
from backend.modules.approvals.providers import TelegramProvider, get_telegram_provider, verify_signed_callback_data
from backend.modules.content_strategy.repository import ContentStrategyRepository
from backend.modules.editorial_briefs.models import BriefStatus, EditorialBrief
from backend.modules.editorial_briefs.repository import EditorialBriefRepository
from backend.modules.editorial_briefs.schemas import BriefGenerateRequest, BriefRewriteRequest
from backend.modules.settings.service import SettingsService
from backend.modules.story_intelligence.models import TrendWorkflowState
from backend.modules.inference.providers import get_llm_provider
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository

# Redis key template for brief short-ID → brief UUID mapping
_BRIEF_SHORT_ID_KEY = "brief:short:{short_id}"
_BRIEF_SHORT_ID_TTL = 86400  # 24 hours


_BRIEF_PROMPT_TEMPLATE = """\
You are an editorial director for a social media content agency.

Story cluster headline: {headline}
Story summary: {summary}
Primary topic: {primary_topic}
Content vertical: {content_vertical}
Risk level: {risk_level}
Keywords: {keywords}
Evidence links: {evidence_links}
Extracted claims: {claims}
{brand_context}
Rewrite instruction: {rewrite_instruction}

Write a concise editorial brief as JSON with these exact keys:
- "topic_title": short title for the trend package
- "why_now": one sentence explaining why the trend matters right now
- "angle": one sentence describing the unique story angle (max 30 words)
- "talking_points": list of 3-5 key points the content must cover
- "recommended_format": one of "text", "video", "both"
- "target_platforms": list of up to 3 platforms from ["x", "instagram", "bluesky", "tiktok", "youtube", "threads"]
- "evidence_links": list of 2-5 trusted evidence links
- "audience_segment": short phrase describing the audience
- "platform_recommendations": list of platform recommendations, may match target_platforms
- "tone_guidance": one-sentence tone instruction (e.g. "authoritative but accessible")
- "cta_strategy": one sentence CTA recommendation
- "caveats": list of caveats or disputed details
- "suggested_formats": list of suggested content formats
- "risk_notes": brief editorial risk warning if any (empty string if none)

Respond with ONLY valid JSON. No markdown fences.
"""


class EditorialBriefService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = EditorialBriefRepository(db)
        self.story_repo = StoryIntelligenceRepository(db)
        self.strategy_repo = ContentStrategyRepository(db)
        self.llm = get_llm_provider()

    async def _resolve_brand_constraints(
        self,
        tenant_id: UUID,
        brand_profile_id: UUID | None,
        primary_topic: str,
    ) -> tuple[str, object | None]:
        if not brand_profile_id:
            return "", None
        brand_profile = await self.strategy_repo.get_brand_profile_by_id(tenant_id, brand_profile_id)
        if not brand_profile:
            return "", None
        brand = await self.strategy_repo.get_brand(tenant_id)
        if brand:
            normalized_topic = primary_topic.lower()
            if brand.blocked_topics and any(topic.lower() in normalized_topic for topic in brand.blocked_topics):
                raise HTTPException(status_code=422, detail="Blocked topic for this brand")
            if brand.allowed_topics and not any(topic.lower() in normalized_topic for topic in brand.allowed_topics):
                raise HTTPException(status_code=422, detail="Topic is outside the brand's allowed topics")
        brand_context = (
            f"Brand tone: {brand_profile.tone}. Audience: {brand_profile.audience}. "
            f"Preferred platforms: {', '.join(brand_profile.preferred_platforms)}. "
            f"Guardrails: {json.dumps(brand_profile.guardrails)}."
        )
        return brand_context, brand_profile

    def _default_target_platforms(self, risk_level: str, preferred_platforms: list[str]) -> list[str]:
        if risk_level in {"risky", "sensitive"}:
            return [platform for platform in preferred_platforms if platform in {"x", "threads", "bluesky"}][:3]
        return preferred_platforms[:3] or ["x", "instagram", "threads"]

    async def generate_brief(
        self,
        tenant_id: UUID,
        request: BriefGenerateRequest,
        *,
        actor_user_id: UUID | None = None,
        rewrite_instruction: str = "",
        force_regenerate: bool = False,
    ) -> EditorialBrief:
        # Idempotent: return existing non-rejected brief if present
        existing = await self.repo.get_by_cluster(tenant_id, request.story_cluster_id)
        if existing and not force_regenerate and existing.status not in (BriefStatus.REJECTED.value, BriefStatus.EXPIRED.value):
            return existing

        cluster = await self.story_repo.get_cluster(tenant_id, request.story_cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail="Story cluster not found")
        if not cluster.worthy_for_content:
            raise HTTPException(
                status_code=422,
                detail="Cluster is not marked worthy_for_content; resolve risk gates first",
            )
        brand_context, brand_profile = await self._resolve_brand_constraints(
            tenant_id,
            request.brand_profile_id,
            cluster.primary_topic,
        )

        if existing and force_regenerate:
            brief = existing
            brief.brand_profile_id = request.brand_profile_id
            brief.status = BriefStatus.GENERATING.value
            brief.content_vertical = cluster.content_vertical
            brief.risk_level = cluster.risk_level
            brief.headline = cluster.headline
            brief.expires_at = datetime.now(timezone.utc) + timedelta(hours=request.ttl_hours)
            brief.operator_note = None
            brief.approved_by_user_id = None
            brief.actioned_at = None
            await self.db.flush()
        else:
            brief = EditorialBrief(
                tenant_id=tenant_id,
                story_cluster_id=cluster.id,
                brand_profile_id=request.brand_profile_id,
                status=BriefStatus.GENERATING.value,
                content_vertical=cluster.content_vertical,
                risk_level=cluster.risk_level,
                headline=cluster.headline,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=request.ttl_hours),
            )
            brief = await self.repo.create(brief)

        try:
            candidate = await self.story_repo.get_trend_candidate_for_cluster(tenant_id, cluster.id)
            evidence_links = candidate.evidence_links if candidate else []
            extracted_claims = candidate.extracted_claims if candidate else []
            preferred_platforms = brand_profile.preferred_platforms if brand_profile else ["x", "instagram", "threads"]

            prompt = _BRIEF_PROMPT_TEMPLATE.format(
                headline=cluster.headline,
                summary=cluster.summary,
                primary_topic=cluster.primary_topic,
                content_vertical=cluster.content_vertical,
                risk_level=cluster.risk_level,
                keywords=cluster.explainability.get("keywords", ""),
                evidence_links=", ".join(evidence_links),
                claims=" | ".join(extracted_claims[:5]),
                brand_context=brand_context,
                rewrite_instruction=rewrite_instruction or "None",
            )
            parsed = await self.llm.generate_structured_json(
                prompt,
                schema_hint={
                    "topic_title": cluster.headline,
                    "why_now": cluster.summary[:220],
                    "angle": "",
                    "talking_points": [],
                    "recommended_format": "text",
                    "target_platforms": self._default_target_platforms(cluster.risk_level, preferred_platforms),
                    "evidence_links": evidence_links[:5],
                    "audience_segment": brand_profile.audience if brand_profile else "general social audience",
                    "platform_recommendations": preferred_platforms[:3],
                    "tone_guidance": brand_profile.tone if brand_profile else "authoritative",
                    "cta_strategy": brand_profile.default_cta if brand_profile else "Follow for more updates",
                    "caveats": [],
                    "suggested_formats": [],
                    "risk_notes": "",
                },
                max_tokens=600,
                temperature=0.4,
                task="editorial_brief",
            )

            brief.headline = parsed.get("topic_title", cluster.headline)
            brief.why_now = parsed.get("why_now", cluster.summary[:220])
            brief.angle = parsed.get("angle", "")
            brief.talking_points = parsed.get("talking_points", [])
            brief.recommended_format = parsed.get("recommended_format", "text")
            brief.target_platforms = parsed.get(
                "target_platforms",
                self._default_target_platforms(cluster.risk_level, preferred_platforms),
            )
            brief.evidence_links = parsed.get("evidence_links", evidence_links[:5])
            brief.audience_segment = parsed.get(
                "audience_segment",
                brand_profile.audience if brand_profile else "general social audience",
            )
            brief.platform_recommendations = parsed.get("platform_recommendations", brief.target_platforms)
            brief.tone_guidance = parsed.get("tone_guidance", brand_profile.tone if brand_profile else "authoritative")
            brief.cta_strategy = parsed.get("cta_strategy", brand_profile.default_cta if brand_profile else "Follow for more updates")
            brief.caveats = parsed.get("caveats", [])
            brief.suggested_formats = parsed.get(
                "suggested_formats",
                ["short post", "thread", "caption"] if brief.recommended_format == "text" else ["script", "caption", "hook"],
            )
            brief.risk_notes = parsed.get("risk_notes", "")
            brief.status = BriefStatus.READY.value
            cluster.workflow_state = TrendWorkflowState.BRIEF_READY.value
            brief.rewrite_context = {"instruction": rewrite_instruction or "", "actor_user_id": str(actor_user_id) if actor_user_id else ""}
            brief.generation_trace = {
                "raw_output": json.dumps(parsed)[:2000],
                "candidate_id": str(candidate.id) if candidate else "",
                "risk_label": str(getattr(candidate, "score_explanation", {}).get("review_risk_label", "low")) if candidate else "low",
            }
        except Exception as exc:  # noqa: BLE001
            brief.status = BriefStatus.PENDING.value  # reset — can retry
            brief.generation_trace = {"error": str(exc)}

        await self.db.flush()
        return brief

    async def approve_brief(
        self,
        tenant_id: UUID,
        brief_id: UUID,
        operator_note: str | None,
        actor_user_id: UUID | None,
    ) -> EditorialBrief:
        brief = await self._get_or_404(tenant_id, brief_id)
        if brief.status != BriefStatus.READY.value:
            raise HTTPException(
                status_code=409, detail=f"Brief is in status '{brief.status}', expected 'ready'"
            )
        cluster = await self.story_repo.get_cluster(tenant_id, brief.story_cluster_id)
        if cluster:
            await self._resolve_brand_constraints(tenant_id, brief.brand_profile_id, cluster.primary_topic)
        brief.status = BriefStatus.APPROVED.value
        if cluster:
            cluster.workflow_state = TrendWorkflowState.APPROVED_TOPIC.value
        brief.operator_note = operator_note
        brief.approved_by_user_id = actor_user_id
        brief.actioned_at = datetime.now(timezone.utc)
        await self.db.flush()
        return brief

    async def reject_brief(
        self,
        tenant_id: UUID,
        brief_id: UUID,
        operator_note: str,
        actor_user_id: UUID | None,
    ) -> EditorialBrief:
        brief = await self._get_or_404(tenant_id, brief_id)
        if brief.status not in (BriefStatus.READY.value, BriefStatus.APPROVED.value):
            raise HTTPException(
                status_code=409, detail=f"Brief is in status '{brief.status}', cannot reject"
            )
        brief.status = BriefStatus.REJECTED.value
        cluster = await self.story_repo.get_cluster(tenant_id, brief.story_cluster_id)
        if cluster:
            cluster.workflow_state = TrendWorkflowState.REJECTED.value
        brief.operator_note = operator_note
        brief.approved_by_user_id = actor_user_id
        brief.actioned_at = datetime.now(timezone.utc)
        await self.db.flush()
        return brief

    async def expire_stale_briefs(self, tenant_id: UUID) -> int:
        """Mark READY briefs past their expires_at as EXPIRED. Called by Celery beat."""
        now = datetime.now(timezone.utc)
        briefs = await self.repo.list_by_tenant(tenant_id, status=BriefStatus.READY.value)
        count = 0
        for brief in briefs:
            if brief.expires_at and brief.expires_at < now:
                brief.status = BriefStatus.EXPIRED.value
                cluster = await self.story_repo.get_cluster(tenant_id, brief.story_cluster_id)
                if cluster:
                    cluster.workflow_state = TrendWorkflowState.EXPIRED.value
                count += 1
        if count:
            await self.db.flush()
        return count

    async def regenerate_brief(
        self,
        tenant_id: UUID,
        brief_id: UUID,
        actor_user_id: UUID | None,
    ) -> EditorialBrief:
        """
        Force-regenerate an existing brief regardless of prior status.
        Allowed from any status except GENERATING (already in progress).
        """
        brief = await self._get_or_404(tenant_id, brief_id)
        if brief.status == BriefStatus.GENERATING.value:
            raise HTTPException(status_code=409, detail="Brief is currently being generated — wait for it to finish")

        cluster = await self.story_repo.get_cluster(tenant_id, brief.story_cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail="Story cluster not found")

        brief.status = BriefStatus.GENERATING.value
        brief.operator_note = None
        brief.actioned_at = None
        brief.approved_by_user_id = None
        await self.db.flush()

        regenerated = await self.generate_brief(
            tenant_id,
            BriefGenerateRequest(
                story_cluster_id=brief.story_cluster_id,
                brand_profile_id=brief.brand_profile_id,
                ttl_hours=max(int(((brief.expires_at - datetime.now(timezone.utc)).total_seconds() // 3600) if brief.expires_at else 24), 1),
            ),
            actor_user_id=actor_user_id,
            rewrite_instruction="Regenerate the brief with a fresh angle while preserving evidence quality.",
            force_regenerate=True,
        )
        regenerated.generation_trace = {
            **regenerated.generation_trace,
            "regenerated_by": str(actor_user_id) if actor_user_id else "",
        }
        await self.db.flush()
        return regenerated

    async def rewrite_brief(
        self,
        tenant_id: UUID,
        brief_id: UUID,
        payload: BriefRewriteRequest,
        actor_user_id: UUID | None,
    ) -> EditorialBrief:
        brief = await self._get_or_404(tenant_id, brief_id)
        cluster = await self.story_repo.get_cluster(tenant_id, brief.story_cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail="Story cluster not found")
        instructions: list[str] = []
        mode = payload.mode.lower()
        if mode == "safer_angle":
            instructions.append("Use a safer and more cautious angle with stronger caveats.")
        elif mode == "soften":
            instructions.append("Use a softer, less confrontational tone.")
        elif mode == "text_only":
            instructions.append("Recommend text-first formats only and avoid video-heavy packaging.")
        elif mode == "text_video":
            instructions.append("Recommend a combined text plus video package.")
        else:
            instructions.append("Rewrite the brief with a materially different but evidence-backed angle.")
        if payload.requested_tone:
            instructions.append(f"Requested tone: {payload.requested_tone}.")
        if payload.platform_mix:
            instructions.append(f"Target platform mix: {', '.join(payload.platform_mix)}.")
        if payload.content_format:
            instructions.append(f"Preferred content format: {payload.content_format}.")
        if payload.operator_note:
            instructions.append(f"Operator note: {payload.operator_note}.")

        regenerated = await self.generate_brief(
            tenant_id,
            BriefGenerateRequest(
                story_cluster_id=brief.story_cluster_id,
                brand_profile_id=brief.brand_profile_id,
                ttl_hours=max(int(((brief.expires_at - datetime.now(timezone.utc)).total_seconds() // 3600) if brief.expires_at else 24), 1),
            ),
            actor_user_id=actor_user_id,
            rewrite_instruction=" ".join(instructions),
            force_regenerate=True,
        )
        regenerated.rewrite_context = {
            "mode": payload.mode,
            "operator_note": payload.operator_note or "",
            "requested_tone": payload.requested_tone or "",
            "platform_mix": ",".join(payload.platform_mix or []),
            "content_format": payload.content_format or "",
        }
        await self.db.flush()
        return regenerated

    async def get_brief(self, tenant_id: UUID, brief_id: UUID) -> EditorialBrief:
        return await self._get_or_404(tenant_id, brief_id)

    async def list_briefs(
        self, tenant_id: UUID, status: str | None = None, limit: int = 50
    ) -> list[EditorialBrief]:
        return await self.repo.list_by_tenant(tenant_id, status=status, limit=limit)

    async def send_to_telegram(self, tenant_id: UUID, brief_id: UUID) -> dict:
        """
        Gate 1 — send editorial brief card to Telegram for topic approval.
        Generates an 8-char short_id, stores brief_id in Redis, sends the card.
        Returns the Telegram API result dict.
        """
        brief = await self._get_or_404(tenant_id, brief_id)
        if brief.status != BriefStatus.READY.value:
            raise HTTPException(
                status_code=409,
                detail=f"Brief must be in 'ready' status to send to Telegram, got '{brief.status}'",
            )

        settings_svc = SettingsService(self.db)
        tg_config = await settings_svc.resolve_telegram_runtime_config(tenant_id)
        if not tg_config.get("enabled") or not tg_config.get("bot_token") or not tg_config.get("chat_id"):
            raise HTTPException(status_code=422, detail="Telegram is not configured or not enabled for this tenant")

        # Generate short ID (idempotent: reuse if already set)
        short_id = brief.telegram_short_id
        if not short_id:
            short_id = secrets.token_urlsafe(6)[:8]
            brief.telegram_short_id = short_id

        redis_key = _BRIEF_SHORT_ID_KEY.format(short_id=short_id)
        await redis_client.setex(redis_key, _BRIEF_SHORT_ID_TTL, str(brief.id))

        bot_token = str(tg_config["bot_token"])
        chat_id = str(tg_config["chat_id"])
        provider = (
            get_telegram_provider(bot_token=bot_token, chat_id=chat_id)
            if bot_token.startswith("mock")
            else TelegramProvider(bot_token=bot_token, chat_id=chat_id)
        )
        result = await provider.send_brief_card(
            headline=brief.headline,
            angle=brief.angle,
            talking_points=brief.talking_points,
            tone=brief.tone_guidance,
            risk_level=brief.risk_level,
            risk_label=str(getattr(brief, "generation_trace", {}).get("risk_label", "low")),
            content_vertical=brief.content_vertical,
            why_now=brief.why_now,
            cta_strategy=brief.cta_strategy,
            platform_targets=brief.target_platforms,
            short_id=short_id,
        )
        # Store message_id for in-place editing after approve/reject
        if result.get("message_id"):
            brief.telegram_message_id = result["message_id"]
        await self.db.flush()
        return result

    async def get_by_short_id(self, short_id: str) -> EditorialBrief | None:
        """Look up a brief from its Redis short-ID (used by Telegram callback handler)."""
        return await self.repo.get_by_telegram_short_id(short_id)

    async def handle_telegram_brief_callback(self, payload: dict) -> None:
        """
        Handle gate-1 Telegram callback: approve_brief:<short_id> or reject_brief:<short_id>.
        Resolves the brief via short_id, transitions status, acks the callback, and edits the
        card message in-place to reflect the decision.
        """
        callback_query = payload.get("callback_query", {})
        if not callback_query:
            return

        callback_query_id = callback_query.get("id", "")
        data = callback_query.get("data", "")
        # Extract message context for in-place editing
        tg_message = callback_query.get("message", {})
        cb_message_id = str(tg_message.get("message_id", ""))
        cb_chat_id = str(tg_message.get("chat", {}).get("id", ""))

        is_valid, action, short_id = verify_signed_callback_data(data)
        if not is_valid:
            return

        brief = await self.get_by_short_id(short_id)
        if not brief or brief.status != BriefStatus.READY.value:
            return

        now = datetime.now(timezone.utc)
        if action == "approve_brief":
            brief.status = BriefStatus.APPROVED.value
            cluster = await self.story_repo.get_cluster(brief.tenant_id, brief.story_cluster_id)
            if cluster:
                cluster.workflow_state = TrendWorkflowState.APPROVED_TOPIC.value
            brief.actioned_at = now
            ack_text = "✅ Brief approved — content generation can proceed."
            edited_text = (
                f"<b>📋 Editorial Brief — ✅ APPROVED</b>\n\n"
                f"<b>Headline:</b> {brief.headline}\n"
                f"<b>Angle:</b> {brief.angle}"
            )
        elif action == "reject_brief":
            brief.status = BriefStatus.REJECTED.value
            cluster = await self.story_repo.get_cluster(brief.tenant_id, brief.story_cluster_id)
            if cluster:
                cluster.workflow_state = TrendWorkflowState.REJECTED.value
            brief.actioned_at = now
            ack_text = "❌ Brief rejected."
            edited_text = (
                f"<b>📋 Editorial Brief — ❌ REJECTED</b>\n\n"
                f"<b>Headline:</b> {brief.headline}\n"
                f"<b>Angle:</b> {brief.angle}"
            )
        elif action in {"safer_brief", "soften_brief", "text_only_brief", "text_video_brief"}:
            rewrite_mode = {
                "safer_brief": "safer_angle",
                "soften_brief": "soften",
                "text_only_brief": "text_only",
                "text_video_brief": "text_video",
            }[action]
            brief = await self.rewrite_brief(
                brief.tenant_id,
                brief.id,
                BriefRewriteRequest(mode=rewrite_mode),
                actor_user_id=None,
            )
            ack_text = "♻️ Brief rewritten."
            edited_text = (
                f"<b>📋 Editorial Brief — ♻️ REWRITTEN</b>\n\n"
                f"<b>Headline:</b> {brief.headline}\n"
                f"<b>Angle:</b> {brief.angle}\n"
                f"<b>Why now:</b> {brief.why_now}"
            )
        else:
            return

        await self.db.flush()

        # Ack the callback button press and edit the message in-place
        try:
            tg_config = await SettingsService(self.db).resolve_telegram_runtime_config(brief.tenant_id)
            bot_token = str(tg_config.get("bot_token", ""))
            chat_id = cb_chat_id or str(tg_config.get("chat_id", ""))
            if bot_token:
                provider = (
                    get_telegram_provider(bot_token=bot_token, chat_id=chat_id)
                    if bot_token.startswith("mock")
                    else TelegramProvider(bot_token=bot_token, chat_id=chat_id)
                )
                if callback_query_id:
                    await provider.answer_callback(callback_query_id, ack_text)
                # Edit the brief card in-place using the message_id from the callback
                edit_message_id = cb_message_id or brief.telegram_message_id
                if edit_message_id and chat_id:
                    await provider.edit_message(
                        chat_id=chat_id,
                        message_id=edit_message_id,
                        new_text=edited_text,
                    )
        except Exception:
            pass  # Ack/edit failure must not roll back status change

    async def _get_or_404(self, tenant_id: UUID, brief_id: UUID) -> EditorialBrief:
        brief = await self.repo.get(tenant_id, brief_id)
        if not brief:
            raise HTTPException(status_code=404, detail="Editorial brief not found")
        return brief
