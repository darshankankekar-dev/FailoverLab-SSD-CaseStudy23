from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from .common import EventSeverity, EventSubsystem


class AuditEventCreate(BaseModel):
    severity: EventSeverity
    subsystem: EventSubsystem
    reason: str
    transition: Optional[str] = None
    details: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    simulated_time_seconds: float = Field(..., description="Monotonically increasing simulated clock time")
    wall_clock_timestamp: str = Field(..., description="ISO 8601 wall-clock timestamp")
    severity: EventSeverity
    subsystem: EventSubsystem
    transition: Optional[str] = None
    reason: str
    details: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


