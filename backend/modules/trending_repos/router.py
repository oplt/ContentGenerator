from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, get_db
from backend.modules.identity_access.models import TenantUser
from backend.modules.trending_repos.schemas import (
    GenerateTwitterPostResponse,
    PostToTwitterRequest,
    TrendingRepoResponse,
    TrendingReposListResponse,
)
from backend.modules.trending_repos.service import TrendingReposService, _serialize_trending_repo_response

router = APIRouter()

Period = Literal["daily", "weekly", "monthly"]


@router.get("", response_model=TrendingReposListResponse)
async def list_trending_repos(
    period: Period = Query("daily", description="Time window: daily | weekly | monthly"),
    db: AsyncSession = Depends(get_db),
    membership: TenantUser = Depends(get_current_membership),
) -> TrendingReposListResponse:
    """Return the latest trending repos for the requested period."""
    svc = TrendingReposService(db)
    return await svc.get_trending(membership.tenant_id, period)


@router.post("/refresh", response_model=TrendingReposListResponse)
async def refresh_trending_repos(
    period: Period = Query("daily"),
    db: AsyncSession = Depends(get_db),
    membership: TenantUser = Depends(get_current_membership),
) -> TrendingReposListResponse:
    """Force-refresh the trending snapshot from GitHub (rate-limited by GitHub API)."""
    svc = TrendingReposService(db)
    try:
        await svc.refresh_snapshot(membership.tenant_id, period)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}") from exc
    return await svc.get_trending(membership.tenant_id, period)


@router.post("/send-digest", status_code=204)
async def send_telegram_digest(
    db: AsyncSession = Depends(get_db),
    membership: TenantUser = Depends(get_current_membership),
) -> None:
    """Send today's trending digest with product ideas to the tenant's Telegram."""
    svc = TrendingReposService(db)
    try:
        await svc.send_daily_digest_to_telegram(membership.tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{repo_id}/generate-twitter-post", response_model=GenerateTwitterPostResponse)
async def generate_twitter_post(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    membership: TenantUser = Depends(get_current_membership),
) -> GenerateTwitterPostResponse:
    """Generate X (Twitter) post variants for a trending repo and send them to Telegram."""
    svc = TrendingReposService(db)
    try:
        post_text = await svc.generate_twitter_post(membership.tenant_id, repo_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return GenerateTwitterPostResponse(repo_id=repo_id, post_text=post_text)


@router.post("/{repo_id}/post-to-twitter")
async def post_to_twitter(
    repo_id: uuid.UUID,
    body: PostToTwitterRequest,
    db: AsyncSession = Depends(get_db),
    membership: TenantUser = Depends(get_current_membership),
) -> dict:
    """Post the accepted text variant directly to the tenant's X (Twitter) account."""
    svc = TrendingReposService(db)
    try:
        result = await svc.post_to_twitter(membership.tenant_id, body.post_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Twitter API error: {exc}") from exc
    return result


@router.post("/{repo_id}/generate-ideas", response_model=TrendingRepoResponse)
async def generate_product_ideas(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    membership: TenantUser = Depends(get_current_membership),
) -> TrendingRepoResponse:
    """Trigger LLM product-idea generation for a specific repo."""
    svc = TrendingReposService(db)
    try:
        record = await svc.generate_product_ideas(membership.tenant_id, repo_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _serialize_trending_repo_response(record)
