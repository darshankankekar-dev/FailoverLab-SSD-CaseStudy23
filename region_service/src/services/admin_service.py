import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..models import (
    RegionalMetadataEntity,
    RecordEntity,
    OutboxEventEntity,
    utc_now,
)
from ..schemas import RegionalStatusResponse, EpochStatusResponse

logger = logging.getLogger("region.services.admin")


async def fence_region(
    session: AsyncSession, epoch: int, revoke_write_lease: bool = True
) -> EpochStatusResponse:
    """Fences writer and revokes write authorization."""
    res = await session.execute(select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1))
    meta = res.scalar_one()

    if revoke_write_lease:
        meta.accepts_writes = False
    meta.is_fenced = True
    meta.updated_at = utc_now()
    await session.commit()
    logger.info(f"Region {meta.region_name} fenced. AcceptsWrites={meta.accepts_writes}, IsFenced={meta.is_fenced}")

    return EpochStatusResponse(
        region_id=meta.region_id,
        role=meta.role,
        fencing_epoch=meta.fencing_epoch,
        accepts_writes=meta.accepts_writes,
        is_fenced=meta.is_fenced,
    )


async def promote_region(
    session: AsyncSession, epoch: int, grant_write_authority: bool = True
) -> EpochStatusResponse:
    """Promotes region to ACTIVE writer with new fencing epoch."""
    res = await session.execute(select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1))
    meta = res.scalar_one()

    meta.role = "ACTIVE"
    meta.accepts_writes = grant_write_authority
    meta.is_fenced = False
    meta.fencing_epoch = epoch
    meta.updated_at = utc_now()
    await session.commit()
    logger.info(f"Region {meta.region_name} promoted to ACTIVE with Epoch #{epoch}.")

    return EpochStatusResponse(
        region_id=meta.region_id,
        role=meta.role,
        fencing_epoch=meta.fencing_epoch,
        accepts_writes=meta.accepts_writes,
        is_fenced=meta.is_fenced,
    )


async def demote_region(session: AsyncSession, epoch: int) -> EpochStatusResponse:
    """Demotes region back to STANDBY mode."""
    res = await session.execute(select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1))
    meta = res.scalar_one()

    meta.role = "STANDBY"
    meta.accepts_writes = False
    meta.is_fenced = False
    meta.fencing_epoch = epoch
    meta.updated_at = utc_now()
    await session.commit()
    logger.info(f"Region {meta.region_name} demoted to STANDBY with Epoch #{epoch}.")

    return EpochStatusResponse(
        region_id=meta.region_id,
        role=meta.role,
        fencing_epoch=meta.fencing_epoch,
        accepts_writes=meta.accepts_writes,
        is_fenced=meta.is_fenced,
    )


async def get_regional_status(session: AsyncSession) -> RegionalStatusResponse:
    """Returns regional status and entity counts."""
    res = await session.execute(select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1))
    meta = res.scalar_one()

    # Count records
    res_rec = await session.execute(select(func.count(RecordEntity.key)))
    total_records = res_rec.scalar() or 0

    # Count outbox events and max sequence_id
    res_out = await session.execute(select(func.count(OutboxEventEntity.sequence_id)))
    outbox_count = res_out.scalar() or 0

    res_max_seq = await session.execute(select(func.max(OutboxEventEntity.sequence_id)))
    max_seq = res_max_seq.scalar() or 0

    return RegionalStatusResponse(
        region_id=meta.region_id,
        region_name=meta.region_name,
        cloud_zone=meta.cloud_zone,
        role=meta.role,
        health=meta.health,
        accepts_writes=meta.accepts_writes,
        fencing_epoch=meta.fencing_epoch,
        is_fenced=meta.is_fenced,
        total_records=total_records,
        outbox_events_count=outbox_count,
        last_outbox_sequence_id=max_seq,
    )

