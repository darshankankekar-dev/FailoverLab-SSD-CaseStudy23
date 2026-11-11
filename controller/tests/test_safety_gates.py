import pytest
from src.domain.safety_gates import (
    can_initiate_quorum,
    evaluate_quorum_majority,
    check_standby_readiness,
    check_replication_lag_policy,
    verify_fencing_confirmed,
    verify_no_dual_primary,
    verify_route_operational,
    check_failback_readiness,
)


def test_gate1_can_initiate_quorum():
    # Below threshold -> fail
    res = can_initiate_quorum(consecutive_failures=2, threshold=3)
    assert res.passed is False
    assert "below required threshold" in res.reason

    # At or above threshold -> pass
    res = can_initiate_quorum(consecutive_failures=3, threshold=3)
    assert res.passed is True
    assert "threshold reached" in res.reason


def test_gate2_evaluate_quorum_majority():
    # Insufficient votes (1 out of 3 when 2 required)
    votes = ["PRIMARY_OUTAGE", "PRIMARY_HEALTHY", "PRIMARY_HEALTHY"]
    res = evaluate_quorum_majority(votes, majority_required=2)
    assert res.passed is False
    assert "Insufficient quorum consensus" in res.reason

    # Quorum consensus (2 out of 3)
    votes = ["PRIMARY_OUTAGE", "PRIMARY_OUTAGE", "PRIMARY_HEALTHY"]
    res = evaluate_quorum_majority(votes, majority_required=2)
    assert res.passed is True
    assert "Quorum consensus achieved" in res.reason

    # Unanimous consensus (3 out of 3)
    votes = ["PRIMARY_OUTAGE", "PRIMARY_OUTAGE", "PRIMARY_OUTAGE"]
    res = evaluate_quorum_majority(votes, majority_required=2)
    assert res.passed is True


def test_gate3_check_standby_readiness():
    # Standby healthy -> pass
    assert check_standby_readiness("HEALTHY").passed is True

    # Standby down or degraded -> fail
    res = check_standby_readiness("DOWN")
    assert res.passed is False
    assert "Standby readiness check failed" in res.reason

    res = check_standby_readiness("DEGRADED")
    assert res.passed is False


def test_gate4_check_replication_lag_policy():
    # Nominal lag (0.8s <= 5.0s) -> pass
    assert check_replication_lag_policy(0.8, "STREAMING", 5.0).passed is True

    # High lag (8.4s > 5.0s) -> fail
    res = check_replication_lag_policy(8.4, "DEGRADED", 5.0)
    assert res.passed is False
    assert "Replication lag gate failed" in res.reason
    assert "RPO data loss" in res.reason

    # Severed replication link -> fail
    res = check_replication_lag_policy(0.5, "SEVERED", 5.0)
    assert res.passed is False
    assert "SEVERED" in res.reason


def test_gate5_verify_fencing_confirmed():
    # Still accepts writes -> fail
    res = verify_fencing_confirmed(accepts_writes=True, is_fenced=True)
    assert res.passed is False
    assert "SPLIT-BRAIN" in res.reason

    # Not marked fenced -> fail
    res = verify_fencing_confirmed(accepts_writes=False, is_fenced=False)
    assert res.passed is False
    assert "not been acknowledged" in res.reason

    # Fenced and no writes -> pass
    res = verify_fencing_confirmed(accepts_writes=False, is_fenced=True)
    assert res.passed is True


def test_gate6_verify_no_dual_primary():
    # Both active -> fail (split-brain)
    res = verify_no_dual_primary(region_a_writes=True, region_b_writes=True)
    assert res.passed is False
    assert "CRITICAL SAFETY INVARIANT VIOLATED" in res.reason

    # Only A -> pass
    assert verify_no_dual_primary(region_a_writes=True, region_b_writes=False).passed is True

    # Only B -> pass
    assert verify_no_dual_primary(region_a_writes=False, region_b_writes=True).passed is True

    # Zero writers (e.g. during fencing cutover) -> pass
    assert verify_no_dual_primary(region_a_writes=False, region_b_writes=False).passed is True


def test_gate7_verify_route_operational():
    # Operational -> pass
    res = verify_route_operational(
        active_target="region-b",
        expected_target="region-b",
        propagation_percent=100,
        verification_status="VERIFIED",
    )
    assert res.passed is True

    # Propagation not 100% -> fail
    res = verify_route_operational(
        active_target="region-b",
        expected_target="region-b",
        propagation_percent=50,
        verification_status="VERIFIED",
    )
    assert res.passed is False
    assert "DNS propagation at 50%" in res.reason

    # Verification status failed -> fail
    res = verify_route_operational(
        active_target="region-b",
        expected_target="region-b",
        propagation_percent=100,
        verification_status="FAILED",
    )
    assert res.passed is False
    assert "Route verification failed" in res.reason


def test_gate8_check_failback_readiness():
    # Region A down -> fail
    res = check_failback_readiness(
        region_a_health="DOWN",
        replication_status="SYNCED",
        lag_seconds=0.5,
        acceptable_lag_sec=5.0,
    )
    assert res.passed is False
    assert "Original primary (Region A) is still DOWN" in res.reason

    # Reverse replication lag excessive -> fail
    res = check_failback_readiness(
        region_a_health="HEALTHY",
        replication_status="REVERSED",
        lag_seconds=8.0,
        acceptable_lag_sec=5.0,
    )
    assert res.passed is False
    assert "Reverse replication lag" in res.reason

    # Ready -> pass
    res = check_failback_readiness(
        region_a_health="HEALTHY",
        replication_status="SYNCED",
        lag_seconds=0.5,
        acceptable_lag_sec=5.0,
    )
    assert res.passed is True

