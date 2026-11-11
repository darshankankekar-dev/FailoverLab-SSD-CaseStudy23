from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db_session
from ..models import (
    RegionEntity,
    ControllerStateEntity,
    ReplicationEntity,
    RouteEntity,
)
from ..services.metrics_tracker import metrics_tracker

router = APIRouter(tags=["Prometheus Metrics"])


@router.get("/metrics", response_class=Response)
@router.get("/api/v1/metrics/prometheus", response_class=Response)
async def get_prometheus_metrics(session: AsyncSession = Depends(get_db_session)) -> Response:
    """
    Exposes Prometheus-compatible plaintext metric exposition format.
    Accurately distinguishes between measured system states and simulated lab metrics.
    """
    # 1. Fetch live system entities
    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    res_a = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()

    res_b = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    region_b = res_b.scalar_one()

    res_rep = await session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    replication = res_rep.scalar_one()

    res_route = await session.execute(select(RouteEntity).where(RouteEntity.id == 1))
    route = res_route.scalar_one()

    # Calculate healthy regions count
    healthy_count = sum(1 for r in [region_a, region_b] if r.health.upper() == "HEALTHY")

    tracker_summary = metrics_tracker.get_summary()

    lines = [
        "# HELP failoverlab_healthy_regions Number of regions currently reporting healthy status",
        "# TYPE failoverlab_healthy_regions gauge",
        f"failoverlab_healthy_regions {healthy_count}",
        "",
        "# HELP failoverlab_consecutive_failed_health_checks Consecutive failed health check probes against primary",
        "# TYPE failoverlab_consecutive_failed_health_checks gauge",
        f"failoverlab_consecutive_failed_health_checks {c_state.consecutive_failures}",
        "",
        "# HELP failoverlab_active_region Binary indicator of currently active primary region",
        "# TYPE failoverlab_active_region gauge",
        f'failoverlab_active_region{{region="region-a"}} {1 if c_state.active_region == "region-a" else 0}',
        f'failoverlab_active_region{{region="region-b"}} {1 if c_state.active_region == "region-b" else 0}',
        "",
        "# HELP failoverlab_fencing_epoch Authoritative monotonic fencing epoch generation",
        "# TYPE failoverlab_fencing_epoch gauge",
        f"failoverlab_fencing_epoch {c_state.fencing_epoch}",
        "",
        "# HELP failoverlab_replication_lag_seconds Measured replication lag in seconds",
        "# TYPE failoverlab_replication_lag_seconds gauge",
        f"failoverlab_replication_lag_seconds {replication.lag_seconds}",
        "",
        "# HELP failoverlab_replication_pending_bytes Current estimated unreplicated bytes",
        "# TYPE failoverlab_replication_pending_bytes gauge",
        f"failoverlab_replication_pending_bytes {replication.pending_bytes}",
        "",
        "# HELP failoverlab_failover_transitions_total Total failover attempts by outcome",
        "# TYPE failoverlab_failover_transitions_total counter",
        f'failoverlab_failover_transitions_total{{outcome="attempt"}} {tracker_summary["failover_attempts_total"]}',
        f'failoverlab_failover_transitions_total{{outcome="success"}} {tracker_summary["failover_successes_total"]}',
        f'failoverlab_failover_transitions_total{{outcome="blocked"}} {tracker_summary["failover_blocked_total"]}',
        "",
        "# HELP failoverlab_route_updates_total Total dynamic route updates requested by status",
        "# TYPE failoverlab_route_updates_total counter",
        f'failoverlab_route_updates_total{{status="attempt"}} {tracker_summary["route_update_attempts_total"]}',
        f'failoverlab_route_updates_total{{status="success"}} {tracker_summary["route_update_successes_total"]}',
        f'failoverlab_route_updates_total{{status="error"}} {tracker_summary["route_update_errors_total"]}',
        "",
    ]

    # Include lab recovery time if measured
    if tracker_summary["last_lab_recovery_seconds"] is not None:
        lines.extend([
            "# HELP failoverlab_lab_recovery_seconds Wall-clock duration from confirmed outage detection to verified recovery in lab test",
            "# TYPE failoverlab_lab_recovery_seconds gauge",
            f'failoverlab_lab_recovery_seconds{{environment="simulated_lab"}} {tracker_summary["last_lab_recovery_seconds"]}',
            "",
        ])

    # Modelled / simulated telemetry metrics with clear labels
    lines.extend([
        "# HELP failoverlab_modelled_client_rps Modelled simulated ingress requests per second",
        "# TYPE failoverlab_modelled_client_rps gauge",
        'failoverlab_modelled_client_rps{mode="simulated"} 2450',
        "",
        "# HELP failoverlab_modelled_success_rate_percent Modelled overall success rate percentage",
        "# TYPE failoverlab_modelled_success_rate_percent gauge",
        'failoverlab_modelled_success_rate_percent{mode="simulated"} 99.98',
        "",
    ])

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
