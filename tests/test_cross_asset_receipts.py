import json

import pytest

from smartcopy.cross_asset_intake import inspect_v5_capture
from smartcopy.cross_asset_receipts import run_v5_receipts
from smartcopy.maker_taker import PolygonReceiptAPI, MakerTakerError
from test_cross_asset_intake import fixture_bundle, sha

WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
EXCHANGE = "0xe111180000d2663c0091e4f400237545b87b996b"
ORDER_FILLED = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"
ORDERS_MATCHED = "0x174b3811690657c217184f89418266767c87e4805d09680c39fc9c031c0cab7c"


def word(value):
    return f"{value:064x}"


def topic(address):
    return "0x" + "0" * 24 + address[2:]


def receipt(tx):
    order = "0x" + "2" * 64
    return {"transactionHash": tx, "status": "0x1", "blockNumber": "0x10",
            "blockHash": "0x" + "3" * 64, "logs": [
                {"address": EXCHANGE, "topics": [ORDER_FILLED, order, topic(WALLET), topic("0x" + "12" * 20)],
                 "data": "0x" + "".join(word(n) for n in (0, 10001, 800000, 2000000, 0, 0, 0)),
                 "logIndex": "0x3", "transactionHash": tx},
                {"address": EXCHANGE, "topics": [ORDERS_MATCHED, order, topic(WALLET)],
                 "data": "0x" + "".join(word(n) for n in (0, 10001, 800000, 2000000)),
                 "logIndex": "0x4", "transactionHash": tx},
            ]}


def setup(tmp_path, **kwargs):
    root, digest = fixture_bundle(tmp_path, **kwargs)
    intake_dir = tmp_path / "intake"
    inspect_v5_capture(bundle_dir=root, expected_manifest_sha256=digest,
                       output_dir=intake_dir, code_commit="a" * 40)
    return root, intake_dir, sha(intake_dir / "cross_asset_intake_manifest.json")


def api(*, valid=True, chain="0x89"):
    def transport(url, payload, headers):
        if isinstance(payload, dict):
            return {"jsonrpc": "2.0", "id": 0, "result": chain}
        return [{"jsonrpc": "2.0", "id": request["id"],
                 "result": receipt(request["params"][0]) if valid else None}
                for request in payload]
    return PolygonReceiptAPI("https://rpc.example", transport=transport)


def test_v5_sol_buy_gets_fee_aware_taker_role(tmp_path):
    root, intake, digest = setup(tmp_path, include_sell=True)
    out = tmp_path / "receipts"
    manifest = run_v5_receipts(bundle_dir=root, intake_dir=intake,
                               expected_intake_sha256=digest, output_dir=out,
                               api=api(), code_commit="b" * 40)
    assert manifest["selected_buy_rows"] == manifest["decoded_rows"] == 1
    assert manifest["core_conditions"] == 1
    row = json.loads((out / "maker_taker_rows.jsonl").read_text())
    assert row["schema_corrected_role"] == "TAKER"


def test_empty_bundle_valid_and_hype_excluded_from_core(tmp_path):
    root, intake, digest = setup(tmp_path, candidate=False)
    manifest = run_v5_receipts(bundle_dir=root, intake_dir=intake,
                               expected_intake_sha256=digest, output_dir=tmp_path / "receipts",
                               api=api(), code_commit="b" * 40)
    assert manifest["decoded_rows"] == 0
    other = tmp_path / "other"
    other.mkdir()
    root, intake, digest = setup(other, asset="hype")
    manifest = run_v5_receipts(bundle_dir=root, intake_dir=intake,
                               expected_intake_sha256=digest, output_dir=other / "receipts",
                               api=api(), code_commit="b" * 40)
    assert manifest["core_conditions"] == 0
    assert manifest["hype_engineering_conditions"] == 1


def test_missing_receipt_and_wrong_chain_fail_without_output(tmp_path):
    root, intake, digest = setup(tmp_path)
    for wrong_api, error in ((api(valid=False), MakerTakerError), (api(chain="0x1"), ValueError)):
        out = tmp_path / ("missing" if error is MakerTakerError else "wrong-chain")
        with pytest.raises(error):
            run_v5_receipts(bundle_dir=root, intake_dir=intake,
                            expected_intake_sha256=digest, output_dir=out,
                            api=wrong_api, code_commit="b" * 40)
        assert not out.exists()


def test_wallet_mutation_after_intake_rejects_receipt_collection(tmp_path):
    root, intake, digest = setup(tmp_path)
    with (root / "wallet" / "live_activity.jsonl").open("ab") as handle:
        handle.write(b"{}\n")
    out = tmp_path / "receipts"
    with pytest.raises(ValueError, match="changed since intake"):
        run_v5_receipts(bundle_dir=root, intake_dir=intake,
                        expected_intake_sha256=digest, output_dir=out,
                        api=api(), code_commit="b" * 40)
    assert not out.exists()
