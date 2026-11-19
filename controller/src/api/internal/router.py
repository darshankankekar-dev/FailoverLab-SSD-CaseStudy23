from fastapi import APIRouter, Depends
from ...security import verify_admin_access
from .chaos import router as chaos_router
from .telemetry import router as telemetry_router

internal_router = APIRouter(prefix="/internal")
internal_router.include_router(chaos_router, dependencies=[Depends(verify_admin_access)])
internal_router.include_router(telemetry_router)

