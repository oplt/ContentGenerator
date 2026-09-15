from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException

from backend.core.security import decrypt_secret, encrypt_secret, resolve_secret_reference
from backend.modules.publishing.account_lineage import resolve_external_id
from backend.modules.publishing.models import (
    ConnectedAccount,
    ConnectedAccountStatus,
    SocialAccount,
    SocialAccountToken,
)
from backend.modules.publishing.providers import AuthValidationResult, get_provider
from backend.modules.publishing.schemas import (
    ConnectedAccountValidationResponse,
    SocialAccountUpsertRequest,
)


async def upsert_social_account(svc, tenant_id: UUID, payload: SocialAccountUpsertRequest) -> SocialAccount:
    """Upsert canonical SocialAccount and dual-write ConnectedAccount projection."""
    auth_type = "stub" if payload.use_stub else "oauth"
    existing: SocialAccount | None = None
    if payload.account_external_id:
        existing = await svc.repo.get_social_account_by_external_id(
            tenant_id, payload.platform, payload.account_external_id.strip()
        )
    if existing is None:
        # Platform-only compat for single-account tenants / stub connects.
        existing = await svc.repo.get_social_account_by_platform(tenant_id, payload.platform)
        if (
            existing is not None
            and payload.account_external_id
            and existing.account_external_id
            and existing.account_external_id != payload.account_external_id.strip()
            and not str(existing.account_external_id).startswith("legacy:")
        ):
            # Distinct provider identity → create additional account (multi-account).
            existing = None

    connected = None
    if existing is not None:
        connected = await svc.repo.get_connected_for_social(tenant_id, existing.id)
    if connected is None:
        connected = await svc.repo.get_connected_account_by_platform(tenant_id, payload.platform)

    provider = get_provider(
        payload.platform,
        use_stub=payload.use_stub,
        access_token=payload.access_token or "",
        account_external_id=payload.account_external_id or "",
    )
    capability_flags = provider.capabilities()
    account_mode: dict[str, object] = {**payload.metadata, "mode": "stub" if payload.use_stub else "real"}

    if existing:
        existing.display_name = payload.display_name
        existing.handle = payload.handle
        existing.auth_type = auth_type
        existing.account_metadata = {str(k): str(v) for k, v in account_mode.items()}
        existing.capability_flags = capability_flags
        if payload.account_external_id:
            existing.account_external_id = payload.account_external_id.strip()
        elif not existing.account_external_id:
            existing.account_external_id = resolve_external_id(
                provided=None,
                connected_id=connected.id if connected else None,
                social_id=existing.id,
            )
        account = existing
    else:
        account = await svc.repo.create_social_account(
            SocialAccount(
                tenant_id=tenant_id,
                platform=payload.platform,
                display_name=payload.display_name,
                handle=payload.handle,
                account_external_id=payload.account_external_id.strip()
                if payload.account_external_id
                else None,
                auth_type=auth_type,
                account_metadata={str(k): str(v) for k, v in account_mode.items()},
                capability_flags=capability_flags,
                settings={},
                legacy_connected_account_id=connected.id if connected else None,
            )
        )
        if not account.account_external_id:
            account.account_external_id = resolve_external_id(
                provided=None,
                connected_id=connected.id if connected else None,
                social_id=account.id,
            )

    credential_ref = None
    if payload.access_token or payload.access_token_secret_ref:
        await svc.repo.upsert_token(
            SocialAccountToken(
                social_account_id=account.id,
                access_token_encrypted=encrypt_secret(payload.access_token)
                if payload.access_token
                else encrypt_secret(f"secret-ref:{payload.access_token_secret_ref}"),
                refresh_token_encrypted=encrypt_secret(payload.refresh_token)
                if payload.refresh_token
                else None,
                scopes=payload.scopes,
            )
        )
        if payload.access_token_secret_ref:
            credential_ref = encrypt_secret(payload.access_token_secret_ref)
        else:
            credential_ref = f"social-account-token:{account.id}"

    if connected:
        connected.social_account_id = account.id
        connected.account_name = payload.display_name
        connected.auth_type = auth_type
        connected.credential_ref = credential_ref or connected.credential_ref
        connected.scopes = payload.scopes
        connected.account_metadata = account_mode
        connected.status = ConnectedAccountStatus.ACTIVE.value
        account.legacy_connected_account_id = connected.id
    else:
        connected = await svc.repo.create_connected_account(
            ConnectedAccount(
                tenant_id=tenant_id,
                social_account_id=account.id,
                platform=payload.platform,
                account_name=payload.display_name,
                auth_type=auth_type,
                credential_ref=credential_ref,
                scopes=payload.scopes,
                account_metadata=account_mode,
                status=ConnectedAccountStatus.ACTIVE.value,
            )
        )
        account.legacy_connected_account_id = connected.id

    validation = await provider.validate_auth(social_account=account)
    account.status = validation.account_status
    return account


async def validate_connected_account(
    svc,
    tenant_id: UUID,
    connected_account_id: UUID,
) -> ConnectedAccountValidationResponse:
    connected = await svc.repo.get_connected_account(tenant_id, connected_account_id)
    if not connected:
        raise HTTPException(status_code=404, detail="Connected account not found")
    social_account = None
    if connected.social_account_id:
        social_account = await svc.repo.get_social_account(tenant_id, connected.social_account_id)
    if not social_account:
        raise HTTPException(status_code=404, detail="Social account not found")
    token_row = await svc.repo.get_token_for_account(social_account.id)
    access_token = decrypt_secret(token_row.access_token_encrypted) if token_row else ""
    if access_token.startswith("secret-ref:"):
        access_token = resolve_secret_reference(access_token.partition(":")[2]) or ""
    provider = get_provider(
        str(connected.platform),
        use_stub=social_account.account_metadata.get("mode") == "stub",
        access_token=access_token,
        account_external_id=social_account.account_external_id or "",
    )
    validation: AuthValidationResult = await provider.validate_auth(social_account=social_account)
    connected.status = validation.account_status
    social_account.status = validation.account_status
    await svc.db.flush()
    return ConnectedAccountValidationResponse(
        connected_account_id=connected.id,
        platform=str(connected.platform),
        is_valid=validation.is_valid,
        account_status=validation.account_status,
        detail=validation.detail,
    )


