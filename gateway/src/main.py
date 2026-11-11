import time
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional, Any, Dict

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, Header, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .routing import RouteTable
from .logging_config import (
    setup_structured_logging,
    correlation_id_ctx,
    transition_id_ctx,
    region_id_ctx,
)
from .metrics import gateway_metrics

setup_structured_logging(service_name="gateway", log_level=settings.log_level)
logger = logging.getLogger("gateway.main")

route_table = RouteTable(
    default_target=settings.default_target,
    region_a_url=settings.region_a_url,
    region_b_url=settings.region_b_url,
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
    yield
    await http_client.aclose()


app = FastAPI(
    title="FailoverLab Ingress Gateway",
    description="Dynamic routing ingress proxy for multi-region active-passive architecture (Case Study 23)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_and_request_id_middleware(request: Request, call_next):
    """
    Assigns request ID, tracks latency, and logs request/response metadata
    without ever exposing credentials, secrets, or internal tokens.
    """
    request_id = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:10]}"
    request.state.request_id = request_id
    correlation_id_ctx.set(request_id)

    trans_id = request.headers.get("X-Transition-ID")
    if trans_id:
        transition_id_ctx.set(trans_id)

    region_id_ctx.set(route_table.active_target)

    start_time = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    # Record metrics
    gateway_metrics.record_request(response.status_code, elapsed_ms)

    # Log metadata: request ID, method, path, selected region, response status, latency
    logger.info(
        f"[REQ: {request_id}] method={request.method} path={request.url.path} "
        f"region={route_table.active_target} status={response.status_code} "
        f"latency_ms={elapsed_ms:.2f}ms"
    )

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Correlation-ID"] = request_id
    response.headers["X-Routed-To-Region"] = route_table.active_target
    if trans_id:
        response.headers["X-Transition-ID"] = trans_id
    return response


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
    }


@app.get("/api/v1/route", tags=["Routing"])
async def get_route() -> Dict[str, Any]:
    """Returns current active route table, regional roles, TTL, and propagation status."""
    return route_table.get_route_state()


@app.get("/metrics", response_class=Response, tags=["Metrics"])
async def prometheus_metrics() -> Response:
    """Exposes gateway Prometheus plaintext metric exposition format."""
    body = gateway_metrics.to_prometheus(route_table.active_target, route_table.route_epoch)
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/api/v1/metrics", tags=["Metrics"])
async def json_metrics() -> Dict[str, Any]:
    """Returns truthful measured JSON operational metrics for the gateway."""
    metrics = gateway_metrics.get_metrics()
    metrics["active_target"] = route_table.active_target
    metrics["route_epoch"] = route_table.route_epoch
    return metrics


# =========================================================================
# Internal Control Operations (Protected)
# =========================================================================

class RoutingUpdateRequest(BaseModel):
    target_region: str = Field(..., description="Target region ID (e.g., 'region-a' or 'region-b')")
    target_role: Optional[str] = Field(default="ACTIVE", description="Role to assign to target ('ACTIVE' or 'STANDBY')")
    dns_ttl_seconds: Optional[int] = Field(default=2, ge=0, le=300)
    propagation_percent: Optional[int] = Field(default=100, ge=0, le=100)


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


@app.post(
    "/internal/routing/reconcile",
    tags=["Internal Routing"],
    dependencies=[Depends(verify_internal_auth)],
)
async def trigger_reconciliation() -> Dict[str, Any]:
    """
    Forces gateway to query the controller and reconcile its routing table.
    """
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
# Application Proxy Endpoints (/api/records and /api/data/records)
# =========================================================================

async def _forward_request(request: Request, path: str) -> Response:
    """
    Forwards client requests to the active region.
    Enforces writer safety: Ordinary writes are NEVER sent to a standby region.
    Preserves status codes, headers, and bodies from the upstream regional service.
    Handles connection errors and timeouts cleanly.
    """
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0))

    # Writer safety invariant check
    if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
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

    active_url = route_table.get_active_url()
    target_endpoint = f"{active_url}{path}"

    body = await request.body()
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length"}
    }

    try:
        backend_resp = await http_client.request(
            method=request.method,
            url=target_endpoint,
            params=request.query_params,
            headers=forward_headers,
            content=body,
        )

        # Preserve status code, headers and response body
        return Response(
            content=backend_resp.content,
            status_code=backend_resp.status_code,
            headers=dict(backend_resp.headers),
            media_type=backend_resp.headers.get("content-type"),
        )
    except httpx.ConnectError as ce:
        logger.error(f"Cannot reach active region at {target_endpoint}: {ce}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "Active region unavailable",
                "active_target": route_table.active_target,
                "target_url": active_url,
                "message": f"Could not connect to {active_url}. Region may be down or experiencing an outage.",
            },
        )
    except httpx.TimeoutException as te:
        logger.error(f"Timeout connecting to active region at {target_endpoint}: {te}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "error": "Upstream timeout",
                "active_target": route_table.active_target,
                "target_url": active_url,
                "message": f"Request to active region '{route_table.active_target}' timed out.",
            },
        )
    except Exception as exc:
        logger.error(f"Error proxying {request.method} to {target_endpoint}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "Gateway proxy error",
                "active_target": route_table.active_target,
                "message": str(exc),
            },
        )


@app.api_route("/api/records", methods=["GET", "POST"])
@app.api_route("/api/data/records", methods=["GET", "POST"])
async def proxy_records_collection(request: Request):
    return await _forward_request(request, "/api/records")


@app.api_route("/api/records/{key:path}", methods=["GET", "DELETE", "PUT"])
@app.api_route("/api/data/records/{key:path}", methods=["GET", "DELETE", "PUT"])
async def proxy_single_record(key: str, request: Request):
    return await _forward_request(request, f"/api/records/{key}")
