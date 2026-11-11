import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import (
    RegionEntity,
    PolicyEntity,
    ControllerStateEntity,
    QuorumVoterEntity,
)
from .audit_service import log_audit_event
from .clients import regional_client
from .metrics_tracker import metrics_tracker

logger = logging.getLogger("controller.services.health_monitor")


async def evaluate_primary_health_probes(session: AsyncSession, simulated_time_delta: float = 2.0) -> None:
    """
    Evaluates health checks for Region A and debounces consecutive failures.
    Suppresses false-positives if health returns before threshold.
    """
    res_state = await session.execute(select(ControllerStateEntity).where(ControllerStateEntity.id == 1))
    c_state = res_state.scalar_one()

    res_policy = await session.execute(select(PolicyEntity).where(PolicyEntity.id == 1))
    policy = res_policy.scalar_one()

    res_a = await session.execute(select(RegionEntity).where(RegionEntity.id == "region-a"))
    region_a = res_a.scalar_one()

    res_voters = await session.execute(select(QuorumVoterEntity))
    voters = list(res_voters.scalars().all())

    c_state.simulated_time_seconds += simulated_time_delta
    c_state.last_health_check_sim_time = c_state.simulated_time_seconds

    # Real or simulated probe to Region A
    probe = await regional_client.get_health("region-a")
    is_failing = (region_a.health != "HEALTHY") or (probe.get("status") == "DOWN")

    if not is_failing:
        # False-positive recovery check:
        if c_state.current_state == "PRIMARY_SUSPECTED":
            prev = c_state.current_state
            c_state.current_state = "HEALTHY"
            failures = c_state.consecutive_failures
            c_state.consecutive_failures = 0
            for v in voters:
                v.vote = "PRIMARY_HEALTHY"
            await log_audit_event(
                session,
                severity="success",
                subsystem="SAFETY_GATE",
                reason=f"False Positive Suppressed: Region A probe succeeded before failure threshold ({failures}/{policy.failure_threshold_consecutive}). Restored to HEALTHY without failover.",
                simulated_time_seconds=c_state.simulated_time_seconds,
                transition=f"{prev} -> HEALTHY",
            )
        else:
            c_state.consecutive_failures = 0
            for v in voters:
                v.vote = "PRIMARY_HEALTHY"
        await session.commit()
        return

    # Failing probe
    if c_state.current_state in ["HEALTHY", "PRIMARY_SUSPECTED"]:
        c_state.consecutive_failures += 1
        failures = c_state.consecutive_failures
        logger.warning(
            f"[HEALTH_PROBE_FAILED] Region A probe failed ({failures}/{policy.failure_threshold_consecutive})",
            extra={"consecutive_failures": failures, "threshold": policy.failure_threshold_consecutive}
        )

        if failures < policy.failure_threshold_consecutive:
            c_state.current_state = "PRIMARY_SUSPECTED"
            await log_audit_event(
                session,
                severity="warn",
                subsystem="CONTROLLER",
                reason=f"Synthetic health probe failed ({failures}/{policy.failure_threshold_consecutive}). Region A suspected. Holding in debounce window to filter transient jitter.",
                simulated_time_seconds=c_state.simulated_time_seconds,
                transition="HEALTHY -> PRIMARY_SUSPECTED" if failures == 1 else None,
            )
        else:
            # Threshold reached: Advance to QUORUM_CHECK and record observer votes
            c_state.current_state = "QUORUM_CHECK"
            metrics_tracker.record_outage_detected()
            logger.critical(
                f"[OUTAGE_CONFIRMED] Consecutive failure threshold reached ({failures}/{policy.failure_threshold_consecutive}). Outage detected.",
                extra={"consecutive_failures": failures, "threshold": policy.failure_threshold_consecutive}
            )
            for v in voters:
                v.vote = "PRIMARY_OUTAGE"

            await log_audit_event(
                session,
                severity="critical",
                subsystem="QUORUM",
                reason=f"Consecutive failure threshold reached ({failures}/{policy.failure_threshold_consecutive}). Gathering independent health monitor votes from 3 observers.",
                simulated_time_seconds=c_state.simulated_time_seconds,
                transition="PRIMARY_SUSPECTED -> QUORUM_CHECK",
            )

    await session.commit()

