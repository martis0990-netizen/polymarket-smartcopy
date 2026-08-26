from __future__ import annotations

import json
from pathlib import Path

import pytest

from smartcopy.executable_state_join import JoinDataError, run_join


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _wallet(
    *,
    side: str = "BUY",
    asset: str = "token-a",
    price: float = 0.40,
    source: str = "2026-08-26T12:00:00Z",
    observed: str = "2026-08-26T12:00:02Z",
    mode: str = "live_observed",
) -> dict:
    return {
        "proxy_wallet": "0xabc",
        "source_event_time": source,
        "first_observed_time": observed,
        "observation_delay_seconds": 2.0,
        "observation_mode": mode,
        "condition_id": "condition-1",
        "activity_type": "TRADE",
        "side": side,
        "size": 10.0,
        "usdc_size": 4.0,
        "price": price,
        "asset": asset,
        "transaction_hash": "0xtx",
        "title": "test",
        "slug": "test",
        "event_slug": "test-event",
        "outcome": "Up",
        "raw": {},
    }


def _market(
    *,
    token: str = "token-a",
    event_type: str = "market_snapshot",
    ts: str = "2026-08-26T12:00:02.500000Z",
    receive: str = "2026-08-26T12:00:03Z",
    metrics: dict | None = None,
    price: float | None = None,
    size: float | None = None,
) -> dict:
    return {
        "venue": "polymarket",
        "event_type": event_type,
        "ts": ts,
        "receive_ts": receive,
        "instrument": token,
        "side": "unknown",
        "price": price,
        "size": size,
        "order_id": None,
        "actor_id": None,
        "sequence": None,
        "metrics": metrics or {},
        "raw": {},
    }


def _run(tmp_path: Path, wallets: list[dict], markets: list[dict]):
    wallet_path = tmp_path / "live_activity.jsonl"
    market_path = tmp_path / "events.jsonl"
    output = tmp_path / "out"
    _write(wallet_path, wallets)
    _write(market_path, markets)
    manifest = run_join(
        wallet_activity_path=wallet_path,
        market_events_path=market_path,
        output_dir=output,
    )
    rows = [
        json.loads(line)
        for line in (output / "executable_state_join.jsonl").read_text().splitlines()
    ]
    return manifest, rows


def test_buy_ignores_pre_observation_quote_and_uses_first_post_observation_ask(tmp_path: Path) -> None:
    markets = [
        _market(
            receive="2026-08-26T12:00:01Z",
            metrics={"best_ask_price": 0.41, "best_ask_size": 10.0},
        ),
        _market(
            receive="2026-08-26T12:00:03Z",
            metrics={"best_ask_price": 0.45, "best_ask_size": 5.0},
        ),
    ]
    manifest, rows = _run(tmp_path, [_wallet()], markets)

    assert manifest["joined_rows"] == 1
    assert rows[0]["status"] == "JOINED"
    assert rows[0]["market_line_number"] == 2
    assert rows[0]["executable_price"] == 0.45
    assert rows[0]["executable_size"] == 5.0
    assert rows[0]["observation_to_state_seconds"] == 1.0
    assert rows[0]["source_to_state_seconds"] == 3.0
    assert rows[0]["deterioration"] == pytest.approx(0.05)
    assert rows[0]["deterioration_bps"] == pytest.approx(1250.0)


def test_sell_uses_bid_and_signed_deterioration_is_positive_when_bid_falls(tmp_path: Path) -> None:
    manifest, rows = _run(
        tmp_path,
        [_wallet(side="SELL", price=0.60)],
        [
            _market(
                metrics={
                    "best_bid_price": 0.55,
                    "best_bid_size": 8.0,
                    "best_ask_price": 0.90,
                    "best_ask_size": 8.0,
                }
            )
        ],
    )

    assert manifest["joined_rows"] == 1
    assert rows[0]["executable_price"] == 0.55
    assert rows[0]["deterioration"] == pytest.approx(0.05)
    assert rows[0]["deterioration_bps"] == pytest.approx(0.05 / 0.60 * 10_000)


def test_join_is_exact_token_id_only(tmp_path: Path) -> None:
    _, rows = _run(
        tmp_path,
        [_wallet(asset="token-a")],
        [
            _market(
                token="token-b",
                receive="2026-08-26T12:00:02.100000Z",
                metrics={"best_ask_price": 0.41, "best_ask_size": 99.0},
            ),
            _market(
                token="token-a",
                receive="2026-08-26T12:00:04Z",
                metrics={"best_ask_price": 0.50, "best_ask_size": 3.0},
            ),
        ],
    )
    assert rows[0]["market_line_number"] == 2
    assert rows[0]["executable_price"] == 0.50


def test_book_delta_can_supply_size_only_when_delta_price_is_current_bbo(tmp_path: Path) -> None:
    _, rows = _run(
        tmp_path,
        [_wallet()],
        [
            _market(
                receive="2026-08-26T12:00:03Z",
                metrics={"best_ask_price": 0.48},
            ),
            _market(
                event_type="book_delta",
                receive="2026-08-26T12:00:04Z",
                metrics={"best_ask_price": 0.48},
                price=0.47,
                size=12.0,
            ),
            _market(
                event_type="book_delta",
                receive="2026-08-26T12:00:05Z",
                metrics={"best_ask_price": 0.49},
                price=0.49,
                size=7.0,
            ),
        ],
    )

    assert rows[0]["market_line_number"] == 3
    assert rows[0]["executable_price"] == 0.49
    assert rows[0]["executable_size"] == 7.0


def test_zero_size_book_removal_is_non_executable_not_corruption(tmp_path: Path) -> None:
    _, rows = _run(
        tmp_path,
        [_wallet()],
        [
            _market(
                event_type="book_delta",
                receive="2026-08-26T12:00:03Z",
                metrics={"best_ask_price": 0.48},
                price=0.48,
                size=0.0,
            ),
            _market(
                event_type="book_delta",
                receive="2026-08-26T12:00:04Z",
                metrics={"best_ask_price": 0.49},
                price=0.49,
                size=2.0,
            ),
        ],
    )
    assert rows[0]["market_line_number"] == 2
    assert rows[0]["executable_size"] == 2.0


def test_missing_post_observation_liquidity_is_not_fabricated(tmp_path: Path) -> None:
    manifest, rows = _run(
        tmp_path,
        [_wallet()],
        [
            _market(
                receive="2026-08-26T12:00:03Z",
                metrics={"best_ask_price": 0.45},
            )
        ],
    )
    assert manifest["joined_rows"] == 0
    assert manifest["no_executable_state_rows"] == 1
    assert rows[0]["status"] == "NO_EXECUTABLE_STATE"
    assert rows[0]["executable_price"] is None


def test_matching_token_receive_time_regression_fails_closed(tmp_path: Path) -> None:
    wallet_path = tmp_path / "live_activity.jsonl"
    market_path = tmp_path / "events.jsonl"
    _write(wallet_path, [_wallet(observed="2026-08-26T12:00:10Z")])
    _write(
        market_path,
        [
            _market(receive="2026-08-26T12:00:05Z", metrics={}),
            _market(receive="2026-08-26T12:00:04Z", metrics={}),
        ],
    )
    with pytest.raises(JoinDataError, match="receive_ts regressed"):
        run_join(
            wallet_activity_path=wallet_path,
            market_events_path=market_path,
            output_dir=tmp_path / "out",
        )


def test_backfill_wallet_rows_are_rejected(tmp_path: Path) -> None:
    wallet_path = tmp_path / "live_activity.jsonl"
    market_path = tmp_path / "events.jsonl"
    _write(wallet_path, [_wallet(mode="backfill")])
    _write(market_path, [])
    with pytest.raises(JoinDataError, match="observation_mode must be live_observed"):
        run_join(
            wallet_activity_path=wallet_path,
            market_events_path=market_path,
            output_dir=tmp_path / "out",
        )


def test_outputs_are_immutable_and_refuse_overwrite(tmp_path: Path) -> None:
    wallet_path = tmp_path / "live_activity.jsonl"
    market_path = tmp_path / "events.jsonl"
    output = tmp_path / "out"
    _write(wallet_path, [_wallet()])
    _write(
        market_path,
        [_market(metrics={"best_ask_price": 0.45, "best_ask_size": 1.0})],
    )
    run_join(wallet_activity_path=wallet_path, market_events_path=market_path, output_dir=output)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        run_join(wallet_activity_path=wallet_path, market_events_path=market_path, output_dir=output)
