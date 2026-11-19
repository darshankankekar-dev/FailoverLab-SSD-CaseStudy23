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
    DestinationReplicationModel,
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
from ..domain.registry import get_region_definition
from .clients import replication_client


async def get_full_state(session: AsyncSession) -> StateResponse:
    """Aggregates and projects complete system state for the UI and external callers."""
    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    res_policy = await session.execute(select(PolicyEntity).where(PolicyEntity.id == 1))
    policy = res_policy.scalar_one()

    res_all_regions = await session.execute(select(RegionEntity).order_by(RegionEntity.id))
    region_entities = {r.id: r for r in res_all_regions.scalars().all()}

    # Query live replication worker telemetry if reachable
    worker_status = await replication_client.get_status()
    worker_destinations = (worker_status or {}).get("destinations", {})
    worker_source_seq = (worker_status or {}).get("last_replicated_sequence_id", 0)

    def to_region_resp(entity: RegionEntity) -> RegionResponse:
        reg_def = get_region_definition(entity.id)
        latency = reg_def.nominal_latency_ms if reg_def else 30

        is_active = (entity.id == c_state.active_region)
        dest_telemetry = worker_destinations.get(entity.id)

        if is_active:
            applied_seq = worker_source_seq if worker_source_seq > 0 else getattr(entity, "applied_sequence", 0)
            lag_sec = 0.0
        elif dest_telemetry:
            applied_seq = dest_telemetry.get("applied_sequence", getattr(entity, "applied_sequence", 0))
            lag_sec = dest_telemetry.get("time_lag_seconds", getattr(entity, "replication_lag_seconds", 0.8))
        else:
            applied_seq = getattr(entity, "applied_sequence", 0)
            lag_sec = getattr(entity, "replication_lag_seconds", 0.8)

        # Allow manual database override for chaos experiments
        if not is_active and getattr(entity, "replication_lag_seconds", 0.8) != 0.8:
            lag_sec = entity.replication_lag_seconds
        if not is_active and getattr(entity, "applied_sequence", 0) > 0:
            applied_seq = entity.applied_sequence

        return RegionResponse(
            id=RegionId(entity.id),
            name=entity.name,
            cloud_zone=entity.cloud_zone,
            role=entity.role,
            health=entity.health,
            status=entity.status,
            accepts_writes=entity.accepts_writes,
            ingress_traffic_percent=entity.ingress_traffic_percent,
            ingress_rps=entity.ingress_rps,
            app_servers_healthy=entity.app_servers_healthy,
            app_servers_total=entity.app_servers_total,
            active_connections=entity.active_connections,
            iops=entity.iops,
            fencing_epoch=entity.fencing_epoch,
            is_fenced=entity.is_fenced,
            applied_sequence=applied_seq,
            replication_lag_seconds=lag_sec,
            latency_ms=latency,
        )

    all_region_responses = [to_region_resp(r) for r in region_entities.values()]
    region_a_resp = to_region_resp(region_entities["region-a"]) if "region-a" in region_entities else None
    region_b_resp = to_region_resp(region_entities["region-b"]) if "region-b" in region_entities else None
    region_c_resp = to_region_resp(region_entities["region-c"]) if "region-c" in region_entities else None
    region_d_resp = to_region_resp(region_entities["region-d"]) if "region-d" in region_entities else None
    region_e_resp = to_region_resp(region_entities["region-e"]) if "region-e" in region_entities else None

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
        region_a=region_a_resp,
        region_b=region_b_resp,
        region_c=region_c_resp,
        region_d=region_d_resp,
        region_e=region_e_resp,
        regions=all_region_responses,
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
            destinations={
                r_id: DestinationReplicationModel(
                    region_id=r_id,
                    status=(
                        "DEGRADED"
                        if (
                            getattr(region_entities[r_id], "replication_lag_seconds", 0.8) > policy.acceptable_replication_lag_sec
                            or (worker_destinations.get(r_id, {}).get("time_lag_seconds", 0.8) > policy.acceptable_replication_lag_sec)
                        )
                        else (
                            worker_destinations.get(r_id, {}).get("status")
                            or (replication.status if replication.status != "STREAMING" else "STREAMING")
                        )
                    ),
                    lag_seconds=round(
                        getattr(region_entities[r_id], "replication_lag_seconds")
                        if getattr(region_entities[r_id], "replication_lag_seconds", 0.8) != 0.8
                        else float(worker_destinations.get(r_id, {}).get("time_lag_seconds", replication.lag_seconds)),
                        2,
                    ),
                    lag_ms=int(
                        (
                            getattr(region_entities[r_id], "replication_lag_seconds")
                            if getattr(region_entities[r_id], "replication_lag_seconds", 0.8) != 0.8
                            else float(worker_destinations.get(r_id, {}).get("time_lag_seconds", replication.lag_seconds))
                        ) * 1000
                    ),
                    applied_sequence=(
                        getattr(region_entities[r_id], "applied_sequence")
                        if getattr(region_entities[r_id], "applied_sequence", 0) > 0
                        else int(worker_destinations.get(r_id, {}).get("applied_sequence", 0))
                    ),
                    source_highest_sequence=int(
                        worker_destinations.get(r_id, {}).get("source_sequence", worker_source_seq)
                    ),
                    sequence_lag=int(
                        worker_destinations.get(r_id, {}).get("sequence_lag", 0)
                    ),
                    time_lag_seconds=round(
                        getattr(region_entities[r_id], "replication_lag_seconds")
                        if getattr(region_entities[r_id], "replication_lag_seconds", 0.8) != 0.8
                        else float(worker_destinations.get(r_id, {}).get("time_lag_seconds", replication.lag_seconds)),
                        2,
                    ),
                    retry_count=int(worker_destinations.get(r_id, {}).get("retry_count", 0)),
                    consecutive_failures=int(worker_destinations.get(r_id, {}).get("consecutive_failures", 0)),
                    is_simulated_lag=bool(
                        worker_destinations.get(r_id, {}).get("is_simulated_lag", False)
                        or getattr(region_entities[r_id], "replication_lag_seconds", 0.8) != 0.8
                    ),
                    injected_delay_sec=float(worker_destinations.get(r_id, {}).get("injected_delay_sec", 0.0)),
                )
                for r_id in region_entities.keys()
                if r_id != c_state.active_region
            },
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
    healthy_count = sum(1 for r in (full_state.regions or [full_state.region_a, full_state.region_b]) if r and r.health.upper() == "HEALTHY")
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

