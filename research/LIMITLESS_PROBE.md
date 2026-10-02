# Limitless: read-only SmartCopy probe

This is a small observability check for Limitless, separate from the Polymarket v5 experiment. It polls the public trading feed and three public wallet histories, records when events first become visible, and fetches a current order book for matching crypto buys.

Run locally:

```bash
python3 research/limitless_smartcopy_probe.py --selftest
python3 research/limitless_smartcopy_probe.py --minutes 3 --interval 15 --out limitless_probe
```

The GitHub Actions workflow runs a three-minute smoke check on this research branch. A manual dispatch can run a 60-minute observation. The script uses standard-library Python and public GET endpoints only. It needs no keys and cannot place orders.

Artifacts contain `observations.jsonl`, `books.jsonl` (when applicable), and `summary.json`. `API_UNAVAILABLE` means that requests failed before any observation. `OBSERVATIONS_ONLY_NO_EDGE_CLAIM` does not imply that a wallet is copyable. Public feed caching, unknown history coverage, response schema changes, polling delay, current versus historical order books, and fees limit conclusions. Review raw records before counting independent intent episodes. Do not infer expected profit from the observed source price or from top-of-book quotes.

This pilot does not alter the four Polymarket v5 signals, its stopping rule, or live trading authorization.
