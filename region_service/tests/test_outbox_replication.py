import pytest
from src.schemas import ReplicationApplyRequest, ReplicationEventPayload


@pytest.mark.asyncio
async def test_outbox_reading_and_acknowledgement(client):
    # 1. Create two records
    await client.post("/api/records", json={"key": "key-1", "value": {"item": 1}})
    await client.post("/api/records", json={"key": "key-2", "value": {"item": 2}})

    # 2. Read outbox from sequence_id 0
    resp = await client.get("/internal/replication/outbox?since_sequence_id=0&limit=50")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["events"]) == 2
    assert data["highest_sequence_id"] == 2
    assert data["unreplicated_count"] == 2

    # Verify event fields
    event1 = data["events"][0]
    assert event1["sequence_id"] == 1
    assert event1["record_key"] == "key-1"
    assert event1["operation"] == "INSERT"
    assert event1["fencing_epoch"] == 101

    # 3. Acknowledge event 1
    ack_resp = await client.post("/internal/replication/ack", json=[event1["event_id"]])
    assert ack_resp.status_code == 200
    assert ack_resp.json()["acknowledged_count"] == 1

    # 4. Check outbox again (unreplicated should now be 1)
    chk_resp = await client.get("/internal/replication/outbox?since_sequence_id=0&limit=50")
    assert chk_resp.json()["unreplicated_count"] == 1


@pytest.mark.asyncio
async def test_apply_replication_batch_idempotency(client):
    # Simulate receiving a batch of events from active primary
    batch_payload = {
        "source_region": "region-a",
        "events": [
            {
                "event_id": "evt-unique-001",
                "source_sequence_id": 1,
                "record_key": "user-account-500",
                "operation": "INSERT",
                "payload": {"name": "Alice", "balance": 1000},
                "version": 1,
                "fencing_epoch": 101,
                "source_region": "region-a",
                "created_at": "2026-11-01T15:00:00Z",
            },
            {
                "event_id": "evt-unique-002",
                "source_sequence_id": 2,
                "record_key": "user-account-501",
                "operation": "INSERT",
                "payload": {"name": "Bob", "balance": 2000},
                "version": 1,
                "fencing_epoch": 101,
                "source_region": "region-a",
                "created_at": "2026-11-01T15:00:01Z",
            },
        ],
    }

    # 1. Apply batch first time
    apply_resp = await client.post("/internal/replication/apply", json=batch_payload)
    assert apply_resp.status_code == 200
    res_data = apply_resp.json()
    assert res_data["applied_count"] == 2
    assert res_data["skipped_duplicates"] == 0
    assert res_data["highest_sequence_id"] == 2

    # Verify records exist in regional storage
    rec1 = await client.get("/api/records/user-account-500")
    assert rec1.status_code == 200
    assert rec1.json()["value"]["name"] == "Alice"

    # 2. Retrying identical batch (duplicate delivery simulation) -> MUST BE IDEMPOTENT
    dup_resp = await client.post("/internal/replication/apply", json=batch_payload)
    assert dup_resp.status_code == 200
    dup_data = dup_resp.json()
    assert dup_data["applied_count"] == 0
    assert dup_data["skipped_duplicates"] == 2
    assert dup_data["highest_sequence_id"] == 2

    # Verify data was preserved without corruption or duplicate keys
    list_resp = await client.get("/api/records")
    assert len(list_resp.json()) == 2

