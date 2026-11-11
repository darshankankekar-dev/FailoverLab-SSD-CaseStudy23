from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...database import get_db_session
from ...schemas import PolicyResponse, PolicyUpdateRequest
from ...models import PolicyEntity, ControllerStateEntity
from ...services import log_audit_event

router = APIRouter(tags=["Policy"])


@router.get("/policy", response_model=PolicyResponse)
async def get_policy(session: AsyncSession = Depends(get_db_session)) -> PolicyResponse:
    """Returns the current failover policy and safety thresholds."""
    res = await session.execute(select(PolicyEntity).where(PolicyEntity.id == 1))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Policy configuration not found.")
    return PolicyResponse(
        health_check_interval_sec=p.health_check_interval_sec,
        failure_threshold_consecutive=p.failure_threshold_consecutive,
        quorum_size=p.quorum_size,
        majority_required=p.majority_required,
        acceptable_replication_lag_sec=p.acceptable_replication_lag_sec,
        fencing_duration_sec=p.fencing_duration_sec,
        route_propagation_sec=p.route_propagation_sec,
        route_verification_sec=p.route_verification_sec,
        auto_failover_enabled=p.auto_failover_enabled,
    )


@router.put("/policy", response_model=PolicyResponse)
async def update_policy(
    payload: PolicyUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> PolicyResponse:
    """Dynamically updates failover policy thresholds and logs an audit event."""
    res = await session.execute(select(PolicyEntity).where(PolicyEntity.id == 1))
    p = res.scalar_one()

    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    updates = []
    if payload.health_check_interval_sec is not None:
        p.health_check_interval_sec = payload.health_check_interval_sec
        updates.append(f"healthCheckIntervalSec={payload.health_check_interval_sec}")
    if payload.failure_threshold_consecutive is not None:
        p.failure_threshold_consecutive = payload.failure_threshold_consecutive
        updates.append(f"failureThresholdConsecutive={payload.failure_threshold_consecutive}")
    if payload.quorum_size is not None:
        p.quorum_size = payload.quorum_size
        updates.append(f"quorumSize={payload.quorum_size}")
    if payload.majority_required is not None:
        p.majority_required = payload.majority_required
        updates.append(f"majorityRequired={payload.majority_required}")
    if payload.acceptable_replication_lag_sec is not None:
        p.acceptable_replication_lag_sec = payload.acceptable_replication_lag_sec
        updates.append(f"acceptableReplicationLagSec={payload.acceptable_replication_lag_sec}")
    if payload.fencing_duration_sec is not None:
        p.fencing_duration_sec = payload.fencing_duration_sec
        updates.append(f"fencingDurationSec={payload.fencing_duration_sec}")
    if payload.route_propagation_sec is not None:
        p.route_propagation_sec = payload.route_propagation_sec
        updates.append(f"routePropagationSec={payload.route_propagation_sec}")
    if payload.route_verification_sec is not None:
        p.route_verification_sec = payload.route_verification_sec
        updates.append(f"routeVerificationSec={payload.route_verification_sec}")
    if payload.auto_failover_enabled is not None:
        p.auto_failover_enabled = payload.auto_failover_enabled
        updates.append(f"autoFailoverEnabled={payload.auto_failover_enabled}")

    await log_audit_event(
        session,
        severity="info",
        subsystem="CONTROLLER",
        reason=f"Policy updated: {', '.join(updates)}",
        simulated_time_seconds=c_state.simulated_time_seconds,
    )
    await session.commit()

    return PolicyResponse(
        health_check_interval_sec=p.health_check_interval_sec,
        failure_threshold_consecutive=p.failure_threshold_consecutive,
        quorum_size=p.quorum_size,
        majority_required=p.majority_required,
        acceptable_replication_lag_sec=p.acceptable_replication_lag_sec,
        fencing_duration_sec=p.fencing_duration_sec,
        route_propagation_sec=p.route_propagation_sec,
        route_verification_sec=p.route_verification_sec,
        auto_failover_enabled=p.auto_failover_enabled,
    )

