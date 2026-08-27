import hashlib
import json
from decimal import Decimal

import pytest

from smartcopy.prospective_economics import (
    build_fifo_pairs,
    build_markouts,
    reconstruct_book_states,
    run_analysis,
)


def _receipt(
    outcome,
    role,
    *,
    token=None,
    condition="condition",
    second=1,
    size=10_000_000,
    base=4_000_000,
    fee=0,
    log=1,
):
    return {
        "condition_id": condition,
        "asset_id": token or outcome.lower(),
        "outcome": outcome,
        "schema_corrected_role": role,
        "source_second": second,
        "block_number": 1,
        "event_log_index": log,
        "transaction_hash": f"0x{outcome.lower()}{log}",
        "taker_amount_filled": size,
        "maker_amount_filled": base,
        "fee": fee,
        "maker_amount_plus_fee": base + fee,
        "bound_slug": "btc-updown-5m-0",
        "bound_asset": "BTC",
        "bound_window_seconds": 300,
    }


def _book(token, timestamp, *, kind="level", side="BUY", price="0.4", size="5"):
    return {
        "token_id": token,
        "source_timestamp_ms": timestamp,
        "record_type": kind,
        "event_type": "book" if kind == "snapshot" else "price_change",
        "coverage_valid": True,
        "side": None if kind == "snapshot" else side,
        "price": None if kind == "snapshot" else price,
        "size": None if kind == "snapshot" else size,
    }


def test_fifo_pair_uses_actual_fee_and_preserves_residual() -> None:
    rows = [
        _receipt("Up", "MAKER", size=10_000_000, base=4_000_000),
        _receipt(
            "Down",
            "TAKER",
            second=2,
            size=6_000_000,
            base=3_300_000,
            fee=60_000,
            log=2,
        ),
    ]
    chunks, conditions = build_fifo_pairs(rows)
    assert len(chunks) == 1
    assert chunks[0]["matched_size"] == "6"
    assert chunks[0]["gross_pair_cost_per_unit"] == "0.95"
    assert chunks[0]["fee_adjusted_pair_cost_per_unit"] == "0.96"
    assert chunks[0]["role_composition"] == "MIXED"
    assert conditions[0]["residuals"]["Up"]["size"] == "4"
    assert conditions[0]["fee_adjusted_edge_total"] == "0.24"


def test_book_reconstruction_and_markout_use_last_state_at_target() -> None:
    records = [
        _book("up", 1_000, kind="snapshot"),
        _book("up", 1_000, side="BUY", price="0.40"),
        _book("up", 1_000, side="SELL", price="0.60"),
        _book("up", 11_000, side="BUY", price="0.44"),
        _book("up", 11_000, side="SELL", price="0.64"),
    ]
    states = reconstruct_book_states(records)
    rows = build_markouts(
        [_receipt("Up", "MAKER", token="up")],
        states=states,
        gaps=[],
        capture_started_ms=0,
        capture_ended_ms=70_000,
    )
    ten = next(row for row in rows if row["horizon_seconds"] == 10)
    assert ten["eligible"] is True
    # Absolute deltas at new prices do not remove the older 0.60 ask.
    assert ten["mid"] == "0.52"
    assert Decimal(ten["markout_per_unit"]) == Decimal("0.12")
    assert next(row for row in rows if row["horizon_seconds"] == 30)["state_timestamp_ms"] == 11_000


def test_markout_target_outside_capture_is_ineligible() -> None:
    rows = build_markouts(
        [_receipt("Up", "TAKER", token="up")],
        states={"up": ((11_000, Decimal("0.4"), Decimal("0.6")),)},
        gaps=[],
        capture_started_ms=0,
        capture_ended_ms=15_000,
    )
    assert rows[0]["eligible"] is True
    assert rows[1]["ineligibility_reason"] == "TARGET_OUTSIDE_CAPTURE"


def _write_json(path, value):
    path.write_text(json.dumps(value) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_analysis_verifies_split_books_and_refuses_overwrite(tmp_path) -> None:
    bundle = tmp_path / "bundle"
    bindings = {}
    metadata_by_group = {
        "current": [
            {"token_id": "up", "condition_id": "condition", "outcome": "Up", "asset": "BTC", "window_seconds": 300, "slug": "btc-updown-5m-0"},
            {"token_id": "down", "condition_id": "condition", "outcome": "Down", "asset": "BTC", "window_seconds": 300, "slug": "btc-updown-5m-0"},
        ],
        "safe": [
            {"token_id": "safe-up", "condition_id": "safe", "outcome": "Up", "asset": "BTC", "window_seconds": 300, "slug": "btc-updown-5m-300"},
            {"token_id": "safe-down", "condition_id": "safe", "outcome": "Down", "asset": "BTC", "window_seconds": 300, "slug": "btc-updown-5m-300"},
        ],
    }
    for group, metadata in metadata_by_group.items():
        root = bundle / f"{group}_public_book"
        root.mkdir(parents=True)
        levels = []
        for token in [row["token_id"] for row in metadata]:
            levels.extend(
                [
                    _book(token, 1_000, kind="snapshot"),
                    _book(token, 1_000, side="BUY", price="0.4"),
                    _book(token, 1_000, side="SELL", price="0.6"),
                ]
            )
        levels_sha = _write_jsonl(root / "book_levels.jsonl", levels)
        gaps_sha = _write_jsonl(root / "book_gaps.jsonl", [])
        metadata_sha = _write_json(root / "token_metadata.json", {"tokens": metadata})
        manifest_sha = _write_json(
            root / "public_book_manifest.json",
            {"artifacts": {"book_levels.jsonl": {"sha256": levels_sha}, "book_gaps.jsonl": {"sha256": gaps_sha}}},
        )
        bindings[group] = {
            "manifest": f"{group}_public_book/public_book_manifest.json",
            "sha256": manifest_sha,
            "token_metadata": f"{group}_public_book/token_metadata.json",
            "token_metadata_sha256": metadata_sha,
        }
    bundle_sha = _write_json(
        bundle / "prospective_bundle_manifest.json",
        {
            "schema_version": "smartcopy-bonereaper-prospective-bundle-v5",
            "clean_finalize": True,
            "started_at": "1970-01-01T00:00:00Z",
            "ended_at": "1970-01-01T00:01:10Z",
            "public_books": bindings,
        },
    )
    decoded = tmp_path / "decoded.jsonl"
    decoded_sha = _write_jsonl(
        decoded,
        [
            _receipt("Up", "MAKER", token="up"),
            _receipt("Down", "TAKER", token="down", second=2, base=5_000_000, log=2),
        ],
    )
    output = tmp_path / "economics"
    result = run_analysis(
        bundle_dir=bundle,
        expected_bundle_sha256=bundle_sha,
        decoded_rows_path=decoded,
        expected_decoded_sha256=decoded_sha,
        output_dir=output,
        code_commit="a" * 40,
    )
    assert result["summary"]["coverage"]["bound_rows"] == 2
    assert result["summary"]["pair_chunks"] == 1
    assert (output / "prospective_economics_manifest.json").is_file()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        run_analysis(
            bundle_dir=bundle,
            expected_bundle_sha256=bundle_sha,
            decoded_rows_path=decoded,
            expected_decoded_sha256=decoded_sha,
            output_dir=output,
            code_commit="a" * 40,
        )
