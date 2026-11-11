import pytest
from sqlalchemy import select
from src.models import RegionalMetadataEntity


@pytest.mark.asyncio
async def test_standby_region_rejects_writes_allows_reads(client, db_session):
    # Demote region to STANDBY
    res = await db_session.execute(select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1))
    meta = res.scalar_one()
    meta.role = "STANDBY"
    meta.accepts_writes = False
    await db_session.commit()

    # 1. Attempt write on STANDBY -> HTTP 403 Forbidden
    resp = await client.post(
        "/api/records",
        json={"key": "test-key-1", "value": {"data": "should_fail"}},
    )
    assert resp.status_code == 403
    err_detail = resp.json()["detail"]
    assert err_detail["error"] == "STANDBY_READ_ONLY"

    # 2. Attempt read on STANDBY -> HTTP 200 OK
    read_resp = await client.get("/api/records")
    assert read_resp.status_code == 200


@pytest.mark.asyncio
async def test_fenced_region_rejects_writes(client, db_session):
    # Fence the active region
    res = await db_session.execute(select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1))
    meta = res.scalar_one()
    meta.is_fenced = True
    meta.accepts_writes = False
    await db_session.commit()

    # Attempt write on fenced region -> HTTP 403 Forbidden
    resp = await client.post(
        "/api/records",
        json={"key": "test-key-2", "value": {"data": "should_fail"}},
    )
    assert resp.status_code == 403
    err_detail = resp.json()["detail"]
    assert err_detail["error"] == "FENCED_WRITE_PROHIBITED"


@pytest.mark.asyncio
async def test_stale_fencing_epoch_rejected(client, db_session):
    # Authoritative epoch is 102
    res = await db_session.execute(select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1))
    meta = res.scalar_one()
    meta.fencing_epoch = 102
    await db_session.commit()

    # Caller submits write with stale epoch 101 -> HTTP 409 Conflict
    resp = await client.post(
        "/api/records",
        json={"key": "test-key-3", "value": {"data": "stale_write"}, "fencing_epoch": 101},
    )
    assert resp.status_code == 409
    err_detail = resp.json()["detail"]
    assert err_detail["error"] == "STALE_FENCING_EPOCH"
    assert err_detail["caller_epoch"] == 101
    assert err_detail["authoritative_epoch"] == 102

    # Caller submits write with valid epoch 102 -> HTTP 201 Created
    valid_resp = await client.post(
        "/api/records",
        json={"key": "test-key-3", "value": {"data": "valid_write"}, "fencing_epoch": 102},
    )
    assert valid_resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_fence_promote_demote_lifecycle(client, db_session):
    # 1. Fence writer
    fence_resp = await client.post(
        "/admin/fence",
        json={"region_id": "region-a", "fencing_epoch": 101, "revoke_write_lease": True},
    )
    assert fence_resp.status_code == 200
    assert fence_resp.json()["is_fenced"] is True
    assert fence_resp.json()["accepts_writes"] is False

    # 2. Promote with new epoch 102
    promote_resp = await client.post(
        "/admin/promote",
        json={"region_id": "region-a", "fencing_epoch": 102, "grant_write_authority": True},
    )
    assert promote_resp.status_code == 200
    assert promote_resp.json()["role"] == "ACTIVE"
    assert promote_resp.json()["fencing_epoch"] == 102
    assert promote_resp.json()["accepts_writes"] is True
    assert promote_resp.json()["is_fenced"] is False

    # Verify write succeeds with epoch 102
    write_resp = await client.post(
        "/api/records",
        json={"key": "post-promote-key", "value": {"status": "promoted"}},
    )
    assert write_resp.status_code == 201

    # 3. Demote back to STANDBY with epoch 103
    demote_resp = await client.post(
        "/admin/demote",
        json={"region_id": "region-a", "fencing_epoch": 103},
    )
    assert demote_resp.status_code == 200
    assert demote_resp.json()["role"] == "STANDBY"
    assert demote_resp.json()["accepts_writes"] is False

