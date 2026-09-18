from fastapi import APIRouter

from backend.api.routes.analytics import router as analytics_router
from backend.api.routes.applications import router as applications_router
from backend.api.routes.health import router as health_router
from backend.api.routes.jobs import router as jobs_router
from backend.api.routes.profile import router as profile_router
from backend.api.routes.resumes import router as resumes_router

api_router = APIRouter()
api_router.include_router(analytics_router, tags=["analytics"])
api_router.include_router(health_router, tags=["health"])
api_router.include_router(profile_router, tags=["profile"])
api_router.include_router(resumes_router, tags=["resumes"])
api_router.include_router(jobs_router, tags=["jobs"])
api_router.include_router(applications_router, tags=["applications"])
