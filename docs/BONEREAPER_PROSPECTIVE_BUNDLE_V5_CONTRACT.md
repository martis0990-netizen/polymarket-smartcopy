# Bonereaper prospective bundle v5 — frozen split-book contract

Status: **FROZEN BEFORE THE FIRST V5 BUNDLE**

## Reason for the new version

Two v4 attempts bound current and following conditions in one CLOB subscription.  Both failed
closed during bootstrap when a delta with an earlier source timestamp arrived immediately after a
newer snapshot.  The frozen public-book contract requires any per-token timestamp regression to
fail the run.  V5 preserves that rule and splits the token populations across independent sockets.

## Bound populations

Gamma discovery retains v4 semantics and labels each exact token with `current`, `safe`, or both:

- `current_book`: every token whose condition is current at discovery, including a condition that
  also satisfies the safe full-capture constraint;
- `safe_book`: safe following-condition tokens only when their condition differs from current.

The groups must be non-empty, disjoint by token ID, and together cover every discovered token.
Condition IDs, token IDs, outcomes, slugs, window starts, lengths and end dates are fixed before
capture.  Discovery remains outside capture time.

## Concurrent capture

After binding, start four children concurrently for at most 120 requested seconds:

1. Chainlink BTC/USD and ETH/USD 60-second TWAP recorder;
2. live Bonereaper wallet observer;
3. public CLOB recorder for `current_book`;
4. independent public CLOB recorder for `safe_book`.

Each book child obeys the unchanged public-book capture contract.  A timestamp regression,
disconnect policy violation, malformed event, or any child exception fails the complete bundle.
Partial files remain diagnostic; no clean root manifest is written.

## Clean root and downstream use

A clean root SHA-binds both book manifests and both token-metadata artifacts in addition to the
Chainlink and wallet manifests.  It records event counts, reconnects and final initialization per
book group.  Receipt analysis must select the unique bound group by token ID before exact-level
classification; cross-group or cross-condition joins are forbidden.

Pre-open and post-open signal gates, same-second exclusion, 30-condition maker stopping rule and
all existing signal thresholds remain unchanged.  A scheduled boundary bundle must still start at
least 76 seconds before the target open and end at or after it to contribute a pre-open condition.
The recorder cannot construct, sign, cancel or submit orders.

