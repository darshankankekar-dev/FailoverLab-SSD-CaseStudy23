from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .common import (
    ControllerState,
    RegionId,
    ReplicationStatus,
    RouteVerificationStatus,
    QuorumVote,
)
from .region import RegionResponse
from .policy import PolicyResponse


class QuorumVoterModel(BaseModel):
    id: str
    name: str
    location: str
    vote: QuorumVote
    latency_ms: int


class ReplicationStateModel(BaseModel):
    status: ReplicationStatus = ReplicationStatus.STREAMING
    lag_seconds: float = 0.8
    lag_ms: int = 800
    bandwidth_mbps: int = 450
    packet_loss_percent: float = 0.0
    pending_bytes: int = 12400
    bytes_transferred: int = 45000000
    mode: str = "ASYNCHRONOUS_RECORD"


class RouteStateModel(BaseModel):
    active_target: RegionId = RegionId.REGION_A
    dns_ttl_seconds: int = 2
    propagation_percent: int = 100
    verification_status: RouteVerificationStatus = RouteVerificationStatus.VERIFIED


class TelemetryMetricsModel(BaseModel):
    uptime_seconds: float = 0.0
    total_client_rps: int = 2450
    overall_success_rate: float = 99.98
    client_error_rate: float = 0.02
    p95_latency_ms: int = 18
    total_failovers_count: int = 0
    last_failover_duration_ms: Optional[int] = None
    estimated_rpo_loss_tx: int = 0


class StateResponse(BaseModel):
    controller_state: ControllerState
    active_region: RegionId
    fencing_epoch: int
    simulated_time_seconds: float
    wall_clock_start_time: str
    consecutive_failures: int
    last_health_check_sim_time: float
    blocked_reason: Optional[str] = None
    blocked_at_state: Optional[ControllerState] = None
    is_sequence_in_progress: bool = False
    route_retry_count: int = 0
    persisted_intent: Optional[str] = None
    is_paused_interrupted: bool = False

    region_a: RegionResponse
    region_b: RegionResponse
    policy: PolicyResponse
    replication: ReplicationStateModel
    route: RouteStateModel
    voters: List[QuorumVoterModel]
    telemetry: TelemetryMetricsModel


class TruthfulFailoverMetricsModel(BaseModel):
    failover_attempts_total: int = 0
    failover_successes_total: int = 0
    failover_blocked_total: int = 0
    failover_blocked_by_gate: Dict[str, int] = Field(default_factory=dict)
    route_update_attempts_total: int = 0
    route_update_successes_total: int = 0
    route_update_errors_total: int = 0
    healthy_regions_count: int = 2
    last_lab_recovery_seconds: Optional[float] = None
    is_simulated_lab_metric: bool = True
    metric_caveat: str = (
        "Measured wall-clock duration in simulated lab test environment. "
        "Does not represent production enterprise RTO."
    )


class MetricsResponse(BaseModel):
    controller_state: ControllerState
    active_region: RegionId
    fencing_epoch: int
    consecutive_failures: int
    replication_lag_seconds: float
    replication_status: ReplicationStatus
    route_target: RegionId
    route_verification: RouteVerificationStatus
    telemetry: TelemetryMetricsModel
    truthful_metrics: TruthfulFailoverMetricsModel = Field(default_factory=TruthfulFailoverMetricsModel)


class HealthLiveResponse(BaseModel):
    status: str = "alive"
    service: str = "failoverlab-controller"
    version: str = "0.1.0"


class HealthReadyResponse(BaseModel):
    status: str = "ready"
    service: str = "failoverlab-controller"
    database_connected: bool = True
    controller_state: ControllerState
    fencing_epoch: int

