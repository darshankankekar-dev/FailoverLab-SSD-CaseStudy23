from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from ...database import get_db_session
from ...schemas import AuditEventResponse, EventSeverity, EventSubsystem
from ...models import AuditEventEntity

router = APIRouter(tags=["Events"])


@router.get("/events", response_model=List[AuditEventResponse])
async def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500, description="Max events to return"),
    severity: Optional[EventSeverity] = Query(default=None, description="Filter by event severity"),
    subsystem: Optional[EventSubsystem] = Query(default=None, description="Filter by event subsystem"),
    session: AsyncSession = Depends(get_db_session),
) -> List[AuditEventResponse]:
    """Returns append-only audit trail records."""
    stmt = select(AuditEventEntity).order_by(desc(AuditEventEntity.created_at)).limit(limit)
    if severity:
        stmt = stmt.where(AuditEventEntity.severity == severity.value)
    if subsystem:
        stmt = stmt.where(AuditEventEntity.subsystem == subsystem.value)

    res = await session.execute(stmt)
    records = res.scalars().all()

    return [
        AuditEventResponse(
            id=r.id,
            simulated_time_seconds=r.simulated_time_seconds,
            wall_clock_timestamp=r.wall_clock_timestamp,
            severity=EventSeverity(r.severity),
            subsystem=EventSubsystem(r.subsystem),
            transition=r.transition,
            reason=r.reason,
            details=r.details,
            metadata_json=r.metadata_json,
        )
        for r in records
    ]

