"""Canonical SocialAccount lineage + ConnectedAccount backfill rules (T4.1).

SocialAccount is the publishable identity. ConnectedAccount is a legacy projection
kept for one-release API compatibility; every retained connected row must link to
exactly one social account after consolidation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class ConsolidationActionKind(str, Enum):
    CREATE_SOCIAL_FROM_CONNECTED = "create_social_from_connected"
    LINK_CONNECTED_TO_SOCIAL = "link_connected_to_social"
    MINT_EXTERNAL_ID = "mint_external_id"
    QUARANTINE_CONNECTED = "quarantine_connected"
    QUARANTINE_SOCIAL = "quarantine_social"
    BACKFILL_JOB_SOCIAL_ID = "backfill_job_social_id"


@dataclass(frozen=True)
class ConnectedSnapshot:
    id: UUID
    tenant_id: UUID
    platform: str
    account_name: str
    social_account_id: UUID | None
    status: str
    auth_type: str = "oauth"
    credential_ref: str | None = None
    scopes: tuple[str, ...] = ()
    metadata: dict[str, object] | None = None
    deleted: bool = False


@dataclass(frozen=True)
class SocialSnapshot:
    id: UUID
    tenant_id: UUID
    platform: str
    display_name: str
    account_external_id: str | None
    status: str
    deleted: bool = False
    legacy_connected_account_id: UUID | None = None


@dataclass(frozen=True)
class JobSnapshot:
    id: UUID
    tenant_id: UUID
    platform: str
    social_account_id: UUID | None
    connected_account_id: UUID | None


@dataclass(frozen=True)
class ConsolidationAction:
    kind: ConsolidationActionKind
    tenant_id: UUID
    platform: str
    connected_id: UUID | None = None
    social_id: UUID | None = None
    external_id: str | None = None
    reason: str | None = None
    job_id: UUID | None = None


def mint_legacy_external_id(*, connected_id: UUID | None = None, social_id: UUID | None = None) -> str:
    """Stable provider identity when OAuth external id is missing."""
    if connected_id is not None:
        return f"legacy:connected:{connected_id}"
    if social_id is not None:
        return f"legacy:social:{social_id}"
    raise ValueError("connected_id or social_id required to mint external id")


def resolve_external_id(
    *,
    provided: str | None,
    connected_id: UUID | None = None,
    social_id: UUID | None = None,
) -> str:
    cleaned = (provided or "").strip()
    if cleaned:
        return cleaned
    return mint_legacy_external_id(connected_id=connected_id, social_id=social_id)


def plan_consolidation(
    *,
    connected: list[ConnectedSnapshot],
    social: list[SocialSnapshot],
    jobs: list[JobSnapshot] | None = None,
) -> list[ConsolidationAction]:
    """
    Deterministic backfill plan.

    Rules
    -----
    * Prefer existing SocialAccount linked by ``connected.social_account_id``.
    * Else match social by tenant+platform+external_id or legacy_connected_account_id.
    * Else create social from connected (first non-deleted per tenant/platform/name).
    * Duplicate connected rows for same tenant/platform without distinct social targets
      are quarantined (status projection only — rows kept).
    * Social rows with NULL external_id get a minted identity.
    * Publishing jobs with connected_account_id but null social_account_id inherit the link.
    """
    actions: list[ConsolidationAction] = []
    live_social = [s for s in social if not s.deleted]
    live_connected = [c for c in connected if not c.deleted]

    social_by_id = {s.id: s for s in live_social}
    social_by_legacy_connected = {
        s.legacy_connected_account_id: s
        for s in live_social
        if s.legacy_connected_account_id is not None
    }
    social_by_external: dict[tuple[UUID, str, str], SocialSnapshot] = {}
    for s in live_social:
        if s.account_external_id:
            social_by_external[(s.tenant_id, s.platform, s.account_external_id)] = s

    for s in live_social:
        if not s.account_external_id:
            actions.append(
                ConsolidationAction(
                    kind=ConsolidationActionKind.MINT_EXTERNAL_ID,
                    tenant_id=s.tenant_id,
                    platform=s.platform,
                    social_id=s.id,
                    external_id=mint_legacy_external_id(social_id=s.id),
                    reason="null_external_id",
                )
            )

    # Group connected by tenant/platform to detect ambiguity.
    by_tenant_platform: dict[tuple[UUID, str], list[ConnectedSnapshot]] = {}
    for c in live_connected:
        by_tenant_platform.setdefault((c.tenant_id, c.platform), []).append(c)

    claimed_social_ids: set[UUID] = set()

    for (tenant_id, platform), group in sorted(
        by_tenant_platform.items(), key=lambda item: (str(item[0][0]), item[0][1])
    ):
        # Stable order: linked first, then created_at proxy via id string.
        ordered = sorted(
            group,
            key=lambda row: (0 if row.social_account_id else 1, str(row.id)),
        )
        seen_names: set[str] = set()
        for row in ordered:
            name_key = row.account_name.strip().lower()
            linked = (
                social_by_id.get(row.social_account_id)
                if row.social_account_id is not None
                else None
            )
            if linked is None and row.id in social_by_legacy_connected:
                linked = social_by_legacy_connected[row.id]

            if linked is not None:
                if linked.id in claimed_social_ids and row.social_account_id != linked.id:
                    actions.append(
                        ConsolidationAction(
                            kind=ConsolidationActionKind.QUARANTINE_CONNECTED,
                            tenant_id=tenant_id,
                            platform=platform,
                            connected_id=row.id,
                            social_id=linked.id,
                            reason="social_already_claimed",
                        )
                    )
                    continue
                claimed_social_ids.add(linked.id)
                if row.social_account_id != linked.id:
                    actions.append(
                        ConsolidationAction(
                            kind=ConsolidationActionKind.LINK_CONNECTED_TO_SOCIAL,
                            tenant_id=tenant_id,
                            platform=platform,
                            connected_id=row.id,
                            social_id=linked.id,
                            reason="legacy_connected_match",
                        )
                    )
                seen_names.add(name_key)
                continue

            if name_key in seen_names:
                actions.append(
                    ConsolidationAction(
                        kind=ConsolidationActionKind.QUARANTINE_CONNECTED,
                        tenant_id=tenant_id,
                        platform=platform,
                        connected_id=row.id,
                        reason="duplicate_platform_account_name",
                    )
                )
                continue
            seen_names.add(name_key)

            external = mint_legacy_external_id(connected_id=row.id)
            existing_ext = social_by_external.get((tenant_id, platform, external))
            if existing_ext is not None:
                claimed_social_ids.add(existing_ext.id)
                actions.append(
                    ConsolidationAction(
                        kind=ConsolidationActionKind.LINK_CONNECTED_TO_SOCIAL,
                        tenant_id=tenant_id,
                        platform=platform,
                        connected_id=row.id,
                        social_id=existing_ext.id,
                        external_id=external,
                        reason="external_id_match",
                    )
                )
                continue

            actions.append(
                ConsolidationAction(
                    kind=ConsolidationActionKind.CREATE_SOCIAL_FROM_CONNECTED,
                    tenant_id=tenant_id,
                    platform=platform,
                    connected_id=row.id,
                    external_id=external,
                    reason="orphan_connected",
                )
            )

    # Orphan social rows that share tenant+platform+external with another (impossible under
    # unique constraint) — quarantine soft-deleted mismatches already handled.

    for job in jobs or []:
        if job.social_account_id is not None:
            continue
        if job.connected_account_id is None:
            continue
        # Prefer planned link / existing connected.social_account_id.
        connected_row = next(
            (c for c in live_connected if c.id == job.connected_account_id),
            None,
        )
        social_id = connected_row.social_account_id if connected_row else None
        if social_id is None:
            for action in actions:
                if (
                    action.connected_id == job.connected_account_id
                    and action.kind
                    in {
                        ConsolidationActionKind.CREATE_SOCIAL_FROM_CONNECTED,
                        ConsolidationActionKind.LINK_CONNECTED_TO_SOCIAL,
                    }
                ):
                    # CREATE will mint social at apply-time; LINK already has social_id.
                    social_id = action.social_id
                    break
        if social_id is None and connected_row is not None:
            # CREATE actions do not yet know social_id; apply layer uses connected_id map.
            actions.append(
                ConsolidationAction(
                    kind=ConsolidationActionKind.BACKFILL_JOB_SOCIAL_ID,
                    tenant_id=job.tenant_id,
                    platform=job.platform,
                    connected_id=job.connected_account_id,
                    job_id=job.id,
                    reason="inherit_from_connected",
                )
            )
        elif social_id is not None:
            actions.append(
                ConsolidationAction(
                    kind=ConsolidationActionKind.BACKFILL_JOB_SOCIAL_ID,
                    tenant_id=job.tenant_id,
                    platform=job.platform,
                    connected_id=job.connected_account_id,
                    social_id=social_id,
                    job_id=job.id,
                    reason="inherit_from_connected",
                )
            )

    return actions
