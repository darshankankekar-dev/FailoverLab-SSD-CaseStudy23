import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    Float,
    Boolean,
    Text,
    DateTime,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, utc_now


class RegionEntity(Base):
    __tablename__ = "regions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # 'region-a' or 'region-b'
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    cloud_zone: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # ACTIVE or STANDBY
    health: Mapped[str] = mapped_column(String(16), nullable=False, default="HEALTHY")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="healthy")
    accepts_writes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ingress_traffic_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ingress_rps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    app_servers_healthy: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    app_servers_total: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    active_connections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    iops: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fencing_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=101)
    is_fenced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class PolicyEntity(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    health_check_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    failure_threshold_consecutive: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    quorum_size: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    majority_required: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    acceptable_replication_lag_sec: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    fencing_duration_sec: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    route_propagation_sec: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    route_verification_sec: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    auto_failover_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ControllerStateEntity(Base):
    __tablename__ = "controller_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    current_state: Mapped[str] = mapped_column(String(32), nullable=False, default="HEALTHY")
    active_region: Mapped[str] = mapped_column(String(32), nullable=False, default="region-a")
    fencing_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=101)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_health_check_sim_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    simulated_time_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blocked_at_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_sequence_in_progress: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    route_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    persisted_intent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_paused_interrupted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ReplicationEntity(Base):
    __tablename__ = "replication_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="STREAMING")
    lag_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    lag_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=800)
    bandwidth_mbps: Mapped[int] = mapped_column(Integer, nullable=False, default=450)
    packet_loss_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pending_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=12400)
    bytes_transferred: Mapped[int] = mapped_column(BigInteger, nullable=False, default=45000000)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="ASYNCHRONOUS_RECORD")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class RouteEntity(Base):
    __tablename__ = "route_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    active_target: Mapped[str] = mapped_column(String(32), nullable=False, default="region-a")
    dns_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    propagation_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="VERIFIED")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class QuorumVoterEntity(Base):
    __tablename__ = "quorum_voters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    location: Mapped[str] = mapped_column(String(128), nullable=False)
    vote: Mapped[str] = mapped_column(String(32), nullable=False, default="PRIMARY_HEALTHY")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class AuditEventEntity(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"ev-{uuid.uuid4().hex[:12]}")
    simulated_time_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    wall_clock_timestamp: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    subsystem: Mapped[str] = mapped_column(String(32), nullable=False)
    transition: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class TransitionIntentEntity(Base):
    __tablename__ = "transition_intents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"tx-{uuid.uuid4().hex[:12]}")
    transition_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source_state: Mapped[str] = mapped_column(String(32), nullable=False)
    target_state: Mapped[str] = mapped_column(String(32), nullable=False)
    target_region: Mapped[str] = mapped_column(String(32), nullable=False)
    fencing_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="IN_PROGRESS")
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    step_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

