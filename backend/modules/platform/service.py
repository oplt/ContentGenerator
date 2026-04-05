import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.identity_access.models import User
from backend.modules.platform.models import (
    ApiKey,
    EmailTemplate,
    FeatureFlag,
    SubscriptionPlan,
    UserSubscription,
    WebhookEndpoint,
)
from backend.modules.platform.repository import PlatformRepository
from backend.modules.platform.schemas import (
    EffectiveFeatureFlagResponse,
    ModuleCatalogItem,
    ModulePackResponse,
    PlatformConfigResponse,
    PlatformMetadataResponse,
)
from backend.modules.settings.repository import SettingsRepository


MODULE_CATALOG = (
    {
        "key": "billing",
        "label": "Billing",
        "description": "Plan catalog and subscription management.",
        "user_visible": True,
    },
    {
        "key": "api_keys",
        "label": "API Keys",
        "description": "User-managed credentials for integrations and automation.",
        "user_visible": True,
    },
    {
        "key": "webhooks",
        "label": "Webhooks",
        "description": "Outbound event delivery to external systems.",
        "user_visible": True,
    },
    {
        "key": "feature_flags",
        "label": "Feature Flags",
        "description": "Runtime rollout controls for features and experiments.",
        "user_visible": True,
    },
    {
        "key": "email_templates",
        "label": "Email Templates",
        "description": "Customizable transactional email content.",
        "user_visible": False,
    },
)

MODULE_PACKS = {
    "lean_saas": {
        "label": "Lean SaaS",
        "description": "Billing plus integration basics for a straightforward SaaS clone.",
        "modules": ["billing", "api_keys", "feature_flags"],
    },
    "automation_suite": {
        "label": "Automation Suite",
        "description": "API keys, webhooks, flags, and templates for workflow-driven products.",
        "modules": ["api_keys", "webhooks", "feature_flags", "email_templates"],
    },
    "client_portal": {
        "label": "Client Portal",
        "description": "Subscription-led portal with flags and email customization.",
        "modules": ["billing", "feature_flags", "email_templates"],
    },
    "full_platform": {
        "label": "Full Platform",
        "description": "Enable every optional platform module.",
        "modules": [item["key"] for item in MODULE_CATALOG],
    },
}

DEFAULT_PLANS = (
    {
        "code": "free",
        "name": "Free",
        "description": "Starter plan for early validation and internal testing.",
        "price_cents": 0,
        "interval": "month",
        "is_default": True,
        "features_json": ["core_access", "community_support"],
    },
    {
        "code": "growth",
        "name": "Growth",
        "description": "Operational plan for customer-facing launches and smaller teams.",
        "price_cents": 4900,
        "interval": "month",
        "is_default": False,
        "features_json": ["core_access", "priority_support", "platform_webhooks", "platform_api_keys"],
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": "Premium plan for large deployments and white-label programs.",
        "price_cents": 19900,
        "interval": "month",
        "is_default": False,
        "features_json": [
            "core_access",
            "priority_support",
            "platform_webhooks",
            "platform_api_keys",
            "advanced_templates",
        ],
    },
)

DEFAULT_FEATURE_FLAGS = (
    {
        "key": "beta_dashboard",
        "name": "Beta Dashboard",
        "description": "Enable next-generation dashboard components.",
        "module_key": "feature_flags",
        "is_enabled": True,
        "rollout_percentage": 100,
    },
    {
        "key": "advanced_billing_controls",
        "name": "Advanced Billing Controls",
        "description": "Expose richer billing controls and internal finance actions.",
        "module_key": "billing",
        "is_enabled": False,
        "rollout_percentage": 0,
    },
    {
        "key": "webhook_replay",
        "name": "Webhook Replay",
        "description": "Prepare replay tooling for webhook troubleshooting workflows.",
        "module_key": "webhooks",
        "is_enabled": False,
        "rollout_percentage": 0,
    },
)

DEFAULT_EMAIL_TEMPLATES = (
    {
        "key": "auth.verify_email",
        "name": "Verify Email",
        "subject_template": "{{app_name}}: verify your email address",
        "html_template": (
            "<p>Thanks for joining {{app_name}}.</p>"
            "<p>Verify your email by opening <a href=\"{{action_url}}\">this link</a>.</p>"
            "<p>If you did not create an account for {{recipient_email}}, you can ignore this email.</p>"
        ),
        "text_template": (
            "Thanks for joining {{app_name}}.\n"
            "Verify your email by opening: {{action_url}}\n"
            "If you did not create an account for {{recipient_email}}, ignore this email."
        ),
        "is_active": True,
    },
    {
        "key": "auth.reset_password",
        "name": "Reset Password",
        "subject_template": "{{app_name}}: reset your password",
        "html_template": (
            "<p>We received a password reset request for {{recipient_email}}.</p>"
            "<p>Use <a href=\"{{action_url}}\">this secure link</a> to choose a new password.</p>"
            "<p>If you did not request this, you can ignore this email.</p>"
        ),
        "text_template": (
            "We received a password reset request for {{recipient_email}}.\n"
            "Use this secure link to choose a new password: {{action_url}}\n"
            "If you did not request this, you can ignore this email."
        ),
        "is_active": True,
    },
)

SETTING_APP_NAME = "platform.app_name"
SETTING_CORE_DOMAIN_SINGULAR = "platform.core_domain_singular"
SETTING_CORE_DOMAIN_PLURAL = "platform.core_domain_plural"
SETTING_MODULE_PACK = "platform.module_pack"
SETTING_MODULE_OVERRIDE_PREFIX = "platform.module_override."

PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


class PlatformService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PlatformRepository(db)
        self.settings_repo = SettingsRepository(db)

    async def ensure_defaults(self) -> None:
        changed = False

        for key, value, description in (
            (SETTING_APP_NAME, settings.APP_NAME, "Clone-specific app display name."),
            (
                SETTING_CORE_DOMAIN_SINGULAR,
                settings.CORE_DOMAIN_SINGULAR,
                "Singular label for the core domain surfaced in the UI.",
            ),
            (
                SETTING_CORE_DOMAIN_PLURAL,
                settings.CORE_DOMAIN_PLURAL,
                "Plural label for the core domain surfaced in the UI.",
            ),
            (
                SETTING_MODULE_PACK,
                settings.PLATFORM_DEFAULT_MODULE_PACK,
                "Active module pack for optional platform capabilities.",
            ),
        ):
            if await self.settings_repo.get_by_key(key) is None:
                await self.settings_repo.create(key=key, value=value, description=description)
                changed = True

        for plan_payload in DEFAULT_PLANS:
            if await self.repo.get_plan_by_code(plan_payload["code"]) is None:
                await self.repo.create_plan(**plan_payload)
                changed = True

        for flag_payload in DEFAULT_FEATURE_FLAGS:
            if await self.repo.get_feature_flag_by_key(flag_payload["key"]) is None:
                await self.repo.create_feature_flag(**flag_payload)
                changed = True

        for template_payload in DEFAULT_EMAIL_TEMPLATES:
            if await self.repo.get_email_template_by_key(template_payload["key"]) is None:
                await self.repo.create_email_template(**template_payload)
                changed = True

        if changed:
            await self.db.commit()

    async def get_platform_metadata(self) -> PlatformMetadataResponse:
        config = await self.get_platform_config()
        return PlatformMetadataResponse(
            app_name=config.app_name,
            core_domain_singular=config.core_domain_singular,
            core_domain_plural=config.core_domain_plural,
            module_pack=config.module_pack,
            enabled_modules=config.enabled_modules,
            module_catalog=config.module_catalog,
            available_module_packs=config.available_module_packs,
        )

    async def get_platform_config(self) -> PlatformConfigResponse:
        platform_settings = await self.settings_repo.list_by_prefix("platform.")
        setting_map = {item.key: item.value for item in platform_settings}

        module_pack = setting_map.get(SETTING_MODULE_PACK, settings.PLATFORM_DEFAULT_MODULE_PACK)
        if module_pack not in MODULE_PACKS:
            module_pack = settings.PLATFORM_DEFAULT_MODULE_PACK

        explicit_overrides: dict[str, bool] = {}
        for item in MODULE_CATALOG:
            raw_value = setting_map.get(f"{SETTING_MODULE_OVERRIDE_PREFIX}{item['key']}")
            if raw_value is not None:
                explicit_overrides[item["key"]] = self._parse_bool(raw_value)

        enabled_modules = self._resolve_enabled_modules(module_pack, explicit_overrides)
        module_catalog = [
            ModuleCatalogItem(
                key=item["key"],
                label=item["label"],
                description=item["description"],
                user_visible=item["user_visible"],
                enabled=item["key"] in enabled_modules,
            )
            for item in MODULE_CATALOG
        ]

        return PlatformConfigResponse(
            app_name=setting_map.get(SETTING_APP_NAME, settings.APP_NAME),
            core_domain_singular=setting_map.get(
                SETTING_CORE_DOMAIN_SINGULAR, settings.CORE_DOMAIN_SINGULAR
            ),
            core_domain_plural=setting_map.get(
                SETTING_CORE_DOMAIN_PLURAL, settings.CORE_DOMAIN_PLURAL
            ),
            module_pack=module_pack,
            enabled_modules=enabled_modules,
            module_catalog=module_catalog,
            available_module_packs=[
                ModulePackResponse(key=key, **pack_payload) for key, pack_payload in MODULE_PACKS.items()
            ],
            module_overrides=explicit_overrides,
        )

    async def update_platform_config(
        self,
        *,
        app_name: str | None,
        core_domain_singular: str | None,
        core_domain_plural: str | None,
        module_pack: str | None,
        module_overrides: dict[str, bool] | None,
    ) -> PlatformConfigResponse:
        current_config = await self.get_platform_config()
        next_pack = module_pack or current_config.module_pack
        if next_pack not in MODULE_PACKS:
            raise HTTPException(status_code=422, detail="Unknown module pack")

        if app_name is not None:
            await self._upsert_setting(SETTING_APP_NAME, app_name, "Clone-specific app display name.")
        if core_domain_singular is not None:
            await self._upsert_setting(
                SETTING_CORE_DOMAIN_SINGULAR,
                core_domain_singular,
                "Singular label for the core domain surfaced in the UI.",
            )
        if core_domain_plural is not None:
            await self._upsert_setting(
                SETTING_CORE_DOMAIN_PLURAL,
                core_domain_plural,
                "Plural label for the core domain surfaced in the UI.",
            )
        if module_pack is not None:
            await self._upsert_setting(
                SETTING_MODULE_PACK,
                module_pack,
                "Active module pack for optional platform capabilities.",
            )

        if module_overrides is not None:
            pack_modules = set(MODULE_PACKS[next_pack]["modules"])
            valid_module_keys = {item["key"] for item in MODULE_CATALOG}
            for key, enabled in module_overrides.items():
                if key not in valid_module_keys:
                    raise HTTPException(status_code=422, detail=f"Unknown module key: {key}")
                setting_key = f"{SETTING_MODULE_OVERRIDE_PREFIX}{key}"
                should_exist = enabled != (key in pack_modules)
                existing = await self.settings_repo.get_by_key(setting_key)
                if should_exist:
                    if existing is None:
                        await self.settings_repo.create(
                            key=setting_key,
                            value=self._serialize_bool(enabled),
                            description=f"Explicit module override for {key}.",
                        )
                    else:
                        existing.value = self._serialize_bool(enabled)
                elif existing is not None:
                    await self.settings_repo.delete(existing)

        await self.db.commit()
        return await self.get_platform_config()

    async def list_plans(self) -> list[SubscriptionPlan]:
        return await self.repo.list_plans()

    async def create_plan(self, payload: dict) -> SubscriptionPlan:
        if await self.repo.get_plan_by_code(payload["code"]) is not None:
            raise HTTPException(status_code=409, detail="A plan with this code already exists")

        plan = await self.repo.create_plan(
            code=payload["code"],
            name=payload["name"],
            description=payload.get("description"),
            price_cents=payload["price_cents"],
            interval=payload["interval"],
            is_active=True,
            is_default=payload.get("is_default", False),
            features_json=payload.get("features", []),
        )
        await self._normalize_default_plan(plan)
        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def update_plan(self, plan_id: str, payload: dict) -> SubscriptionPlan:
        plan = await self.repo.get_plan_by_id(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        for field, value in payload.items():
            if field == "features":
                setattr(plan, "features_json", value)
            else:
                setattr(plan, field, value)

        await self._normalize_default_plan(plan)
        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def get_subscription_for_user(self, user: User) -> UserSubscription | None:
        await self.ensure_module_enabled("billing")
        return await self.repo.get_subscription_for_user(user.id)

    async def select_plan_for_user(self, user: User, plan_code: str) -> UserSubscription:
        await self.ensure_module_enabled("billing")
        plan = await self.repo.get_plan_by_code(plan_code)
        if not plan or not plan.is_active:
            raise HTTPException(status_code=404, detail="Plan not found")

        subscription = await self.repo.get_subscription_for_user(user.id)
        current_period_end = self._calculate_period_end(plan.interval)
        if subscription is None:
            subscription = await self.repo.create_subscription(
                user_id=user.id,
                plan_id=plan.id,
                status="active",
                cancel_at_period_end=False,
                started_at=datetime.now(timezone.utc),
                current_period_end=current_period_end,
            )
        else:
            subscription.plan_id = plan.id
            subscription.status = "active"
            subscription.cancel_at_period_end = False
            subscription.current_period_end = current_period_end

        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def list_api_keys_for_user(self, user: User) -> list[ApiKey]:
        await self.ensure_module_enabled("api_keys")
        return await self.repo.list_api_keys_for_user(user.id)

    async def create_api_key_for_user(self, user: User, name: str) -> tuple[ApiKey, str]:
        await self.ensure_module_enabled("api_keys")
        raw_token = f"gap_{secrets.token_urlsafe(32)}"
        api_key = await self.repo.create_api_key(
            user_id=user.id,
            name=name,
            key_prefix=raw_token[:12],
            key_hash=self._hash_secret(raw_token),
        )
        await self.db.commit()
        await self.db.refresh(api_key)
        return api_key, raw_token

    async def revoke_api_key_for_user(self, user: User, api_key_id: str) -> ApiKey:
        await self.ensure_module_enabled("api_keys")
        api_key = await self.repo.get_api_key_for_user(user.id, api_key_id)
        if not api_key:
            raise HTTPException(status_code=404, detail="API key not found")
        api_key.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(api_key)
        return api_key

    async def list_webhooks_for_user(self, user: User) -> list[WebhookEndpoint]:
        await self.ensure_module_enabled("webhooks")
        return await self.repo.list_webhooks_for_user(user.id)

    async def create_webhook_for_user(
        self,
        user: User,
        *,
        target_url: str,
        description: str | None,
        events: list[str],
    ) -> WebhookEndpoint:
        await self.ensure_module_enabled("webhooks")
        webhook = await self.repo.create_webhook(
            user_id=user.id,
            target_url=target_url,
            description=description,
            secret=secrets.token_urlsafe(24),
            is_active=True,
            events_json=events,
        )
        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    async def update_webhook_for_user(self, user: User, webhook_id: str, payload: dict) -> WebhookEndpoint:
        await self.ensure_module_enabled("webhooks")
        webhook = await self.repo.get_webhook_for_user(user.id, webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        for field, value in payload.items():
            if field == "events":
                webhook.events_json = value
            elif field == "target_url" and value is not None:
                webhook.target_url = str(value)
            elif value is not None:
                setattr(webhook, field, value)

        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    async def delete_webhook_for_user(self, user: User, webhook_id: str) -> None:
        await self.ensure_module_enabled("webhooks")
        webhook = await self.repo.get_webhook_for_user(user.id, webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")
        await self.repo.delete_webhook(webhook)
        await self.db.commit()

    async def test_webhook_for_user(self, user: User, webhook_id: str) -> dict:
        await self.ensure_module_enabled("webhooks")
        webhook = await self.repo.get_webhook_for_user(user.id, webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        metadata = await self.get_platform_metadata()
        payload = {
            "event": "platform.test",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "app_name": metadata.app_name,
            "core_domain_plural": metadata.core_domain_plural,
            "target_user_id": user.id,
        }
        raw_body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(webhook.secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    webhook.target_url,
                    content=raw_body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Generic-App-Event": payload["event"],
                        "X-Generic-App-Signature": signature,
                    },
                )
            webhook.last_tested_at = datetime.now(timezone.utc)
            webhook.last_response_status = response.status_code
            await self.db.commit()
            await self.db.refresh(webhook)
            return {
                "delivered": response.is_success,
                "status_code": response.status_code,
                "response_preview": response.text[:500] if response.text else None,
                "error": None,
            }
        except httpx.HTTPError as exc:
            webhook.last_tested_at = datetime.now(timezone.utc)
            webhook.last_response_status = None
            await self.db.commit()
            await self.db.refresh(webhook)
            return {
                "delivered": False,
                "status_code": None,
                "response_preview": None,
                "error": str(exc),
            }

    async def list_feature_flags(self) -> list[FeatureFlag]:
        return await self.repo.list_feature_flags()

    async def list_effective_feature_flags_for_user(self, user: User) -> list[EffectiveFeatureFlagResponse]:
        await self.ensure_module_enabled("feature_flags")
        flags = await self.repo.list_feature_flags()
        metadata = await self.get_platform_metadata()
        enabled_modules = set(metadata.enabled_modules)
        return [
            EffectiveFeatureFlagResponse(
                id=flag.id,
                key=flag.key,
                name=flag.name,
                description=flag.description,
                module_key=flag.module_key,
                is_enabled=flag.is_enabled,
                rollout_percentage=flag.rollout_percentage,
                updated_at=flag.updated_at,
                effective_enabled=self._is_flag_effective(flag, user.id, enabled_modules),
            )
            for flag in flags
        ]

    async def create_feature_flag(self, payload: dict) -> FeatureFlag:
        if await self.repo.get_feature_flag_by_key(payload["key"]) is not None:
            raise HTTPException(status_code=409, detail="A feature flag with this key already exists")

        flag = await self.repo.create_feature_flag(**payload)
        await self.db.commit()
        await self.db.refresh(flag)
        return flag

    async def update_feature_flag(self, feature_flag_id: str, payload: dict) -> FeatureFlag:
        flag = await self.repo.get_feature_flag_by_id(feature_flag_id)
        if not flag:
            raise HTTPException(status_code=404, detail="Feature flag not found")
        for field, value in payload.items():
            setattr(flag, field, value)
        await self.db.commit()
        await self.db.refresh(flag)
        return flag

    async def list_email_templates(self) -> list[EmailTemplate]:
        return await self.repo.list_email_templates()

    async def create_email_template(self, payload: dict) -> EmailTemplate:
        if await self.repo.get_email_template_by_key(payload["key"]) is not None:
            raise HTTPException(status_code=409, detail="An email template with this key already exists")
        template = await self.repo.create_email_template(**payload)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def update_email_template(self, template_id: str, payload: dict) -> EmailTemplate:
        template = await self.repo.get_email_template_by_id(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Email template not found")
        for field, value in payload.items():
            setattr(template, field, value)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def render_email_template(
        self,
        *,
        key: str,
        context: dict[str, str],
        fallback_subject: str,
        fallback_html: str,
        fallback_text: str | None = None,
    ) -> tuple[str, str, str | None]:
        template = await self.repo.get_email_template_by_key(key)
        if not template or not template.is_active:
            return fallback_subject, fallback_html, fallback_text
        return (
            self._render_template_string(template.subject_template, context),
            self._render_template_string(template.html_template, context),
            self._render_template_string(template.text_template, context) if template.text_template else None,
        )

    async def ensure_module_enabled(self, module_key: str) -> None:
        metadata = await self.get_platform_metadata()
        if module_key not in metadata.enabled_modules:
            raise HTTPException(status_code=404, detail=f"Module `{module_key}` is not enabled")

    async def _normalize_default_plan(self, active_plan: SubscriptionPlan) -> None:
        if not active_plan.is_default:
            return
        plans = await self.repo.list_plans()
        for plan in plans:
            if plan.id != active_plan.id and plan.is_default:
                plan.is_default = False

    async def _upsert_setting(self, key: str, value: str, description: str) -> None:
        setting = await self.settings_repo.get_by_key(key)
        if setting is None:
            await self.settings_repo.create(key=key, value=value, description=description)
        else:
            setting.value = value
            setting.description = description

    @staticmethod
    def _resolve_enabled_modules(module_pack: str, explicit_overrides: dict[str, bool]) -> list[str]:
        enabled = set(MODULE_PACKS[module_pack]["modules"])
        for key, value in explicit_overrides.items():
            if value:
                enabled.add(key)
            else:
                enabled.discard(key)
        ordered_module_keys = [item["key"] for item in MODULE_CATALOG]
        return [key for key in ordered_module_keys if key in enabled]

    @staticmethod
    def _parse_bool(raw_value: str) -> bool:
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _serialize_bool(value: bool) -> str:
        return "true" if value else "false"

    @staticmethod
    def _hash_secret(raw_value: str) -> str:
        return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()

    @staticmethod
    def _calculate_period_end(interval: str) -> datetime | None:
        now = datetime.now(timezone.utc)
        normalized = interval.lower()
        if normalized == "month":
            return now + timedelta(days=30)
        if normalized == "year":
            return now + timedelta(days=365)
        if normalized == "week":
            return now + timedelta(days=7)
        if normalized == "lifetime":
            return None
        return now + timedelta(days=30)

    @staticmethod
    def _render_template_string(template: str, context: dict[str, str]) -> str:
        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(context.get(key, ""))

        return PLACEHOLDER_PATTERN.sub(_replace, template)

    @staticmethod
    def _is_flag_effective(flag: FeatureFlag, user_id: str, enabled_modules: set[str]) -> bool:
        if not flag.is_enabled:
            return False
        if flag.module_key and flag.module_key not in enabled_modules:
            return False
        if flag.rollout_percentage >= 100:
            return True
        if flag.rollout_percentage <= 0:
            return False
        digest = hashlib.sha256(f"{flag.key}:{user_id}".encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 100
        return bucket < flag.rollout_percentage
