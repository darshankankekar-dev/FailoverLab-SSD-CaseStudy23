import pytest
import httpx
from unittest.mock import AsyncMock
import gateway.src.main as gateway_module
from gateway.src.main import app, route_table

AUTH_HEADERS = {"X-Internal-Secret": "internal-secret-token"}


@pytest.mark.asyncio
async def test_health_live_and_ready(async_client):
    res_live = await async_client.get("/health/live")
    assert res_live.status_code == 200
    assert res_live.json() == {"status": "alive", "service": "failoverlab-gateway"}

    res_ready = await async_client.get("/health/ready")
    assert res_ready.status_code == 200
    data = res_ready.json()
    assert data["status"] == "ready"
    assert data["active_target"] == "region-a"
    assert data["target_role"] == "ACTIVE"


@pytest.mark.asyncio
async def test_get_and_update_route(async_client):
    res = await async_client.get("/api/v1/route")
    assert res.status_code == 200
    data = res.json()
    assert data["active_target"] == "region-a"
    assert data["target_role"] == "ACTIVE"
    assert data["route_epoch"] == 1

    # Shift route to region-b with valid auth token
    update_res = await async_client.put(
        "/internal/routing/target",
        json={
            "target_region": "region-b",
            "target_role": "ACTIVE",
            "dns_ttl_seconds": 5,
            "propagation_percent": 100,
        },
        headers=AUTH_HEADERS,
    )
    assert update_res.status_code == 200
    update_data = update_res.json()
    assert update_data["success"] is True
    assert update_data["route"]["active_target"] == "region-b"
    assert update_data["route"]["target_role"] == "ACTIVE"
    assert update_data["route"]["route_epoch"] == 2


@pytest.mark.asyncio
async def test_internal_route_auth_required(async_client):
    # Attempt update without auth header
    res_no_auth = await async_client.put(
        "/internal/routing/target",
        json={"target_region": "region-b"},
    )
    assert res_no_auth.status_code == 403
    assert "Invalid or missing internal authentication token" in res_no_auth.json()["detail"]

    # Attempt with wrong secret
    res_bad_auth = await async_client.put(
        "/internal/routing/target",
        json={"target_region": "region-b"},
        headers={"X-Internal-Secret": "wrong-token"},
    )
    assert res_bad_auth.status_code == 403


@pytest.mark.asyncio
async def test_request_id_and_logging_headers(async_client):
    res = await async_client.get("/health/live")
    assert "x-request-id" in res.headers
    assert "x-routed-to-region" in res.headers
    assert res.headers["x-routed-to-region"] == "region-a"


@pytest.mark.asyncio
async def test_writer_safety_rejects_writes_to_standby(async_client):
    # Demote current target to STANDBY
    route_table.set_region_role("region-a", "STANDBY")

    res = await async_client.post(
        "/api/records",
        json={"key": "test-key", "value": {"test": "data"}},
    )
    assert res.status_code == 403
    data = res.json()["detail"]
    assert data["error"] == "Write rejected by gateway"
    assert "designated STANDBY" in data["message"]


@pytest.mark.asyncio
async def test_route_probe_success(async_client):
    mock_client = AsyncMock()
    mock_client.get.return_value = httpx.Response(200, json={"status": "alive"})

    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client
    try:
        res = await async_client.get("/internal/routing/probe", headers=AUTH_HEADERS)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["active_target"] == "region-a"
        assert "latency_ms" in data
    finally:
        gateway_module.http_client = original_client


@pytest.mark.asyncio
async def test_route_probe_failure(async_client):
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.ConnectError("Connection refused")

    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client
    try:
        res = await async_client.get("/internal/routing/probe", headers=AUTH_HEADERS)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert "Connection refused" in data["message"]
    finally:
        gateway_module.http_client = original_client


@pytest.mark.asyncio
async def test_proxy_records_forward_success(async_client):
    mock_client = AsyncMock()
    mock_client.request.return_value = httpx.Response(
        201,
        json={"id": "rec-1", "key": "k1", "value": {"foo": "bar"}, "version": 1},
        headers={"content-type": "application/json"},
    )

    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client
    try:
        res = await async_client.post(
            "/api/records",
            json={"key": "k1", "value": {"foo": "bar"}},
        )
        assert res.status_code == 201
        assert res.json()["key"] == "k1"
        assert mock_client.request.called
    finally:
        gateway_module.http_client = original_client


@pytest.mark.asyncio
async def test_proxy_records_forward_upstream_timeout(async_client):
    mock_client = AsyncMock()
    mock_client.request.side_effect = httpx.TimeoutException("Read timed out")

    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client
    try:
        res = await async_client.get("/api/records")
        assert res.status_code == 504
        data = res.json()["detail"]
        assert data["error"] == "Upstream timeout"
    finally:
        gateway_module.http_client = original_client


@pytest.mark.asyncio
async def test_proxy_records_forward_active_region_unreachable(async_client):
    mock_client = AsyncMock()
    mock_client.request.side_effect = httpx.ConnectError("Refused")

    original_client = gateway_module.http_client
    gateway_module.http_client = mock_client
    try:
        res = await async_client.get("/api/records")
        assert res.status_code == 503
        data = res.json()["detail"]
        assert data["error"] == "Active region unavailable"
        assert data["active_target"] == "region-a"
    finally:
        gateway_module.http_client = original_client
