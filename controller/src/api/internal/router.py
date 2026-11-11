from fastapi import APIRouter
from .chaos import router as chaos_router
from .telemetry import router as telemetry_router

internal_router = APIRouter(prefix="/internal")
internal_router.include_router(chaos_router)
internal_router.include_router(telemetry_router)

