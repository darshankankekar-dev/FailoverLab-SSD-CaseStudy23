from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...database import get_db_session
from ...schemas import StateResponse, QuorumVoteSubmission
from ...models import QuorumVoterEntity
from ...services import evaluate_primary_health_probes, get_full_state

router = APIRouter(prefix="/telemetry", tags=["Internal Telemetry"])


@router.post("/tick", response_model=StateResponse)
async def trigger_clock_tick(
    delta_seconds: float = Query(default=2.0, ge=0.1, le=10.0),
    session: AsyncSession = Depends(get_db_session),
) -> StateResponse:
    """Advances simulated clock and triggers health check evaluation cycle."""
    await evaluate_primary_health_probes(session, simulated_time_delta=delta_seconds)
    return await get_full_state(session)


@router.post("/vote", response_model=StateResponse)
async def submit_voter_vote(
    payload: QuorumVoteSubmission,
    session: AsyncSession = Depends(get_db_session),
) -> StateResponse:
    """Explicitly sets a simulated observer's vote."""
    res_v = await session.execute(select(QuorumVoterEntity).where(QuorumVoterEntity.id == payload.voter_id))
    voter = res_v.scalar_one_or_none()
    if voter:
        voter.vote = payload.vote.value
        voter.latency_ms = payload.latency_ms
        await session.commit()
    return await get_full_state(session)

