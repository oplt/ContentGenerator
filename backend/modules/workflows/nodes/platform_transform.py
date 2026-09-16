"""PlatformTransform — late specialization of canonical content (Phase 9)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.publishing.account_selection import group_by_fingerprint
from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)
from backend.modules.workflows.platform_adapt import adapt_canonical_for_platform


class _AccountLike(Protocol):
    id: UUID
    platform: str
    capability_flags: dict[str, str]
    settings: dict[str, object]


class PlatformTransformConfig(BaseModel):
    include_hashtags: bool = True


class PlatformTransformInput(BaseModel):
    text: str = Field(min_length=1)
    title: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    social_account_ids: list[UUID] | None = None
    content_job_id: UUID | None = None


class PlatformVariantModel(BaseModel):
    platform: str
    fingerprint: str
    text: str
    title: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    social_account_ids: list[str] = Field(default_factory=list)


class PlatformTransformOutput(BaseModel):
    canonical_text: str
    variants: list[PlatformVariantModel]
    fingerprint_count: int
    content_job_id: UUID | None = None


class _SnapshotAccount:
    def __init__(
        self,
        *,
        id: UUID,
        platform: str,
        capability_flags: dict[str, str],
        settings: dict[str, object],
    ) -> None:
        self.id = id
        self.platform = platform
        self.capability_flags = capability_flags
        self.settings = settings


class PlatformTransformNode(
    WorkflowNode[PlatformTransformConfig, PlatformTransformInput, PlatformTransformOutput]
):
    """One adaptation per account fingerprint — never re-writes research/canonical copy."""

    type = "platform_transform"
    version = 1
    category = "distribution"
    display_name = "Platform Transform"
    description = (
        "Adapt canonical content to platform constraints once per variant fingerprint."
    )
    ConfigSchema = PlatformTransformConfig
    InputSchema = PlatformTransformInput
    OutputSchema = PlatformTransformOutput
    required_capabilities = []
    input_ports = [
        NodePort(name="text", data_type="string"),
        NodePort(name="title", data_type="string", required=False),
        NodePort(name="hashtags", data_type="array", required=False),
        NodePort(name="social_account_ids", data_type="array", required=False),
        NodePort(name="content_job_id", data_type="uuid", required=False),
    ]
    output_ports = [
        NodePort(name="canonical_text", data_type="string"),
        NodePort(name="variants", data_type="array"),
        NodePort(name="fingerprint_count", data_type="number"),
        NodePort(name="content_job_id", data_type="uuid", required=False),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        typed_in = PlatformTransformInput.model_validate(inputs.model_dump())
        typed_cfg = PlatformTransformConfig.model_validate(config.model_dump())
        accounts = await self._resolve_accounts(context, typed_in.social_account_ids)
        if not accounts:
            return NodeResult(
                status=NodeResultStatus.FAILED,
                error={
                    "code": "missing_accounts",
                    "message": "PlatformTransform requires social accounts (input or snapshot)",
                },
            )

        groups = group_by_fingerprint(list(accounts))  # type: ignore[arg-type]
        variants: list[PlatformVariantModel] = []
        for fingerprint, group in sorted(groups.items(), key=lambda item: item[0]):
            adapted = adapt_canonical_for_platform(
                canonical_text=typed_in.text,
                platform=group[0].platform,
                fingerprint=fingerprint,
                social_account_ids=[str(a.id) for a in group],
                title=typed_in.title,
                hashtags=list(typed_in.hashtags),
                include_hashtags=typed_cfg.include_hashtags,
                capability_flags=dict(group[0].capability_flags or {}),
            )
            variants.append(PlatformVariantModel.model_validate(adapted.as_dict()))

        output = PlatformTransformOutput(
            canonical_text=typed_in.text.strip(),
            variants=variants,
            fingerprint_count=len(variants),
            content_job_id=typed_in.content_job_id,
        )
        return NodeResult(
            status=NodeResultStatus.SUCCEEDED,
            output=output.model_dump(mode="json"),
        )

    async def _resolve_accounts(
        self,
        context: WorkflowNodeContext,
        social_account_ids: list[UUID] | None,
    ) -> list[_AccountLike]:
        ids = list(social_account_ids or [])
        if not ids:
            for row in context.snapshot.get("accounts") or []:
                if isinstance(row, dict) and row.get("social_account_id"):
                    try:
                        ids.append(UUID(str(row["social_account_id"])))
                    except ValueError:
                        continue
        if not ids:
            return []
        if context.db is not None:
            from backend.modules.publishing.repository import PublishingRepository

            found = await PublishingRepository(context.db).get_social_accounts_by_ids(
                context.tenant_id, ids
            )
            if found:
                return list(found)
        return self._accounts_from_snapshot(context, ids)

    @staticmethod
    def _accounts_from_snapshot(
        context: WorkflowNodeContext, ids: list[UUID]
    ) -> list[_AccountLike]:
        wanted = {str(i) for i in ids}
        rows: list[_AccountLike] = []
        for row in context.snapshot.get("accounts") or []:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("social_account_id") or "")
            if sid not in wanted:
                continue
            caps = row.get("capability_flags") or {}
            rows.append(
                _SnapshotAccount(
                    id=UUID(sid),
                    platform=str(row.get("platform") or "x"),
                    capability_flags=dict(caps) if isinstance(caps, dict) else {},
                    settings={},
                )
            )
        return rows
