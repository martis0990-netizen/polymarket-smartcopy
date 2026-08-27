from smartcopy.targeted_prehistory import compare_histories


def _row(tx, timestamp="2026-08-27T14:40:00Z"):
    return {
        "condition_id": "0xc",
        "activity_type": "TRADE",
        "source_event_time": timestamp,
        "transaction_hash": tx,
        "side": "BUY",
        "size": 10,
        "usdc_size": 4,
        "asset": "token",
        "outcome": "Up",
        "slug": "slug",
        "observation_mode": "backfill",
    }


def test_compare_histories_requires_exact_identity_overlap() -> None:
    old = [_row("0x1"), _row("0x2")]
    current = [_row("0x0", "2026-08-26T14:47:42Z"), *old]
    result = compare_histories(old, current)
    assert result == {
        "old_rows": 2,
        "extended_rows": 3,
        "overlap_rows": 2,
        "missing_old_rows": 0,
        "new_rows": 1,
    }
