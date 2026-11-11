import uuid
import logging
from typing import Dict, Any, Optional, List
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from ..models import (
    RecordEntity,
    OutboxEventEntity,
    RegionalMetadataEntity,
    utc_now,
)

logger = logging.getLogger("region.services.records")


async def validate_writer_authority(
    session: AsyncSession, caller_epoch: Optional[int] = None
) -> RegionalMetadataEntity:
    """
    Enforces Writer Safety Rules:
    1. Standby regions strictly reject write requests (HTTP 403).
    2. Fenced regions strictly reject write requests (HTTP 403).
    3. Old/stale fencing epochs are rejected (HTTP 409).
    """
    res = await session.execute(
        select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1)
    )
    meta = res.scalar_one_or_none()
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Regional metadata not initialized.",
        )

    # 1. Role must be ACTIVE
    if meta.role != "ACTIVE":
        logger.warning(f"[WRITE_REJECTED] Region '{meta.region_name}' is in STANDBY role. Writes strictly prohibited. epoch={meta.fencing_epoch}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "STANDBY_READ_ONLY",
                "message": f"Region '{meta.region_name}' is in STANDBY role. Writes are strictly prohibited.",
                "region_id": meta.region_id,
                "role": meta.role,
                "fencing_epoch": meta.fencing_epoch,
            },
        )

    # 2. Must actively accept writes and not be fenced
    if not meta.accepts_writes or meta.is_fenced:
        logger.warning(f"[WRITE_REJECTED] Region '{meta.region_name}' write authority is revoked or fenced (accepts_writes={meta.accepts_writes}, is_fenced={meta.is_fenced}). epoch={meta.fencing_epoch}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "FENCED_WRITE_PROHIBITED",
                "message": f"Write authority on region '{meta.region_name}' is revoked or hard-fenced.",
                "region_id": meta.region_id,
                "is_fenced": meta.is_fenced,
                "accepts_writes": meta.accepts_writes,
            },
        )

    # 3. Epoch verification (stale tokens rejected)
    if caller_epoch is not None and caller_epoch < meta.fencing_epoch:
        logger.warning(f"[WRITE_REJECTED] Caller epoch #{caller_epoch} is stale compared to authoritative epoch #{meta.fencing_epoch}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "STALE_FENCING_EPOCH",
                "message": f"Caller fencing epoch #{caller_epoch} is stale. Authoritative region epoch is #{meta.fencing_epoch}.",
                "caller_epoch": caller_epoch,
                "authoritative_epoch": meta.fencing_epoch,
            },
        )

    return meta


async def write_record(
    session: AsyncSession,
    key: str,
    value: Dict[str, Any],
    caller_epoch: Optional[int] = None,
) -> RecordEntity:
    """
    Atomically writes record and emits an ordered, uniquely identified outbox replication event.
    """
    meta = await validate_writer_authority(session, caller_epoch)

    res = await session.execute(select(RecordEntity).where(RecordEntity.key == key))
    existing = res.scalar_one_or_none()

    now = utc_now()
    if existing:
        existing.value = value
        existing.version += 1
        existing.fencing_epoch = meta.fencing_epoch
        existing.updated_at = now
        operation = "UPDATE"
        record = existing
    else:
        record = RecordEntity(
            key=key,
            value=value,
            version=1,
            fencing_epoch=meta.fencing_epoch,
            source_region=meta.region_id,
            created_at=now,
            updated_at=now,
        )
        session.add(record)
        operation = "INSERT"

    # Transactional outbox event creation
    event_id = f"evt-{meta.region_id}-{int(now.timestamp())}-{uuid.uuid4().hex[:8]}"
    outbox_event = OutboxEventEntity(
        event_id=event_id,
        record_key=key,
        operation=operation,
        payload=value,
        version=record.version,
        fencing_epoch=meta.fencing_epoch,
        created_at=now,
        replicated=False,
    )
    session.add(outbox_event)

    await session.commit()
    await session.refresh(record)
    logger.info(
        f"[RECORD_COMMITTED] region={meta.region_id} key='{key}' operation={operation} version={record.version} epoch=#{meta.fencing_epoch} outbox_evt={event_id}"
    )
    return record


async def delete_record(
    session: AsyncSession,
    key: str,
    caller_epoch: Optional[int] = None,
) -> bool:
    """Atomically deletes record and emits a DELETE outbox replication event."""
    meta = await validate_writer_authority(session, caller_epoch)

    res = await session.execute(select(RecordEntity).where(RecordEntity.key == key))
    existing = res.scalar_one_or_none()
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Record with key '{key}' not found.",
        )

    now = utc_now()
    event_id = f"evt-{meta.region_id}-{int(now.timestamp())}-{uuid.uuid4().hex[:8]}"
    outbox_event = OutboxEventEntity(
        event_id=event_id,
        record_key=key,
        operation="DELETE",
        payload={},
        version=existing.version + 1,
        fencing_epoch=meta.fencing_epoch,
        created_at=now,
        replicated=False,
    )
    session.add(outbox_event)
    await session.delete(existing)
    await session.commit()
    return True


async def get_record(session: AsyncSession, key: str) -> Optional[RecordEntity]:
    """Reads a record by key (permitted on active and standby)."""
    res = await session.execute(select(RecordEntity).where(RecordEntity.key == key))
    return res.scalar_one_or_none()


async def list_records(
    session: AsyncSession, limit: int = 100, offset: int = 0
) -> List[RecordEntity]:
    """Lists records (permitted on active and standby)."""
    res = await session.execute(
        select(RecordEntity).order_by(desc(RecordEntity.updated_at)).limit(limit).offset(offset)
    )
    return list(res.scalars().all())

