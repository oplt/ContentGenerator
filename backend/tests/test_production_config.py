from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core import bootstrap


def production_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "APP_ENV": "production",
        "JWT_SECRET": "strong-jwt-secret-value",
        "csrf_secret": "strong-csrf-secret-value",
        "ENCRYPTION_KEY": "strong-encryption-key",
        "COOKIE_SECURE": True,
        "STORAGE_USE_SSL": True,
        "PUBLIC_URL": "https://signalforge.example",
        "TELEGRAM_WEBHOOK_SECRET": "strong-webhook-secret",
        "TELEGRAM_CALLBACK_SIGNING_SECRET": "strong-callback-secret",
        "DEMO_SEED_ENABLED": False,
        "DEMO_ADMIN_PASSWORD": "unused-strong-password",
        "DATABASE_URL": "postgresql+asyncpg://app:strong@db:5432/signalforge",
        "STORAGE_ACCESS_KEY": "production-access-key",
        "STORAGE_SECRET_KEY": "production-secret-key",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"JWT_SECRET": "change-me"}, "JWT_SECRET"),
        ({"DEMO_SEED_ENABLED": True}, "DEMO_SEED_ENABLED"),
        ({"DEMO_ADMIN_PASSWORD": "password1234"}, "DEMO_ADMIN_PASSWORD"),
        ({"DATABASE_URL": bootstrap._DEFAULT_DATABASE_URL}, "DATABASE_URL"),
        ({"STORAGE_SECRET_KEY": "minioadmin"}, "Storage credentials"),
    ],
)
def test_production_rejects_insecure_defaults(
    monkeypatch: pytest.MonkeyPatch, override: dict[str, object], message: str
) -> None:
    monkeypatch.setattr(bootstrap, "settings", production_settings(**override))

    with pytest.raises(RuntimeError, match=message):
        bootstrap._assert_production_secrets()


def test_production_accepts_explicit_secure_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "settings", production_settings())

    bootstrap._assert_production_secrets()


def test_development_keeps_convenient_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "settings", production_settings(APP_ENV="development"))

    bootstrap._assert_production_secrets()
