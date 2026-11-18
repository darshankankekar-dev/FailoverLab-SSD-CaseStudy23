from typing import Optional
import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...database import get_db_session
from ...config import Settings
from ...models import (
    RegionEntity,
    ReplicationEntity,
    RouteEntity,
    QuorumVoterEntity,
    ControllerStateEntity,
)
from ...schemas import StateResponse
from ...services import log_audit_event, get_full_state
from ...services.clients import replication_client
from ...domain.registry import REGION_REGISTRY

router = APIRouter(prefix="/chaos", tags=["Internal Chaos"])
settings = Settings()


@router.post("/primary-outage", response_model=StateResponse)
async def inject_primary_outage(session: AsyncSession = Depends(get_db_session)) -> StateResponse:
    """Injects Primary Outage: crashes Region A (Mumbai) storage daemon."""
    res_a = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()
    region_a.health = "DOWN"
    region_a.iops = 0

    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    await log_audit_event(
        session,
        severity="critical",
        subsystem="CHAOS",
        reason="Primary Outage Injected: PostgreSQL/Aurora storage daemon collapsed in Mumbai (ap-south-1).",
        simulated_time_seconds=c_state.simulated_time_seconds,
    )
    await session.commit()
    return await get_full_state(session)


@router.post("/recover-primary", response_model=StateResponse)
async def recover_primary(session: AsyncSession = Depends(get_db_session)) -> StateResponse:
    """Restores Region A back online (rejoins as standby if Region B is active)."""
    res_a = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()

    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    region_a.health = "HEALTHY"
    if c_state.current_state == "SECONDARY_ACTIVE":
        region_a.role = "STANDBY"
        region_a.accepts_writes = False
        region_a.ingress_traffic_percent = 0
        region_a.iops = 0
        c_state.current_state = "PRIMARY_RECOVERING"

    await log_audit_event(
        session,
        severity="info",
        subsystem="CHAOS",
        reason="Primary Storage Restored: Mumbai instance rebooted and passed hardware self-test.",
        simulated_time_seconds=c_state.simulated_time_seconds,
    )
    await session.commit()
    return await get_full_state(session)


@router.post("/partition", response_model=StateResponse)
async def inject_partition(session: AsyncSession = Depends(get_db_session)) -> StateResponse:
    """Injects Cross-Region WAN partition (severing replication and splitting quorum)."""
    res_rep = await session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    rep = res_rep.scalar_one()
    rep.status = "SEVERED"

    res_voters = await session.execute(select(QuorumVoterEntity))
    for v in res_voters.scalars().all():
        if v.id == "voter-1":
            v.vote = "PRIMARY_HEALTHY"  # Isolated in Mumbai
        else:
            v.vote = "PRIMARY_OUTAGE"

    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    await log_audit_event(
        session,
        severity="critical",
        subsystem="NETWORK",
        reason="Cross-Region WAN Partition Injected: Inter-region fiber connection severed. Replication pipeline interrupted.",
        simulated_time_seconds=c_state.simulated_time_seconds,
    )
    await session.commit()
    return await get_full_state(session)


@router.post("/replication-lag", response_model=StateResponse)
async def inject_replication_lag(
    lag_seconds: float = Query(default=8.4, ge=0.1, le=60.0),
    session: AsyncSession = Depends(get_db_session),
) -> StateResponse:
    """Spikes asynchronous replication lag."""
    res_rep = await session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    rep = res_rep.scalar_one()
    rep.status = "DEGRADED"
    rep.lag_seconds = lag_seconds
    rep.lag_ms = int(lag_seconds * 1000)

    # Forward to replication worker
    await replication_client.set_delay(lag_seconds)

    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    await log_audit_event(
        session,
        severity="warn",
        subsystem="DATABASE",
        reason=f"Replication Throttling Injected: Replication lag spiked to {lag_seconds:.1f}s.",
        simulated_time_seconds=c_state.simulated_time_seconds,
    )
    await session.commit()
    return await get_full_state(session)


@router.post("/standby-unready", response_model=StateResponse)
async def inject_standby_unready(session: AsyncSession = Depends(get_db_session)) -> StateResponse:
    """Corrupts standby storage in Region B."""
    res_b = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-b"))
    region_b = res_b.scalar_one()
    region_b.health = "DOWN"

    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    await log_audit_event(
        session,
        severity="critical",
        subsystem="CHAOS",
        reason="Standby Readiness Broken: Region B (Singapore) simulated storage volume corrupted.",
        simulated_time_seconds=c_state.simulated_time_seconds,
    )
    await session.commit()
    return await get_full_state(session)


@router.post("/route-failure", response_model=StateResponse)
async def inject_route_failure(session: AsyncSession = Depends(get_db_session)) -> StateResponse:
    """Injects route verification probe failure."""
    res_route = await session.execute(select(RouteEntity).where(RouteEntity.id == 1))
    route = res_route.scalar_one()
    route.verification_status = "FAILED"

    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    await log_audit_event(
        session,
        severity="critical",
        subsystem="DNS",
        reason="Route Verification Failure Injected: Anycast BGP routing table drop induced.",
        simulated_time_seconds=c_state.simulated_time_seconds,
    )
    await session.commit()
    return await get_full_state(session)


@router.post("/regional-lag", response_model=StateResponse)
async def inject_regional_lag(
    region_id: str = Query(..., description="Target region ID"),
    lag_seconds: float = Query(default=8.4, ge=0.0, le=60.0),
    session: AsyncSession = Depends(get_db_session),
) -> StateResponse:
    """Sets replication lag for a specific region."""
    res = await session.execute(select(RegionEntity).where(RegionEntity.id == region_id))
    reg = res.scalar_one_or_none()
    if reg:
        reg.replication_lag_seconds = lag_seconds
        await session.commit()

    # Forward to replication worker selectively
    await replication_client.set_delay(lag_seconds, destination=region_id)

    return await get_full_state(session)


@router.post("/regional-health", response_model=StateResponse)
async def inject_regional_health(
    region_id: str = Query(..., description="Target region ID"),
    health: str = Query(default="HEALTHY", description="HEALTHY, DEGRADED, or DOWN"),
    session: AsyncSession = Depends(get_db_session),
) -> StateResponse:
    """Sets health status for a specific region."""
    res = await session.execute(select(RegionEntity).where(RegionEntity.id == region_id))
    reg = res.scalar_one_or_none()
    if reg:
        reg.health = health.upper()
        if health.upper() == "DOWN":
            reg.status = "DOWN"
            reg.app_servers_healthy = 0
        else:
            reg.status = "healthy"
            reg.app_servers_healthy = reg.app_servers_total
        await session.commit()
    return await get_full_state(session)


@router.post("/regional-sequence", response_model=StateResponse)
async def inject_regional_sequence(
    region_id: str = Query(..., description="Target region ID"),
    applied_sequence: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> StateResponse:
    """Sets applied replication sequence for a specific region."""
    res = await session.execute(select(RegionEntity).where(RegionEntity.id == region_id))
    reg = res.scalar_one_or_none()
    if reg:
        reg.applied_sequence = applied_sequence
        await session.commit()
    return await get_full_state(session)


@router.post("/replication-pause", response_model=StateResponse)
async def pause_replication_target(
    destination: Optional[str] = Query(None, description="Optional target destination region (e.g., 'region-b')"),
    session: AsyncSession = Depends(get_db_session),
) -> StateResponse:
    """Pauses replication globally or to a specific target standby region."""
    res_rep = await session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    rep = res_rep.scalar_one_or_none()
    if rep:
        rep.status = "DEGRADED"

    # Forward to replication worker if reachable
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            url = f"{settings.replication_worker_url}/controls/pause"
            if destination:
                url = f"{url}?destination={destination}"
            await client.post(url)
    except Exception:
        pass

    target_desc = f"target '{destination}'" if destination else "all destinations"
    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    await log_audit_event(
        session,
        severity="warn",
        subsystem="REPLICATION",
        reason=f"Replication paused for {target_desc} via administrative chaos panel.",
        simulated_time_seconds=c_state.simulated_time_seconds,
    )
    await session.commit()
    return await get_full_state(session)


@router.post("/replication-resume", response_model=StateResponse)
async def resume_replication_target(
    destination: Optional[str] = Query(None, description="Optional target destination region (e.g., 'region-b')"),
    session: AsyncSession = Depends(get_db_session),
) -> StateResponse:
    """Resumes replication globally or to a specific target standby region."""
    res_rep = await session.execute(select(ReplicationEntity).where(ReplicationEntity.id == 1))
    rep = res_rep.scalar_one_or_none()
    if rep:
        rep.status = "STREAMING"

    # Forward to replication worker if reachable
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            url = f"{settings.replication_worker_url}/controls/resume"
            if destination:
                url = f"{url}?destination={destination}"
            await client.post(url)
    except Exception:
        pass

    target_desc = f"target '{destination}'" if destination else "all destinations"
    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    await log_audit_event(
        session,
        severity="info",
        subsystem="REPLICATION",
        reason=f"Replication resumed for {target_desc} via administrative chaos panel.",
        simulated_time_seconds=c_state.simulated_time_seconds,
    )
    await session.commit()
    return await get_full_state(session)


@router.post("/regional-wan-latency", response_model=StateResponse)
async def configure_regional_wan_latency(
    region_id: str = Query(..., description="Target region ID"),
    latency_ms: int = Query(default=30, ge=1, le=2000),
    session: AsyncSession = Depends(get_db_session),
) -> StateResponse:
    """Configures simulated WAN latency for a specific region."""
    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()
    await log_audit_event(
        session,
        severity="info",
        subsystem="NETWORK",
        reason=f"Simulated WAN latency for {region_id} configured to {latency_ms}ms.",
        simulated_time_seconds=c_state.simulated_time_seconds,
    )
    await session.commit()
    return await get_full_state(session)


@router.post("/reset-regional", response_model=StateResponse)
async def reset_regional_health(
    region_id: str = Query(..., description="Target region ID to restore"),
    session: AsyncSession = Depends(get_db_session),
) -> StateResponse:
    """Restores a single region back to baseline health, lag, and sequence."""
    res = await session.execute(select(RegionEntity).where(RegionEntity.id == region_id))
    reg = res.scalar_one_or_none()
    if reg:
        reg.health = "HEALTHY"
        reg.status = "healthy"
        reg.app_servers_healthy = reg.app_servers_total
        reg.replication_lag_seconds = 0.8
        reg_def = REGION_REGISTRY.get(region_id)
        if reg_def:
            reg.iops = reg_def.baseline_iops

        # If replication worker reachable, resume replication
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                await client.post(f"{settings.replication_worker_url}/controls/resume?destination={region_id}")
        except Exception:
            pass

        res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
        c_state = res_state.scalar_one()
        await log_audit_event(
            session,
            severity="info",
            subsystem="CHAOS",
            reason=f"Region {region_id} restored to healthy baseline.",
            simulated_time_seconds=c_state.simulated_time_seconds,
        )
        await session.commit()
    return await get_full_state(session)

