from typing import List
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db_session
from ..security import verify_internal_access
from sqlalchemy import select, func
from ..models import RegionalMetadataEntity, AppliedReplicationEventEntity
from ..schemas import (
    OutboxBatchResponse,
    ReplicationApplyRequest,
    ReplicationApplyResponse,
    CheckpointResponse,
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


@router.get("/checkpoint", response_model=CheckpointResponse)
async def get_replication_checkpoint(
    session: AsyncSession = Depends(get_db_session),
) -> CheckpointResponse:
    """
    Returns the target region's current applied replication checkpoint.
    Allows the replication worker to safely resume per-destination replication without desync.
    """
    res_meta = await session.execute(select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1))
    meta = res_meta.scalar_one_or_none()
    res_app_seq = await session.execute(select(func.max(AppliedReplicationEventEntity.source_sequence_id)))
    applied_seq = res_app_seq.scalar() or 0
    res_count = await session.execute(select(func.count(AppliedReplicationEventEntity.event_id)))
    total_applied = res_count.scalar() or 0
    return CheckpointResponse(
        region_id=meta.region_id if meta else "unknown",
        region_name=meta.region_name if meta else "unknown",
        role=meta.role if meta else "STANDBY",
        last_applied_sequence_id=applied_seq,
        total_applied_events=total_applied,
        fencing_epoch=meta.fencing_epoch if meta else 101,
    )

