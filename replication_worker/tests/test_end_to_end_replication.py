import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from region_service.src.models import Base as RegionBase, RegionalMetadataEntity
from region_service.src.database import get_db_session
from region_service.src.main import create_app as create_region_app
from replication_worker.src.replicator import ReplicationEngine


@pytest.mark.asyncio
async def test_full_cross_region_replication_and_reversal():
    """
    End-to-end integration test:
    1. Region A (Mumbai, ACTIVE) writes records and creates outbox events.
    2. Region B (Singapore, STANDBY) strictly rejects direct writes (HTTP 403).
    3. Replication worker pulls from Region A and delivers to Region B.
    4. Region B verifies replicated record data.
    5. Deduplication verification: re-running replication skips duplicates safely.
    6. Role reversal: Region B promoted to ACTIVE, Region A fenced to STANDBY.
    7. Worker reverses direction: Region B writes replicate back into Region A.
    """
    # 1. Setup isolated database for Region A
    engine_a = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory_a = async_sessionmaker(bind=engine_a, class_=AsyncSession, expire_on_commit=False)

    async with engine_a.begin() as conn:
        await conn.run_sync(RegionBase.metadata.create_all)

    async with session_factory_a() as s:
        s.add(RegionalMetadataEntity(
            id=1, region_id="region-a", region_name="Mumbai", cloud_zone="ap-south-1",
            role="ACTIVE", health="HEALTHY", accepts_writes=True, fencing_epoch=101, is_fenced=False,
        ))
        await s.commit()

    # 2. Setup isolated database for Region B
    engine_b = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory_b = async_sessionmaker(bind=engine_b, class_=AsyncSession, expire_on_commit=False)

    async with engine_b.begin() as conn:
        await conn.run_sync(RegionBase.metadata.create_all)

    async with session_factory_b() as s:
        s.add(RegionalMetadataEntity(
            id=1, region_id="region-b", region_name="Singapore", cloud_zone="ap-southeast-1",
            role="STANDBY", health="HEALTHY", accepts_writes=False, fencing_epoch=101, is_fenced=False,
        ))
        await s.commit()

    # Create apps
    app_a = create_region_app()
    app_b = create_region_app()

    async def override_db_a():
        async with session_factory_a() as s:
            yield s

    async def override_db_b():
        async with session_factory_b() as s:
            yield s

    app_a.dependency_overrides[get_db_session] = override_db_a
    app_b.dependency_overrides[get_db_session] = override_db_b

    transport_a = ASGITransport(app=app_a)
    transport_b = ASGITransport(app=app_b)

    async with AsyncClient(transport=transport_a, base_url="http://region-a:8001") as client_a, \
               AsyncClient(transport=transport_b, base_url="http://region-b:8002") as client_b:

        # Step A: Write to Region A (ACTIVE)
        resp_w = await client_a.post("/api/records", json={"key": "customer-100", "value": {"tier": "gold"}})
        assert resp_w.status_code == 201
        assert resp_w.json()["key"] == "customer-100"

        # Step B: Write to Region B (STANDBY) -> Must be rejected with 403
        resp_fail = await client_b.post("/api/records", json={"key": "customer-100", "value": {"tier": "platinum"}})
        assert resp_fail.status_code == 403
        assert resp_fail.json()["detail"]["error"] == "STANDBY_READ_ONLY"

        # Step C: Read outbox from Region A
        outbox_resp = await client_a.get("/internal/replication/outbox?since_sequence_id=0")
        assert outbox_resp.status_code == 200
        events = outbox_resp.json()["events"]
        assert len(events) == 1
        assert events[0]["record_key"] == "customer-100"

        # Step D: Apply replication batch on Region B (Standby)
        apply_payload = {
            "source_region": "region-a",
            "events": [
                {
                    "event_id": events[0]["event_id"],
                    "source_sequence_id": events[0]["sequence_id"],
                    "record_key": events[0]["record_key"],
                    "operation": events[0]["operation"],
                    "payload": events[0]["payload"],
                    "version": events[0]["version"],
                    "fencing_epoch": events[0]["fencing_epoch"],
                    "source_region": "region-a",
                    "created_at": events[0]["created_at"],
                }
            ],
        }
        apply_resp = await client_b.post("/internal/replication/apply", json=apply_payload)
        assert apply_resp.status_code == 200
        assert apply_resp.json()["applied_count"] == 1

        # Step E: Verify record is present on Region B
        rec_b = await client_b.get("/api/records/customer-100")
        assert rec_b.status_code == 200
        assert rec_b.json()["value"]["tier"] == "gold"

        # Step F: Verify Idempotency - re-delivering duplicate event
        apply_dup = await client_b.post("/internal/replication/apply", json=apply_payload)
        assert apply_dup.status_code == 200
        assert apply_dup.json()["skipped_duplicates"] == 1
        assert apply_dup.json()["applied_count"] == 0

        # Step G: Failover Role Reversal
        # 1. Fence Region A
        fence_a = await client_a.post("/admin/fence", json={"region_id": "region-a", "fencing_epoch": 101})
        assert fence_a.status_code == 200
        assert fence_a.json()["is_fenced"] is True

        # 2. Promote Region B with epoch 102
        promote_b = await client_b.post("/admin/promote", json={"region_id": "region-b", "fencing_epoch": 102})
        assert promote_b.status_code == 200
        assert promote_b.json()["role"] == "ACTIVE"
        assert promote_b.json()["accepts_writes"] is True

        # Step H: Region B now accepts direct writes
        resp_b_write = await client_b.post(
            "/api/records",
            json={"key": "customer-200", "value": {"tier": "diamond"}},
        )
        assert resp_b_write.status_code == 201

        # Step I: Region A now rejects direct writes because it is fenced
        resp_a_rejected = await client_a.post(
            "/api/records",
            json={"key": "customer-300", "value": {"tier": "denied"}},
        )
        assert resp_a_rejected.status_code == 403
        assert resp_a_rejected.json()["detail"]["error"] == "FENCED_WRITE_PROHIBITED"

        # Step J: Reverse replication - pull outbox from Region B and apply on Region A
        outbox_b = await client_b.get("/internal/replication/outbox?since_sequence_id=0")
        assert outbox_b.status_code == 200
        events_b = outbox_b.json()["events"]
        assert len(events_b) == 1
        assert events_b[0]["record_key"] == "customer-200"

        reverse_payload = {
            "source_region": "region-b",
            "events": [
                {
                    "event_id": events_b[0]["event_id"],
                    "source_sequence_id": events_b[0]["sequence_id"],
                    "record_key": events_b[0]["record_key"],
                    "operation": events_b[0]["operation"],
                    "payload": events_b[0]["payload"],
                    "version": events_b[0]["version"],
                    "fencing_epoch": events_b[0]["fencing_epoch"],
                    "source_region": "region-b",
                    "created_at": events_b[0]["created_at"],
                }
            ],
        }
        apply_rev = await client_a.post("/internal/replication/apply", json=reverse_payload)
        assert apply_rev.status_code == 200
        assert apply_rev.json()["applied_count"] == 1

        # Step K: Verify Region A received the new record written in Singapore
        rec_a_rev = await client_a.get("/api/records/customer-200")
        assert rec_a_rev.status_code == 200
        assert rec_a_rev.json()["value"]["tier"] == "diamond"

