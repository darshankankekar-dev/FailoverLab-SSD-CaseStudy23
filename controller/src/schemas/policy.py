from typing import Optional
from pydantic import BaseModel, Field


class PolicyBase(BaseModel):
    health_check_interval_sec: int = Field(default=2, ge=1, le=60, description="Interval in seconds between health checks")
    failure_threshold_consecutive: int = Field(default=3, ge=1, le=10, description="Consecutive failed probes to trigger quorum")
    quorum_size: int = Field(default=3, ge=1, le=7, description="Number of independent quorum observers")
    majority_required: int = Field(default=2, ge=1, le=7, description="Required votes to achieve consensus")
    acceptable_replication_lag_sec: float = Field(default=5.0, ge=0.1, le=60.0, description="Max acceptable replication lag before blocking failover")
    fencing_duration_sec: float = Field(default=2.0, ge=0.5, le=30.0, description="Lease duration / fencing delay")
    route_propagation_sec: float = Field(default=2.0, ge=0.5, le=30.0, description="Route propagation delay")
    route_verification_sec: float = Field(default=2.0, ge=0.5, le=30.0, description="Route verification probe delay")
    auto_failover_enabled: bool = Field(default=True, description="Whether automatic failover is enabled upon consensus")


class PolicyResponse(PolicyBase):
    pass


class PolicyUpdateRequest(BaseModel):
    health_check_interval_sec: Optional[int] = Field(None, ge=1, le=60)
    failure_threshold_consecutive: Optional[int] = Field(None, ge=1, le=10)
    quorum_size: Optional[int] = Field(None, ge=1, le=7)
    majority_required: Optional[int] = Field(None, ge=1, le=7)
    acceptable_replication_lag_sec: Optional[float] = Field(None, ge=0.1, le=60.0)
    fencing_duration_sec: Optional[float] = Field(None, ge=0.5, le=30.0)
    route_propagation_sec: Optional[float] = Field(None, ge=0.5, le=30.0)
    route_verification_sec: Optional[float] = Field(None, ge=0.5, le=30.0)
    auto_failover_enabled: Optional[bool] = None

