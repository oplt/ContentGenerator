"""Response mappers for publishing API (no token decryption on list paths)."""

from __future__ import annotations

from backend.modules.publishing.models import SocialAccount
from backend.modules.publishing.schemas import SocialAccountResponse


def social_account_to_response(account: SocialAccount) -> SocialAccountResponse:
    return SocialAccountResponse(
        id=account.id,
        platform=str(account.platform),
        display_name=account.display_name,
        handle=account.handle,
        account_external_id=account.account_external_id,
        status=str(account.status),
        auth_type=getattr(account, "auth_type", "oauth") or "oauth",
        capability_flags=account.capability_flags,
        metadata=account.account_metadata,
        settings=getattr(account, "settings", None) or {},
        legacy_connected_account_id=getattr(account, "legacy_connected_account_id", None),
        quarantine_reason=getattr(account, "quarantine_reason", None),
    )
