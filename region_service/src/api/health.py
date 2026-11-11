from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from ..database import get_db_session
from ..config import settings
from ..models import RegionalMetadataEntity

router = APIRouter(tags=["Health"])


@router.get("/health")
@router.get("/health/live")
async def health_live():
    """Liveness probe confirming regional process is running."""
    return {
        "status": "alive",
        "region_id": settings.region_id,
        "region_name": settings.region_name,
        "service": "failoverlab-region-service",
    }


@router.get("/health/ready")
async def health_ready(session: AsyncSession = Depends(get_db_session)):
    """Readiness probe verifying regional database connectivity and metadata."""
    try:
        await session.execute(text("SELECT 1"))
        res = await session.execute(
            select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1)
        )
        meta = res.scalar_one_or_none()
        return {
            "status": "ready",
            "region_id": meta.region_id if meta else settings.region_id,
            "region_name": meta.region_name if meta else settings.region_name,
            "role": meta.role if meta else settings.initial_role,
            "health": meta.health if meta else "HEALTHY",
            "accepts_writes": meta.accepts_writes if meta else False,
            "fencing_epoch": meta.fencing_epoch if meta else settings.initial_epoch,
            "is_fenced": meta.is_fenced if meta else False,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Regional database readiness check failed: {str(e)}",
        )

