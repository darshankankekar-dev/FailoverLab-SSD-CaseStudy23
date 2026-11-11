from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from ..database import get_db_session
from ..schemas import HealthLiveResponse, HealthReadyResponse, ControllerState
from ..models import ControllerStateEntity

router = APIRouter(tags=["Health"])


@router.get("/health/live", response_model=HealthLiveResponse)
async def health_live() -> HealthLiveResponse:
    """Liveness probe: verifies process is responding."""
    return HealthLiveResponse()


@router.get("/health/ready", response_model=HealthReadyResponse)
async def health_ready(session: AsyncSession = Depends(get_db_session)) -> HealthReadyResponse:
    """Readiness probe: verifies database connectivity and state loading."""
    try:
        await session.execute(text("SELECT 1"))
        res = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
        c_state = res.scalar_one_or_none()

        state_val = ControllerState(c_state.current_state) if c_state else ControllerState.HEALTHY
        epoch_val = c_state.fencing_epoch if c_state else 101

        return HealthReadyResponse(
            status="ready",
            database_connected=True,
            controller_state=state_val,
            fencing_epoch=epoch_val,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connectivity check failed: {str(e)}")

