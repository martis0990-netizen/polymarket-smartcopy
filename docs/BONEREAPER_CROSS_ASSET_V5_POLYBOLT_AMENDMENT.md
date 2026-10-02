# Bonereaper cross-asset v5 — prospective capture transport amendment

Status: **FROZEN BEFORE ANY V5-ELIGIBLE CONDITION**. The 2026-10-02 RTDS
smokes were engineering-only; no v5 condition has been scored.

The original v5 contract names the public RTDS `crypto_prices_twap_sixty`
transport. Polymarket now documents migration of price topics to authenticated
PolyBolt `price.crypto.twap`. This amendment changes only transport and evidence
handling. The six core assets, HYPE exclusion, features, decision windows,
stopping rule, and gates in `BONEREAPER_CROSS_ASSET_MODEL_V5_CONTRACT.md` remain
fixed. No RTDS and PolyBolt observations are combined in one bundle.

- Explicitly subscribe to the seven frozen `*usd` 60-second TWAP symbols on
  PolyBolt; its protocol does not offer an unfiltered topic subscription.
- Use CLOB API key, secret and passphrase from the environment for read-only
  feed authentication; never write, log or hash these credentials into artifacts.
- Save every received TWAP data frame including snapshots, with its receive
  timestamp, channel sequence, producer timestamp, symbol and exact decimal
  value. Snapshots are historic initialization and are never eligible live
  observations. Only live updates contribute to event counts or features.
- Require successful authentication, acceptance and initial snapshot for each
  symbol, then at least one live update for every symbol. Fail the complete
  bundle on any missing/duplicate/out-of-order channel sequence, positive
  `dropped` count, premature disconnect, protocol error or missing symbol.
  This deliberately conservative rule rejects more data than the original
  per-lookback reconnect-gap rule; it cannot turn invalid data into eligible
  data.
- Bind a child manifest that names the feed protocol, all seven symbols, raw
  and gap artifact digests, update counts and clean-finalize status. Bind this
  child manifest with the wallet child manifest in the root bundle as before.

Official protocol:
https://docs.polymarket.com/migrate/rtds-to-polybolt
https://docs.polymarket.com/api-reference/live-data/overview
