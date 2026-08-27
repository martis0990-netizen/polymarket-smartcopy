import hashlib
import json
from datetime import datetime, timezone

import pytest

from smartcopy.models import ObservationMode, WalletActivity
from smartcopy.prospective_settlement import (
    ProspectiveSettlementError,
    allocate_terminal,
    parse_resolution,
    run_analysis,
)

ECONOMICS_SHA = "8c848d320e2cc53e931fb408d493166f7ccb784416a56bcc4e8bdfdb745fb32f"


def _economics(condition="0xc", slug="btc-updown-5m-1"):
    return {
        "condition_id": condition,
        "slug": slug,
        "asset": "BTC",
        "window_seconds": 300,
        "matched_size": "10",
        "fee_adjusted_pair_cost_total": "9.5",
        "residuals": {
            "Up": {"size": "4", "fee_adjusted_cost": "1.2"},
            "Down": {"size": "1", "fee_adjusted_cost": "0.7"},
        },
    }


def _market(condition="0xc", slug="btc-updown-5m-1", prices='["1", "0"]'):
    return {
        "conditionId": condition,
        "slug": slug,
        "closed": True,
        "outcomes": '["Up", "Down"]',
        "outcomePrices": prices,
    }


def test_resolution_parses_json_arrays_and_exact_winner() -> None:
    result = parse_resolution(_market(), expected_slug="btc-updown-5m-1", expected_condition_id="0xc")
    assert result["resolution_status"] == "RESOLVED"
    assert result["winning_outcome"] == "Up"
    unresolved = parse_resolution(
        _market(prices='["0.6", "0.4"]'),
        expected_slug="btc-updown-5m-1",
        expected_condition_id="0xc",
    )
    assert unresolved["resolution_status"] == "UNRESOLVED_OR_AMBIGUOUS"


def test_terminal_allocation_pays_pair_and_winning_residual() -> None:
    resolution = parse_resolution(_market(), expected_slug="btc-updown-5m-1", expected_condition_id="0xc")
    row = allocate_terminal(_economics(), resolution)
    assert row["bounded_acquisition_cost"] == "11.4"
    assert row["bounded_terminal_value"] == "14"
    assert row["bounded_terminal_edge"] == "2.6"
    assert row["residuals"]["Down"]["terminal_value"] == "0"
    assert row["largest_residual_aligned_with_winner"] is True


def test_unresolved_market_gets_no_terminal_allocation() -> None:
    resolution = parse_resolution(
        _market(prices='["0.5", "0.5"]'),
        expected_slug="btc-updown-5m-1",
        expected_condition_id="0xc",
    )
    row = allocate_terminal(_economics(), resolution)
    assert row["bounded_terminal_value"] is None
    assert row["bounded_terminal_edge"] is None


def test_gamma_identity_mismatch_fails_closed() -> None:
    with pytest.raises(ProspectiveSettlementError, match="condition ID mismatch"):
        parse_resolution(_market(condition="0xwrong"), expected_slug="btc-updown-5m-1", expected_condition_id="0xc")


class _ActivityClient:
    def collect_activity_range(self, user, *, start, end, activity_type):
        assert user == "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
        assert (start, end, activity_type) == (1787841769, 1787855700, "MERGE,REDEEM")
        timestamp = datetime.fromtimestamp(start, tz=timezone.utc)
        return (
            WalletActivity(
                proxy_wallet=user,
                source_event_time=timestamp,
                first_observed_time=datetime.now(timezone.utc),
                condition_id="0xc0",
                activity_type="REDEEM",
                side=None,
                size=14,
                usdc_size=14,
                price=None,
                asset=None,
                transaction_hash="0xtx",
                title=None,
                slug="btc-updown-5m-0",
                event_slug=None,
                outcome="Up",
                observation_mode=ObservationMode.BACKFILL,
                raw={"type": "REDEEM"},
            ),
        )


def test_run_analysis_is_sha_bound_and_refuses_overwrite(tmp_path, monkeypatch) -> None:
    rows = [_economics(f"0xc{i}", f"btc-updown-5m-{i}") for i in range(5)]
    economics = tmp_path / "conditions.jsonl"
    economics.write_text("".join(json.dumps(row) + "\n" for row in rows))
    digest = hashlib.sha256(economics.read_bytes()).hexdigest()
    monkeypatch.setattr("smartcopy.prospective_settlement._ECONOMICS_SHA", digest)

    def gamma(url, _headers):
        slug = url.rsplit("/", 1)[-1]
        index = int(slug.rsplit("-", 1)[-1])
        return _market(f"0xc{index}", slug)

    output = tmp_path / "settlement"
    result = run_analysis(
        economics_conditions_path=economics,
        expected_economics_sha256=digest,
        output_dir=output,
        code_commit="a" * 40,
        client=_ActivityClient(),
        gamma_transport=gamma,
    )
    assert result["summary"]["resolved_conditions"] == 5
    assert result["summary"]["activity"]["target_rows"] == 1
    assert (output / "prospective_settlement_manifest.json").is_file()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        run_analysis(
            economics_conditions_path=economics,
            expected_economics_sha256=digest,
            output_dir=output,
            code_commit="a" * 40,
            client=_ActivityClient(),
            gamma_transport=gamma,
        )
