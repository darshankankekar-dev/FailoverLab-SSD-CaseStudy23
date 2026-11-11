"""
Simulated Quorum Consensus Engine
Academic prototype implementing 3 simulated independent observers.
Explicitly not claiming a production Paxos or Raft consensus.
"""
from typing import List, Dict, Any, NamedTuple


class QuorumConsensusResult(NamedTuple):
    consensus_reached: bool
    majority_vote: str
    outage_votes: int
    healthy_votes: int
    abstain_votes: int
    details: Dict[str, Any]


def compute_quorum_consensus(
    voter_votes: List[str], majority_required: int = 2
) -> QuorumConsensusResult:
    """
    Evaluates votes from independent observers.
    Requires at least majority_required matching votes to form consensus.
    """
    outage_count = voter_votes.count("PRIMARY_OUTAGE")
    healthy_count = voter_votes.count("PRIMARY_HEALTHY")
    abstain_count = voter_votes.count("ABSTAIN")

    if outage_count >= majority_required:
        return QuorumConsensusResult(
            consensus_reached=True,
            majority_vote="PRIMARY_OUTAGE",
            outage_votes=outage_count,
            healthy_votes=healthy_count,
            abstain_votes=abstain_count,
            details={"majority_required": majority_required, "winner": "PRIMARY_OUTAGE"},
        )
    elif healthy_count >= majority_required:
        return QuorumConsensusResult(
            consensus_reached=True,
            majority_vote="PRIMARY_HEALTHY",
            outage_votes=outage_count,
            healthy_votes=healthy_count,
            abstain_votes=abstain_count,
            details={"majority_required": majority_required, "winner": "PRIMARY_HEALTHY"},
        )
    else:
        return QuorumConsensusResult(
            consensus_reached=False,
            majority_vote="SPLIT",
            outage_votes=outage_count,
            healthy_votes=healthy_count,
            abstain_votes=abstain_count,
            details={"majority_required": majority_required, "winner": "NO_CONSENSUS"},
        )

