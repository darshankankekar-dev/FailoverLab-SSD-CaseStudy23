import pytest
from sqlalchemy import select
from src.models import RecordEntity, OutboxEventEntity


@pytest.mark.asyncio
async def test_create_and_read_record(client, db_session):
    # 1. Create a record
    resp = await client.post(
        "/api/records",
        json={"key": "account-101", "value": {"name": "Acme Corp", "balance": 50000}},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["key"] == "account-101"
    assert data["value"]["balance"] == 50000
    assert data["version"] == 1
    assert data["fencing_epoch"] == 101

    # 2. Read single record
    get_resp = await client.get("/api/records/account-101")
    assert get_resp.status_code == 200
    assert get_resp.json()["key"] == "account-101"

    # 3. List records
    list_resp = await client.get("/api/records")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 4. Verify transactional outbox event creation
    res_out = await db_session.execute(select(OutboxEventEntity).where(OutboxEventEntity.record_key == "account-101"))
    outbox_event = res_out.scalar_one_or_none()
    assert outbox_event is not None
    assert outbox_event.operation == "INSERT"
    assert outbox_event.payload["balance"] == 50000
    assert outbox_event.version == 1
    assert outbox_event.fencing_epoch == 101
    assert outbox_event.replicated is False


@pytest.mark.asyncio
async def test_update_record(client, db_session):
    # Create
    await client.post(
        "/api/records",
        json={"key": "inventory-item-42", "value": {"quantity": 100}},
    )

    # Update
    update_resp = await client.put(
        "/api/records/inventory-item-42",
        json={"value": {"quantity": 85}},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["version"] == 2
    assert update_resp.json()["value"]["quantity"] == 85

    # Verify second outbox event was generated for update
    res_out = await db_session.execute(
        select(OutboxEventEntity).where(OutboxEventEntity.record_key == "inventory-item-42").order_by(OutboxEventEntity.sequence_id.asc())
    )
    events = res_out.scalars().all()
    assert len(events) == 2
    assert events[0].operation == "INSERT"
    assert events[1].operation == "UPDATE"
    assert events[1].version == 2
    assert events[1].payload["quantity"] == 85


@pytest.mark.asyncio
async def test_delete_record(client, db_session):
    # Create
    await client.post(
        "/api/records",
        json={"key": "temp-key", "value": {"flag": True}},
    )

    # Delete
    del_resp = await client.delete("/api/records/temp-key")
    assert del_resp.status_code == 204

    # Verify not found
    get_resp = await client.get("/api/records/temp-key")
    assert get_resp.status_code == 404

    # Verify DELETE outbox event
    res_out = await db_session.execute(
        select(OutboxEventEntity).where(OutboxEventEntity.record_key == "temp-key").order_by(OutboxEventEntity.sequence_id.desc())
    )
    last_event = res_out.scalars().first()
    assert last_event.operation == "DELETE"

