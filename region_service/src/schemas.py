from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RecordCreateRequest(BaseModel):
    key: str = Field(..., description="Unique record identifier / primary key")
    value: Dict[str, Any] = Field(..., description="JSON data payload")
    fencing_epoch: Optional[int] = Field(None, description="Optional caller-asserted fencing epoch")


class RecordUpdateRequest(BaseModel):
    value: Dict[str, Any] = Field(..., description="Updated JSON data payload")
    fencing_epoch: Optional[int] = Field(None, description="Optional caller-asserted fencing epoch")


class RecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Dict[str, Any]
    version: int
    fencing_epoch: int
    source_region: str
    created_at: datetime
    updated_at: datetime


class RegionalStatusResponse(BaseModel):
    region_id: str
    region_name: str
    name: Optional[str] = None
    cloud_zone: str
    role: str
    health: str
    accepts_writes: bool
    fencing_epoch: int
    is_fenced: bool
    total_records: int
    outbox_events_count: int
    last_outbox_sequence_id: int
    applied_sequence: int = 0
    replication_lag_seconds: float = 0.0


class OutboxEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence_id: int
    sequence_number: Optional[int] = None
    event_id: str
    record_key: str
    operation: str
    payload: Dict[str, Any]
    payload_hash: Optional[str] = None
    version: int
    fencing_epoch: int
    source_fencing_epoch: Optional[int] = None
    source_region_id: Optional[str] = None
    created_at: datetime
    replicated: bool


class OutboxBatchResponse(BaseModel):
    events: List[OutboxEventResponse]
    highest_sequence_id: int
    unreplicated_count: int
    oldest_unreplicated_created_at: Optional[str] = None


class ReplicationEventPayload(BaseModel):
    event_id: str
    source_sequence_id: int
    sequence_number: Optional[int] = None
    record_key: str
    operation: str
    payload: Dict[str, Any]
    payload_hash: Optional[str] = None
    version: int
    fencing_epoch: int
    source_fencing_epoch: Optional[int] = None
    source_region: Optional[str] = None
    source_region_id: Optional[str] = None
    created_at: Optional[str] = None


class ReplicationApplyRequest(BaseModel):
    source_region: str
    events: List[ReplicationEventPayload]


class ReplicationApplyResponse(BaseModel):
    success: bool
    applied_count: int
    skipped_duplicates: int
    highest_sequence_id: int
    message: str


class CheckpointResponse(BaseModel):
    region_id: str
    region_name: str
    role: str
    last_applied_sequence_id: int
    total_applied_events: int
    fencing_epoch: int


class FenceRequest(BaseModel):
    region_id: str
    fencing_epoch: int
    revoke_write_lease: bool = True
    reason: Optional[str] = "Controller fencing invocation"


class PromoteRequest(BaseModel):
    region_id: str
    fencing_epoch: int
    grant_write_authority: bool = True
    reason: Optional[str] = "Controller standby promotion invocation"


class DemoteRequest(BaseModel):
    region_id: str
    fencing_epoch: int
    reason: Optional[str] = "Controller demotion invocation"


class EpochStatusResponse(BaseModel):
    region_id: str
    role: str
    fencing_epoch: int
    accepts_writes: bool
    is_fenced: bool

