"""Select one finalized Polymarket capture for a frozen Stage 3B wallet artifact.

The selector does not score captures.  It proves that exactly one finalized ``events.jsonl``
under a caller-supplied root spans the complete prospective wallet-observation interval and
contains exact token-id overlap.  The selected file is hashed during the same streaming pass
used for inspection so its digest can be bound directly into ``executable_state_join``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CaptureSelectionError(ValueError):
    """Raised when capture evidence cannot support a unique deterministic selection."""


@dataclass(frozen=True, slots=True)
class WalletEvidence:
    row_count: int
    token_ids: frozenset[str]
    first_observed_min: datetime
    first_observed_max: datetime
    sha256: str


@dataclass(frozen=True, slots=True)
class CaptureInspection:
    path: str
    sha256: str
    bytes: int
    line_count: int
    polymarket_rows: int
    receive_min: datetime
    receive_max: datetime
    overlapping_tokens: tuple[str, ...]
    final_manifest_path: str

    def covers(self, wallet: WalletEvidence) -> bool:
        return (
            self.receive_min <= wallet.first_observed_min
            and self.receive_max >= wallet.first_observed_max
            and bool(self.overlapping_tokens)
        )

    def as_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["receive_min"] = _iso(self.receive_min)
        payload["receive_max"] = _iso(self.receive_max)
        payload["overlapping_tokens"] = list(self.overlapping_tokens)
        return payload


@dataclass(frozen=True, slots=True)
class CaptureSelection:
    wallet: WalletEvidence
    selected: CaptureInspection
    inspected_files: int
    rejected_files: tuple[dict[str, str], ...]

    def as_json(self) -> dict[str, Any]:
        return {
            "schema_version": "smartcopy-pm-capture-selection-v1",
            "wallet": {
                "row_count": self.wallet.row_count,
                "token_count": len(self.wallet.token_ids),
                "first_observed_min": _iso(self.wallet.first_observed_min),
                "first_observed_max": _iso(self.wallet.first_observed_max),
                "sha256": self.wallet.sha256,
            },
            "selected": self.selected.as_json(),
            "inspected_files": self.inspected_files,
            "rejected_files": list(self.rejected_files),
        }


def select_capture(
    *,
    capture_root: str | Path,
    wallet_activity_path: str | Path,
    final_manifest_name: str = "PM_CAPTURE_V2_MANIFEST.json",
) -> CaptureSelection:
    """Return the unique finalized capture covering the frozen wallet evidence interval.

    Only files named ``events.jsonl`` are inspected.  A candidate is eligible only when a
    sibling final manifest exists, all Polymarket rows have valid receive timestamps, the
    file spans the entire wallet observation interval, and at least one exact token id is
    shared with the wallet artifact.  Zero or multiple eligible captures fail closed.
    """

    root = Path(capture_root)
    wallet_path = Path(wallet_activity_path)
    if not root.is_dir():
        raise CaptureSelectionError(f"capture root is not a directory: {root}")
    if not final_manifest_name or Path(final_manifest_name).name != final_manifest_name:
        raise CaptureSelectionError("final_manifest_name must be a simple file name")

    wallet = _load_wallet_evidence(wallet_path)
    candidates = sorted(root.rglob("events.jsonl"), key=lambda path: str(path))
    if not candidates:
        raise CaptureSelectionError(f"no events.jsonl files found under {root}")

    eligible: list[CaptureInspection] = []
    rejected: list[dict[str, str]] = []
    for path in candidates:
        manifest_path = path.parent / final_manifest_name
        if not manifest_path.is_file():
            rejected.append({"path": str(path), "reason": "FINAL_MANIFEST_MISSING"})
            continue
        try:
            inspected = _inspect_capture(path, wallet.token_ids, manifest_path)
        except CaptureSelectionError as exc:
            rejected.append({"path": str(path), "reason": f"INVALID_CAPTURE: {exc}"})
            continue
        if inspected.covers(wallet):
            eligible.append(inspected)
        else:
            reasons: list[str] = []
            if inspected.receive_min > wallet.first_observed_min:
                reasons.append("STARTS_AFTER_WALLET_INTERVAL")
            if inspected.receive_max < wallet.first_observed_max:
                reasons.append("ENDS_BEFORE_WALLET_INTERVAL")
            if not inspected.overlapping_tokens:
                reasons.append("NO_EXACT_TOKEN_OVERLAP")
            rejected.append({"path": str(path), "reason": "+".join(reasons) or "NOT_ELIGIBLE"})

    if len(eligible) != 1:
        paths = [item.path for item in eligible]
        raise CaptureSelectionError(
            "expected exactly one finalized capture covering the wallet interval with exact "
            f"token overlap; found {len(eligible)}: {paths}"
        )

    return CaptureSelection(
        wallet=wallet,
        selected=eligible[0],
        inspected_files=len(candidates),
        rejected_files=tuple(rejected),
    )


def write_selection(selection: CaptureSelection, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite capture selection artifact: {path}")
    raw = _json_line(selection.as_json())
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()


def _load_wallet_evidence(path: Path) -> WalletEvidence:
    digest = hashlib.sha256()
    tokens: set[str] = set()
    observed: list[datetime] = []
    row_count = 0
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            digest.update(raw)
            payload = _decode_json(raw, path, line_number)
            if payload.get("observation_mode") != "live_observed":
                raise CaptureSelectionError(
                    f"wallet line {line_number}: observation_mode must be live_observed"
                )
            token = payload.get("asset")
            if not isinstance(token, str) or not token or token != token.strip():
                raise CaptureSelectionError(f"wallet line {line_number}: invalid asset token id")
            tokens.add(token)
            observed.append(
                _timestamp(
                    payload.get("first_observed_time"),
                    f"wallet line {line_number} first_observed_time",
                )
            )
            row_count += 1
    if not row_count:
        raise CaptureSelectionError("wallet activity artifact is empty")
    return WalletEvidence(
        row_count=row_count,
        token_ids=frozenset(tokens),
        first_observed_min=min(observed),
        first_observed_max=max(observed),
        sha256=digest.hexdigest(),
    )


def _inspect_capture(
    path: Path, wallet_tokens: frozenset[str], manifest_path: Path
) -> CaptureInspection:
    digest = hashlib.sha256()
    line_count = 0
    polymarket_rows = 0
    receive_min: datetime | None = None
    receive_max: datetime | None = None
    overlapping: set[str] = set()

    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line_count = line_number
            digest.update(raw)
            payload = _decode_json(raw, path, line_number)
            if payload.get("venue") != "polymarket":
                continue
            polymarket_rows += 1
            receive = _timestamp(payload.get("receive_ts"), f"{path} line {line_number} receive_ts")
            if receive_min is None or receive < receive_min:
                receive_min = receive
            if receive_max is None or receive > receive_max:
                receive_max = receive
            instrument = payload.get("instrument")
            if isinstance(instrument, str) and instrument in wallet_tokens:
                overlapping.add(instrument)

    if not line_count:
        raise CaptureSelectionError("events.jsonl is empty")
    if polymarket_rows == 0 or receive_min is None or receive_max is None:
        raise CaptureSelectionError("events.jsonl has no normalized Polymarket rows")

    return CaptureInspection(
        path=str(path),
        sha256=digest.hexdigest(),
        bytes=path.stat().st_size,
        line_count=line_count,
        polymarket_rows=polymarket_rows,
        receive_min=receive_min,
        receive_max=receive_max,
        overlapping_tokens=tuple(sorted(overlapping)),
        final_manifest_path=str(manifest_path),
    )


def _decode_json(raw: bytes, path: Path, line_number: int) -> dict[str, Any]:
    if not raw.strip():
        raise CaptureSelectionError(f"{path}: blank JSONL line {line_number}")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureSelectionError(f"{path}: invalid JSON at line {line_number}") from exc
    if not isinstance(payload, dict):
        raise CaptureSelectionError(f"{path}: line {line_number} must be a JSON object")
    return payload


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CaptureSelectionError(f"{label} must be a non-empty ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CaptureSelectionError(f"{label} is not a valid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CaptureSelectionError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _json_line(payload: Any) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description="Select one finalized PM capture for Stage 3B")
    parser.add_argument("--capture-root", required=True)
    parser.add_argument("--wallet-activity", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--final-manifest-name", default="PM_CAPTURE_V2_MANIFEST.json")
    args = parser.parse_args()
    selection = select_capture(
        capture_root=args.capture_root,
        wallet_activity_path=args.wallet_activity,
        final_manifest_name=args.final_manifest_name,
    )
    write_selection(selection, args.output)
    print(json.dumps(selection.as_json(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
