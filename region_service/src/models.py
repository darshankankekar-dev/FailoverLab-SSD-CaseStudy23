import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    Boolean,
    DateTime,
    JSON,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class RegionalMetadataEntity(Base):
    __tablename__ = "regional_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    region_id: Mapped[str] = mapped_column(String(32), nullable=False)
    region_name: Mapped[str] = mapped_column(String(64), nullable=False)
    cloud_zone: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="STANDBY")  # ACTIVE or STANDBY
    health: Mapped[str] = mapped_column(String(16), nullable=False, default="HEALTHY")
    accepts_writes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fencing_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=101)
    is_fenced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class RecordEntity(Base):
    __tablename__ = "records"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fencing_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=101)
    source_region: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class OutboxEventEntity(Base):
    __tablename__ = "outbox_events"

    sequence_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, default=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    record_key: Mapped[str] = mapped_column(String(255), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)  # 'INSERT', 'UPDATE', 'DELETE'
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fencing_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=101)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    replicated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AppliedReplicationEventEntity(Base):
    __tablename__ = "applied_replication_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_sequence_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    record_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_region: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    fencing_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)

