from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_validator


class TrafficBatchSubmission(BaseModel):
    """
    Schema for telemetry batch submissions from Gateway to Controller.
    Validated at POST /internal/telemetry/traffic-batch.
    """
    schema_version: str = Field(default="1.0", description="Telemetry metric schema version")
    gateway_instance_id: str = Field(..., min_length=1, max_length=64, description="Gateway instance ID")
    batch_id: str = Field(..., min_length=1, max_length=64, description="Unique batch UUID for idempotency")
    timestamp: datetime = Field(..., description="Timestamp of the batch observation")
    reporting_interval_seconds: float = Field(..., gt=0.0, le=60.0, description="Reporting interval in seconds")

    # Customer-facing cumulative payload bytes and counts
    client_ingress_bytes: int = Field(ge=0, description="Cumulative request payload bytes from customers")
    client_egress_bytes: int = Field(ge=0, description="Cumulative response payload bytes to customers")
    interval_client_ingress_bytes: int = Field(default=0, ge=0, description="Interval request payload bytes")
    interval_client_egress_bytes: int = Field(default=0, ge=0, description="Interval response payload bytes")

    # Upstream regional cumulative and interval payload bytes
    upstream_ingress_bytes: int = Field(default=0, ge=0, description="Cumulative response payload bytes from regions")
    upstream_egress_bytes: int = Field(default=0, ge=0, description="Cumulative request payload bytes to regions")
    interval_upstream_ingress_bytes: int = Field(default=0, ge=0, description="Interval response bytes from regions")
    interval_upstream_egress_bytes: int = Field(default=0, ge=0, description="Interval request bytes to regions")

    # Rates
    client_ingress_rate: float = Field(default=0.0, ge=0.0, description="Client ingress bytes per second")
    client_egress_rate: float = Field(default=0.0, ge=0.0, description="Client egress bytes per second")
    upstream_ingress_rate: float = Field(default=0.0, ge=0.0, description="Upstream ingress bytes per second")
    upstream_egress_rate: float = Field(default=0.0, ge=0.0, description="Upstream egress bytes per second")

    # Request counts & status breakdown
    request_count: int = Field(ge=0, description="Cumulative total requests")
    interval_requests: int = Field(default=0, ge=0, description="Interval total requests")
    request_rate: float = Field(default=0.0, ge=0.0, description="Requests per second")
    status_2xx: int = Field(default=0, ge=0)
    status_3xx: int = Field(default=0, ge=0)
    status_4xx: int = Field(default=0, ge=0)
    status_5xx: int = Field(default=0, ge=0)
    rate_limited_429: int = Field(default=0, ge=0)

    # Latencies
    latency_avg_ms: float = Field(default=0.0, ge=0.0)
    latency_p50_ms: float = Field(default=0.0, ge=0.0)
    latency_p95_ms: float = Field(default=0.0, ge=0.0)
    latency_p99_ms: float = Field(default=0.0, ge=0.0)

    # Segment breakdowns
    regional_traffic: Dict[str, Any] = Field(default_factory=dict, description="Per-region metrics")
    traffic_sources: Dict[str, Any] = Field(default_factory=dict, description="Per-traffic-source metrics")
    dropped_telemetry_count: int = Field(default=0, ge=0, description="Count of dropped telemetry batches")
    events: List[Dict[str, Any]] = Field(default_factory=list, description="Recent bounded request events")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_skew(cls, v: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        # Reject future-dated batches exceeding 10s clock skew
        if (v - now).total_seconds() > 10.0:
            raise ValueError(f"Batch timestamp is future-dated: {v.isoformat()} (server time: {now.isoformat()})")
        return v


class TrafficBatchResponse(BaseModel):
    status: str = Field(..., description="'accepted', 'duplicate', or 'rejected'")
    batch_id: str
    message: str
    processed_at: datetime


class TrafficSummaryResponse(BaseModel):
    """Real-time summary of application/API payload traffic."""
    current_ingress_bytes_per_sec: float
    current_egress_bytes_per_sec: float
    cumulative_ingress_bytes: int
    cumulative_egress_bytes: int
    upstream_ingress_bytes_per_sec: float
    upstream_egress_bytes_per_sec: float
    request_rate: float
    total_requests: int
    status_2xx: int
    status_3xx: int
    status_4xx: int
    status_5xx: int
    rate_limited_429: int
    latency_avg_ms: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    last_received_timestamp: Optional[datetime] = None
    telemetry_freshness: str = Field(..., description="'FRESH', 'STALE', 'UNAVAILABLE', or 'PENDING'")
    telemetry_age_seconds: Optional[float] = None
    is_available: bool
    measurement_source: str = Field(..., description="Reporting gateway instance ID, or 'none'")
    measurement_unit: str = "bytes"
    measurement_type: str = "application_payload_bytes"
    note: str = "Application/API payload bytes measured at Gateway proxy boundaries."


class TrafficTimeseriesPoint(BaseModel):
    timestamp: datetime
    client_ingress_bytes: int
    client_egress_bytes: int
    client_ingress_rate: float
    client_egress_rate: float
    upstream_ingress_rate: float
    upstream_egress_rate: float
    request_rate: float
    error_rate: float
    status_2xx: int
    status_4xx: int
    status_5xx: int
    latency_p95_ms: float


class TrafficTimeseriesResponse(BaseModel):
    time_range_seconds: int
    step_seconds: int
    point_count: int
    points: List[TrafficTimeseriesPoint]


class RegionalTrafficItem(BaseModel):
    region_id: str
    region_name: str
    cloud_zone: str
    requests_total: int
    request_rate: float
    upstream_request_bytes: int
    upstream_response_bytes: int
    upstream_ingress_rate: float
    upstream_egress_rate: float
    status_2xx: int
    status_3xx: int
    status_4xx: int
    status_5xx: int
    failed_requests: int
    timeouts: int
    latency_avg_ms: float


class RegionalTrafficResponse(BaseModel):
    timestamp: datetime
    regions: Dict[str, RegionalTrafficItem]


class TrafficEventModel(BaseModel):
    id: str
    timestamp: str
    method: str
    endpoint: str
    client_region: str
    served_region: str
    request_type: str
    rate_limiter_decision: str
    status_code: int
    duration_ms: float
    request_payload_bytes: int = 0
    response_payload_bytes: int = 0
    request_category: str = "other"
    upstream_region: Optional[str] = None
    upstream_request_bytes: int = 0
    upstream_response_bytes: int = 0
    upstream_duration_ms: float = 0.0
    traffic_source: str = "online_store"
    is_replay: bool = False


class TrafficEventsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    events: List[TrafficEventModel]
