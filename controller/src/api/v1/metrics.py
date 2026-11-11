from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import get_db_session
from ...schemas import MetricsResponse
from ...services import get_metrics

router = APIRouter(tags=["Metrics"])


@router.get("/metrics", response_model=MetricsResponse)
async def get_system_metrics(session: AsyncSession = Depends(get_db_session)) -> MetricsResponse:
    """Returns focused operational and telemetry metrics."""
    return await get_metrics(session)

