import pytest
from src.domain.fencing import advance_epoch, is_token_valid


def test_advance_epoch_monotonicity():
    epoch = 101
    next_epoch = advance_epoch(epoch)
    assert next_epoch == 102
    assert advance_epoch(next_epoch) == 103


def test_is_token_valid():
    # Stale token must be rejected
    assert is_token_valid(incoming_epoch=101, authoritative_epoch=102) is False

    # Current or future token is valid
    assert is_token_valid(incoming_epoch=102, authoritative_epoch=102) is True
    assert is_token_valid(incoming_epoch=103, authoritative_epoch=102) is True

