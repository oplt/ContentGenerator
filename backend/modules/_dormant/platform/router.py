from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.admin import get_admin_user
from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules._dormant.platform.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    EmailTemplateCreate,
    EmailTemplateResponse,
    EmailTemplateUpdate,
    EffectiveFeatureFlagResponse,
    FeatureFlagCreate,
    FeatureFlagResponse,
    FeatureFlagUpdate,
    PlatformConfigResponse,
    PlatformConfigUpdateRequest,
    PlatformMetadataResponse,
    SubscriptionPlanCreate,
    SubscriptionPlanResponse,
    SubscriptionPlanUpdate,
    SubscriptionSelectionRequest,
    UserSubscriptionResponse,
    WebhookEndpointCreate,
    WebhookEndpointResponse,
    WebhookEndpointUpdate,
    WebhookTestResponse,
)
from backend.modules._dormant.platform.service import PlatformService

router = APIRouter()


def _plan_to_response(plan) -> SubscriptionPlanResponse:
    return SubscriptionPlanResponse(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        description=plan.description,
        price_cents=plan.price_cents,
        interval=plan.interval,
        is_active=plan.is_active,
        is_default=plan.is_default,
        features=plan.features_json,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def _subscription_to_response(subscription, plan) -> UserSubscriptionResponse:
    return UserSubscriptionResponse(
        id=subscription.id,
        status=subscription.status,
        cancel_at_period_end=subscription.cancel_at_period_end,
        started_at=subscription.started_at,
        current_period_end=subscription.current_period_end,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
        plan=_plan_to_response(plan),
    )


def _api_key_to_response(api_key) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        last_used_at=api_key.last_used_at,
        revoked_at=api_key.revoked_at,
        created_at=api_key.created_at,
    )


def _webhook_to_response(webhook) -> WebhookEndpointResponse:
    return WebhookEndpointResponse(
        id=webhook.id,
        target_url=webhook.target_url,
        description=webhook.description,
        secret=webhook.secret,
        is_active=webhook.is_active,
        events=webhook.events_json,
        last_tested_at=webhook.last_tested_at,
        last_response_status=webhook.last_response_status,
        created_at=webhook.created_at,
        updated_at=webhook.updated_at,
    )


def _feature_flag_to_response(flag) -> FeatureFlagResponse:
    return FeatureFlagResponse(
        id=flag.id,
        key=flag.key,
        name=flag.name,
        description=flag.description,
        module_key=flag.module_key,
        is_enabled=flag.is_enabled,
        rollout_percentage=flag.rollout_percentage,
        updated_at=flag.updated_at,
    )


def _email_template_to_response(template) -> EmailTemplateResponse:
    return EmailTemplateResponse(
        id=template.id,
        key=template.key,
        name=template.name,
        subject_template=template.subject_template,
        html_template=template.html_template,
        text_template=template.text_template,
        is_active=template.is_active,
        updated_at=template.updated_at,
    )


@router.get("/metadata", response_model=PlatformMetadataResponse)
async def get_platform_metadata(db: AsyncSession = Depends(get_db)):
    service = PlatformService(db)
    return await service.get_platform_metadata()


@router.get("/billing/plans", response_model=list[SubscriptionPlanResponse])
async def list_subscription_plans(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    service = PlatformService(db)
    await service.ensure_module_enabled("billing")
    plans = await service.list_plans()
    return [_plan_to_response(plan) for plan in plans if plan.is_active]


@router.get("/billing/subscription", response_model=UserSubscriptionResponse | None)
async def get_subscription(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PlatformService(db)
    subscription = await service.get_subscription_for_user(current_user)
    if subscription is None:
        return None
    plan = await service.repo.get_plan_by_id(subscription.plan_id)
    if plan is None:
        return None
    return _subscription_to_response(subscription, plan)


@router.put("/billing/subscription", response_model=UserSubscriptionResponse)
async def select_subscription_plan(
    payload: SubscriptionSelectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PlatformService(db)
    subscription = await service.select_plan_for_user(current_user, payload.plan_code)
    plan = await service.repo.get_plan_by_id(subscription.plan_id)
    assert plan is not None
    return _subscription_to_response(subscription, plan)


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PlatformService(db)
    return [_api_key_to_response(item) for item in await service.list_api_keys_for_user(current_user)]


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PlatformService(db)
    api_key, plaintext_key = await service.create_api_key_for_user(current_user, payload.name)
    response = _api_key_to_response(api_key)
    return ApiKeyCreateResponse(**response.model_dump(), plaintext_key=plaintext_key)


@router.delete("/api-keys/{api_key_id}", response_model=ApiKeyResponse)
async def revoke_api_key(
    api_key_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PlatformService(db)
    api_key = await service.revoke_api_key_for_user(current_user, api_key_id)
    return _api_key_to_response(api_key)


@router.get("/webhooks", response_model=list[WebhookEndpointResponse])
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PlatformService(db)
    return [_webhook_to_response(item) for item in await service.list_webhooks_for_user(current_user)]


@router.post("/webhooks", response_model=WebhookEndpointResponse, status_code=201)
async def create_webhook(
    payload: WebhookEndpointCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PlatformService(db)
    webhook = await service.create_webhook_for_user(
        current_user,
        target_url=str(payload.target_url),
        description=payload.description,
        events=payload.events,
    )
    return _webhook_to_response(webhook)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookEndpointResponse)
async def update_webhook(
    webhook_id: str,
    payload: WebhookEndpointUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PlatformService(db)
    updates = payload.model_dump(exclude_unset=True)
    if "target_url" in updates and updates["target_url"] is not None:
        updates["target_url"] = str(updates["target_url"])
    webhook = await service.update_webhook_for_user(current_user, webhook_id, updates)
    return _webhook_to_response(webhook)


@router.delete("/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PlatformService(db)
    await service.delete_webhook_for_user(current_user, webhook_id)
    return Response(status_code=204)


@router.post("/webhooks/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PlatformService(db)
    return WebhookTestResponse(**(await service.test_webhook_for_user(current_user, webhook_id)))


@router.get("/feature-flags", response_model=list[EffectiveFeatureFlagResponse])
async def list_effective_feature_flags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PlatformService(db)
    return await service.list_effective_feature_flags_for_user(current_user)


@router.get("/admin/config", response_model=PlatformConfigResponse)
async def get_platform_config(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    service = PlatformService(db)
    return await service.get_platform_config()


@router.put("/admin/config", response_model=PlatformConfigResponse)
async def update_platform_config(
    payload: PlatformConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    service = PlatformService(db)
    return await service.update_platform_config(**payload.model_dump())


@router.get("/admin/plans", response_model=list[SubscriptionPlanResponse])
async def list_admin_plans(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    service = PlatformService(db)
    return [_plan_to_response(plan) for plan in await service.list_plans()]


@router.post("/admin/plans", response_model=SubscriptionPlanResponse, status_code=201)
async def create_plan(
    payload: SubscriptionPlanCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    service = PlatformService(db)
    plan = await service.create_plan(payload.model_dump())
    return _plan_to_response(plan)


@router.patch("/admin/plans/{plan_id}", response_model=SubscriptionPlanResponse)
async def update_plan(
    plan_id: str,
    payload: SubscriptionPlanUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    service = PlatformService(db)
    plan = await service.update_plan(plan_id, payload.model_dump(exclude_unset=True))
    return _plan_to_response(plan)


@router.get("/admin/feature-flags", response_model=list[FeatureFlagResponse])
async def list_feature_flags(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    service = PlatformService(db)
    return [_feature_flag_to_response(flag) for flag in await service.list_feature_flags()]


@router.post("/admin/feature-flags", response_model=FeatureFlagResponse, status_code=201)
async def create_feature_flag(
    payload: FeatureFlagCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    service = PlatformService(db)
    flag = await service.create_feature_flag(payload.model_dump())
    return _feature_flag_to_response(flag)


@router.patch("/admin/feature-flags/{feature_flag_id}", response_model=FeatureFlagResponse)
async def update_feature_flag(
    feature_flag_id: str,
    payload: FeatureFlagUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    service = PlatformService(db)
    flag = await service.update_feature_flag(feature_flag_id, payload.model_dump(exclude_unset=True))
    return _feature_flag_to_response(flag)


@router.get("/admin/email-templates", response_model=list[EmailTemplateResponse])
async def list_email_templates(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    service = PlatformService(db)
    return [_email_template_to_response(item) for item in await service.list_email_templates()]


@router.post("/admin/email-templates", response_model=EmailTemplateResponse, status_code=201)
async def create_email_template(
    payload: EmailTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    service = PlatformService(db)
    template = await service.create_email_template(payload.model_dump())
    return _email_template_to_response(template)


@router.patch("/admin/email-templates/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: str,
    payload: EmailTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    service = PlatformService(db)
    template = await service.update_email_template(template_id, payload.model_dump(exclude_unset=True))
    return _email_template_to_response(template)
