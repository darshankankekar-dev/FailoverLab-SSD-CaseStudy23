from typing import List, Optional
import json
import hashlib
import logging
from datetime import datetime, timezone
from fastapi import HTTPException, status
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
            sequence_number=e.sequence_id,
            event_id=e.event_id,
            record_key=e.record_key,
            operation=e.operation,
            payload=e.payload,
            payload_hash=getattr(e, "payload_hash", None),
            version=e.version,
            fencing_epoch=e.fencing_epoch,
            source_fencing_epoch=e.fencing_epoch,
            source_region_id=getattr(e, "source_region_id", None),
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
    Guarantees:
    1. In-batch monotonic ordering.
    2. Idempotent deduplication via AppliedReplicationEventEntity.
    3. Rejection of out-of-order / regressive non-duplicate events.
    4. End-to-end payload hash verification.
    """
    applied_count = 0
    skipped_duplicates = 0
    highest_seq = 0

    now = utc_now()

    # 1. Enforce monotonic ordering within batch
    last_seq_in_batch = -1
    for ev in events:
        seq = ev.sequence_number if ev.sequence_number is not None else ev.source_sequence_id
        if last_seq_in_batch >= 0 and seq < last_seq_in_batch:
            logger.warning(f"[REPLICATION_OUT_OF_ORDER] Event sequence decreased within batch: {seq} < {last_seq_in_batch}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Out-of-order event batch: sequence #{seq} arrived after #{last_seq_in_batch}."
            )
        last_seq_in_batch = seq

    # 2. Get highest previously applied sequence for this source region
    res_max_applied = await session.execute(
        select(func.max(AppliedReplicationEventEntity.source_sequence_id)).where(
            AppliedReplicationEventEntity.source_region == source_region
        )
    )
    current_max_applied = res_max_applied.scalar() or 0

    for ev in events:
        seq = ev.sequence_number if ev.sequence_number is not None else ev.source_sequence_id

        # 3. Deduplication check
        res_chk = await session.execute(
            select(AppliedReplicationEventEntity).where(
                AppliedReplicationEventEntity.event_id == ev.event_id
            )
        )
        if res_chk.scalar_one_or_none():
            skipped_duplicates += 1
            highest_seq = max(highest_seq, seq)
            continue

        # 4. Out-of-order rejection for non-duplicate events
        if current_max_applied > 0 and seq < current_max_applied:
            logger.warning(
                f"[REPLICATION_OUT_OF_ORDER] Non-duplicate event #{seq} is lower than current checkpoint #{current_max_applied}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Out-of-order event rejected: sequence #{seq} is lower than current checkpoint #{current_max_applied}."
            )

        # 5. Integrity verification
        if ev.payload_hash:
            canonical_json = json.dumps(ev.payload, sort_keys=True)
            computed_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
            if computed_hash != ev.payload_hash:
                logger.warning(f"[PAYLOAD_CORRUPT] Event {ev.event_id} payload hash mismatch")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Payload corruption detected: expected {ev.payload_hash}, computed {computed_hash}."
                )

        # 6. Apply record mutation idempotently
        if ev.operation in ["INSERT", "UPDATE"]:
            res_rec = await session.execute(
                select(RecordEntity).where(RecordEntity.key == ev.record_key)
            )
            rec = res_rec.scalar_one_or_none()
            if rec:
                rec.value = ev.payload
                rec.version = ev.version
                rec.fencing_epoch = ev.source_fencing_epoch or ev.fencing_epoch
                rec.source_region = source_region
                rec.updated_at = now
            else:
                rec = RecordEntity(
                    key=ev.record_key,
                    value=ev.payload,
                    version=ev.version,
                    fencing_epoch=ev.source_fencing_epoch or ev.fencing_epoch,
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

        # 7. Record applied event for duplicate prevention
        applied_marker = AppliedReplicationEventEntity(
            event_id=ev.event_id,
            source_sequence_id=seq,
            record_key=ev.record_key,
            source_region=source_region,
            applied_at=now,
            fencing_epoch=ev.source_fencing_epoch or ev.fencing_epoch,
        )
        session.add(applied_marker)

        highest_seq = max(highest_seq, seq)
        current_max_applied = max(current_max_applied, seq)
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

