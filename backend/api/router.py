from fastapi import APIRouter

from backend.modules.analytics.router import router as analytics_router
from backend.modules.approvals.router import router as approvals_router
from backend.modules.audit.router import router as audit_router
from backend.modules.trending_repos.router import router as trending_repos_router
from backend.modules.content_generation.router import router as content_generation_router
from backend.modules.content_strategy.router import router as content_strategy_router
from backend.modules.editorial_briefs.router import router as editorial_briefs_router
from backend.modules.identity_access.router import router as auth_router
from backend.modules.publishing.router import router as publishing_router
from backend.modules.settings.router import router as settings_router
from backend.modules.source_ingestion.router import router as source_router
from backend.modules.story_intelligence.router import router as story_router
from backend.modules.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(source_router, prefix="/sources", tags=["sources"])
api_router.include_router(story_router, prefix="/stories", tags=["stories"])
api_router.include_router(story_router, prefix="/trends", tags=["trends"])
# Note: both content routers share /content prefix — routes are on distinct sub-paths
api_router.include_router(content_strategy_router, prefix="/content", tags=["content-strategy"])
api_router.include_router(content_generation_router, prefix="/content", tags=["content-generation"])
api_router.include_router(editorial_briefs_router, prefix="/briefs", tags=["editorial-briefs"])
api_router.include_router(approvals_router, prefix="/approvals", tags=["approvals"])
api_router.include_router(publishing_router, prefix="/publishing", tags=["publishing"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(audit_router, prefix="/audit", tags=["audit"])
api_router.include_router(trending_repos_router, prefix="/trending-repos", tags=["trending-repos"])
