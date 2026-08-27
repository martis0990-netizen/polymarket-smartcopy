from smartcopy.correction_overlay import WalletFill
from smartcopy.prospective_receipts import _opposite_flags, _prospective_summary


def test_prospective_summary_drops_stage3a_contract_and_primary_labels() -> None:
    metrics = {"rows": {"total": 1}, "size": {"total": 2}, "notional": {"total": 3}}
    decoded = {
        "completeness": {"source_rows": 1, "schema_corrected_uniquely_matched_rows": 1},
        "schema_corrected_secondary": {
            "all_fills": metrics,
            "opposite_fills": metrics,
            "non_opposite_fills": metrics,
        },
        "per_market": {
            "condition": {
                "slug": "btc-updown-5m-1",
                "schema_corrected_roles": metrics,
                "outcomes": {"Up": {"schema_corrected_roles": metrics}},
            }
        },
        "interpretation_limit": "maker role is not placement duration",
        "contract_frozen_commit": "stage3a",
        "primary_mechanism": {"verdict": "INCONCLUSIVE"},
    }
    summary = _prospective_summary(decoded)
    assert summary["decoder_semantics"] == "CTF_EXCHANGE_V2_FEE_AWARE"
    assert summary["per_market"]["condition"]["roles"] == metrics
    assert "contract_frozen_commit" not in summary
    assert "primary_mechanism" not in summary


def test_duplicate_transaction_fills_share_strict_prior_opposite_state() -> None:
    def fill(number, second, outcome, size, tx):
        return WalletFill(
            condition_id="condition",
            source_second=second,
            source_event_time=f"1970-01-01T00:00:{second:02d}Z",
            outcome=outcome,
            price=0.5,
            size=size,
            notional=size * 0.5,
            asset_id=str(number),
            transaction_hash=tx,
        )

    fills = [
        fill(1, 1, "Up", 10, "0xfirst"),
        fill(2, 2, "Down", 2, "0xsweep"),
        fill(2, 2, "Down", 3, "0xsweep"),
    ]
    flagged = _opposite_flags(fills)
    assert [flag for _fill, flag in flagged] == [False, True, True]
