from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from smartcopy.correction_overlay import (
    CorrectionOverlayError,
    MarketSpec,
    MarketTrade,
    PolymarketTradeTapeAPI,
    TapePoint,
    WalletFill,
    analyze_fills,
    build_independent_tape,
    collect_market_rows,
    load_wallet_evidence,
    market_spec,
    normalize_market_rows,
    run_study,
    summarize,
)

WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
CONDITION = "0xcondition"


def _wallet_row(
    *,
    second: int,
    outcome: str,
    price: float,
    size: float,
    transaction_hash: str,
) -> dict:
    return {
        "proxy_wallet": WALLET,
        "source_event_time": f"1970-01-01T00:{second // 60:02d}:{second % 60:02d}Z",
        "first_observed_time": "1970-01-01T00:03:20Z",
        "observation_mode": "live_observed",
        "condition_id": CONDITION,
        "activity_type": "TRADE",
        "side": "BUY",
        "size": size,
        "usdc_size": size * price,
        "price": price,
        "asset": f"asset-{outcome}",
        "transaction_hash": transaction_hash,
        "title": "Bitcoin Up or Down",
        "slug": "btc-updown-5m-100",
        "outcome": outcome,
    }


def _public_trade(
    *,
    second: int,
    outcome: str,
    price: float,
    size: float = 10.0,
    wallet: str = "0xother",
    transaction_hash: str | None = None,
) -> dict:
    return {
        "proxyWallet": wallet,
        "side": "BUY",
        "asset": f"asset-{outcome}",
        "conditionId": CONDITION,
        "size": size,
        "price": price,
        "timestamp": second,
        "outcome": outcome,
        "transactionHash": transaction_hash or f"tx-{second}-{outcome}-{wallet}",
    }


def _fill(second: int, outcome: str, *, size: float = 10.0, price: float = 0.5) -> WalletFill:
    return WalletFill(
        condition_id=CONDITION,
        source_second=second,
        source_event_time=f"1970-01-01T00:{second // 60:02d}:{second % 60:02d}Z",
        outcome=outcome,
        price=price,
        size=size,
        notional=size * price,
        asset_id=f"asset-{outcome}",
        transaction_hash=f"wallet-{second}-{outcome}-{size}",
    )


def _spec() -> MarketSpec:
    return market_spec(
        condition_id=CONDITION,
        slug="btc-updown-5m-100",
        title="Bitcoin Up or Down",
    )


def test_market_spec_freezes_canonical_window() -> None:
    spec = _spec()
    assert spec.asset == "BTC"
    assert spec.horizon == "5m"
    assert spec.window_start == 100
    assert spec.window_end == 400
    with pytest.raises(CorrectionOverlayError, match="unsupported market slug"):
        market_spec(condition_id="c", slug="btc-updown-10m-100", title="bad")


def test_wallet_evidence_is_sha_bound_and_same_second_precision(tmp_path: Path) -> None:
    path = tmp_path / "wallet.jsonl"
    path.write_text(json.dumps(_wallet_row(second=120, outcome="Up", price=0.4, size=2, transaction_hash="w")) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence = load_wallet_evidence(path, expected_sha256=digest)
    assert len(evidence.rows) == 1
    assert evidence.rows[0].source_second == 120
    with pytest.raises(CorrectionOverlayError, match="SHA256 mismatch"):
        load_wallet_evidence(path, expected_sha256="0" * 64)


def test_market_collection_paginates_and_fails_closed_at_cap() -> None:
    calls: list[int] = []

    def transport(url: str, headers: dict[str, str]) -> list[dict]:
        del headers
        offset = int(parse_qs(urlparse(url).query)["offset"][0])
        calls.append(offset)
        return [_public_trade(second=110 + offset, outcome="Up", price=0.5)] if offset < 2 else []

    api = PolymarketTradeTapeAPI(transport=transport)
    rows, requests = collect_market_rows(api, [CONDITION], page_size=1, max_offset=2)
    assert calls == [0, 1, 2]
    assert len(rows) == 2
    assert [item["row_count"] for item in requests] == [1, 1, 0]

    def always_full(url: str, headers: dict[str, str]) -> list[dict]:
        del url, headers
        return [_public_trade(second=110, outcome="Up", price=0.5)]

    with pytest.raises(CorrectionOverlayError, match="final addressable page"):
        collect_market_rows(
            PolymarketTradeTapeAPI(transport=always_full),
            [CONDITION],
            page_size=1,
            max_offset=1,
        )


def test_normalization_is_exact_and_tape_excludes_source_wallet() -> None:
    rows = [
        {
            "requested_condition_id": CONDITION,
            "request_offset": 0,
            "response_index": 0,
            "row": _public_trade(second=110, outcome="Up", price=0.7, size=10),
        },
        {
            "requested_condition_id": CONDITION,
            "request_offset": 0,
            "response_index": 1,
            "row": _public_trade(second=110, outcome="Down", price=0.2, size=10),
        },
        {
            "requested_condition_id": CONDITION,
            "request_offset": 0,
            "response_index": 2,
            "row": _public_trade(second=110, outcome="Up", price=0.1, size=100, wallet=WALLET),
        },
    ]
    trades = normalize_market_rows(rows, specs={CONDITION: _spec()})
    tape = build_independent_tape(trades)
    assert tape[CONDITION][0].q == pytest.approx(0.75)
    bad = [dict(rows[0], row=dict(rows[0]["row"], conditionId="other"))]
    with pytest.raises(CorrectionOverlayError, match="market filter mismatch"):
        normalize_market_rows(bad, specs={CONDITION: _spec()})


def test_same_second_fills_share_pre_second_inventory_state() -> None:
    fills = [
        _fill(100, "Up", size=10),
        _fill(100, "Down", size=5),
        _fill(120, "Down", size=2),
    ]
    tape = {
        CONDITION: (
            TapePoint(105, 0.70, 1, 1),
            TapePoint(110, 0.80, 1, 1),
            TapePoint(119, 0.85, 1, 1),
        )
    }
    rows = analyze_fills(fills, tape)
    same_second = [row for row in rows if row["source_second"] == 100]
    assert {row["pre_dominant_outcome"] for row in same_second} == {None}
    later = next(row for row in rows if row["source_second"] == 120)
    assert later["pre_dominant_outcome"] == "Up"
    assert later["opposite_fill"] is True
    assert later["horizons"]["15"]["correction_depth"] == pytest.approx(0.15)
    assert later["horizons"]["15"]["horizon_change"] == pytest.approx(-0.15)


def test_primary_gate_is_deterministic() -> None:
    fills = [_fill(100, "Up", size=10), _fill(120, "Down", size=5)]
    supporting_tape = {
        CONDITION: (
            TapePoint(105, 0.70, 1, 1),
            TapePoint(110, 0.80, 1, 1),
            TapePoint(119, 0.85, 1, 1),
        )
    }
    supported = summarize(
        analyze_fills(fills, supporting_tape),
        tape=supporting_tape,
        specs={CONDITION: _spec()},
    )
    assert supported["primary_hypothesis"]["verdict"] == "SUPPORTED_DESCRIPTIVELY"

    opposing_tape = {
        CONDITION: (
            TapePoint(105, 0.90, 1, 1),
            TapePoint(110, 0.80, 1, 1),
            TapePoint(119, 0.70, 1, 1),
        )
    }
    not_supported = summarize(
        analyze_fills(fills, opposing_tape),
        tape=opposing_tape,
        specs={CONDITION: _spec()},
    )
    assert not_supported["primary_hypothesis"]["verdict"] == "NOT_SUPPORTED"


def test_run_study_writes_sha_bound_overlay_artifacts(tmp_path: Path) -> None:
    wallet_path = tmp_path / "wallet.jsonl"
    wallet_rows = [
        _wallet_row(second=100, outcome="Up", price=0.5, size=10, transaction_hash="w1"),
        _wallet_row(second=120, outcome="Down", price=0.2, size=5, transaction_hash="w2"),
    ]
    wallet_path.write_text("".join(json.dumps(row) + "\n" for row in wallet_rows))
    wallet_sha = hashlib.sha256(wallet_path.read_bytes()).hexdigest()
    public_rows = [
        _public_trade(second=105, outcome="Up", price=0.70),
        _public_trade(second=110, outcome="Up", price=0.80),
        _public_trade(second=119, outcome="Up", price=0.85),
    ]

    def transport(url: str, headers: dict[str, str]) -> list[dict]:
        del headers
        offset = int(parse_qs(urlparse(url).query)["offset"][0])
        return public_rows if offset == 0 else []

    output = tmp_path / "study"
    result = run_study(
        wallet_activity_path=wallet_path,
        expected_wallet_sha256=wallet_sha,
        output_dir=output,
        api=PolymarketTradeTapeAPI(transport=transport),
        page_size=10,
        max_offset=100,
    )
    assert result["summary"]["primary_hypothesis"]["verdict"] == "SUPPORTED_DESCRIPTIVELY"
    assert (output / "correction_overlay.svg").read_text().startswith("<svg")
    manifest = json.loads((output / "collection_manifest.json").read_text())
    assert manifest["wallet_activity"]["sha256"] == wallet_sha
    assert manifest["artifacts"]["market_trades_raw.jsonl"]["sha256"]
    with pytest.raises(FileExistsError):
        run_study(
            wallet_activity_path=wallet_path,
            output_dir=output,
            api=PolymarketTradeTapeAPI(transport=transport),
            page_size=10,
            max_offset=100,
        )
