import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock
import gateway.src.main as gateway_module
from gateway.src.main import app, route_table
from gateway.src.traffic_manager import traffic_coordinator, LimiterMode


@pytest.fixture(autouse=True)
async def setup_and_teardown_stream():
    route_table.set_target(
        target_region="region-a",
        target_role="ACTIVE",
        dns_ttl_seconds=2,
        propagation_percent=100,
    )
    traffic_coordinator.set_mode(LimiterMode.OFF)
    traffic_coordinator.reset_all()
    yield
    traffic_coordinator.reset_all()


@pytest.mark.asyncio
async def test_traffic_history_and_events(async_client, monkeypatch):
    mock_resp = httpx.Response(
        status_code=200,
        content=b'[{"id":"prod-1","name":"Coffee"}]',
        headers={"content-type": "application/json", "X-Served-Region": "region-a", "X-Consistency-Level": "eventual_read"},
    )
    mock_request = AsyncMock(return_value=mock_resp)
    mock_http_client = AsyncMock()
    mock_http_client.request = mock_request
    monkeypatch.setattr(gateway_module, "http_client", mock_http_client)

    # Make application request
    res = await async_client.get(
        "/api/ecommerce/products",
        headers={"X-Client-Region": "ap-south-1", "X-Request-ID": "test-req-123"},
    )
    assert res.status_code == 200

    # Verify history
    hist_res = await async_client.get("/api/v1/traffic/history")
    assert hist_res.status_code == 200
    events = hist_res.json()["events"]
    assert len(events) >= 1
    last_event = events[-1]
    assert last_event["endpoint"] == "/api/ecommerce/products"
    assert last_event["request_id"] == "test-req-123"
    assert last_event["client_region"] == "ap-south-1"
    assert last_event["served_region"] == "region-a"
    assert last_event["rate_limiter_decision"] == "accepted"
    assert last_event["status_code"] == 200


@pytest.mark.asyncio
async def test_traffic_public_config_and_reset(async_client):
    # Switch to TOKEN_BUCKET
    cfg_res = await async_client.put(
        "/api/v1/traffic/config",
        json={"mode": "TOKEN_BUCKET", "token_capacity": 15.0, "token_refill_rate": 3.0},
    )
    assert cfg_res.status_code == 200
    data = cfg_res.json()["traffic_control"]
    assert data["mode"] == "TOKEN_BUCKET"
    assert data["token_bucket"]["capacity"] == 15.0

    # Reset
    reset_res = await async_client.post("/api/v1/traffic/reset")
    assert reset_res.status_code == 200
    hist_res = await async_client.get("/api/v1/traffic/history")
    assert len(hist_res.json()["events"]) == 0
