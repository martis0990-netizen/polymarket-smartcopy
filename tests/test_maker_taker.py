from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from smartcopy.correction_overlay import WalletFill
from smartcopy.maker_taker import (
    MakerTakerError,
    PolygonReceiptAPI,
    classify_opposite_fills,
    collect_receipts,
    decode_rows,
    summarize,
)

WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
EXCHANGE = "0xe111180000d2663c0091e4f400237545b87b996b"
ORDER_FILLED = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"
ORDERS_MATCHED = "0x174b3811690657c217184f89418266767c87e4805d09680c39fc9c031c0cab7c"


def _hash(number: int) -> str:
    return f"0x{number:064x}"


def _fill(
    number: int,
    *,
    second: int = 100,
    outcome: str = "Up",
    size: float = 2.0,
    price: float = 0.4,
    condition: str = "condition",
) -> WalletFill:
    return WalletFill(
        condition_id=condition,
        source_second=second,
        source_event_time=f"1970-01-01T00:01:{second - 60:02d}Z",
        outcome=outcome,
        price=price,
        size=size,
        notional=size * price,
        asset_id=str(10_000 + number),
        transaction_hash=_hash(number),
    )


def _word(value: int) -> str:
    return f"{value:064x}"


def _address_topic(address: str) -> str:
    return "0x" + "0" * 24 + address[2:]


def _order_log(
    fill: WalletFill,
    *,
    order_hash: str,
    maker_amount: int | None = None,
    fee: int = 0,
) -> dict[str, Any]:
    usdc = round(fill.notional * 1_000_000) if maker_amount is None else maker_amount
    tokens = round(fill.size * 1_000_000)
    return {
        "address": EXCHANGE,
        "topics": [
            ORDER_FILLED,
            order_hash,
            _address_topic(WALLET),
            _address_topic("0x" + "12" * 20),
        ],
        "data": "0x" + "".join(
            [
                _word(0),
                _word(int(fill.asset_id)),
                _word(usdc),
                _word(tokens),
                _word(fee),
                _word(0),
                _word(0),
            ]
        ),
        "logIndex": "0x3",
        "transactionHash": fill.transaction_hash,
    }


def _matched_log(fill: WalletFill, *, order_hash: str) -> dict[str, Any]:
    return {
        "address": EXCHANGE,
        "topics": [ORDERS_MATCHED, order_hash, _address_topic(WALLET)],
        "data": "0x" + "".join(
            [
                _word(0),
                _word(int(fill.asset_id)),
                _word(round(fill.notional * 1_000_000)),
                _word(round(fill.size * 1_000_000)),
            ]
        ),
        "logIndex": "0x4",
        "transactionHash": fill.transaction_hash,
    }


def _envelope(fill: WalletFill, logs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "request": {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getTransactionReceipt",
            "params": [fill.transaction_hash],
        },
        "response": {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "transactionHash": fill.transaction_hash,
                "status": "0x1",
                "blockNumber": "0x10",
                "blockHash": _hash(999),
                "logs": logs,
            },
        },
    }


def test_collect_receipts_accepts_unordered_batch_and_binds_ids() -> None:
    hashes = [_hash(1), _hash(2)]

    def transport(url: str, payload: Any, headers: dict[str, str]) -> Any:
        assert url == "https://rpc.example"
        assert headers["User-Agent"]
        if isinstance(payload, dict):
            return {"jsonrpc": "2.0", "id": 0, "result": "0x89"}
        return [
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "transactionHash": request["params"][0],
                    "status": "0x1",
                    "blockNumber": "0x1",
                    "blockHash": _hash(100 + request["id"]),
                    "logs": [],
                },
            }
            for request in reversed(payload)
        ]

    chain_id, envelopes = collect_receipts(
        PolygonReceiptAPI("https://rpc.example", transport=transport),
        hashes,
        batch_size=2,
    )
    assert chain_id == 137
    assert len(envelopes) == 3
    assert [item["request"]["id"] for item in envelopes] == [0, 1, 2]


def test_collect_receipts_rejects_missing_batch_response() -> None:
    def transport(url: str, payload: Any, headers: dict[str, str]) -> Any:
        del url, headers
        if isinstance(payload, dict):
            return {"jsonrpc": "2.0", "id": 0, "result": "0x89"}
        return []

    with pytest.raises(MakerTakerError, match="response ids mismatch"):
        collect_receipts(
            PolygonReceiptAPI("https://rpc.example", transport=transport),
            [_hash(1)],
        )


def test_order_hash_in_orders_matched_is_the_taker_role_test() -> None:
    maker_fill = _fill(1)
    taker_fill = _fill(2)
    maker_order = _hash(101)
    taker_order = _hash(102)
    rows = decode_rows(
        [maker_fill, taker_fill],
        [
            _envelope(maker_fill, [_order_log(maker_fill, order_hash=maker_order)]),
            _envelope(
                taker_fill,
                [
                    _order_log(taker_fill, order_hash=taker_order),
                    _matched_log(taker_fill, order_hash=taker_order),
                ],
            ),
        ],
    )
    assert [row["role"] for row in rows] == ["MAKER", "TAKER"]
    assert [row["schema_corrected_role"] for row in rows] == ["MAKER", "TAKER"]
    assert rows[0]["decoded_price"] == pytest.approx(0.4)


def test_amount_mismatch_is_ambiguous_and_forces_inconclusive() -> None:
    fill = _fill(1)
    rows = decode_rows(
        [fill],
        [_envelope(fill, [_order_log(fill, order_hash=_hash(101), maker_amount=123)])],
    )
    assert rows[0]["role"] == "AMBIGUOUS"
    result = summarize(rows, market_slugs={fill.condition_id: "btc-updown-5m-100"})
    assert result["primary_mechanism"]["verdict"] == "INCONCLUSIVE"
    assert result["completeness"]["ambiguous_rows"] == 1


def test_fee_inclusive_buy_cost_is_reported_only_as_post_hoc_schema_repair() -> None:
    fill = replace(_fill(1), notional=0.82)
    order_hash = _hash(101)
    maker_amount = 800_000
    rows = decode_rows(
        [fill],
        [
            _envelope(
                fill,
                [
                    _order_log(
                        fill,
                        order_hash=order_hash,
                        maker_amount=maker_amount,
                        fee=20_000,
                    ),
                    _matched_log(fill, order_hash=order_hash),
                ],
            )
        ],
    )
    assert rows[0]["role"] == "AMBIGUOUS"
    assert rows[0]["schema_corrected_role"] == "TAKER"
    assert rows[0]["schema_correction_used"] is True
    result = summarize(rows, market_slugs={fill.condition_id: "btc-updown-5m-100"})
    assert result["primary_mechanism"]["verdict"] == "INCONCLUSIVE"
    assert (
        result["schema_corrected_secondary"]["verdict_under_original_80_20_gate"]
        == "ACTIVE_TAKER_DOMINANT"
    )


def test_opposite_classification_uses_strict_prior_second() -> None:
    fills = [
        _fill(1, second=100, outcome="Up", size=10),
        _fill(2, second=100, outcome="Down", size=5),
        _fill(3, second=120, outcome="Down", size=2),
    ]
    flags = classify_opposite_fills(fills)
    assert flags[_hash(1)] is False
    assert flags[_hash(2)] is False
    assert flags[_hash(3)] is True


def test_notional_gate_is_frozen_at_eighty_twenty() -> None:
    rows = [
        {
            "role": "MAKER",
            "schema_corrected_role": "MAKER",
            "source_size": 10.0,
            "source_notional": 80.0,
            "opposite_fill": False,
            "condition_id": "c",
            "outcome": "Up",
        },
        {
            "role": "TAKER",
            "schema_corrected_role": "TAKER",
            "source_size": 10.0,
            "source_notional": 20.0,
            "opposite_fill": True,
            "condition_id": "c",
            "outcome": "Down",
        },
    ]
    result = summarize(rows, market_slugs={"c": "btc-updown-5m-100"})
    assert result["primary_mechanism"]["maker_notional_share"] == pytest.approx(0.8)
    assert result["primary_mechanism"]["verdict"] == "PASSIVE_MAKER_DOMINANT"
