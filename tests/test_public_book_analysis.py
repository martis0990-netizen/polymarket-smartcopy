import hashlib
import json

import pytest

from smartcopy.public_book_analysis import (
    PublicBookAnalysisError,
    analyze_bound_fills,
    run_analysis,
)


def _book(line, timestamp, *, token="btc", kind="level", price="0.42", size="5"):
    return {
        "line_number": line,
        "record_type": kind,
        "event_type": "book" if kind == "snapshot" else "price_change",
        "token_id": token,
        "source_timestamp_ms": timestamp,
        "side": None if kind == "snapshot" else "BUY",
        "price": None if kind == "snapshot" else price,
        "size": None if kind == "snapshot" else size,
        "coverage_valid": True,
    }


def _fill(condition, token, role, *, price="0.42", notional=10):
    return {
        "condition_id": condition,
        "asset_id": token,
        "source_second": 10,
        "source_price": float(price),
        "source_notional": notional,
        "schema_corrected_role": role,
    }


def _metadata():
    return [
        {"token_id": "btc", "condition_id": "c1", "asset": "BTC", "window_seconds": 300, "outcome": "Up", "slug": "btc-updown-5m-1"},
        {"token_id": "eth", "condition_id": "c2", "asset": "ETH", "window_seconds": 900, "outcome": "Up", "slug": "eth-updown-15m-1"},
    ]


def test_condition_level_confirmatory_scoring_and_unbound_exclusion():
    books = [
        _book(1, 8_000, token="btc", kind="snapshot"),
        _book(2, 8_000, token="btc"),
        _book(3, 9_500, token="eth", kind="snapshot"),
        _book(4, 9_500, token="eth", price="0.33"),
    ]
    fills = [
        _fill("c1", "btc", "MAKER"),
        _fill("c2", "eth", "MAKER", price="0.33", notional=20),
        _fill("c1", "btc", "TAKER", notional=3),
        _fill("other", "unbound", "MAKER"),
    ]
    rows, summary = analyze_bound_fills(
        fills, book_records=books, gaps=[], token_metadata=_metadata()
    )
    assert len(rows) == 3
    assert summary["excluded_unbound_rows"] == 1
    assert summary["conditions"]["c1"]["classification"] == "PRE_POSITIONED_DOMINANT"
    assert summary["conditions"]["c2"]["classification"] == "LATE_DOMINANT"
    progress = summary["confirmatory_progress"]
    assert progress["eligible_conditions"] == 2
    assert progress["strata"] == {"BTC_300": 1, "BTC_900": 0, "ETH_300": 0, "ETH_900": 1}
    assert progress["verdict"] == "COLLECTING"


def _write_json(path, value):
    path.write_text(json.dumps(value) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_analysis_verifies_bundle_and_writes_sha_bound_outputs(tmp_path):
    bundle = tmp_path / "bundle"
    book = bundle / "public_book"
    book.mkdir(parents=True)
    levels_sha = _write_jsonl(
        book / "book_levels.jsonl",
        [_book(1, 8_000, kind="snapshot"), _book(2, 8_000)],
    )
    gaps_sha = _write_jsonl(book / "book_gaps.jsonl", [])
    token_sha = _write_json(book / "token_metadata.json", {"tokens": _metadata()})
    book_manifest = {
        "artifacts": {
            "book_levels.jsonl": {"sha256": levels_sha},
            "book_gaps.jsonl": {"sha256": gaps_sha},
        }
    }
    book_manifest_sha = _write_json(book / "public_book_manifest.json", book_manifest)
    root_manifest = {
        "schema_version": "smartcopy-bonereaper-prospective-bundle-v3",
        "clean_finalize": True,
        "public_book": {
            "manifest": "public_book/public_book_manifest.json",
            "sha256": book_manifest_sha,
            "token_metadata": "public_book/token_metadata.json",
            "token_metadata_sha256": token_sha,
        },
    }
    _write_json(bundle / "prospective_bundle_manifest.json", root_manifest)
    decoded = tmp_path / "decoded.jsonl"
    decoded_sha = _write_jsonl(decoded, [_fill("c1", "btc", "MAKER")])
    result = run_analysis(
        bundle_dir=bundle,
        decoded_rows_path=decoded,
        expected_decoded_sha256=decoded_sha,
        output_dir=tmp_path / "analysis",
        code_commit="a" * 40,
    )
    assert result["summary"]["conditions"]["c1"]["classification"] == "PRE_POSITIONED_DOMINANT"
    assert (tmp_path / "analysis" / "public_book_analysis_manifest.json").is_file()


def test_run_analysis_rejects_wrong_receipt_row_hash_before_output(tmp_path):
    bundle = tmp_path / "bundle"
    book = bundle / "public_book"
    book.mkdir(parents=True)
    levels_sha = _write_jsonl(book / "book_levels.jsonl", [])
    gaps_sha = _write_jsonl(book / "book_gaps.jsonl", [])
    token_sha = _write_json(book / "token_metadata.json", {"tokens": _metadata()})
    book_manifest_sha = _write_json(
        book / "public_book_manifest.json",
        {"artifacts": {"book_levels.jsonl": {"sha256": levels_sha}, "book_gaps.jsonl": {"sha256": gaps_sha}}},
    )
    _write_json(
        bundle / "prospective_bundle_manifest.json",
        {
            "schema_version": "smartcopy-bonereaper-prospective-bundle-v3",
            "clean_finalize": True,
            "public_book": {
                "manifest": "public_book/public_book_manifest.json",
                "sha256": book_manifest_sha,
                "token_metadata": "public_book/token_metadata.json",
                "token_metadata_sha256": token_sha,
            },
        },
    )
    decoded = tmp_path / "decoded.jsonl"
    _write_jsonl(decoded, [_fill("c1", "btc", "MAKER")])
    with pytest.raises(PublicBookAnalysisError, match="decoded receipt rows SHA256 mismatch"):
        run_analysis(
            bundle_dir=bundle,
            decoded_rows_path=decoded,
            expected_decoded_sha256="0" * 64,
            output_dir=tmp_path / "analysis",
            code_commit="a" * 40,
        )
    assert not (tmp_path / "analysis").exists()


def test_run_analysis_joins_disjoint_v5_book_groups(tmp_path):
    bundle = tmp_path / "bundle"
    bindings = {}
    for name, token, metadata in (
        ("current", "btc", [_metadata()[0]]),
        ("safe", "eth", [_metadata()[1]]),
    ):
        book = bundle / f"{name}_public_book"
        book.mkdir(parents=True)
        levels_sha = _write_jsonl(
            book / "book_levels.jsonl",
            [_book(1, 8_000, token=token, kind="snapshot"), _book(2, 8_000, token=token)],
        )
        gaps_sha = _write_jsonl(book / "book_gaps.jsonl", [])
        token_sha = _write_json(book / "token_metadata.json", {"tokens": metadata})
        manifest_sha = _write_json(
            book / "public_book_manifest.json",
            {"artifacts": {"book_levels.jsonl": {"sha256": levels_sha}, "book_gaps.jsonl": {"sha256": gaps_sha}}},
        )
        bindings[name] = {
            "manifest": f"{name}_public_book/public_book_manifest.json",
            "sha256": manifest_sha,
            "token_metadata": f"{name}_public_book/token_metadata.json",
            "token_metadata_sha256": token_sha,
        }
    _write_json(
        bundle / "prospective_bundle_manifest.json",
        {
            "schema_version": "smartcopy-bonereaper-prospective-bundle-v5",
            "clean_finalize": True,
            "public_books": bindings,
        },
    )
    decoded = tmp_path / "decoded.jsonl"
    decoded_sha = _write_jsonl(
        decoded,
        [_fill("c1", "btc", "MAKER"), _fill("c2", "eth", "MAKER")],
    )
    result = run_analysis(
        bundle_dir=bundle,
        decoded_rows_path=decoded,
        expected_decoded_sha256=decoded_sha,
        output_dir=tmp_path / "analysis",
        code_commit="b" * 40,
    )
    assert set(result["summary"]["conditions"]) == {"c1", "c2"}
