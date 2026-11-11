import pytest


@pytest.mark.asyncio
async def test_health_live_endpoint(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"
    assert data["service"] == "failoverlab-controller"


@pytest.mark.asyncio
async def test_health_ready_endpoint(client):
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["database_connected"] is True
    assert data["controller_state"] == "HEALTHY"
    assert data["fencing_epoch"] == 101


@pytest.mark.asyncio
async def test_get_state_endpoint(client):
    resp = await client.get("/api/v1/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["controller_state"] == "HEALTHY"
    assert data["active_region"] == "region-a"
    assert data["fencing_epoch"] == 101
    assert data["region_a"]["id"] == "region-a"
    assert data["region_b"]["id"] == "region-b"
    assert data["policy"]["quorum_size"] == 3
    assert data["replication"]["status"] == "STREAMING"
    assert data["route"]["active_target"] == "region-a"
    assert len(data["voters"]) == 3


@pytest.mark.asyncio
async def test_regions_endpoints(client):
    # List regions
    resp = await client.get("/api/v1/regions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert {r["id"] for r in data} == {"region-a", "region-b"}

    # Get single region
    resp_a = await client.get("/api/v1/regions/region-a")
    assert resp_a.status_code == 200
    assert resp_a.json()["cloud_zone"] == "ap-south-1"

    # Get non-existent region
    resp_err = await client.get("/api/v1/regions/region-unknown")
    assert resp_err.status_code == 404


@pytest.mark.asyncio
async def test_policy_get_and_put(client):
    # Get initial policy
    resp = await client.get("/api/v1/policy")
    assert resp.status_code == 200
    assert resp.json()["failure_threshold_consecutive"] == 3

    # Update policy
    put_resp = await client.put(
        "/api/v1/policy",
        json={"failure_threshold_consecutive": 4, "acceptable_replication_lag_sec": 7.5},
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["failure_threshold_consecutive"] == 4
    assert updated["acceptable_replication_lag_sec"] == 7.5

    # Verify event was logged for policy update
    events_resp = await client.get("/api/v1/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    assert any("Policy updated" in e["reason"] for e in events)


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    resp = await client.get("/api/v1/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["controller_state"] == "HEALTHY"
    assert data["telemetry"]["total_client_rps"] == 2450


@pytest.mark.asyncio
async def test_failover_api_blocked_and_success(client):
    # 1. Trigger failover with failures=0 -> blocked with HTTP 409
    resp = await client.post("/api/v1/failover", json={"force": False})
    assert resp.status_code == 409
    data = resp.json()
    assert data["status"] == "BLOCKED"
    assert "Debounce threshold not met" in data["message"]

    # 2. Trigger failover with force=True and quorum outage -> succeeds with HTTP 200
    # Set voters to outage
    for v_id in ["voter-1", "voter-2", "voter-3"]:
        await client.post(
            "/internal/telemetry/vote",
            json={"voter_id": v_id, "vote": "PRIMARY_OUTAGE", "latency_ms": 10},
        )

    force_resp = await client.post(
        "/api/v1/failover",
        json={"force": True, "reason": "Drill execution"},
    )
    assert force_resp.status_code == 200
    assert force_resp.json()["status"] == "COMPLETED"
    assert force_resp.json()["current_state"] == "SECONDARY_ACTIVE"
    assert force_resp.json()["fencing_epoch"] == 102


@pytest.mark.asyncio
async def test_failback_api_flow(client):
    # 1. Force failover to region-b
    for v_id in ["voter-1", "voter-2", "voter-3"]:
        await client.post(
            "/internal/telemetry/vote",
            json={"voter_id": v_id, "vote": "PRIMARY_OUTAGE"},
        )
    await client.post("/api/v1/failover", json={"force": True})

    # 2. Attempt failback without confirmation -> HTTP 409
    fb_no_conf = await client.post(
        "/api/v1/failback",
        json={"operator_id": "op-1", "confirmation": False},
    )
    assert fb_no_conf.status_code == 409

    # 3. Successful deliberate failback with confirmation -> HTTP 200
    fb_success = await client.post(
        "/api/v1/failback",
        json={"operator_id": "lead-sre", "confirmation": True},
    )
    assert fb_success.status_code == 200
    assert fb_success.json()["status"] == "COMPLETED"
    assert fb_success.json()["current_state"] == "HEALTHY"
    assert fb_success.json()["fencing_epoch"] == 103


@pytest.mark.asyncio
async def test_reset_endpoint(client):
    resp = await client.post("/api/v1/reset", json={"preserve_policy": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["controller_state"] == "HEALTHY"
    assert data["fencing_epoch"] == 101
    assert data["active_region"] == "region-a"


@pytest.mark.asyncio
async def test_security_no_credential_leak(client):
    # Check all public endpoints to ensure credentials/passwords are never leaked
    for url in ["/health/live", "/health/ready", "/api/v1/state", "/api/v1/metrics", "/api/v1/policy"]:
        resp = await client.get(url)
        content_text = resp.text.lower()
        assert "password" not in content_text
        assert "secret" not in content_text
        assert "internal_api_secret" not in content_text

