from typing import Optional
from pydantic import BaseModel, Field
from .common import RegionId, RegionRole, HealthStatus


class RegionBase(BaseModel):
    id: RegionId
    name: str = Field(..., description="Region descriptive name (e.g. Mumbai, Singapore)")
    cloud_zone: str = Field(..., description="Cloud zone identifier (e.g. ap-south-1, ap-southeast-1)")
    role: RegionRole = Field(..., description="ACTIVE or STANDBY")
    health: HealthStatus = Field(default=HealthStatus.HEALTHY)
    status: str = Field(default="healthy")
    accepts_writes: bool = Field(default=False, description="Whether this region is authorized to accept writes")
    ingress_traffic_percent: int = Field(default=0, ge=0, le=100)
    ingress_rps: int = Field(default=0, ge=0)
    app_servers_healthy: int = Field(default=12, ge=0)
    app_servers_total: int = Field(default=12, ge=0)
    active_connections: int = Field(default=0, ge=0)
    iops: int = Field(default=0, ge=0)
    fencing_epoch: int = Field(default=101, ge=1)
    is_fenced: bool = Field(default=False)


class RegionResponse(RegionBase):
    pass


class RegionUpdateRequest(BaseModel):
    health: Optional[HealthStatus] = None
    role: Optional[RegionRole] = None
    accepts_writes: Optional[bool] = None
    is_fenced: Optional[bool] = None
    ingress_traffic_percent: Optional[int] = Field(None, ge=0, le=100)
    ingress_rps: Optional[int] = Field(None, ge=0)
    fencing_epoch: Optional[int] = Field(None, ge=1)

