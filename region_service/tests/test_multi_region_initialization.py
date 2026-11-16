import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.models import Base, RegionalMetadataEntity, RecordEntity
from src.database import get_db_session
from src.main import create_app


@pytest.mark.asyncio
async def test_region_c_frankfurt_standby_initialization():
    """Tests that region-c (Frankfurt) initializes as STANDBY with its own database and rejects writes."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        meta = RegionalMetadataEntity(
            id=1,
            region_id="region-c",
            region_name="Frankfurt",
            cloud_zone="eu-central-1",
            role="STANDBY",
            health="HEALTHY",
            accepts_writes=False,
            fencing_epoch=101,
            is_fenced=False,
        )
        session.add(meta)
        await session.commit()

    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Check status
        status_resp = await client.get("/api/status")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["region_id"] == "region-c"
        assert data["name"] == "Frankfurt"
        assert data["role"] == "STANDBY"
        assert data["health"] == "HEALTHY"
        assert data["accepts_writes"] is False
        assert data["is_fenced"] is False
        assert data["fencing_epoch"] == 101
        assert data["applied_sequence"] == 0
        assert data["replication_lag_seconds"] == 0.0

        # 2. Reject write
        write_resp = await client.post("/api/records", json={"key": "k1", "value": {"item": "notebook"}})
        assert write_resp.status_code == 403
        detail = write_resp.json().get("detail", {})
        assert detail.get("error") == "STANDBY_READ_ONLY" or "STANDBY" in str(detail)


@pytest.mark.asyncio
async def test_region_d_virginia_standby_initialization():
    """Tests that region-d (Virginia) initializes as STANDBY with its own database and rejects writes."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        meta = RegionalMetadataEntity(
            id=1,
            region_id="region-d",
            region_name="Virginia",
            cloud_zone="us-east-1",
            role="STANDBY",
            health="HEALTHY",
            accepts_writes=False,
            fencing_epoch=101,
            is_fenced=False,
        )
        session.add(meta)
        await session.commit()

    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        status_resp = await client.get("/api/status")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["region_id"] == "region-d"
        assert data["name"] == "Virginia"
        assert data["role"] == "STANDBY"
        assert data["accepts_writes"] is False

        write_resp = await client.post("/api/records", json={"key": "k2", "value": {"item": "phone"}})
        assert write_resp.status_code == 403


@pytest.mark.asyncio
async def test_region_e_saopaulo_standby_initialization():
    """Tests that region-e (São Paulo) initializes as STANDBY with its own database and rejects writes."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        meta = RegionalMetadataEntity(
            id=1,
            region_id="region-e",
            region_name="São Paulo",
            cloud_zone="sa-east-1",
            role="STANDBY",
            health="HEALTHY",
            accepts_writes=False,
            fencing_epoch=101,
            is_fenced=False,
        )
        session.add(meta)
        await session.commit()

    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        status_resp = await client.get("/api/status")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["region_id"] == "region-e"
        assert data["name"] == "São Paulo"
        assert data["role"] == "STANDBY"
        assert data["accepts_writes"] is False

        write_resp = await client.post("/api/records", json={"key": "k3", "value": {"item": "camera"}})
        assert write_resp.status_code == 403


@pytest.mark.asyncio
async def test_independent_databases_isolation():
    """Confirms two regional databases maintain distinct record namespaces without cross-contamination."""
    engine_c = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    engine_d = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine_c.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine_d.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory_c = async_sessionmaker(bind=engine_c, class_=AsyncSession, expire_on_commit=False)
    factory_d = async_sessionmaker(bind=engine_d, class_=AsyncSession, expire_on_commit=False)

    # Insert record into C only
    async with factory_c() as session:
        rec = RecordEntity(key="rec-frankfurt-1", value={"server": "de-1"}, version=1, fencing_epoch=101, source_region="region-c")
        session.add(rec)
        await session.commit()

    # Verify C has the record
    async with factory_c() as session:
        rec_c = await session.get(RecordEntity, "rec-frankfurt-1")
        assert rec_c is not None

    # Verify D does NOT have the record
    async with factory_d() as session:
        rec_d = await session.get(RecordEntity, "rec-frankfurt-1")
        assert rec_d is None
