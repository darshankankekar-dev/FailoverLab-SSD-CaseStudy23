from typing import Optional
from pydantic import BaseModel, Field
from .common import RegionId, QuorumVote, HealthStatus, ReplicationStatus


class GatewayRouteUpdateRequest(BaseModel):
    target_region: RegionId
    dns_ttl_seconds: int = 2
    propagation_percent: int = 100


class GatewayRouteProbeResponse(BaseModel):
    success: bool
    active_target: RegionId
    latency_ms: float
    message: str


class RegionalFenceRequest(BaseModel):
    region_id: RegionId
    fencing_epoch: int
    revoke_write_lease: bool = True
    reason: str = "Controller fencing invocation"


class RegionalPromoteRequest(BaseModel):
    region_id: RegionId
    fencing_epoch: int
    grant_write_authority: bool = True
    reason: str = "Controller standby promotion invocation"


class RegionalDemoteRequest(BaseModel):
    region_id: RegionId
    fencing_epoch: int
    reason: str = "Controller demotion invocation"


class RegionalHealthReport(BaseModel):
    region_id: RegionId
    health: HealthStatus
    iops: int
    active_connections: int
    app_servers_healthy: int
    app_servers_total: int


class QuorumVoteSubmission(BaseModel):
    voter_id: str
    vote: QuorumVote
    latency_ms: int = 25
    reason: Optional[str] = None


class ChaosInjectionRequest(BaseModel):
    chaos_type: str = Field(..., description="outage | partition | lag | unready | route")
    active: bool = True
    parameter_value: Optional[float] = None
    reason: Optional[str] = None

