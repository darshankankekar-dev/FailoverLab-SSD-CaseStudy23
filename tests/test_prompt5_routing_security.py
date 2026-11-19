"""
Test Suite for PROMPT 5: Nginx, Vite Routing and Deployment Security Verification.
Validates:
1. Nginx and Vite route separation:
   - /api/v1/traffic/summary, /timeseries, /regions, /recent-events, /stream -> Controller
   - /api/v1/traffic/events -> Gateway
   - SSE configuration headers & timeout directives
   - /internal/telemetry/ blocking from public reverse proxy
2. Internal telemetry security:
   - POST /internal/telemetry/traffic-batch requires X-Internal-Secret
   - Rejects unauthenticated or invalid tokens with HTTP 401
   - Internal token is not leaked to frontend headers
3. Administrative authentication:
   - Controller requires valid X-Admin-Secret or Bearer token when require_admin_auth=True or environment=production
   - Fails when unauthenticated or with invalid secret
   - Accepts valid admin secret
   - Separates admin auth from internal telemetry secret
   - Permits unauthenticated local testing when require_admin_auth=False in dev
4. Compose exposure:
   - Database and internal services are bound strictly to 127.0.0.1
   - Only frontend is published as public entry point
"""

import pytest
import re
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from controller.src.main import create_app as create_controller_app
from controller.src.config import settings as controller_settings
from gateway.src.main import app as gateway_app
from gateway.src.config import settings as gateway_settings
from datetime import datetime, timezone
import uuid


def make_valid_batch(
    batch_id: str = None,
    gateway_id: str = "gateway-1",
    timestamp: datetime = None,
    ingress_bytes: int = 15000,
    egress_bytes: int = 45000,
    request_count: int = 120,
    interval_seconds: float = 1.0,
) -> dict:
    ts = timestamp or datetime.now(timezone.utc)
    b_id = batch_id or f"batch-{uuid.uuid4().hex[:12]}"
    return {
        "schema_version": "1.0",
        "gateway_instance_id": gateway_id,
        "batch_id": b_id,
        "timestamp": ts.isoformat(),
        "reporting_interval_seconds": interval_seconds,
        "client_ingress_bytes": ingress_bytes,
        "client_egress_bytes": egress_bytes,
        "interval_client_ingress_bytes": 1500,
        "interval_client_egress_bytes": 4500,
        "upstream_ingress_bytes": 40000,
        "upstream_egress_bytes": 12000,
        "interval_upstream_ingress_bytes": 4000,
        "interval_upstream_egress_bytes": 1200,
        "client_ingress_rate": 1500.0,
        "client_egress_rate": 4500.0,
        "upstream_ingress_rate": 4000.0,
        "upstream_egress_rate": 1200.0,
        "request_count": request_count,
        "interval_requests": 12,
        "request_rate": 12.0,
        "status_2xx": 115,
        "status_3xx": 0,
        "status_4xx": 3,
        "status_5xx": 2,
        "rate_limited_429": 1,
        "avg_latency_ms": 14.5,
        "p50_latency_ms": 12.0,
        "p95_latency_ms": 28.0,
        "p99_latency_ms": 45.0,
        "dropped_telemetry_count": 0,
        "consecutive_failures": 0,
        "regions": {
            "region-a": {
                "region_id": "region-a",
                "request_count": 80,
                "interval_requests": 8,
                "request_rate": 8.0,
                "upstream_ingress_bytes": 25000,
                "upstream_egress_bytes": 8000,
                "interval_upstream_ingress_bytes": 2500,
                "interval_upstream_egress_bytes": 800,
                "upstream_ingress_rate": 2500.0,
                "upstream_egress_rate": 800.0,
                "status_2xx": 78,
                "status_4xx": 2,
                "status_5xx": 0,
                "avg_latency_ms": 11.2,
                "p50_latency_ms": 10.0,
                "p95_latency_ms": 22.0,
                "p99_latency_ms": 35.0,
            }
        },
    }


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


# =========================================================================
# 1. NGINX & VITE ROUTING CHECKS
# =========================================================================

def test_nginx_route_separation_and_sse_configuration():
    nginx_path = WORKSPACE_ROOT / "FailoverLab - Frontend" / "nginx.conf"
    assert nginx_path.exists(), "nginx.conf must exist"
    content = nginx_path.read_text(encoding="utf-8")

    # Controller endpoints mapped to controller:8000
    for ep in ["summary", "timeseries", "regions", "recent-events", "stream"]:
        pattern = rf"location\s+=\s+/api/v1/traffic/{ep}\s*\{{[^}}]*proxy_pass\s+http://controller:8000/api/v1/traffic/{ep}"
        assert re.search(pattern, content), f"Nginx must route /api/v1/traffic/{ep} to controller:8000"

    # Gateway event stream endpoint mapped to gateway:8080
    gw_event_pattern = r"location\s+=\s+/api/v1/traffic/events\s*\{[^}]*proxy_pass\s+http://gateway:8080/api/v1/traffic/events"
    assert re.search(gw_event_pattern, content), "Nginx must route /api/v1/traffic/events to gateway:8080"

    # SSE directives for controller stream
    stream_block = re.search(r"location\s+=\s+/api/v1/traffic/stream\s*\{([^}]+)\}", content)
    assert stream_block, "Controller stream location block must be present"
    stream_directives = stream_block.group(1)
    assert "proxy_buffering off;" in stream_directives
    assert "proxy_cache off;" in stream_directives
    assert "proxy_http_version 1.1;" in stream_directives
    assert 'proxy_set_header Connection "";' in stream_directives
    assert "proxy_read_timeout" in stream_directives

    # SSE directives for gateway events
    events_block = re.search(r"location\s+=\s+/api/v1/traffic/events\s*\{([^}]+)\}", content)
    assert events_block, "Gateway events location block must be present"
    events_directives = events_block.group(1)
    assert "proxy_buffering off;" in events_directives
    assert "proxy_cache off;" in events_directives
    assert "proxy_http_version 1.1;" in events_directives
    assert 'proxy_set_header Connection "";' in events_directives
    assert "proxy_read_timeout" in events_directives

    # Internal telemetry ingestion blocked from public proxy
    assert "location /internal/telemetry/" in content
    assert "return 403" in content, "Public proxy must return 403 for /internal/telemetry/"

    # X-Internal-Secret not forwarded from client
    assert "proxy_set_header X-Internal-Secret $http_x_admin_secret;" not in content
    assert "proxy_set_header X-Internal-Secret $http_x_internal_secret;" not in content


def test_vite_proxy_configuration_parity():
    vite_path = WORKSPACE_ROOT / "FailoverLab - Frontend" / "vite.config.ts"
    assert vite_path.exists(), "vite.config.ts must exist"
    content = vite_path.read_text(encoding="utf-8")

    # Controller endpoints mapped to localhost:8000
    for ep in ["summary", "timeseries", "regions", "recent-events", "stream"]:
        pattern = rf"'/api/v1/traffic/{ep}':\s*\{{[^}}]*target:\s*'http://localhost:8000'"
        assert re.search(pattern, content), f"Vite proxy must route /api/v1/traffic/{ep} to localhost:8000"

    # Gateway event stream endpoint mapped to localhost:8080
    gw_event_pattern = r"'/api/v1/traffic/events':\s*\{[^}]*target:\s*'http://localhost:8080'"
    assert re.search(gw_event_pattern, content), "Vite proxy must route /api/v1/traffic/events to localhost:8080"


# =========================================================================
# 2. INTERNAL TELEMETRY SECURITY
# =========================================================================

@pytest.mark.asyncio
async def test_internal_telemetry_batch_requires_x_internal_secret():
    app = create_controller_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://controller") as client:
        unique_b_id = f"sec-test-{uuid.uuid4().hex[:8]}"
        payload = make_valid_batch(batch_id=unique_b_id)

        # 1. No secret header -> 401 Unauthorized
        res_no_auth = await client.post("/internal/telemetry/traffic-batch", json=payload)
        assert res_no_auth.status_code == 401
        assert "X-Internal-Secret" in res_no_auth.json()["detail"]

        # 2. Invalid secret header -> 401 Unauthorized
        res_bad_auth = await client.post(
            "/internal/telemetry/traffic-batch",
            json=payload,
            headers={"X-Internal-Secret": "wrong-secret-token"},
        )
        assert res_bad_auth.status_code == 401

        # 3. Valid X-Internal-Secret -> 200 OK
        res_ok = await client.post(
            "/internal/telemetry/traffic-batch",
            json=payload,
            headers={"X-Internal-Secret": controller_settings.internal_api_secret},
        )
        assert res_ok.status_code == 200
        assert res_ok.json()["status"].lower() in ("accepted", "processed", "duplicate")


# =========================================================================
# 3. ADMINISTRATIVE AUTHENTICATION & SEPARATION
# =========================================================================

@pytest.mark.asyncio
async def test_admin_authentication_enforcement_and_separation():
    app = create_controller_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://controller") as client:
        # Save original settings
        orig_require_auth = controller_settings.require_admin_auth
        orig_admin_secret = controller_settings.admin_api_secret
        orig_env = controller_settings.environment

        try:
            # 1. Non-production with require_admin_auth=False -> Open for local dev
            controller_settings.require_admin_auth = False
            controller_settings.environment = "development"
            res_open = await client.get("/api/v1/state")
            assert res_open.status_code == 200

            # 2. Production or require_admin_auth=True -> Enforced
            controller_settings.require_admin_auth = True
            controller_settings.admin_api_secret = "super-secret-admin-pass-99"

            # Sensitive admin endpoint: /api/v1/reset
            # Unauthenticated attempt -> 401 Unauthorized
            res_unauth = await client.post("/api/v1/reset", json={"reason": "test"})
            assert res_unauth.status_code == 401
            assert "X-Admin-Secret" in res_unauth.json()["detail"]

            # Wrong secret -> 401 Unauthorized
            res_wrong = await client.post(
                "/api/v1/reset",
                json={"reason": "test"},
                headers={"X-Admin-Secret": "invalid-pass"},
            )
            assert res_wrong.status_code == 401

            # Internal secret token CANNOT authenticate admin operations when admin_api_secret is configured!
            res_internal_leak = await client.post(
                "/api/v1/reset",
                json={"reason": "test"},
                headers={"X-Admin-Secret": controller_settings.internal_api_secret},
            )
            assert res_internal_leak.status_code == 401, "Internal secret must not grant administrative access!"

            # Valid X-Admin-Secret -> Succeeds!
            res_auth_ok = await client.post(
                "/api/v1/reset",
                json={"reason": "test"},
                headers={"X-Admin-Secret": "super-secret-admin-pass-99"},
            )
            assert res_auth_ok.status_code == 200

            # Valid Bearer Authorization token -> Also succeeds!
            res_bearer_ok = await client.post(
                "/api/v1/reset",
                json={"reason": "test"},
                headers={"Authorization": "Bearer super-secret-admin-pass-99"},
            )
            assert res_bearer_ok.status_code == 200

            # 3. Production mode NEVER silently disables authentication
            controller_settings.require_admin_auth = False
            controller_settings.environment = "production"
            res_prod_enforced = await client.post("/api/v1/reset", json={"reason": "test"})
            assert res_prod_enforced.status_code == 401, "Production mode must enforce admin auth even if require_admin_auth=False"

        finally:
            # Restore original settings
            controller_settings.require_admin_auth = orig_require_auth
            controller_settings.admin_api_secret = orig_admin_secret
            controller_settings.environment = orig_env


# =========================================================================
# 4. DOCKER COMPOSE EXPOSURE & PORT HARDENING
# =========================================================================

def test_compose_port_isolation_and_loopback_binding():
    compose_path = WORKSPACE_ROOT / "compose.yaml"
    assert compose_path.exists(), "compose.yaml must exist"
    content = compose_path.read_text(encoding="utf-8")

    # Databases must be bound to 127.0.0.1
    for db in [
        "controller-db",
        "region-a-db",
        "region-b-db",
        "region-c-db",
        "region-d-db",
        "region-e-db",
    ]:
        db_block = re.search(rf"{db}:[\s\S]+?ports:\s*\n\s*-\s*\"([^\"]+)\"", content)
        assert db_block, f"Port definition for {db} must exist"
        port_mapping = db_block.group(1)
        assert port_mapping.startswith("127.0.0.1:"), f"{db} port must be bound to 127.0.0.1, got: {port_mapping}"

    # Internal services must be bound to 127.0.0.1
    for srv in [
        "region-a",
        "region-b",
        "region-c",
        "region-d",
        "region-e",
        "controller",
        "gateway",
        "replicator",
    ]:
        srv_block = re.search(rf"\n  {srv}:[\s\S]+?ports:\s*\n\s*-\s*\"([^\"]+)\"", content)
        assert srv_block, f"Port definition for {srv} must exist"
        port_mapping = srv_block.group(1)
        assert port_mapping.startswith("127.0.0.1:"), f"{srv} port must be bound to 127.0.0.1, got: {port_mapping}"

    # Only frontend is exposed publicly
    fe_block = re.search(r"frontend:[\s\S]+?ports:\s*\n\s*-\s*\"([^\"]+)\"", content)
    assert fe_block, "Frontend port mapping must exist"
    fe_port = fe_block.group(1)
    assert not fe_port.startswith("127.0.0.1:"), "Frontend should be exposed as the public entry point"


# =========================================================================
# 5. CONTROLLER & GATEWAY ENDPOINT HEALTH & SEPARATION
# =========================================================================

@pytest.mark.asyncio
async def test_controller_public_telemetry_endpoints_functional():
    app = create_controller_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://controller") as client:
        # /api/v1/traffic/summary is public and functional
        res_summary = await client.get("/api/v1/traffic/summary")
        assert res_summary.status_code == 200
        data = res_summary.json()
        assert "current_ingress_bytes_per_sec" in data
        assert "telemetry_freshness" in data

        # /api/v1/traffic/timeseries is public and functional
        res_ts = await client.get("/api/v1/traffic/timeseries?window_seconds=60&step_seconds=5")
        assert res_ts.status_code == 200
        assert "points" in res_ts.json()

        # /api/v1/traffic/regions is public and functional
        res_regions = await client.get("/api/v1/traffic/regions")
        assert res_regions.status_code == 200
        assert "regions" in res_regions.json()

        # /api/v1/traffic/recent-events is public and functional
        res_events = await client.get("/api/v1/traffic/recent-events?limit=10")
        assert res_events.status_code == 200
        assert "events" in res_events.json()


@pytest.mark.asyncio
async def test_gateway_sse_stream_separate_from_controller():
    transport = ASGITransport(app=gateway_app)
    async with AsyncClient(transport=transport, base_url="http://gateway") as client:
        # Gateway has its own /api/v1/traffic/events stream
        res = await client.get("/api/v1/traffic/events?max_events=1")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")
        assert "event: connect" in res.text or "data:" in res.text

    # And Controller has its own /api/v1/traffic/stream
    ctrl_app = create_controller_app()
    ctrl_transport = ASGITransport(app=ctrl_app)
    async with AsyncClient(transport=ctrl_transport, base_url="http://controller") as ctrl_client:
        res = await ctrl_client.get("/api/v1/traffic/stream?max_events=1")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")
        assert "event: connect" in res.text or "data:" in res.text
