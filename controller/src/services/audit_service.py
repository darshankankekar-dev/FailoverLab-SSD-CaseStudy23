import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import AuditEventEntity


async def log_audit_event(
    session: AsyncSession,
    severity: str,
    subsystem: str,
    reason: str,
    simulated_time_seconds: float = 0.0,
    transition: Optional[str] = None,
    details: Optional[str] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
) -> AuditEventEntity:
    """Creates and persists an immutable append-only audit record."""
    event_id = f"ev-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6]}"
    record = AuditEventEntity(
        id=event_id,
        simulated_time_seconds=simulated_time_seconds,
        wall_clock_timestamp=datetime.now(timezone.utc).isoformat(),
        severity=severity,
        subsystem=subsystem,
        transition=transition,
        reason=reason,
        details=details,
        metadata_json=metadata_json,
    )
    session.add(record)
    return record

