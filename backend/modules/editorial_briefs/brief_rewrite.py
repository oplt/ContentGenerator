"""Brief regenerate and rewrite operations."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException

from backend.modules.editorial_briefs.models import BriefStatus, EditorialBrief
from backend.modules.editorial_briefs.schemas import BriefGenerateRequest, BriefRewriteRequest


class BriefRewriteMixin:
    """Force-regenerate and guided rewrite flows built on generate_brief."""

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
            raise HTTPException(
                status_code=409, detail="Brief is currently being generated — wait for it to finish"
            )

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
                ttl_hours=max(
                    int(
                        ((brief.expires_at - datetime.now(timezone.utc)).total_seconds() // 3600)
                        if brief.expires_at
                        else 24
                    ),
                    1,
                ),
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
                ttl_hours=max(
                    int(
                        ((brief.expires_at - datetime.now(timezone.utc)).total_seconds() // 3600)
                        if brief.expires_at
                        else 24
                    ),
                    1,
                ),
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
