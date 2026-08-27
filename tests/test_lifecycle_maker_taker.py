from smartcopy.lifecycle_maker_taker import _dominance, label_lifecycle_rows


def test_dominance_uses_frozen_eighty_percent_gate() -> None:
    assert _dominance({"maker_share": 0.1, "taker_share": 0.9}) == "TAKER_DOMINANT"
    assert _dominance({"maker_share": 0.8, "taker_share": 0.2}) == "MAKER_DOMINANT"
    assert _dominance({"maker_share": 0.5, "taker_share": 0.5}) == "MIXED"


def test_lifecycle_labels_unique_preopen_side_and_excludes_mixed_market() -> None:
    rows = [
        {"condition_id": "a", "source_second": 99, "outcome": "Up"},
        {"condition_id": "a", "source_second": 100, "outcome": "Up"},
        {"condition_id": "a", "source_second": 101, "outcome": "Down"},
        {"condition_id": "b", "source_second": 98, "outcome": "Up"},
        {"condition_id": "b", "source_second": 99, "outcome": "Down"},
        {"condition_id": "b", "source_second": 101, "outcome": "Up"},
    ]
    labelled = label_lifecycle_rows(
        rows,
        slugs={"a": "btc-updown-5m-100", "b": "eth-updown-5m-100"},
    )
    assert [row["lifecycle_relation"] for row in labelled[:3]] == [
        "PRE_OPEN_DIRECTIONAL",
        "POST_OPEN_SAME_SIDE",
        "POST_OPEN_COMPLEMENT",
    ]
    assert all(
        row["lifecycle_relation"] == "NO_UNIQUE_PREOPEN_SIDE" for row in labelled[3:]
    )
