import pytest
from src.domain.quorum import compute_quorum_consensus


def test_compute_quorum_consensus_outage():
    # 2 out of 3 outage
    votes = ["PRIMARY_OUTAGE", "PRIMARY_OUTAGE", "PRIMARY_HEALTHY"]
    res = compute_quorum_consensus(votes, majority_required=2)
    assert res.consensus_reached is True
    assert res.majority_vote == "PRIMARY_OUTAGE"
    assert res.outage_votes == 2


def test_compute_quorum_consensus_healthy():
    # 2 out of 3 healthy
    votes = ["PRIMARY_HEALTHY", "PRIMARY_HEALTHY", "PRIMARY_OUTAGE"]
    res = compute_quorum_consensus(votes, majority_required=2)
    assert res.consensus_reached is True
    assert res.majority_vote == "PRIMARY_HEALTHY"
    assert res.healthy_votes == 2


def test_compute_quorum_consensus_split():
    # Split: 1 outage, 1 healthy, 1 abstain (no 2-vote majority)
    votes = ["PRIMARY_OUTAGE", "PRIMARY_HEALTHY", "ABSTAIN"]
    res = compute_quorum_consensus(votes, majority_required=2)
    assert res.consensus_reached is False
    assert res.majority_vote == "SPLIT"

