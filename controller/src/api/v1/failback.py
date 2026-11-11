from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import get_db_session
from ...schemas import FailbackRequest, TransitionResponse, TransitionStatus
from ...services import execute_failback_workflow

router = APIRouter(tags=["Failback"])


@router.post(
    "/failback",
    response_model=TransitionResponse,
    responses={
        200: {"description": "Guarded failback successfully executed"},
        409: {"description": "Failback transition blocked by a safety gate check"},
    },
)
async def trigger_failback(
    payload: FailbackRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Executes deliberate guarded failback to Region A after data reconciliation.
    Prohibits automatic switchback. Requires operator authorization and healthy replica.
    """
    result = await execute_failback_workflow(
        session=session,
        operator_id=payload.operator_id,
        confirmation=payload.confirmation,
        reason=payload.reason or "Guarded manual failback authorized via API",
    )

    if result.status == TransitionStatus.BLOCKED:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=result.model_dump(),
        )

    return result

