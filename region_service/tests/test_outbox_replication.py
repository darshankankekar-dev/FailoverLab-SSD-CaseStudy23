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


@pytest.mark.asyncio
async def test_apply_replication_rejects_out_of_order_and_corrupt_payload(client):
    # 1. Non-monotonic batch (seq 5 followed by seq 3)
    bad_batch = {
        "source_region": "region-a",
        "events": [
            {
                "event_id": "evt-seq-5",
                "source_sequence_id": 5,
                "record_key": "k-5",
                "operation": "INSERT",
                "payload": {"v": 5},
                "version": 1,
                "fencing_epoch": 101,
                "source_region": "region-a",
                "created_at": "2026-11-01T15:00:05Z",
            },
            {
                "event_id": "evt-seq-3",
                "source_sequence_id": 3,
                "record_key": "k-3",
                "operation": "INSERT",
                "payload": {"v": 3},
                "version": 1,
                "fencing_epoch": 101,
                "source_region": "region-a",
                "created_at": "2026-11-01T15:00:03Z",
            },
        ],
    }
    resp = await client.post("/internal/replication/apply", json=bad_batch)
    assert resp.status_code == 400
    assert "Out-of-order" in resp.json()["detail"]

    # 2. Corrupt payload hash
    corrupt_batch = {
        "source_region": "region-a",
        "events": [
            {
                "event_id": "evt-corrupt",
                "source_sequence_id": 10,
                "record_key": "k-10",
                "operation": "INSERT",
                "payload": {"v": 10},
                "payload_hash": "bad-hash-000000000000000000000000000000000000000000000000000000000000",
                "version": 1,
                "fencing_epoch": 101,
                "source_region": "region-a",
                "created_at": "2026-11-01T15:00:10Z",
            }
        ],
    }
    corrupt_resp = await client.post("/internal/replication/apply", json=corrupt_batch)
    assert corrupt_resp.status_code == 400
    assert "Payload corruption" in corrupt_resp.json()["detail"]


@pytest.mark.asyncio
async def test_replication_checkpoint_endpoint(client):
    chk_resp = await client.get("/internal/replication/checkpoint")
    assert chk_resp.status_code == 200
    data = chk_resp.json()
    assert "last_applied_sequence_id" in data
    assert "region_id" in data


