from __future__ import annotations

import hashlib
import hmac

from backend.core.config import settings


def sign_telegram_callback(payload: str) -> str:
    digest = hmac.new(
        settings.telegram_callback_signing_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:10]


def build_signed_callback_data(action: str, identifier: str) -> str:
    payload = f"{action}:{identifier}"
    return f"{payload}:{sign_telegram_callback(payload)}"


def verify_signed_callback_data(data: str) -> tuple[bool, str, str]:
    parts = data.split(":")
    if len(parts) < 2:
        return False, "", ""
    if len(parts) == 2:
        return True, parts[0], parts[1]
    action, identifier, signature = parts[0], parts[1], parts[2]
    payload = f"{action}:{identifier}"
    return hmac.compare_digest(signature, sign_telegram_callback(payload)), action, identifier
