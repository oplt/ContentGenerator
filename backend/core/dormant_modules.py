"""Canonical registry of product-dormant feature modules.

These packages live under ``backend.modules._dormant`` and must not be mounted on
``api_router``, registered in ``model_registry``, or shipped in Alembic until a
capability is completed end-to-end (models + migration + auth + OpenAPI + tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class DormantModule:
    name: str
    package: str
    decision: str
    reason: str
    table_names: frozenset[str]
    forbidden_openapi_prefixes: frozenset[str]
    blockers: tuple[str, ...]


DORMANT_MODULES: Final[tuple[DormantModule, ...]] = (
    DormantModule(
        name="platform",
        package="backend.modules._dormant.platform",
        decision="quarantine",
        reason=(
            "Billing/config/API-key/webhook/feature-flag surface is incomplete: "
            "PlatformService depends on missing settings/config contracts and has no migrations."
        ),
        table_names=frozenset(
            {
                "subscription_plans",
                "user_subscriptions",
                "api_keys",
                "webhook_endpoints",
                "feature_flags",
                "email_templates",
            }
        ),
        forbidden_openapi_prefixes=frozenset(
            {
                "/api/v1/platform",
                "/api/v1/billing",
                "/api/v1/api-keys",
                "/api/v1/webhooks",
                "/api/v1/feature-flags",
            }
        ),
        blockers=(
            "Missing SettingsRepository methods used by PlatformService.ensure_defaults()",
            "Missing settings.APP_NAME / CORE_DOMAIN_* / PLATFORM_DEFAULT_MODULE_PACK fields",
            "No Alembic revision for platform tables",
            "No frontend client or UI",
        ),
    ),
    DormantModule(
        name="projects",
        package="backend.modules._dormant.projects",
        decision="quarantine",
        reason="Project/task domain is unmounted and has no migrations or frontend surface.",
        table_names=frozenset({"projects", "project_tasks"}),
        forbidden_openapi_prefixes=frozenset({"/api/v1/projects"}),
        blockers=("No Alembic revision", "No frontend client or UI"),
    ),
    DormantModule(
        name="profile",
        package="backend.modules._dormant.profile",
        decision="quarantine",
        reason="User profile module is unmounted; identity/users cover active account needs.",
        table_names=frozenset({"user_profiles"}),
        forbidden_openapi_prefixes=frozenset({"/api/v1/profile", "/api/v1/profiles"}),
        blockers=("No Alembic revision", "No frontend client or UI"),
    ),
    DormantModule(
        name="notifications",
        package="backend.modules._dormant.notifications",
        decision="quarantine",
        reason="In-app notification center is incomplete; approvals/Telegram cover operational alerts.",
        table_names=frozenset({"notifications", "notification_preferences"}),
        forbidden_openapi_prefixes=frozenset({"/api/v1/notifications"}),
        blockers=("No Alembic revision", "No frontend client or UI"),
    ),
    DormantModule(
        name="calendar",
        package="backend.modules._dormant.calendar",
        decision="quarantine",
        reason="Calendar depends on dormant projects and has no migrations or UI.",
        table_names=frozenset({"calendar_entries"}),
        forbidden_openapi_prefixes=frozenset({"/api/v1/calendar"}),
        blockers=("Depends on dormant projects", "No Alembic revision", "No frontend client or UI"),
    ),
    DormantModule(
        name="admin",
        package="backend.modules._dormant.admin",
        decision="quarantine",
        reason=(
            "Admin console is unmounted and broken: list_audit_logs calls missing "
            "AuditRepository.list_recent(); live audit lives under /api/v1/audit."
        ),
        table_names=frozenset(),
        forbidden_openapi_prefixes=frozenset({"/api/v1/admin"}),
        blockers=(
            "AuditRepository.list_recent() does not exist (list_logs does)",
            "No frontend admin console",
        ),
    ),
)

DORMANT_PACKAGE_NAMES: Final[frozenset[str]] = frozenset(module.name for module in DORMANT_MODULES)

DORMANT_TABLE_NAMES: Final[frozenset[str]] = frozenset().union(
    *(module.table_names for module in DORMANT_MODULES)
)

FORBIDDEN_OPENAPI_PREFIXES: Final[frozenset[str]] = frozenset().union(
    *(module.forbidden_openapi_prefixes for module in DORMANT_MODULES)
)

# Legacy import paths that must remain absent from the live tree.
LEGACY_LIVE_PACKAGE_PATHS: Final[tuple[str, ...]] = (
    "backend/modules/platform",
    "backend/modules/projects",
    "backend/modules/profile",
    "backend/modules/notifications",
    "backend/modules/calendar",
    "backend/modules/admin",
)
