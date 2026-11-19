import asyncio
import time
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional, Any, Dict, List

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, Header, Depends, status, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .routing import RouteTable
from .client_profiles import CLIENT_PROFILES, resolve_client_profile
from .traffic_manager import traffic_coordinator, LimiterMode, TrafficEvent
from .route_selector import RouteDecision
from .logging_config import (
    setup_structured_logging,
    correlation_id_ctx,
    transition_id_ctx,
    region_id_ctx,
)
from .metrics import gateway_metrics
from .telemetry import (
    ASGITrafficTelemetryMiddleware,
    telemetry_collector,
    normalize_endpoint,
    detect_traffic_source,
)
from .telemetry_exporter import telemetry_exporter

setup_structured_logging(service_name="gateway", log_level=settings.log_level)
logger = logging.getLogger("gateway.main")

route_table = RouteTable(
    default_target=settings.default_target,
    region_a_url=settings.region_a_url,
    region_b_url=settings.region_b_url,
    region_c_url=settings.region_c_url,
    region_d_url=settings.region_d_url,
    region_e_url=settings.region_e_url,
    dns_ttl_seconds=settings.dns_ttl_seconds,
    propagation_percent=settings.propagation_percent,
)

http_client: Optional[httpx.AsyncClient] = None


async def reconcile_route_from_controller() -> bool:
    """
    Fetches the validated active region from the controller plane
    to ensure routing table consistency upon startup or reconciliation.
    """
    global http_client
    if http_client is None:
        return False
    try:
        resp = await http_client.get(f"{settings.controller_url}/api/v1/state")
        if resp.status_code == 200:
            data = resp.json()
            active_region = data.get("active_region") or data.get("route", {}).get("active_target")
            if active_region and active_region in route_table.target_urls:
                dns_ttl = data.get("route", {}).get("dns_ttl_seconds", route_table.dns_ttl_seconds)
                propagation = data.get("route", {}).get("propagation_percent", route_table.propagation_percent)
                route_table.set_target(
                    target_region=active_region,
                    target_role="ACTIVE",
                    dns_ttl_seconds=dns_ttl,
                    propagation_percent=propagation,
                )
                # Synchronize regional lag and health if reported
                regions = data.get("regions", [])
                for r in regions:
                    r_id = r.get("id")
                    if r_id in route_table.target_urls:
                        route_table.set_region_health(r_id, r.get("health", "HEALTHY"))
                        route_table.set_region_lag(r_id, float(r.get("replication_lag_seconds", 0.0)))

                logger.info(f"Reconciled route from Controller: active_target='{active_region}'")
                return True
    except Exception as e:
        logger.warning(f"Could not reconcile route from Controller ({e}); using cached/default route '{route_table.active_target}'.")
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0))
    logger.info(
        f"Gateway service starting. Initial active target: '{route_table.active_target}' "
        f"({route_table.get_active_url()})"
    )
    # Attempt initial route reconciliation from Controller
    await reconcile_route_from_controller()
    # Start leaky bucket background drain dispatcher
    await traffic_coordinator.leaky_shaper.start()
    # Start background telemetry exporter if enabled
    if settings.telemetry_export_enabled:
        await telemetry_exporter.start()
    yield
    if settings.telemetry_export_enabled:
        await telemetry_exporter.stop()
    await traffic_coordinator.leaky_shaper.stop()
    await http_client.aclose()


app = FastAPI(
    title="FailoverLab Ingress Gateway",
    description="Dynamic routing ingress proxy with Token Bucket rate limiting and Leaky Bucket traffic shaping (Case Study 23)",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Note: ASGITrafficTelemetryMiddleware is added after logging_and_traffic_middleware
# so that it wraps as the outermost middleware, accurately measuring client bodies and responses.


def classify_request_type(method: str, path: str) -> str:
    if method in {"POST", "PUT", "DELETE", "PATCH"}:
        return "write"
    if "inventory" in path or "order" in path:
        return "strong_read"
    if "product" in path or "record" in path:
        return "eventual_read"
    return "system"


@app.middleware("http")
async def logging_and_traffic_middleware(request: Request, call_next):
    """
    Enforces traffic management (Token Bucket / Leaky Bucket) before requests reach regional services.
    Assigns request ID, tracks actual gateway execution latency, and logs request/response metadata.
    """
    request_id = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:10]}"
    request.state.request_id = request_id
    correlation_id_ctx.set(request_id)

    trans_id = request.headers.get("X-Transition-ID")
    if trans_id:
        transition_id_ctx.set(trans_id)

    region_id_ctx.set(route_table.active_target)

    # Traffic Control Filter
    path = request.url.path
    is_internal_or_health = (
        path.startswith("/internal/")
        or path.startswith("/health/")
        or path.startswith("/api/v1/")
        or path.startswith("/api/traffic/")
        or path == "/metrics"
    )

    rate_decision = "accepted"
    leaky_wait_ms = 0.0
    client_key = (
        request.headers.get("X-Client-ID")
        or request.headers.get("X-API-Key")
        or request.headers.get("X-Client-Region")
        or (request.client.host if request.client else "global")
    )
    client_region = request.headers.get("X-Client-Region") or client_key

    # Classify traffic source, endpoint category, and measure client request payload bytes
    headers_map = {k.lower(): v for k, v in request.headers.items()}
    traffic_src = detect_traffic_source(headers_map, path)
    norm_template, req_category = normalize_endpoint(path)

    if request.method in {"POST", "PUT", "PATCH"}:
        req_body = await request.body()
        req_payload_bytes = len(req_body) if req_body else 0
    else:
        req_payload_bytes = 0
    request.state.measured_ingress_bytes = req_payload_bytes

    if not is_internal_or_health:
        # 1. Mode: TOKEN_BUCKET
        if traffic_coordinator.mode == LimiterMode.TOKEN_BUCKET:
            allowed, remaining, retry_after = await traffic_coordinator.token_limiter.check(client_key)
            if not allowed:
                traffic_coordinator.record_request_outcome(status.HTTP_429_TOO_MANY_REQUESTS, 0.5)
                resp_429 = JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "Rate limit exceeded",
                        "message": "Token bucket capacity exhausted. Rate limit exceeded.",
                        "client_id": client_key,
                        "retry_after_seconds": retry_after,
                        "mode": "TOKEN_BUCKET",
                    },
                    headers={
                        "Retry-After": str(int(retry_after) + 1),
                        "X-RateLimit-Limit": str(int(traffic_coordinator.token_limiter.capacity)),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(retry_after),
                        "X-RateLimit-Mode": "TOKEN_BUCKET",
                        "X-Request-ID": request_id,
                        "X-Served-Region": route_table.active_target,
                        "X-Routed-To-Region": route_table.active_target,
                    },
                )
                resp_payload_bytes = len(resp_429.body) if hasattr(resp_429, "body") else 0
                await traffic_coordinator.record_traffic_event(
                    TrafficEvent(
                        request_id=request_id,
                        method=request.method,
                        endpoint=path,
                        client_region=client_region,
                        served_region=route_table.active_target,
                        request_type=classify_request_type(request.method, path),
                        rate_limiter_decision="rejected",
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        duration_ms=0.5,
                        simulated_wan_delay_ms=0.0,
                        queue_wait_time_ms=0.0,
                        request_payload_bytes=req_payload_bytes,
                        response_payload_bytes=resp_payload_bytes,
                        request_category=req_category,
                        upstream_region=None,
                        upstream_request_bytes=0,
                        upstream_response_bytes=0,
                        upstream_duration_ms=0.0,
                        traffic_source=traffic_src,
                        is_replay=False,
                    )
                )
                logger.warning(f"[TOKEN_BUCKET_THROTTLED] Client '{client_key}' exceeded capacity. Retry-After: {retry_after}s")
                return resp_429

        # 2. Mode: LEAKY_BUCKET
        elif traffic_coordinator.mode == LimiterMode.LEAKY_BUCKET:
            try:
                allowed, wait_or_retry, err_msg = await traffic_coordinator.leaky_shaper.enqueue(client_key, request_id)
                if not allowed:
                    traffic_coordinator.record_request_outcome(status.HTTP_429_TOO_MANY_REQUESTS, 0.5)
                    resp_429 = JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "error": "Rate limit exceeded",
                            "message": err_msg,
                            "client_id": client_key,
                            "retry_after_seconds": wait_or_retry,
                            "mode": "LEAKY_BUCKET",
                        },
                        headers={
                            "Retry-After": str(int(wait_or_retry) + 1),
                            "X-RateLimit-Limit": str(traffic_coordinator.leaky_shaper.queue_capacity),
                            "X-RateLimit-Mode": "LEAKY_BUCKET",
                            "X-Request-ID": request_id,
                            "X-Served-Region": route_table.active_target,
                            "X-Routed-To-Region": route_table.active_target,
                        },
                    )
                    resp_payload_bytes = len(resp_429.body) if hasattr(resp_429, "body") else 0
                    await traffic_coordinator.record_traffic_event(
                        TrafficEvent(
                            request_id=request_id,
                            method=request.method,
                            endpoint=path,
                            client_region=client_region,
                            served_region=route_table.active_target,
                            request_type=classify_request_type(request.method, path),
                            rate_limiter_decision="rejected",
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            duration_ms=0.5,
                            simulated_wan_delay_ms=0.0,
                            queue_wait_time_ms=0.0,
                            request_payload_bytes=req_payload_bytes,
                            response_payload_bytes=resp_payload_bytes,
                            request_category=req_category,
                            upstream_region=None,
                            upstream_request_bytes=0,
                            upstream_response_bytes=0,
                            upstream_duration_ms=0.0,
                            traffic_source=traffic_src,
                            is_replay=False,
                        )
                    )
                    logger.warning(f"[LEAKY_BUCKET_OVERFLOW] Client '{client_key}' rejected: {err_msg}")
                    return resp_429
                else:
                    leaky_wait_ms = round(wait_or_retry * 1000, 2)
                    if leaky_wait_ms > 5.0:
                        rate_decision = "delayed"
            except asyncio.CancelledError:
                # Client disconnected or cancelled while waiting in queue
                traffic_coordinator.record_request_outcome(499, 0.0)
                raise

    start_time = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        traffic_coordinator.record_request_outcome(status.HTTP_500_INTERNAL_SERVER_ERROR, elapsed_ms)
        is_mgmt = (
            path.startswith("/internal/")
            or path.startswith("/health/")
            or path.startswith("/api/v1/traffic")
            or path.startswith("/api/traffic")
            or path == "/metrics"
        )
        if not is_mgmt:
            status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
            up_reg = getattr(request.state, "upstream_region", None)
            up_req_b = getattr(request.state, "upstream_request_bytes", 0)
            up_resp_b = getattr(request.state, "upstream_response_bytes", 0)
            up_dur = getattr(request.state, "upstream_duration_ms", 0.0)
            await traffic_coordinator.record_traffic_event(
                TrafficEvent(
                    request_id=request_id,
                    method=request.method,
                    endpoint=path,
                    client_region=client_region,
                    served_region=route_table.active_target,
                    request_type=classify_request_type(request.method, path),
                    rate_limiter_decision=rate_decision,
                    status_code=status_code,
                    duration_ms=round(elapsed_ms, 2),
                    simulated_wan_delay_ms=0.0,
                    queue_wait_time_ms=leaky_wait_ms,
                    request_payload_bytes=req_payload_bytes,
                    response_payload_bytes=0,
                    request_category=req_category,
                    upstream_region=up_reg,
                    upstream_request_bytes=up_req_b,
                    upstream_response_bytes=up_resp_b,
                    upstream_duration_ms=round(up_dur, 2),
                    traffic_source=traffic_src,
                    is_replay=False,
                )
            )
        raise exc

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    # Record metrics
    gateway_metrics.record_request(response.status_code, elapsed_ms)
    traffic_coordinator.record_request_outcome(response.status_code, elapsed_ms)

    routed_region = response.headers.get("X-Served-Region") or response.headers.get("X-Routed-To-Region") or route_table.active_target
    request.state.routed_region = routed_region

    is_replay = getattr(request.state, "is_replay", False)
    if is_replay:
        rate_decision = "idempotent_replay"

    up_reg = getattr(request.state, "upstream_region", None)
    up_req_b = getattr(request.state, "upstream_request_bytes", 0)
    up_resp_b = getattr(request.state, "upstream_response_bytes", 0)
    up_dur = getattr(request.state, "upstream_duration_ms", 0.0)

    # Response payload bytes
    resp_payload_bytes = getattr(request.state, "response_payload_bytes", 0)
    if resp_payload_bytes == 0 and hasattr(response, "body") and isinstance(getattr(response, "body", None), (bytes, bytearray)):
        resp_payload_bytes = len(response.body)
    if resp_payload_bytes == 0 and up_resp_b > 0:
        resp_payload_bytes = up_resp_b

    # Record traffic event for customer/application requests
    is_mgmt = (
        path.startswith("/internal/")
        or path.startswith("/health/")
        or path.startswith("/api/v1/traffic")
        or path.startswith("/api/traffic")
        or path == "/metrics"
    )
    if not is_mgmt:
        wan_delay_val = 0.0
        if "X-Simulated-WAN-Delay-Ms" in response.headers:
            try:
                wan_delay_val = float(response.headers["X-Simulated-WAN-Delay-Ms"])
            except ValueError:
                wan_delay_val = 0.0
        req_type = response.headers.get("X-Consistency-Level") or classify_request_type(request.method, path)
        request.state.request_type = req_type
        await traffic_coordinator.record_traffic_event(
            TrafficEvent(
                request_id=request_id,
                method=request.method,
                endpoint=path,
                client_region=client_region,
                served_region=routed_region,
                request_type=req_type,
                rate_limiter_decision=rate_decision,
                status_code=response.status_code,
                duration_ms=round(elapsed_ms, 2),
                simulated_wan_delay_ms=wan_delay_val,
                queue_wait_time_ms=leaky_wait_ms,
                request_payload_bytes=req_payload_bytes,
                response_payload_bytes=resp_payload_bytes,
                request_category=req_category,
                upstream_region=up_reg,
                upstream_request_bytes=up_req_b,
                upstream_response_bytes=up_resp_b,
                upstream_duration_ms=round(up_dur, 2),
                traffic_source=traffic_src,
                is_replay=is_replay,
            )
        )

    # Log metadata: request ID, method, path, selected region, response status, latency
    logger.info(
        f"[REQ: {request_id}] method={request.method} path={request.url.path} "
        f"region={routed_region} active={route_table.active_target} status={response.status_code} "
        f"latency_ms={elapsed_ms:.2f}ms mode={traffic_coordinator.mode.value}"
    )

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Correlation-ID"] = request_id
    if "X-Routed-To-Region" not in response.headers:
        response.headers["X-Routed-To-Region"] = routed_region
    if "X-Served-Region" not in response.headers:
        response.headers["X-Served-Region"] = routed_region
    if "X-Active-Region" not in response.headers:
        response.headers["X-Active-Region"] = route_table.active_target
    response.headers["X-RateLimit-Mode"] = traffic_coordinator.mode.value
    if trans_id:
        response.headers["X-Transition-ID"] = trans_id
    return response


# Add ASGITrafficTelemetryMiddleware as the outermost middleware layer so that it
# reliably intercepts all requests, responses, streaming chunks, and rate-limit rejections.
app.add_middleware(ASGITrafficTelemetryMiddleware)


# =========================================================================
# Security & Internal Authentication Dependency
# =========================================================================

async def verify_internal_auth(
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
    authorization: Optional[str] = Header(None),
):
    """
    Enforces that internal control-plane endpoints (route updates, probes, reconciliation)
    can only be invoked by authorized internal services carrying the shared secret.
    """
    token = x_internal_secret
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()

    if not token or token != settings.internal_token:
        logger.warning("Forbidden: Attempt to access internal gateway endpoint with invalid/missing token.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid or missing internal authentication token.",
        )


# =========================================================================
# Health & Status Endpoints
# =========================================================================

@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Returns gateway diagnostic health and exporter status."""
    exporter_status = telemetry_exporter.get_status()
    return {
        "status": "healthy" if exporter_status["is_healthy"] else "degraded",
        "service": "failoverlab-gateway",
        "active_target": route_table.active_target,
        "exporter": exporter_status,
        **exporter_status,
    }


@app.get("/health/live", tags=["Health"])
async def live_check() -> Dict[str, str]:
    return {"status": "alive", "service": "failoverlab-gateway"}


@app.get("/health/ready", tags=["Health"])
async def ready_check() -> Dict[str, Any]:
    return {
        "status": "ready",
        "service": "failoverlab-gateway",
        "active_target": route_table.active_target,
        "target_role": route_table.target_roles.get(route_table.active_target, "STANDBY"),
        "target_url": route_table.get_active_url(),
        "total_regions": len(route_table.target_urls),
        "traffic_limiter_mode": traffic_coordinator.mode.value,
    }


@app.get("/api/v1/route", tags=["Routing"])
async def get_route() -> Dict[str, Any]:
    """Returns current active route table, regional roles, health, lags, TTL, and propagation status."""
    return route_table.get_route_state()


@app.get("/api/v1/routing/profiles", tags=["Routing"])
async def list_client_profiles() -> Dict[str, Any]:
    """Returns the pre-configured geographic client profiles and nominal WAN delay models."""
    return {
        "profiles": {k: p.model_dump() for k, p in CLIENT_PROFILES.items()},
        "active_region": route_table.active_target,
    }


@app.get("/api/v1/routing/decision", tags=["Routing"])
async def preview_routing_decision(
    method: str = Query(default="GET", description="HTTP method"),
    path: str = Query(default="/api/ecommerce/products", description="Request URI path"),
    client_region: Optional[str] = Query(default=None, description="Client region/profile identifier (e.g. 'europe', 'ap-south-1')"),
    consistency: Optional[str] = Query(default=None, description="Explicit consistency ('strong' or 'eventual')"),
) -> Dict[str, Any]:
    """Previews the latency-aware routing decision without proxying backend requests."""
    decision = route_table.evaluate_route(
        method=method,
        path=path,
        client_region_identifier=client_region,
        explicit_consistency=consistency,
    )
    return decision.model_dump()


@app.get("/api/v1/traffic/status", tags=["Traffic Control"])
@app.get("/api/v1/routing/rate-limits", tags=["Traffic Control"])
async def get_traffic_status(
    client_id: Optional[str] = Query(None, description="Client ID"),
    x_client_id: Optional[str] = Header(None, alias="X-Client-ID"),
) -> Dict[str, Any]:
    """Returns runtime statistics for Token Bucket rate limiter and Leaky Bucket traffic shaper."""
    cid = client_id or x_client_id
    return traffic_coordinator.get_full_status(cid)


@app.get("/metrics", response_class=Response, tags=["Metrics"])
async def prometheus_metrics() -> Response:
    """Exposes gateway Prometheus plaintext metric exposition format."""
    body = gateway_metrics.to_prometheus(route_table.active_target, route_table.route_epoch)
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/api/v1/traffic/telemetry", tags=["Traffic Telemetry"])
@app.get("/api/traffic/telemetry", tags=["Traffic Telemetry"])
async def get_traffic_telemetry() -> Dict[str, Any]:
    """Returns real-time customer ingress/egress payload telemetry and upstream regional traffic metrics."""
    data = telemetry_collector.get_telemetry_snapshot(route_table.active_target)
    data["exporter"] = telemetry_exporter.get_status()
    return data


@app.get("/api/v1/traffic/exporter/status", tags=["Traffic Telemetry"])
async def get_traffic_exporter_status() -> Dict[str, Any]:
    """Returns status of the background telemetry exporter to Controller."""
    return telemetry_exporter.get_status()


@app.get("/api/v1/traffic/summary", tags=["Controller Traffic Proxy"])
async def proxy_traffic_summary(request: Request):
    """Proxies request to Controller's aggregated traffic summary endpoint."""
    global http_client
    if http_client is None:
        return JSONResponse(status_code=503, content={"detail": "Gateway HTTP client not ready"})
    try:
        url = f"{settings.controller_url}/api/v1/traffic/summary"
        resp = await http_client.get(url, params=dict(request.query_params))
        return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
    except Exception as e:
        logger.warning(f"Could not forward traffic summary to Controller: {e}")
        return JSONResponse(status_code=503, content={"detail": f"Controller unavailable: {e}"})


@app.get("/api/v1/traffic/timeseries", tags=["Controller Traffic Proxy"])
async def proxy_traffic_timeseries(request: Request):
    """Proxies request to Controller's historical traffic timeseries endpoint."""
    global http_client
    if http_client is None:
        return JSONResponse(status_code=503, content={"detail": "Gateway HTTP client not ready"})
    try:
        url = f"{settings.controller_url}/api/v1/traffic/timeseries"
        resp = await http_client.get(url, params=dict(request.query_params))
        return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
    except Exception as e:
        return JSONResponse(status_code=503, content={"detail": f"Controller unavailable: {e}"})


@app.get("/api/v1/traffic/regions", tags=["Controller Traffic Proxy"])
async def proxy_traffic_regions(request: Request):
    """Proxies request to Controller's regional traffic endpoint."""
    global http_client
    if http_client is None:
        return JSONResponse(status_code=503, content={"detail": "Gateway HTTP client not ready"})
    try:
        url = f"{settings.controller_url}/api/v1/traffic/regions"
        resp = await http_client.get(url, params=dict(request.query_params))
        return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
    except Exception as e:
        return JSONResponse(status_code=503, content={"detail": f"Controller unavailable: {e}"})


@app.get("/api/v1/metrics", tags=["Metrics"])
async def json_metrics() -> Dict[str, Any]:
    """Returns truthful measured JSON operational metrics for the gateway."""
    metrics = gateway_metrics.get_metrics()
    metrics["active_target"] = route_table.active_target
    metrics["route_epoch"] = route_table.route_epoch
    metrics["traffic_control"] = traffic_coordinator.get_full_status()
    metrics["regional_measured_latency"] = dict(route_table.regional_measured_latency)
    return metrics


# =========================================================================
# Internal Control Operations (Protected)
# =========================================================================

class RoutingUpdateRequest(BaseModel):
    target_region: str = Field(..., description="Target region ID (e.g., 'region-a', 'region-b', 'region-c')")
    target_role: Optional[str] = Field(default="ACTIVE", description="Role to assign to target ('ACTIVE' or 'STANDBY')")
    dns_ttl_seconds: Optional[int] = Field(default=2, ge=0, le=300)
    propagation_percent: Optional[int] = Field(default=100, ge=0, le=100)


class RegionalTelemetryUpdate(BaseModel):
    regional_health: Optional[Dict[str, str]] = Field(default=None, description="Health state per region ('HEALTHY' or 'DOWN')")
    regional_lag: Optional[Dict[str, float]] = Field(default=None, description="Replication lag in seconds per region")
    max_stale_seconds: Optional[float] = Field(default=None, description="Max acceptable stale read threshold in seconds")


class TrafficConfigUpdate(BaseModel):
    mode: Optional[str] = Field(default=None, description="OFF, TOKEN_BUCKET, or LEAKY_BUCKET")
    token_capacity: Optional[float] = Field(default=None, ge=1.0)
    token_refill_rate: Optional[float] = Field(default=None, ge=0.01)
    leaky_capacity: Optional[int] = Field(default=None, ge=1)
    leaky_drain_rate: Optional[float] = Field(default=None, ge=0.01)


@app.put(
    "/internal/routing/target",
    tags=["Internal Routing"],
    dependencies=[Depends(verify_internal_auth)],
)
async def update_target(payload: RoutingUpdateRequest) -> Dict[str, Any]:
    """
    Called by the controller during failover step 8 to shift ingress routing.
    Protected by internal authentication token.
    """
    try:
        updated_state = route_table.set_target(
            target_region=payload.target_region,
            target_role=payload.target_role or "ACTIVE",
            dns_ttl_seconds=payload.dns_ttl_seconds,
            propagation_percent=payload.propagation_percent,
        )
        return {
            "success": True,
            "message": f"Ingress route updated to {payload.target_region}",
            "route": updated_state,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.put(
    "/internal/routing/telemetry",
    tags=["Internal Routing"],
    dependencies=[Depends(verify_internal_auth)],
)
async def update_telemetry(payload: RegionalTelemetryUpdate) -> Dict[str, Any]:
    """Updates regional health, lag, or maximum stale read threshold."""
    route_table.update_telemetry(
        regional_health=payload.regional_health,
        regional_lag=payload.regional_lag,
        max_stale_seconds=payload.max_stale_seconds,
    )
    return {
        "success": True,
        "route_state": route_table.get_route_state(),
    }


@app.put(
    "/internal/traffic/config",
    tags=["Traffic Control"],
    dependencies=[Depends(verify_internal_auth)],
)
@app.put(
    "/internal/routing/rate-limits",
    tags=["Traffic Control"],
    dependencies=[Depends(verify_internal_auth)],
)
async def update_traffic_config(payload: TrafficConfigUpdate) -> Dict[str, Any]:
    """Dynamically reconfigures traffic mode (OFF, TOKEN_BUCKET, LEAKY_BUCKET) and parameters."""
    new_stats = traffic_coordinator.update_config(
        mode=payload.mode,
        token_capacity=payload.token_capacity,
        token_refill_rate=payload.token_refill_rate,
        leaky_capacity=payload.leaky_capacity,
        leaky_drain_rate=payload.leaky_drain_rate,
    )
    return {
        "success": True,
        "traffic_control": new_stats,
    }


@app.post(
    "/internal/traffic/reset",
    tags=["Traffic Control"],
    dependencies=[Depends(verify_internal_auth)],
)
async def reset_traffic_state() -> Dict[str, Any]:
    """Resets all token buckets, leaky queues, and metrics counters."""
    traffic_coordinator.reset_all()
    telemetry_collector.reset()
    gateway_metrics.reset()
    return {
        "success": True,
        "message": "Traffic manager state reset successfully",
        "traffic_control": traffic_coordinator.get_full_status(),
        "traffic_telemetry": telemetry_collector.get_telemetry_snapshot(route_table.active_target),
    }


# =========================================================================
# Public Traffic Control & Event Streaming Endpoints (Dashboard Integration)
# =========================================================================

@app.get("/api/v1/traffic/history", tags=["Traffic Control"])
@app.get("/api/traffic/history", tags=["Traffic Control"])
async def get_traffic_history(limit: int = Query(default=100, ge=1, le=250)) -> Dict[str, Any]:
    """Returns the most recent bounded traffic events recorded by the gateway."""
    return {"events": traffic_coordinator.get_traffic_history(limit=limit)}


@app.get("/api/v1/traffic/events", tags=["Traffic Control"])
@app.get("/api/traffic/events", tags=["Traffic Control"])
async def stream_traffic_events(request: Request):
    """
    Server-Sent Events (SSE) live stream of all requests passing through the gateway.
    Each event carries method, path, client_region, served_region, status, duration, WAN delay, wait time.
    """
    async def event_generator():
        queue = await traffic_coordinator.subscribe()
        try:
            # Yield initial connect greeting
            yield f"event: connect\ndata: {{\"connected\": true, \"history_count\": {len(traffic_coordinator.traffic_events)}}}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=12.0)
                    yield f"data: {event.model_dump_json()}\n\n"
                except (asyncio.TimeoutError, TimeoutError):
                    # Heartbeat comment to keep SSE connection alive
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await traffic_coordinator.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/v1/traffic/config", tags=["Traffic Control"])
@app.put("/api/v1/traffic/config", tags=["Traffic Control"])
@app.post("/api/traffic/config", tags=["Traffic Control"])
@app.put("/api/traffic/config", tags=["Traffic Control"])
async def public_update_traffic_config(payload: TrafficConfigUpdate) -> Dict[str, Any]:
    """Public control panel endpoint for dashboard traffic mode & parameter switching."""
    new_stats = traffic_coordinator.update_config(
        mode=payload.mode,
        token_capacity=payload.token_capacity,
        token_refill_rate=payload.token_refill_rate,
        leaky_capacity=payload.leaky_capacity,
        leaky_drain_rate=payload.leaky_drain_rate,
    )
    return {"success": True, "traffic_control": new_stats}


@app.post("/api/v1/traffic/reset", tags=["Traffic Control"])
@app.post("/api/traffic/reset", tags=["Traffic Control"])
async def public_reset_traffic() -> Dict[str, Any]:
    """Public reset endpoint for dashboard."""
    traffic_coordinator.reset_all()
    telemetry_collector.reset()
    gateway_metrics.reset()
    return {
        "success": True,
        "message": "Traffic manager state reset successfully",
        "traffic_control": traffic_coordinator.get_full_status(),
        "traffic_telemetry": telemetry_collector.get_telemetry_snapshot(route_table.active_target),
    }


@app.post(
    "/internal/routing/reconcile",
    tags=["Internal Routing"],
    dependencies=[Depends(verify_internal_auth)],
)
async def trigger_reconciliation() -> Dict[str, Any]:
    """Forces gateway to query the controller and reconcile its routing table."""
    synced = await reconcile_route_from_controller()
    return {
        "success": synced,
        "active_target": route_table.active_target,
        "route": route_table.get_route_state(),
    }


@app.get(
    "/internal/routing/probe",
    tags=["Internal Routing"],
    dependencies=[Depends(verify_internal_auth)],
)
async def probe_route() -> Dict[str, Any]:
    """
    Called by the controller during failover step 9 to verify route operability.
    Sends a test probe to the current active regional endpoint and measures latency.
    """
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=httpx.Timeout(3.0))

    target_url = route_table.get_active_url()
    probe_url = f"{target_url}/health/live"

    start_time = time.perf_counter()
    try:
        resp = await http_client.get(probe_url)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if resp.status_code == 200:
            return {
                "success": True,
                "active_target": route_table.active_target,
                "target_url": target_url,
                "latency_ms": round(elapsed_ms, 2),
                "message": "Route operational and reachable",
            }
        else:
            return {
                "success": False,
                "active_target": route_table.active_target,
                "target_url": target_url,
                "latency_ms": round(elapsed_ms, 2),
                "message": f"Target responded with HTTP {resp.status_code}",
            }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(f"Synthetic probe to {probe_url} failed: {exc}")
        return {
            "success": False,
            "active_target": route_table.active_target,
            "target_url": target_url,
            "latency_ms": round(elapsed_ms, 2),
            "message": f"Probe connection failure: {exc}",
        }


# =========================================================================
# Application Proxy Engine (Multi-Region Latency & Consistency Routing)
# =========================================================================

async def _execute_backend_request(request: Request, path: str, decision: RouteDecision) -> Response:
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0))

    target_endpoint = f"{decision.target_url}{path}"
    body = await request.body()
    up_req_bytes = len(body) if body else 0
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length"}
    }

    start_time = time.perf_counter()
    try:
        backend_resp = await http_client.request(
            method=request.method,
            url=target_endpoint,
            params=request.query_params,
            headers=forward_headers,
            content=body,
        )
        elapsed_backend_ms = (time.perf_counter() - start_time) * 1000
        route_table.record_measured_latency(decision.target_region, elapsed_backend_ms)

        up_resp_bytes = len(backend_resp.content) if backend_resp.content else 0
        telemetry_collector.record_upstream(
            region_id=decision.target_region,
            request_bytes=up_req_bytes,
            response_bytes=up_resp_bytes,
            duration_ms=elapsed_backend_ms,
            status_code=backend_resp.status_code,
        )

        request.state.upstream_region = decision.target_region
        request.state.upstream_request_bytes = up_req_bytes
        request.state.upstream_response_bytes = up_resp_bytes
        request.state.upstream_duration_ms = elapsed_backend_ms
        request.state.upstream_status = backend_resp.status_code
        request.state.response_payload_bytes = up_resp_bytes

        resp_headers = {
            k: v for k, v in backend_resp.headers.items()
            if k.lower() not in {
                "x-request-id", "x-correlation-id", "x-served-region",
                "x-active-region", "x-routed-to-region", "x-consistency-level",
                "x-route-reason", "x-gateway-latency-ms", "x-simulated-wan-delay-ms",
                "x-replication-lag-sec", "x-client-region", "content-length",
            }
        }
        req_id = getattr(request.state, "request_id", None) or f"req-{uuid.uuid4().hex[:10]}"

        # Decorate response with required metadata headers
        resp_headers["X-Request-ID"] = req_id
        resp_headers["X-Correlation-ID"] = req_id
        resp_headers["X-Served-Region"] = decision.target_region
        resp_headers["X-Active-Region"] = route_table.active_target
        resp_headers["X-Routed-To-Region"] = decision.target_region
        resp_headers["X-Consistency-Level"] = decision.consistency_level
        resp_headers["X-Route-Reason"] = decision.route_reason
        resp_headers["X-Gateway-Latency-Ms"] = f"{elapsed_backend_ms:.2f}"
        resp_headers["X-Simulated-WAN-Delay-Ms"] = f"{decision.simulated_wan_delay_ms:.1f}"
        resp_headers["X-Replication-Lag-Sec"] = f"{decision.replication_lag_seconds:.2f}"
        resp_headers["X-Client-Region"] = decision.client_region

        return Response(
            content=backend_resp.content,
            status_code=backend_resp.status_code,
            headers=resp_headers,
            media_type=backend_resp.headers.get("content-type"),
        )
    except httpx.ConnectError as ce:
        elapsed_backend_ms = (time.perf_counter() - start_time) * 1000
        telemetry_collector.record_upstream(
            region_id=decision.target_region,
            request_bytes=up_req_bytes,
            response_bytes=0,
            duration_ms=elapsed_backend_ms,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            is_failure=True,
        )
        request.state.upstream_region = decision.target_region
        request.state.upstream_request_bytes = up_req_bytes
        request.state.upstream_response_bytes = 0
        request.state.upstream_duration_ms = elapsed_backend_ms
        request.state.upstream_status = status.HTTP_503_SERVICE_UNAVAILABLE

        logger.error(f"Cannot reach target region at {target_endpoint}: {ce}")
        err_type = "Active region unavailable" if decision.target_region == route_table.active_target else "Target region unavailable"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": err_type,
                "served_region": decision.target_region,
                "active_target": route_table.active_target,
                "target_url": decision.target_url,
                "message": f"Could not connect to {decision.target_url}. Region may be down or experiencing an outage.",
            },
        )
    except httpx.TimeoutException as te:
        elapsed_backend_ms = (time.perf_counter() - start_time) * 1000
        telemetry_collector.record_upstream(
            region_id=decision.target_region,
            request_bytes=up_req_bytes,
            response_bytes=0,
            duration_ms=elapsed_backend_ms,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            is_timeout=True,
        )
        request.state.upstream_region = decision.target_region
        request.state.upstream_request_bytes = up_req_bytes
        request.state.upstream_response_bytes = 0
        request.state.upstream_duration_ms = elapsed_backend_ms
        request.state.upstream_status = status.HTTP_504_GATEWAY_TIMEOUT

        logger.error(f"Timeout connecting to target region at {target_endpoint}: {te}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "error": "Upstream timeout",
                "served_region": decision.target_region,
                "active_target": route_table.active_target,
                "target_url": decision.target_url,
                "message": f"Request to region '{decision.target_region}' timed out.",
            },
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        elapsed_backend_ms = (time.perf_counter() - start_time) * 1000
        telemetry_collector.record_upstream(
            region_id=decision.target_region,
            request_bytes=up_req_bytes,
            response_bytes=0,
            duration_ms=elapsed_backend_ms,
            status_code=status.HTTP_502_BAD_GATEWAY,
            is_failure=True,
        )
        request.state.upstream_region = decision.target_region
        request.state.upstream_request_bytes = up_req_bytes
        request.state.upstream_response_bytes = 0
        request.state.upstream_duration_ms = elapsed_backend_ms
        request.state.upstream_status = status.HTTP_502_BAD_GATEWAY

        logger.error(f"Error proxying {request.method} to {target_endpoint}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "Gateway proxy error",
                "served_region": decision.target_region,
                "active_target": route_table.active_target,
                "message": str(exc),
            },
        )


async def _forward_request(request: Request, path: str) -> Response:
    """
    Proxies client application requests using multi-region routing:
    - Writes: Strictly forwarded to current active primary writer.
    - Strong Reads: Strictly forwarded to current active primary writer.
    - Eventual Reads: Routed to lowest-latency healthy, non-stale replica.
    - Idempotency-Key support: Duplicate mutation retries return cached responses without re-executing.
    Preserves status codes, headers, and bodies from the upstream regional service.
    """
    client_region = request.headers.get("X-Client-Region") or request.headers.get("X-Client-Location") or request.query_params.get("client_region")
    explicit_consistency = request.headers.get("X-Consistency-Level") or request.query_params.get("consistency")

    decision = route_table.evaluate_route(
        method=request.method,
        path=path,
        client_region_identifier=client_region,
        explicit_consistency=explicit_consistency,
    )

    # Writer safety invariant check
    if decision.consistency_level == "write":
        if not route_table.is_write_allowed():
            logger.warning(
                f"Write request blocked: Target region '{route_table.active_target}' is designated STANDBY."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Write rejected by gateway",
                    "active_target": route_table.active_target,
                    "target_role": route_table.target_roles.get(route_table.active_target, "STANDBY"),
                    "message": f"Target region '{route_table.active_target}' is currently designated STANDBY and cannot accept write requests.",
                },
            )

    # Idempotency deduplication check on mutation requests
    idempotency_key = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
    if idempotency_key and request.method in {"POST", "PUT", "DELETE", "PATCH"}:
        cached = traffic_coordinator.idempotency.get(idempotency_key)
        if cached:
            logger.info(f"[IDEMPOTENCY_HIT] Returning cached response for key '{idempotency_key}'")
            resp_headers = dict(cached.headers)
            resp_headers["X-Idempotency-Replay"] = "true"
            request.state.is_replay = True
            request.state.upstream_region = None
            request.state.upstream_request_bytes = 0
            request.state.upstream_response_bytes = 0
            request.state.upstream_duration_ms = 0.0
            request.state.response_payload_bytes = len(cached.content)
            return Response(
                content=cached.content,
                status_code=cached.status_code,
                headers=resp_headers,
                media_type=cached.headers.get("content-type"),
            )

        lock = await traffic_coordinator.idempotency.get_lock(idempotency_key)
        async with lock:
            # Recheck after acquiring lock
            cached = traffic_coordinator.idempotency.get(idempotency_key)
            if cached:
                logger.info(f"[IDEMPOTENCY_HIT] Returning cached response for key '{idempotency_key}' (post-lock)")
                resp_headers = dict(cached.headers)
                resp_headers["X-Idempotency-Replay"] = "true"
                request.state.is_replay = True
                request.state.upstream_region = None
                request.state.upstream_request_bytes = 0
                request.state.upstream_response_bytes = 0
                request.state.upstream_duration_ms = 0.0
                request.state.response_payload_bytes = len(cached.content)
                return Response(
                    content=cached.content,
                    status_code=cached.status_code,
                    headers=resp_headers,
                    media_type=cached.headers.get("content-type"),
                )

            # Execute actual upstream request
            response = await _execute_backend_request(request, path, decision)
            if response.status_code < 400:
                traffic_coordinator.idempotency.store(
                    idempotency_key,
                    response.status_code,
                    response.body,
                    dict(response.headers),
                )
            return response
    else:
        return await _execute_backend_request(request, path, decision)


# =========================================================================
# Generic Records Endpoints
# =========================================================================

@app.api_route("/api/records", methods=["GET", "POST"])
@app.api_route("/api/data/records", methods=["GET", "POST"])
async def proxy_records_collection(request: Request):
    return await _forward_request(request, "/api/records")


@app.api_route("/api/records/{key:path}", methods=["GET", "DELETE", "PUT"])
@app.api_route("/api/data/records/{key:path}", methods=["GET", "DELETE", "PUT"])
async def proxy_single_record(key: str, request: Request):
    return await _forward_request(request, f"/api/records/{key}")


# =========================================================================
# Integrated Online Shopping Demonstration Endpoints
# =========================================================================

@app.api_route("/api/ecommerce/products", methods=["GET"])
@app.api_route("/api/shop/products", methods=["GET"])
async def proxy_ecommerce_catalog(request: Request):
    """Eventual-consistency read: Product catalog."""
    return await _forward_request(request, "/api/ecommerce/products")


@app.api_route("/api/ecommerce/products/{product_id:path}", methods=["GET"])
@app.api_route("/api/shop/products/{product_id:path}", methods=["GET"])
async def proxy_ecommerce_product_detail(product_id: str, request: Request):
    """Eventual-consistency read: Product details."""
    return await _forward_request(request, f"/api/ecommerce/products/{product_id}")


@app.api_route("/api/ecommerce/inventory/{product_id:path}", methods=["GET"])
@app.api_route("/api/shop/inventory/{product_id:path}", methods=["GET"])
async def proxy_ecommerce_inventory(product_id: str, request: Request):
    """Strong-consistency read: Authoritative live stock."""
    return await _forward_request(request, f"/api/ecommerce/inventory/{product_id}")


@app.api_route("/api/ecommerce/orders", methods=["GET", "POST"])
@app.api_route("/api/shop/orders", methods=["GET", "POST"])
async def proxy_ecommerce_orders(request: Request):
    """
    POST: Write order (strictly routed to active writer, with idempotency support).
    GET: Strong-consistency read (list orders from active writer).
    """
    return await _forward_request(request, "/api/ecommerce/orders")


@app.api_route("/api/ecommerce/orders/{order_id:path}", methods=["GET", "DELETE"])
@app.api_route("/api/shop/orders/{order_id:path}", methods=["GET", "DELETE"])
async def proxy_ecommerce_single_order(order_id: str, request: Request):
    """
    GET: Strong-consistency read (order fulfillment status).
    DELETE: Write cancellation (strictly routed to active writer).
    """
    return await _forward_request(request, f"/api/ecommerce/orders/{order_id}")
