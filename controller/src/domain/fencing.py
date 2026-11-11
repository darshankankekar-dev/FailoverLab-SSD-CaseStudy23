"""
Fencing Epoch and Token Management
Implements generation-based fencing tokens to prevent split-brain writes.
Reference: Martin Kleppmann, 'Designing Data-Intensive Applications'
"""
from typing import Tuple


def advance_epoch(current_epoch: int) -> int:
    """Monotonically increments fencing epoch."""
    if current_epoch < 1:
        return 101
    return current_epoch + 1


def is_token_valid(incoming_epoch: int, authoritative_epoch: int) -> bool:
    """
    Validates whether an incoming write token is authoritative.
    Any request carrying a token lower than the authoritative epoch is rejected as stale.
    """
    return incoming_epoch >= authoritative_epoch

