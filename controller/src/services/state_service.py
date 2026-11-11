from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import (
    RegionEntity,
    PolicyEntity,
    ControllerStateEntity,
    ReplicationEntity,
    RouteEntity,
    QuorumVoterEntity,
)
from ..schemas import (
    StateResponse,
    MetricsResponse,
    RegionResponse,
    PolicyResponse,
    ReplicationStateModel,
    RouteStateModel,
    QuorumVoterModel,
    TelemetryMetricsModel,
    ControllerState,
    RegionId,
    ReplicationStatus,
    RouteVerificationStatus,
    QuorumVote,
)
from ..schemas.state import TruthfulFailoverMetricsModel
from .metrics_tracker import metrics_tracker


async def get_full_state(session: AsyncSession) -> StateResponse:
    """Aggregates and projects complete system state for the UI and external callers."""
    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    res_policy = await session.execute(select(PolicyEntity).where(PolicyEntity.id == 1))
    policy = res_policy.scalar_one()

    res_a = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()

    res_b = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    region_b = res_b.scalar_one()

    res_rep = await session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    replication = res_rep.scalar_one()

    res_route = await session.execute(select(RouteEntity).where(RouteEntity.id == 1))
    route = res_route.scalar_one()

    res_voters = await session.execute(select(QuorumVoterEntity))
    voters = list(res_voters.scalars().all())

    # Derive telemetry metrics
    is_healthy = c_state.current_state in ["HEALTHY", "SECONDARY_ACTIVE"]
    is_failing = c_state.current_state in ["PRIMARY_SUSPECTED", "QUORUM_CHECK", "FENCING_PRIMARY", "PROMOTING_STANDBY"]
    success_rate = 99.98 if is_healthy else (14.5 if is_failing else 85.0)
    p95_latency = 18 if (is_healthy and c_state.active_region == "region-a") else (32 if is_healthy else 850)

    est_rpo_loss = (
        int(replication.lag_seconds * 2450)
        if (replication.status == "DEGRADED" or replication.lag_seconds > policy.acceptable_replication_lag_sec)
        else 0
    )

    telemetry = TelemetryMetricsModel(
        uptime_seconds=c_state.simulated_time_seconds,
        total_client_rps=2450,
        overall_success_rate=success_rate,
        client_error_rate=float(f"{100.0 - success_rate:.2f}"),
        p95_latency_ms=p95_latency,
        total_failovers_count=1 if c_state.fencing_epoch > 101 else 0,
        last_failover_duration_ms=6200 if c_state.active_region == "region-b" else None,
        estimated_rpo_loss_tx=est_rpo_loss,
    )

    return StateResponse(
        controller_state=ControllerState(c_state.current_state),
        active_region=RegionId(c_state.active_region),
        fencing_epoch=c_state.fencing_epoch,
        simulated_time_seconds=c_state.simulated_time_seconds,
        wall_clock_start_time=c_state.updated_at.isoformat() if c_state.updated_at else datetime.now(timezone.utc).isoformat(),
        consecutive_failures=c_state.consecutive_failures,
        last_health_check_sim_time=c_state.last_health_check_sim_time,
        blocked_reason=c_state.blocked_reason,
        blocked_at_state=ControllerState(c_state.blocked_at_state) if c_state.blocked_at_state else None,
        is_sequence_in_progress=c_state.is_sequence_in_progress,
        route_retry_count=c_state.route_retry_count,
        persisted_intent=c_state.persisted_intent,
        is_paused_interrupted=c_state.is_paused_interrupted,
        region_a=RegionResponse(
            id=RegionId(region_a.id),
            name=region_a.name,
            cloud_zone=region_a.cloud_zone,
            role=region_a.role,
            health=region_a.health,
            status=region_a.status,
            accepts_writes=region_a.accepts_writes,
            ingress_traffic_percent=region_a.ingress_traffic_percent,
            ingress_rps=region_a.ingress_rps,
            app_servers_healthy=region_a.app_servers_healthy,
            app_servers_total=region_a.app_servers_total,
            active_connections=region_a.active_connections,
            iops=region_a.iops,
            fencing_epoch=region_a.fencing_epoch,
            is_fenced=region_a.is_fenced,
        ),
        region_b=RegionResponse(
            id=RegionId(region_b.id),
            name=region_b.name,
            cloud_zone=region_b.cloud_zone,
            role=region_b.role,
            health=region_b.health,
            status=region_b.status,
            accepts_writes=region_b.accepts_writes,
            ingress_traffic_percent=region_b.ingress_traffic_percent,
            ingress_rps=region_b.ingress_rps,
            app_servers_healthy=region_b.app_servers_healthy,
            app_servers_total=region_b.app_servers_total,
            active_connections=region_b.active_connections,
            iops=region_b.iops,
            fencing_epoch=region_b.fencing_epoch,
            is_fenced=region_b.is_fenced,
        ),
        policy=PolicyResponse(
            health_check_interval_sec=policy.health_check_interval_sec,
            failure_threshold_consecutive=policy.failure_threshold_consecutive,
            quorum_size=policy.quorum_size,
            majority_required=policy.majority_required,
            acceptable_replication_lag_sec=policy.acceptable_replication_lag_sec,
            fencing_duration_sec=policy.fencing_duration_sec,
            route_propagation_sec=policy.route_propagation_sec,
            route_verification_sec=policy.route_verification_sec,
            auto_failover_enabled=policy.auto_failover_enabled,
        ),
        replication=ReplicationStateModel(
            status=ReplicationStatus(replication.status),
            lag_seconds=replication.lag_seconds,
            lag_ms=replication.lag_ms,
            bandwidth_mbps=replication.bandwidth_mbps,
            packet_loss_percent=replication.packet_loss_percent,
            pending_bytes=replication.pending_bytes,
            bytes_transferred=replication.bytes_transferred,
            mode=replication.mode,
        ),
        route=RouteStateModel(
            active_target=RegionId(route.active_target),
            dns_ttl_seconds=route.dns_ttl_seconds,
            propagation_percent=route.propagation_percent,
            verification_status=RouteVerificationStatus(route.verification_status),
        ),
        voters=[
            QuorumVoterModel(
                id=v.id,
                name=v.name,
                location=v.location,
                vote=QuorumVote(v.vote),
                latency_ms=v.latency_ms,
            )
            for v in voters
        ],
        telemetry=telemetry,
    )


async def get_metrics(session: AsyncSession) -> MetricsResponse:
    """Returns focused operational and telemetry metrics."""
    full_state = await get_full_state(session)
    summary = metrics_tracker.get_summary()
    healthy_count = sum(1 for r in [full_state.region_a, full_state.region_b] if r.health.upper() == "HEALTHY")
    truthful = TruthfulFailoverMetricsModel(
        failover_attempts_total=summary["failover_attempts_total"],
        failover_successes_total=summary["failover_successes_total"],
        failover_blocked_total=summary["failover_blocked_total"],
        failover_blocked_by_gate=summary["failover_blocked_by_gate"],
        route_update_attempts_total=summary["route_update_attempts_total"],
        route_update_successes_total=summary["route_update_successes_total"],
        route_update_errors_total=summary["route_update_errors_total"],
        healthy_regions_count=healthy_count,
        last_lab_recovery_seconds=summary["last_lab_recovery_seconds"],
        is_simulated_lab_metric=True,
    )
    return MetricsResponse(
        controller_state=full_state.controller_state,
        active_region=full_state.active_region,
        fencing_epoch=full_state.fencing_epoch,
        consecutive_failures=full_state.consecutive_failures,
        replication_lag_seconds=full_state.replication.lag_seconds,
        replication_status=full_state.replication.status,
        route_target=full_state.route.active_target,
        route_verification=full_state.route.verification_status,
        telemetry=full_state.telemetry,
        truthful_metrics=truthful,
    )

