from fastapi import APIRouter, WebSocket
from fastapi.responses import RedirectResponse

from backend.api.v1.health import health_router
from backend.api.v1.media import router as media_router
from backend.modules.analytics.router import router as analytics_router
from backend.modules.approvals.router import router as approvals_router
from backend.modules.audit.router import router as audit_router
from backend.modules.chess_video.router import router as chess_video_router
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
from backend.modules.workflows.router import router as workflows_router
from backend.modules.workflows.automation_router import router as workflow_automations_router
from backend.api.websocket import websocket_manager

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(source_router, prefix="/sources", tags=["sources"])
api_router.include_router(story_router, prefix="/stories", tags=["stories"])
# T5.1: removed duplicate mount at /trends (caused /trends/trends/dashboard aliases).
# Legacy callers get a 308 to /stories/* via legacy_trends_alias below.
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
api_router.include_router(chess_video_router, prefix="/chess-videos", tags=["chess-videos"])
api_router.include_router(workflows_router, prefix="/workflows", tags=["workflows"])
api_router.include_router(
    workflow_automations_router, prefix="/workflows", tags=["workflows"]
)
api_router.include_router(media_router, prefix="/media", tags=["media"])
api_router.include_router(health_router)


@api_router.api_route(
    "/trends",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
    name="legacy_trends_root",
)
@api_router.api_route(
    "/trends/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
    name="legacy_trends_path",
)
async def legacy_trends_alias(path: str = "") -> RedirectResponse:
    """Deprecation shim: /api/v1/trends/* → /api/v1/stories/* (T5.1)."""
    target = f"/api/v1/stories/{path}" if path else "/api/v1/stories/clusters"
    return RedirectResponse(url=target, status_code=308)


@api_router.websocket("/ws/job/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str) -> None:
    """WebSocket endpoint for real-time job status updates"""
    await websocket_manager.connect(websocket, job_id)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except Exception:
        websocket_manager.disconnect(websocket, job_id)
