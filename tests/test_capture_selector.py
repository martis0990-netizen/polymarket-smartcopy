from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from smartcopy.capture_selector import (
    CaptureSelectionError,
    select_capture,
    write_selection,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _wallet(asset: str, observed: str, mode: str = "live_observed") -> dict:
    return {
        "observation_mode": mode,
        "activity_type": "TRADE",
        "asset": asset,
        "first_observed_time": observed,
    }


def _market(token: str, receive: str) -> dict:
    return {
        "venue": "polymarket",
        "event_type": "market_snapshot",
        "instrument": token,
        "receive_ts": receive,
    }


def _finalized(root: Path, name: str, rows: list[dict]) -> Path:
    run = root / name
    events = run / "events.jsonl"
    _write_jsonl(events, rows)
    (run / "PM_CAPTURE_V2_MANIFEST.json").write_text(
        json.dumps({"status": "finalized"}) + "\n", encoding="utf-8"
    )
    return events


def _wallet_file(tmp_path: Path) -> Path:
    path = tmp_path / "live_activity.jsonl"
    _write_jsonl(
        path,
        [
            _wallet("token-a", "2026-08-26T12:00:02Z"),
            _wallet("token-b", "2026-08-26T12:00:05Z"),
        ],
    )
    return path


def test_selects_unique_finalized_capture_with_full_time_and_exact_token_overlap(tmp_path: Path) -> None:
    wallet = _wallet_file(tmp_path)
    capture_root = tmp_path / "captures"
    events = _finalized(
        capture_root,
        "good",
        [
            _market("token-a", "2026-08-26T12:00:01Z"),
            _market("other", "2026-08-26T12:00:06Z"),
        ],
    )
    _finalized(
        capture_root,
        "too-late",
        [
            _market("token-a", "2026-08-26T12:00:03Z"),
            _market("token-a", "2026-08-26T12:00:07Z"),
        ],
    )

    selection = select_capture(capture_root=capture_root, wallet_activity_path=wallet)

    assert selection.selected.path == str(events)
    assert selection.selected.overlapping_tokens == ("token-a",)
    assert selection.selected.sha256 == hashlib.sha256(events.read_bytes()).hexdigest()
    assert selection.inspected_files == 2
    assert any(item["reason"] == "STARTS_AFTER_WALLET_INTERVAL" for item in selection.rejected_files)


def test_unfinished_capture_without_final_manifest_is_not_eligible(tmp_path: Path) -> None:
    wallet = _wallet_file(tmp_path)
    root = tmp_path / "captures"
    good = _finalized(
        root,
        "good",
        [
            _market("token-a", "2026-08-26T12:00:01Z"),
            _market("token-a", "2026-08-26T12:00:06Z"),
        ],
    )
    active = root / "active" / "events.jsonl"
    _write_jsonl(
        active,
        [
            _market("token-a", "2026-08-26T12:00:00Z"),
            _market("token-a", "2026-08-26T12:00:07Z"),
        ],
    )

    selection = select_capture(capture_root=root, wallet_activity_path=wallet)

    assert selection.selected.path == str(good)
    assert {item["path"]: item["reason"] for item in selection.rejected_files}[str(active)] == "FINAL_MANIFEST_MISSING"


def test_multiple_eligible_finalized_captures_fail_closed(tmp_path: Path) -> None:
    wallet = _wallet_file(tmp_path)
    root = tmp_path / "captures"
    rows = [
        _market("token-a", "2026-08-26T12:00:01Z"),
        _market("token-a", "2026-08-26T12:00:06Z"),
    ]
    _finalized(root, "one", rows)
    _finalized(root, "two", rows)

    with pytest.raises(CaptureSelectionError, match="found 2"):
        select_capture(capture_root=root, wallet_activity_path=wallet)


def test_full_time_coverage_without_exact_token_overlap_is_rejected(tmp_path: Path) -> None:
    wallet = _wallet_file(tmp_path)
    root = tmp_path / "captures"
    _finalized(
        root,
        "wrong-token",
        [
            _market("token-z", "2026-08-26T12:00:01Z"),
            _market("token-z", "2026-08-26T12:00:06Z"),
        ],
    )

    with pytest.raises(CaptureSelectionError, match="found 0"):
        select_capture(capture_root=root, wallet_activity_path=wallet)


def test_invalid_final_manifest_fails_closed(tmp_path: Path) -> None:
    wallet = _wallet_file(tmp_path)
    root = tmp_path / "captures"
    events = _finalized(
        root,
        "bad-manifest",
        [
            _market("token-a", "2026-08-26T12:00:01Z"),
            _market("token-a", "2026-08-26T12:00:06Z"),
        ],
    )
    (events.parent / "PM_CAPTURE_V2_MANIFEST.json").write_text("not-json\n", encoding="utf-8")

    with pytest.raises(CaptureSelectionError, match="final manifest is invalid JSON"):
        select_capture(capture_root=root, wallet_activity_path=wallet)


def test_corrupt_finalized_events_file_fails_closed_instead_of_being_skipped(tmp_path: Path) -> None:
    wallet = _wallet_file(tmp_path)
    root = tmp_path / "captures"
    _finalized(
        root,
        "good",
        [
            _market("token-a", "2026-08-26T12:00:01Z"),
            _market("token-a", "2026-08-26T12:00:06Z"),
        ],
    )
    corrupt = _finalized(root, "corrupt", [_market("token-a", "2026-08-26T12:00:00Z")])
    with corrupt.open("ab") as handle:
        handle.write(b"{broken\n")

    with pytest.raises(CaptureSelectionError, match="invalid finalized capture"):
        select_capture(capture_root=root, wallet_activity_path=wallet)


def test_backfill_wallet_evidence_is_rejected(tmp_path: Path) -> None:
    wallet = tmp_path / "live_activity.jsonl"
    _write_jsonl(wallet, [_wallet("token-a", "2026-08-26T12:00:02Z", mode="backfill")])
    root = tmp_path / "captures"
    _finalized(
        root,
        "good",
        [
            _market("token-a", "2026-08-26T12:00:01Z"),
            _market("token-a", "2026-08-26T12:00:03Z"),
        ],
    )

    with pytest.raises(CaptureSelectionError, match="observation_mode must be live_observed"):
        select_capture(capture_root=root, wallet_activity_path=wallet)


def test_selection_artifact_refuses_overwrite(tmp_path: Path) -> None:
    wallet = _wallet_file(tmp_path)
    root = tmp_path / "captures"
    _finalized(
        root,
        "good",
        [
            _market("token-a", "2026-08-26T12:00:01Z"),
            _market("token-a", "2026-08-26T12:00:06Z"),
        ],
    )
    selection = select_capture(capture_root=root, wallet_activity_path=wallet)
    output = tmp_path / "selection.json"

    write_selection(selection, output)
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == "smartcopy-pm-capture-selection-v1"
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_selection(selection, output)
