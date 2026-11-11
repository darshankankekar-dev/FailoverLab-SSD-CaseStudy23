from typing import List, Optional
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from ..models import (
    RecordEntity,
    OutboxEventEntity,
    AppliedReplicationEventEntity,
    utc_now,
)
from ..schemas import (
    OutboxEventResponse,
    OutboxBatchResponse,
    ReplicationEventPayload,
    ReplicationApplyResponse,
)

logger = logging.getLogger("region.services.replication")


async def get_outbox_events(
    session: AsyncSession, since_sequence_id: int = 0, limit: int = 100
) -> OutboxBatchResponse:
    """Reads ordered outbox events starting after since_sequence_id."""
    stmt = (
        select(OutboxEventEntity)
        .where(OutboxEventEntity.sequence_id > since_sequence_id)
        .order_by(OutboxEventEntity.sequence_id.asc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    events = list(res.scalars().all())

    # Calculate highest sequence id
    res_max = await session.execute(select(func.max(OutboxEventEntity.sequence_id)))
    highest_seq = res_max.scalar() or 0

    # Count unreplicated
    res_unrep = await session.execute(
        select(func.count(OutboxEventEntity.sequence_id)).where(OutboxEventEntity.replicated == False)
    )
    unreplicated_count = res_unrep.scalar() or 0

    # Find oldest unreplicated created_at for lag calculation
    oldest_ts_res = await session.execute(
        select(func.min(OutboxEventEntity.created_at)).where(OutboxEventEntity.replicated == False)
    )
    oldest_ts = oldest_ts_res.scalar()

    event_responses = [
        OutboxEventResponse(
            sequence_id=e.sequence_id,
            event_id=e.event_id,
            record_key=e.record_key,
            operation=e.operation,
            payload=e.payload,
            version=e.version,
            fencing_epoch=e.fencing_epoch,
            created_at=e.created_at,
            replicated=e.replicated,
        )
        for e in events
    ]

    return OutboxBatchResponse(
        events=event_responses,
        highest_sequence_id=highest_seq,
        unreplicated_count=unreplicated_count,
        oldest_unreplicated_created_at=oldest_ts.isoformat() if oldest_ts else None,
    )


async def mark_events_replicated(session: AsyncSession, event_ids: List[str]) -> int:
    """Marks outbox events as confirmed delivered."""
    if not event_ids:
        return 0
    stmt = (
        select(OutboxEventEntity)
        .where(OutboxEventEntity.event_id.in_(event_ids))
    )
    res = await session.execute(stmt)
    records = res.scalars().all()
    count = 0
    for r in records:
        r.replicated = True
        count += 1
    await session.commit()
    return count


async def apply_replication_batch(
    session: AsyncSession, source_region: str, events: List[ReplicationEventPayload]
) -> ReplicationApplyResponse:
    """
    Applies incoming replication events into local tables.
    Guarantees strict idempotency and deduplication via AppliedReplicationEventEntity.
    """
    applied_count = 0
    skipped_duplicates = 0
    highest_seq = 0

    now = utc_now()

    for ev in events:
        # 1. Deduplication check
        res_chk = await session.execute(
            select(AppliedReplicationEventEntity).where(
                AppliedReplicationEventEntity.event_id == ev.event_id
            )
        )
        if res_chk.scalar_one_or_none():
            skipped_duplicates += 1
            highest_seq = max(highest_seq, ev.source_sequence_id)
            continue

        # 2. Apply record mutation idempotently
        if ev.operation in ["INSERT", "UPDATE"]:
            res_rec = await session.execute(
                select(RecordEntity).where(RecordEntity.key == ev.record_key)
            )
            rec = res_rec.scalar_one_or_none()
            if rec:
                rec.value = ev.payload
                rec.version = ev.version
                rec.fencing_epoch = ev.fencing_epoch
                rec.source_region = source_region
                rec.updated_at = now
            else:
                rec = RecordEntity(
                    key=ev.record_key,
                    value=ev.payload,
                    version=ev.version,
                    fencing_epoch=ev.fencing_epoch,
                    source_region=source_region,
                    created_at=now,
                    updated_at=now,
                )
                session.add(rec)

        elif ev.operation == "DELETE":
            res_rec = await session.execute(
                select(RecordEntity).where(RecordEntity.key == ev.record_key)
            )
            rec = res_rec.scalar_one_or_none()
            if rec:
                await session.delete(rec)

        # 3. Record applied event for duplicate prevention
        applied_marker = AppliedReplicationEventEntity(
            event_id=ev.event_id,
            source_sequence_id=ev.source_sequence_id,
            record_key=ev.record_key,
            source_region=source_region,
            applied_at=now,
            fencing_epoch=ev.fencing_epoch,
        )
        session.add(applied_marker)

        highest_seq = max(highest_seq, ev.source_sequence_id)
        applied_count += 1

    await session.commit()
    logger.info(
        f"[REPLICATION_APPLIED] from={source_region} applied={applied_count} skipped_duplicates={skipped_duplicates} highest_seq={highest_seq}"
    )

    return ReplicationApplyResponse(
        success=True,
        applied_count=applied_count,
        skipped_duplicates=skipped_duplicates,
        highest_sequence_id=highest_seq,
        message=f"Replication batch processed: {applied_count} applied, {skipped_duplicates} duplicates skipped.",
    )

