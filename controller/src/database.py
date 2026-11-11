import logging
from typing import AsyncGenerator
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy import select
from .config import settings
from .models import (
    Base,
    RegionEntity,
    PolicyEntity,
    ControllerStateEntity,
    ReplicationEntity,
    RouteEntity,
    QuorumVoterEntity,
    AuditEventEntity,
)

logger = logging.getLogger("controller.database")

# Create engine
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initializes tables and seeds baseline state if not present."""
    logger.info("Initializing controller database schema...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # 1. Seed Policy
            existing_policy = await session.execute(select(PolicyEntity).where(PolicyEntity.id == 1))
            if not existing_policy.scalar_one_or_none():
                policy = PolicyEntity(
                    id=1,
                    health_check_interval_sec=2,
                    failure_threshold_consecutive=3,
                    quorum_size=3,
                    majority_required=2,
                    acceptable_replication_lag_sec=5.0,
                    fencing_duration_sec=2.0,
                    route_propagation_sec=2.0,
                    route_verification_sec=2.0,
                    auto_failover_enabled=True,
                )
                session.add(policy)

            # 2. Seed Regions
            res_a = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
            if not res_a.scalar_one_or_none():
                region_a = RegionEntity(
                    id="region-a",
                    name="Mumbai",
                    cloud_zone="ap-south-1",
                    role="ACTIVE",
                    health="HEALTHY",
                    status="healthy",
                    accepts_writes=True,
                    ingress_traffic_percent=100,
                    ingress_rps=2450,
                    app_servers_healthy=12,
                    app_servers_total=12,
                    active_connections=2450,
                    iops=4800,
                    fencing_epoch=101,
                    is_fenced=False,
                )
                session.add(region_a)

            res_b = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
            if not res_b.scalar_one_or_none():
                region_b = RegionEntity(
                    id="region-b",
                    name="Singapore",
                    cloud_zone="ap-southeast-1",
                    role="STANDBY",
                    health="HEALTHY",
                    status="healthy",
                    accepts_writes=False,
                    ingress_traffic_percent=0,
                    ingress_rps=0,
                    app_servers_healthy=12,
                    app_servers_total=12,
                    active_connections=0,
                    iops=120,
                    fencing_epoch=101,
                    is_fenced=False,
                )
                session.add(region_b)

            # 3. Seed Controller State
            res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
            if not res_state.scalar_one_or_none():
                c_state = ControllerStateEntity(
                    id=1,
                    current_state="HEALTHY",
                    active_region="region-a",
                    fencing_epoch=101,
                    consecutive_failures=0,
                    last_health_check_sim_time=0.0,
                    simulated_time_seconds=0.0,
                    blocked_reason=None,
                    blocked_at_state=None,
                    is_sequence_in_progress=False,
                    route_retry_count=0,
                    persisted_intent=None,
                    is_paused_interrupted=False,
                )
                session.add(c_state)

            # 4. Seed Replication
            res_rep = await session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
            if not res_rep.scalar_one_or_none():
                rep = ReplicationEntity(
                    id=1,
                    status="STREAMING",
                    lag_seconds=0.8,
                    lag_ms=800,
                    bandwidth_mbps=450,
                    packet_loss_percent=0.0,
                    pending_bytes=12400,
                    bytes_transferred=45000000,
                    mode="ASYNCHRONOUS_RECORD",
                )
                session.add(rep)

            # 5. Seed Route
            res_route = await session.execute(select(RouteEntity).where(RouteEntity.id == 1))
            if not res_route.scalar_one_or_none():
                route = RouteEntity(
                    id=1,
                    active_target="region-a",
                    dns_ttl_seconds=2,
                    propagation_percent=100,
                    verification_status="VERIFIED",
                )
                session.add(route)

            # 6. Seed Quorum Observers
            voters_data = [
                ("voter-1", "Observer 1", "ap-south-1 (Mumbai Local)", "PRIMARY_HEALTHY", 5),
                ("voter-2", "Observer 2", "ap-southeast-1 (Singapore Local)", "PRIMARY_HEALTHY", 32),
                ("voter-3", "Observer 3 (Neutral Tie-Breaker)", "eu-central-1 (Zurich Independent)", "PRIMARY_HEALTHY", 78),
            ]
            for v_id, name, loc, vote, lat in voters_data:
                res_v = await session.execute(select(QuorumVoterEntity).where(QuorumVoterEntity.id == v_id))
                if not res_v.scalar_one_or_none():
                    session.add(QuorumVoterEntity(
                        id=v_id,
                        name=name,
                        location=loc,
                        vote=vote,
                        latency_ms=lat,
                    ))

            # 7. Seed Initial Audit Record
            res_ev = await session.execute(select(AuditEventEntity))
            if not res_ev.scalars().first():
                init_event = AuditEventEntity(
                    id="init-1",
                    simulated_time_seconds=0.0,
                    wall_clock_timestamp=datetime.now(timezone.utc).isoformat(),
                    severity="info",
                    subsystem="CONTROLLER",
                    transition="INITIALIZED -> HEALTHY",
                    reason="FailoverLab controller initialized in nominal state. Region A (Mumbai) ACTIVE [Epoch 101], Region B (Singapore) STANDBY replica. Heartbeat probes normal.",
                    details="Control plane running on FastAPI with persistent PostgreSQL/SQLite storage.",
                )
                session.add(init_event)

        logger.info("Controller database initialization completed successfully.")

