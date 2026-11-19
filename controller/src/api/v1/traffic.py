import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db_session
from ...schemas.traffic import (
    TrafficSummaryResponse,
    TrafficTimeseriesResponse,
    RegionalTrafficResponse,
    TrafficEventsResponse,
)
from ...services.traffic_service import traffic_service

logger = logging.getLogger("controller.api.traffic")

router = APIRouter(prefix="/traffic", tags=["Traffic Telemetry"])


@router.get("/summary", response_model=TrafficSummaryResponse)
async def get_traffic_summary() -> TrafficSummaryResponse:
    """
    Returns real-time customer and upstream traffic summary.
    Includes ingress/egress bytes/sec, cumulative totals, request rate,
    latency percentiles, error breakdown, and telemetry freshness.
    Distinguishes measured zero traffic from missing/unavailable telemetry.
    """
    return traffic_service.get_traffic_summary()


@router.get("/timeseries", response_model=TrafficTimeseriesResponse)
async def get_traffic_timeseries(
    time_range_seconds: Optional[int] = Query(default=None, ge=10, le=86400, description="Time range in seconds (default 300s/5m)"),
    range_seconds: Optional[int] = Query(default=None, ge=10, le=86400, description="Alias for time_range_seconds"),
    step_seconds: int = Query(default=1, ge=1, le=300, description="Sampling bucket interval in seconds"),
    session: AsyncSession = Depends(get_db_session),
) -> TrafficTimeseriesResponse:
    """
    Returns historical traffic time-series samples for graphs and charts.
    Supports flexible time ranges and step sampling.
    """
    effective_range = time_range_seconds if time_range_seconds is not None else (range_seconds if range_seconds is not None else 300)
    return await traffic_service.get_traffic_timeseries(
        session=session, time_range_seconds=effective_range, step_seconds=step_seconds
    )


@router.get("/regions", response_model=RegionalTrafficResponse)
async def get_regional_traffic() -> RegionalTrafficResponse:
    """
    Returns measured upstream traffic counters and throughput for all five regions:
    Mumbai (region-a), Singapore (region-b), Frankfurt (region-c),
    Virginia (region-d), and São Paulo (region-e).
    """
    return traffic_service.get_regional_traffic()


@router.get("/recent-events", response_model=TrafficEventsResponse)
@router.get("/events", response_model=TrafficEventsResponse)
async def get_recent_traffic_events(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Page size (max 100)"),
    traffic_source: Optional[str] = Query(None, description="Filter by traffic source"),
    client_region: Optional[str] = Query(None, description="Filter by client region"),
    served_region: Optional[str] = Query(None, description="Filter by served region"),
    status_code: Optional[int] = Query(None, description="Filter by HTTP status code"),
    request_type: Optional[str] = Query(None, description="Filter by request type"),
) -> TrafficEventsResponse:
    """
    Returns recent bounded request traffic events with pagination (newest first).
    Supports filtering by traffic source, regions, status code, and request type.
    Sanitized to never expose passwords, personal data, or customer secrets.
    """
    return traffic_service.get_traffic_events(
        page=page,
        page_size=page_size,
        traffic_source=traffic_source,
        client_region=client_region,
        served_region=served_region,
        status_code=status_code,
        request_type=request_type,
    )


@router.get("/stream")
async def stream_traffic_telemetry(
    request: Request,
    max_events: Optional[int] = Query(None, description="Optional maximum number of events to stream before closing"),
) -> StreamingResponse:
    """
    Server-Sent Events (SSE) stream for live Controller UI traffic observability.
    Emits 'traffic_metric' and 'traffic_event' messages in real-time.
    Cleanly handles client disconnects.
    """
    async def event_generator():
        queue = await traffic_service.subscribe_sse()
        events_emitted = 0
        try:
            # Send initial state snapshot immediately upon connection
            initial_summary = traffic_service.get_traffic_summary().model_dump(mode="json")
            yield f"event: connect\ndata: {{\"connected\": true, \"summary\": {json.dumps(initial_summary)}}}\n\n"
            events_emitted += 1
            if max_events is not None and events_emitted >= max_events:
                return

            # Stream incoming events or send heartbeat if idle
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                    event_type = msg.get("event", "traffic_metric")
                    data_str = json.dumps(msg.get("data", {}))
                    yield f"event: {event_type}\ndata: {data_str}\n\n"
                    events_emitted += 1
                    if max_events is not None and events_emitted >= max_events:
                        break
                except (asyncio.TimeoutError, TimeoutError):
                    if await request.is_disconnected():
                        break
                    # Heartbeat comment to keep HTTP connection alive through proxies
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await traffic_service.unsubscribe_sse(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
