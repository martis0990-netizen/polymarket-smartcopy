"""Frozen on-chain maker/taker study for the Stage 3A Bonereaper fills."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from urllib.request import Request, urlopen

from smartcopy.correction_overlay import WalletFill, load_wallet_evidence

_SCHEMA = "smartcopy-bonereaper-maker-taker-v1"
_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
_CHAIN_ID = 137
_CONTRACT_COMMIT = "91cd1a12c75ec6ad1be80086ad871bafbb3be897"
_RAW = "receipt_responses_raw.jsonl"
_ROWS = "maker_taker_rows.jsonl"
_SUMMARY = "maker_taker_summary.json"
_MANIFEST = "collection_manifest.json"

_EXCHANGES = {
    "0xe111180000d2663c0091e4f400237545b87b996b",
    "0xe2222d279d744050d28e00520010520000310f59",
}
_ORDER_FILLED_TOPIC = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"
_ORDERS_MATCHED_TOPIC = "0x174b3811690657c217184f89418266767c87e4805d09680c39fc9c031c0cab7c"

Transport = Callable[[str, Any, dict[str, str]], Any]


class MakerTakerError(RuntimeError):
    """Raised when the frozen receipt evidence contract cannot be satisfied."""


def _default_transport(url: str, payload: Any, headers: dict[str, str]) -> Any:
    request = Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:  # noqa: S310 - caller records endpoint
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network boundary
        raise MakerTakerError(f"JSON-RPC POST {url} failed: {exc}") from exc


@dataclass(slots=True)
class PolygonReceiptAPI:
    rpc_url: str
    transport: Transport = _default_transport
    user_agent: str = "polymarket-smartcopy/0.1"

    def post(self, payload: Any) -> Any:
        return self.transport(
            self.rpc_url,
            payload,
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
            },
        )


@dataclass(frozen=True, slots=True)
class OrderFilledEvent:
    exchange: str
    order_hash: str
    maker: str
    taker: str
    side: int
    token_id: int
    maker_amount: int
    taker_amount: int
    fee: int
    builder: str
    metadata: str
    log_index: int


def collect_receipts(
    api: PolygonReceiptAPI,
    transaction_hashes: Iterable[str],
    *,
    batch_size: int = 25,
) -> tuple[int, tuple[dict[str, Any], ...]]:
    """Collect chain id and exact receipt response envelopes with deterministic ids."""

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    hashes = tuple(sorted(set(transaction_hashes)))
    chain_request = {"jsonrpc": "2.0", "id": 0, "method": "eth_chainId", "params": []}
    chain_response = api.post(chain_request)
    _validate_rpc_response(chain_response, expected_id=0)
    chain_id = _hex_int(chain_response.get("result"), "eth_chainId result")
    envelopes: list[dict[str, Any]] = [
        {"request": chain_request, "response": chain_response}
    ]

    requests = [
        {
            "jsonrpc": "2.0",
            "id": index,
            "method": "eth_getTransactionReceipt",
            "params": [transaction_hash],
        }
        for index, transaction_hash in enumerate(hashes, start=1)
    ]
    seen_ids: set[int] = set()
    for start in range(0, len(requests), batch_size):
        batch = requests[start : start + batch_size]
        response = api.post(batch)
        if not isinstance(response, list):
            raise MakerTakerError("receipt batch response must be a list")
        by_id: dict[int, dict[str, Any]] = {}
        for item in response:
            if not isinstance(item, dict):
                raise MakerTakerError("receipt batch contains a non-object response")
            response_id = item.get("id")
            if not isinstance(response_id, int):
                raise MakerTakerError("receipt response id must be an integer")
            if response_id in seen_ids or response_id in by_id:
                raise MakerTakerError(f"duplicate JSON-RPC response id {response_id}")
            by_id[response_id] = item
        expected_ids = {int(item["id"]) for item in batch}
        if set(by_id) != expected_ids:
            raise MakerTakerError(
                "receipt response ids mismatch: "
                f"expected {sorted(expected_ids)}, got {sorted(by_id)}"
            )
        for request in batch:
            response_item = by_id[int(request["id"])]
            _validate_rpc_response(response_item, expected_id=int(request["id"]))
            if response_item.get("result") is None:
                raise MakerTakerError(f"missing receipt for {request['params'][0]}")
            envelopes.append({"request": request, "response": response_item})
            seen_ids.add(int(request["id"]))
    return chain_id, tuple(envelopes)


def decode_rows(
    fills: Sequence[WalletFill],
    envelopes: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Bind every source fill to one V2 OrderFilled event and classify its role."""

    receipt_by_hash: dict[str, dict[str, Any]] = {}
    for envelope in envelopes:
        request = envelope.get("request")
        response = envelope.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            raise MakerTakerError("malformed JSON-RPC envelope")
        if request.get("method") != "eth_getTransactionReceipt":
            continue
        params = request.get("params")
        if not isinstance(params, list) or len(params) != 1:
            raise MakerTakerError("malformed receipt request params")
        tx_hash = _transaction_hash(params[0], "receipt request transaction hash")
        receipt = response.get("result")
        if not isinstance(receipt, dict):
            raise MakerTakerError(f"receipt for {tx_hash} is not an object")
        actual_hash = _transaction_hash(receipt.get("transactionHash"), "receipt transactionHash")
        if actual_hash != tx_hash:
            raise MakerTakerError(f"receipt transaction hash mismatch for {tx_hash}")
        if tx_hash in receipt_by_hash:
            raise MakerTakerError(f"duplicate receipt for {tx_hash}")
        receipt_by_hash[tx_hash] = receipt

    opposite = classify_opposite_fills(fills)
    rows: list[dict[str, Any]] = []
    for fill in sorted(fills, key=_fill_sort_key):
        tx_hash = _transaction_hash(fill.transaction_hash, "wallet transaction hash")
        receipt = receipt_by_hash.get(tx_hash)
        if receipt is None:
            raise MakerTakerError(f"no collected receipt for {tx_hash}")
        rows.append(
            _decode_fill(
                fill,
                receipt,
                opposite_fill=opposite[tx_hash],
            )
        )
    return tuple(rows)


def classify_opposite_fills(fills: Sequence[WalletFill]) -> dict[str, bool]:
    """Apply the correction contract's strict-prior, same-second inventory rule."""

    by_condition: dict[str, list[WalletFill]] = defaultdict(list)
    for fill in fills:
        by_condition[fill.condition_id].append(fill)
    output: dict[str, bool] = {}
    for condition_fills in by_condition.values():
        up_size = 0.0
        down_size = 0.0
        by_second: dict[int, list[WalletFill]] = defaultdict(list)
        for fill in condition_fills:
            by_second[fill.source_second].append(fill)
        for second in sorted(by_second):
            dominant = "Up" if up_size > down_size else "Down" if down_size > up_size else None
            for fill in by_second[second]:
                if fill.transaction_hash in output:
                    raise MakerTakerError(
                        f"duplicate wallet transaction hash {fill.transaction_hash}"
                    )
                output[fill.transaction_hash] = dominant is not None and fill.outcome != dominant
            up_size += sum(fill.size for fill in by_second[second] if fill.outcome == "Up")
            down_size += sum(fill.size for fill in by_second[second] if fill.outcome == "Down")
    return output


def summarize(rows: Sequence[dict[str, Any]], *, market_slugs: dict[str, str]) -> dict[str, Any]:
    matched = [row for row in rows if row["role"] in {"MAKER", "TAKER"}]
    ambiguous = [row for row in rows if row["role"] == "AMBIGUOUS"]
    all_metrics = _role_metrics(rows)
    maker_share = all_metrics["notional"]["maker_share"]
    if ambiguous or len(matched) != len(rows) or maker_share is None:
        verdict = "INCONCLUSIVE"
    elif maker_share >= 0.80:
        verdict = "PASSIVE_MAKER_DOMINANT"
    elif maker_share <= 0.20:
        verdict = "ACTIVE_TAKER_DOMINANT"
    else:
        verdict = "MIXED_EXECUTION"

    corrected_matched = [
        row for row in rows if row["schema_corrected_role"] in {"MAKER", "TAKER"}
    ]
    corrected_ambiguous = [row for row in rows if row["schema_corrected_role"] == "AMBIGUOUS"]
    corrected_metrics = _role_metrics(rows, role_field="schema_corrected_role")
    corrected_share = corrected_metrics["notional"]["maker_share"]
    if corrected_ambiguous or len(corrected_matched) != len(rows) or corrected_share is None:
        corrected_verdict = "INCONCLUSIVE"
    elif corrected_share >= 0.80:
        corrected_verdict = "PASSIVE_MAKER_DOMINANT"
    elif corrected_share <= 0.20:
        corrected_verdict = "ACTIVE_TAKER_DOMINANT"
    else:
        corrected_verdict = "MIXED_EXECUTION"

    per_market: dict[str, Any] = {}
    for condition_id in sorted(market_slugs):
        market_rows = [row for row in rows if row["condition_id"] == condition_id]
        per_market[condition_id] = {
            "slug": market_slugs[condition_id],
            "contract_roles": _role_metrics(market_rows),
            "schema_corrected_roles": _role_metrics(
                market_rows, role_field="schema_corrected_role"
            ),
            "outcomes": {
                outcome: {
                    "contract_roles": _role_metrics(
                        [row for row in market_rows if row["outcome"] == outcome]
                    ),
                    "schema_corrected_roles": _role_metrics(
                        [row for row in market_rows if row["outcome"] == outcome],
                        role_field="schema_corrected_role",
                    ),
                }
                for outcome in ("Up", "Down")
            },
        }

    return {
        "schema_version": _SCHEMA,
        "contract_frozen_commit": _CONTRACT_COMMIT,
        "primary_mechanism": {
            "verdict": verdict,
            "population": "all frozen Stage 3A BUY rows",
            "weight": "source_notional",
            "maker_dominant_floor": 0.80,
            "taker_dominant_maker_share_ceiling": 0.20,
            "maker_notional_share": maker_share,
        },
        "completeness": {
            "source_rows": len(rows),
            "uniquely_matched_rows": len(matched),
            "ambiguous_rows": len(ambiguous),
            "schema_corrected_uniquely_matched_rows": len(corrected_matched),
            "schema_corrected_ambiguous_rows": len(corrected_ambiguous),
        },
        "all_fills": all_metrics,
        "opposite_fills": _role_metrics([row for row in rows if row["opposite_fill"]]),
        "non_opposite_fills": _role_metrics([row for row in rows if not row["opposite_fill"]]),
        "schema_corrected_secondary": {
            "status": "POST_HOC_EVENT_SCHEMA_REPAIR",
            "repair": (
                "For BUY fills, source usdc_size binds to makerAmountFilled + fee when the "
                "separate V2 fee word is non-zero; price remains makerAmountFilled / "
                "takerAmountFilled. The frozen contract omitted this fee-inclusive case."
            ),
            "verdict_under_original_80_20_gate": corrected_verdict,
            "all_fills": corrected_metrics,
            "opposite_fills": _role_metrics(
                [row for row in rows if row["opposite_fill"]],
                role_field="schema_corrected_role",
            ),
            "non_opposite_fills": _role_metrics(
                [row for row in rows if not row["opposite_fill"]],
                role_field="schema_corrected_role",
            ),
        },
        "per_market": per_market,
        "interpretation_limit": (
            "Maker status establishes passive execution at fill time, not order placement time, "
            "resting duration, cancellations, queue position, or follower copyability."
        ),
    }


def run_study(
    *,
    wallet_activity_path: str | Path,
    expected_wallet_sha256: str,
    output_dir: str | Path,
    api: PolygonReceiptAPI,
    batch_size: int = 25,
) -> dict[str, Any]:
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output}")
    evidence = load_wallet_evidence(
        wallet_activity_path,
        expected_sha256=expected_wallet_sha256,
    )
    if len(evidence.rows) != 77:
        raise MakerTakerError(f"frozen input requires 77 rows, got {len(evidence.rows)}")
    if len({fill.transaction_hash for fill in evidence.rows}) != 77:
        raise MakerTakerError("frozen input requires 77 unique transaction hashes")

    chain_id, envelopes = collect_receipts(
        api,
        (fill.transaction_hash for fill in evidence.rows),
        batch_size=batch_size,
    )
    if chain_id != _CHAIN_ID:
        raise MakerTakerError(f"expected Polygon chain id {_CHAIN_ID}, got {chain_id}")
    rows = decode_rows(evidence.rows, envelopes)
    summary = summarize(
        rows,
        market_slugs={condition_id: spec.slug for condition_id, spec in evidence.specs.items()},
    )

    output.mkdir(parents=True)
    raw_path = output / _RAW
    rows_path = output / _ROWS
    summary_path = output / _SUMMARY
    manifest_path = output / _MANIFEST
    _write_jsonl(raw_path, envelopes)
    _write_jsonl(rows_path, rows)
    _write_json(summary_path, summary)
    artifacts = {
        path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
        for path in (raw_path, rows_path, summary_path)
    }
    manifest = {
        "schema_version": _SCHEMA,
        "contract_frozen_commit": _CONTRACT_COMMIT,
        "collection_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "rpc_endpoint": api.rpc_url,
        "chain_id": chain_id,
        "receipt_requests": len(evidence.rows),
        "receipt_responses": len(envelopes) - 1,
        "wallet_activity": {
            "path": str(wallet_activity_path),
            "rows": len(evidence.rows),
            "sha256": evidence.sha256,
        },
        "artifacts": artifacts,
    }
    _write_json(manifest_path, manifest)
    return {"summary": summary, "manifest": manifest, "output_dir": str(output)}


def _decode_fill(
    fill: WalletFill,
    receipt: dict[str, Any],
    *,
    opposite_fill: bool,
) -> dict[str, Any]:
    tx_hash = _transaction_hash(fill.transaction_hash, "wallet transaction hash")
    if _hex_int(receipt.get("status"), f"receipt {tx_hash} status") != 1:
        raise MakerTakerError(f"receipt {tx_hash} was not successful")
    logs = receipt.get("logs")
    if not isinstance(logs, list):
        raise MakerTakerError(f"receipt {tx_hash} logs must be a list")

    order_events: list[OrderFilledEvent] = []
    matched_hashes: set[tuple[str, str]] = set()
    for raw_log in logs:
        if not isinstance(raw_log, dict):
            raise MakerTakerError(f"receipt {tx_hash} contains a non-object log")
        topics = raw_log.get("topics")
        if not isinstance(topics, list) or not topics:
            continue
        topic0 = str(topics[0]).lower()
        if topic0 not in {_ORDER_FILLED_TOPIC, _ORDERS_MATCHED_TOPIC}:
            continue
        exchange = _address(raw_log.get("address"), f"receipt {tx_hash} log address")
        if exchange not in _EXCHANGES:
            raise MakerTakerError(
                f"receipt {tx_hash} target event from unapproved exchange {exchange}"
            )
        if raw_log.get("removed") is True:
            raise MakerTakerError(f"receipt {tx_hash} contains a removed exchange log")
        log_tx_hash = raw_log.get("transactionHash")
        if (
            log_tx_hash is not None
            and _transaction_hash(log_tx_hash, "log transactionHash") != tx_hash
        ):
            raise MakerTakerError(f"receipt {tx_hash} contains a log for another transaction")
        if topic0 == _ORDER_FILLED_TOPIC:
            order_events.append(_decode_order_filled(raw_log, exchange=exchange))
        else:
            if len(topics) != 3:
                raise MakerTakerError(f"receipt {tx_hash} malformed OrdersMatched topics")
            _data_words(raw_log.get("data"), expected=4, context="OrdersMatched")
            matched_hashes.add((exchange, _bytes32(topics[1], "OrdersMatched order hash")))

    expected_usdc = round(fill.notional * 1_000_000)
    expected_size = round(fill.size * 1_000_000)
    expected_token = _decimal_int(fill.asset_id, "wallet asset id")
    common_candidates = [
        event
        for event in order_events
        if event.maker == _WALLET
        and event.side == 0
        and event.token_id == expected_token
        and abs(event.taker_amount - expected_size) <= 1
        and event.taker_amount > 0
        and abs(event.maker_amount / event.taker_amount - fill.price) <= 1e-6
    ]
    candidates = [
        event for event in common_candidates if abs(event.maker_amount - expected_usdc) <= 1
    ]
    schema_corrected_candidates = [
        event
        for event in common_candidates
        if abs(event.maker_amount + event.fee - expected_usdc) <= 1
    ]
    base = {
        "transaction_hash": tx_hash,
        "condition_id": fill.condition_id,
        "source_event_time": fill.source_event_time,
        "source_second": fill.source_second,
        "outcome": fill.outcome,
        "asset_id": fill.asset_id,
        "source_price": fill.price,
        "source_size": fill.size,
        "source_notional": fill.notional,
        "opposite_fill": opposite_fill,
        "block_number": _hex_int(receipt.get("blockNumber"), f"receipt {tx_hash} blockNumber"),
        "block_hash": _bytes32(receipt.get("blockHash"), f"receipt {tx_hash} blockHash"),
        "candidate_event_count": len(candidates),
        "schema_corrected_candidate_event_count": len(schema_corrected_candidates),
    }
    event = candidates[0] if len(candidates) == 1 else None
    corrected_event = (
        schema_corrected_candidates[0] if len(schema_corrected_candidates) == 1 else None
    )
    role = _event_role(event, matched_hashes)
    corrected_role = _event_role(corrected_event, matched_hashes)
    selected = event or corrected_event
    if selected is None:
        return {
            **base,
            "role": role,
            "schema_corrected_role": corrected_role,
            "ambiguity": "expected exactly one matching OrderFilled",
        }
    return {
        **base,
        "role": role,
        "schema_corrected_role": corrected_role,
        "schema_correction_used": event is None and corrected_event is not None,
        "ambiguity": "frozen contract omitted fee-inclusive BUY cost" if event is None else None,
        "exchange": selected.exchange,
        "order_hash": selected.order_hash,
        "event_taker": selected.taker,
        "event_log_index": selected.log_index,
        "maker_amount_filled": selected.maker_amount,
        "taker_amount_filled": selected.taker_amount,
        "fee": selected.fee,
        "maker_amount_plus_fee": selected.maker_amount + selected.fee,
        "decoded_price": selected.maker_amount / selected.taker_amount,
        "builder": selected.builder,
        "metadata": selected.metadata,
    }


def _decode_order_filled(raw_log: dict[str, Any], *, exchange: str) -> OrderFilledEvent:
    topics = raw_log.get("topics")
    if not isinstance(topics, list) or len(topics) != 4:
        raise MakerTakerError("malformed OrderFilled topics")
    words = _data_words(raw_log.get("data"), expected=7, context="OrderFilled")
    return OrderFilledEvent(
        exchange=exchange,
        order_hash=_bytes32(topics[1], "OrderFilled order hash"),
        maker=_topic_address(topics[2], "OrderFilled maker"),
        taker=_topic_address(topics[3], "OrderFilled taker"),
        side=int(words[0], 16),
        token_id=int(words[1], 16),
        maker_amount=int(words[2], 16),
        taker_amount=int(words[3], 16),
        fee=int(words[4], 16),
        builder="0x" + words[5],
        metadata="0x" + words[6],
        log_index=_hex_int(raw_log.get("logIndex"), "OrderFilled logIndex"),
    )


def _event_role(
    event: OrderFilledEvent | None,
    matched_hashes: set[tuple[str, str]],
) -> str:
    if event is None:
        return "AMBIGUOUS"
    if (event.exchange, event.order_hash) in matched_hashes:
        return "TAKER"
    return "MAKER"


def _role_metrics(
    rows: Sequence[dict[str, Any]],
    *,
    role_field: str = "role",
) -> dict[str, Any]:
    return {
        "rows": _weighted_role(rows, lambda row: 1.0, role_field=role_field),
        "size": _weighted_role(
            rows, lambda row: float(row["source_size"]), role_field=role_field
        ),
        "notional": _weighted_role(
            rows, lambda row: float(row["source_notional"]), role_field=role_field
        ),
    }


def _weighted_role(
    rows: Sequence[dict[str, Any]],
    weight: Callable[[dict[str, Any]], float],
    *,
    role_field: str,
) -> dict[str, Any]:
    total = sum(weight(row) for row in rows)
    maker = sum(weight(row) for row in rows if row[role_field] == "MAKER")
    taker = sum(weight(row) for row in rows if row[role_field] == "TAKER")
    ambiguous = sum(weight(row) for row in rows if row[role_field] == "AMBIGUOUS")
    return {
        "total": total,
        "maker": maker,
        "taker": taker,
        "ambiguous": ambiguous,
        "maker_share": maker / total if total and not ambiguous else None,
        "taker_share": taker / total if total and not ambiguous else None,
    }


def _validate_rpc_response(response: Any, *, expected_id: int) -> None:
    if not isinstance(response, dict):
        raise MakerTakerError("JSON-RPC response must be an object")
    if response.get("jsonrpc") != "2.0" or response.get("id") != expected_id:
        raise MakerTakerError(f"malformed JSON-RPC response for id {expected_id}")
    if "error" in response:
        raise MakerTakerError(f"JSON-RPC error for id {expected_id}: {response['error']}")
    if "result" not in response:
        raise MakerTakerError(f"JSON-RPC response id {expected_id} has no result")


def _data_words(value: Any, *, expected: int, context: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise MakerTakerError(f"{context} data must be 0x-prefixed hex")
    payload = value[2:].lower()
    if len(payload) != 64 * expected or any(char not in "0123456789abcdef" for char in payload):
        raise MakerTakerError(f"{context} data must contain exactly {expected} words")
    return tuple(payload[index : index + 64] for index in range(0, len(payload), 64))


def _topic_address(value: Any, context: str) -> str:
    topic = _bytes32(value, context)
    if any(char != "0" for char in topic[2:26]):
        raise MakerTakerError(f"{context} is not a padded address topic")
    return "0x" + topic[-40:]


def _address(value: Any, context: str) -> str:
    if not isinstance(value, str):
        raise MakerTakerError(f"{context} must be a string")
    text = value.lower()
    if (
        len(text) != 42
        or not text.startswith("0x")
        or any(char not in "0123456789abcdef" for char in text[2:])
    ):
        raise MakerTakerError(f"{context} must be a 20-byte hex address")
    return text


def _bytes32(value: Any, context: str) -> str:
    if not isinstance(value, str):
        raise MakerTakerError(f"{context} must be a string")
    text = value.lower()
    if (
        len(text) != 66
        or not text.startswith("0x")
        or any(char not in "0123456789abcdef" for char in text[2:])
    ):
        raise MakerTakerError(f"{context} must be a 32-byte hex value")
    return text


def _transaction_hash(value: Any, context: str) -> str:
    return _bytes32(value, context)


def _hex_int(value: Any, context: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise MakerTakerError(f"{context} must be 0x-prefixed hex")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise MakerTakerError(f"{context} must be valid hex") from exc


def _decimal_int(value: Any, context: str) -> int:
    if not isinstance(value, str) or not value.isdigit():
        raise MakerTakerError(f"{context} must be an unsigned decimal integer")
    return int(value)


def _fill_sort_key(fill: WalletFill) -> tuple[Any, ...]:
    return (
        fill.source_second,
        fill.condition_id,
        fill.transaction_hash,
        fill.asset_id,
        fill.outcome,
    )


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet-activity", required=True)
    parser.add_argument("--expected-wallet-sha256", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--batch-size", type=int, default=25)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_study(
        wallet_activity_path=args.wallet_activity,
        expected_wallet_sha256=args.expected_wallet_sha256,
        output_dir=args.output,
        api=PolygonReceiptAPI(rpc_url=args.rpc_url),
        batch_size=args.batch_size,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    main()
