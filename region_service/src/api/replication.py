from typing import List
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db_session
from ..security import verify_internal_access
from ..schemas import (
    OutboxBatchResponse,
    ReplicationApplyRequest,
    ReplicationApplyResponse,
)
from ..services.replication_service import (
    get_outbox_events,
    apply_replication_batch,
    mark_events_replicated,
)

router = APIRouter(
    prefix="/internal/replication",
    tags=["Internal Replication"],
    dependencies=[Depends(verify_internal_access)],
)


@router.get("/outbox", response_model=OutboxBatchResponse)
async def read_outbox_events(
    since_sequence_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
) -> OutboxBatchResponse:
    """
    Called by the replication worker to fetch ordered, unreplicated outbox events from the active region.
    """
    return await get_outbox_events(session, since_sequence_id=since_sequence_id, limit=limit)


@router.post("/apply", response_model=ReplicationApplyResponse)
async def apply_replication_events(
    payload: ReplicationApplyRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ReplicationApplyResponse:
    """
    Called by the replication worker to deliver a batch of replication events to the standby region.
    Guarantees idempotency and deduplication using stable event IDs.
    """
    return await apply_replication_batch(
        session,
        source_region=payload.source_region,
        events=payload.events,
    )


@router.post("/ack")
async def acknowledge_replicated_events(
    event_ids: List[str] = Body(...),
    session: AsyncSession = Depends(get_db_session),
):
    """Marks outbox events as confirmed delivered."""
    count = await mark_events_replicated(session, event_ids)
    return {"acknowledged_count": count}

