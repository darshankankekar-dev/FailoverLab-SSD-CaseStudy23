import pytest
import pytest_asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport

from src.models import Base
from src.database import get_db_session
from src.main import create_app
from src.database import init_db

# Use in-memory SQLite for test isolation
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed baseline state using TestSessionLocal
    from src.models import (
        RegionEntity,
        PolicyEntity,
        ControllerStateEntity,
        ReplicationEntity,
        RouteEntity,
        QuorumVoterEntity,
        AuditEventEntity,
    )
    async with TestSessionLocal() as session:
        session.add(PolicyEntity(
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
        ))
        session.add(RegionEntity(
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
        ))
        session.add(RegionEntity(
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
        ))
        session.add(ControllerStateEntity(
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
        ))
        session.add(ReplicationEntity(
            id=1,
            status="STREAMING",
            lag_seconds=0.8,
            lag_ms=800,
            bandwidth_mbps=450,
            packet_loss_percent=0.0,
            pending_bytes=12400,
            bytes_transferred=45000000,
            mode="ASYNCHRONOUS_RECORD",
        ))
        session.add(RouteEntity(
            id=1,
            active_target="region-a",
            dns_ttl_seconds=2,
            propagation_percent=100,
            verification_status="VERIFIED",
        ))
        session.add(QuorumVoterEntity(
            id="voter-1", name="Observer 1", location="ap-south-1 (Mumbai Local)", vote="PRIMARY_HEALTHY", latency_ms=5
        ))
        session.add(QuorumVoterEntity(
            id="voter-2", name="Observer 2", location="ap-southeast-1 (Singapore Local)", vote="PRIMARY_HEALTHY", latency_ms=32
        ))
        session.add(QuorumVoterEntity(
            id="voter-3", name="Observer 3", location="eu-central-1 (Zurich)", vote="PRIMARY_HEALTHY", latency_ms=78
        ))
        session.add(AuditEventEntity(
            id="init-test-1",
            simulated_time_seconds=0.0,
            wall_clock_timestamp="2026-10-31T22:00:00Z",
            severity="info",
            subsystem="CONTROLLER",
            transition="INITIALIZED -> HEALTHY",
            reason="Test controller initialized in nominal state.",
        ))
        await session.commit()

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

