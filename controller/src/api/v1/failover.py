from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import get_db_session
from ...schemas import FailoverRequest, TransitionResponse, TransitionStatus
from ...services import execute_failover_workflow

router = APIRouter(tags=["Failover"])


@router.post(
    "/failover",
    response_model=TransitionResponse,
    responses={
        200: {"description": "Failover successfully executed across all 10 decision steps"},
        409: {"description": "Failover transition blocked by a safety gate check"},
    },
)
async def trigger_failover(
    payload: FailoverRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Triggers the 10-step multi-region active-passive failover decision workflow.
    Validates all safety gates and persists transition intent before applying side effects.
    """
    result = await execute_failover_workflow(
        session=session,
        force=payload.force,
        target_region=payload.target_region.value if payload.target_region else "region-b",
        reason=payload.reason or "Manual failover drill requested via API",
    )

    if result.status == TransitionStatus.BLOCKED:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=result.model_dump(),
        )

    return result

