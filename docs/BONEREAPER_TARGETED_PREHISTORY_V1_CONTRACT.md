# Bonereaper targeted prehistory v1 — frozen contract

Status: **FROZEN BEFORE TARGETED PREHISTORY RETRIEVAL**

## Purpose

Extend lifecycle ledger v1 backwards from the slug epoch to the earliest frozen Gamma creation
timestamp.  Determine whether earlier public activity explains the 1,459.025539-token deficit in
the current BTC 5m winning `Up` redemption and place all five target conditions on the same public
Data API cash basis.

This remains public-flow accounting, not fee-adjusted wallet PnL.  Exact trade fees, rewards,
rebates, transfers and activity before market creation remain outside this stage.

## Immutable inputs

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- Gamma response rows SHA256:
  `d28c1fa9de96766c8828238a1f8f49c9d2cb63a182bb9f76e4c320d20fc9ef24`
- economics condition rows SHA256:
  `8c848d320e2cc53e931fb408d493166f7ccb784416a56bcc4e8bdfdb745fb32f`
- settlement rows SHA256:
  `76e1dbae9cd9ef7708cde1976afa6ec13bc9018134483b87c5b91f9c599617b8`
- decoded clean-capture rows SHA256:
  `1cbbe07f740682e1f6542d1ed70d7d2b8b63a9099a3366382aa3e3b1bff2ab31`
- lifecycle v1 target activity SHA256:
  `97887d7905a03967fe574d6e4ee8b2af34bf1d0d03c133ba9a559834bb9891c2`

## Frozen query

- inclusive interval: Unix `[1787755662, 1787855700]`
- start source: floor to whole seconds of earliest frozen Gamma `createdAt`,
  `2026-08-26T14:47:42.057943Z`
- end: unchanged settlement-v1 cutoff, `2026-08-27T18:35:00Z`
- activity types: exact `TRADE,SPLIT,MERGE,REDEEM`
- condition filter: exact comma-separated string, in this order:

`0x3117cfe02c20d02daf2d4e30addbe7d188c42e191e51437eef1022ffb56e3fbe,0x52156b9f8f14c0c15022bb2187be136415341382b92f63e6de059f0db74f3aa3,0x7021e760b33268e406766a7077a7571d8fd3935bc1ced475dc1e9d406ce81b7c,0x9bb775834f30a9014bd48b28e72ac73b187ba7b61c6cbe6050bd79da20ab3e04,0xa0201d069b577fbeb1b31967db06be613bd825b6e9acc656ebd58e17eb1d3809`

The complete range collector must pass `market` unchanged on every page and recursive subwindow.
Any returned condition outside this set fails closed.  Pagination truncation or exhausted bounded
HTTP retry fails closed.

## Accounting

Reuse lifecycle ledger v1 outcome equations without modification:

`flow_balance = BUY + SPLIT - SELL - MERGE - REDEEM`

and public pre-fee cash:

`SELL usdcSize + MERGE usdcSize + REDEEM usdcSize - BUY usdcSize - SPLIT usdcSize`.

Report each outcome and condition, plus:

- exact row identity overlap with lifecycle v1;
- newly recovered pre-epoch rows, BUY tokens and BUY USDC by condition/outcome;
- previous versus extended minimum unexplained inflow;
- previous versus extended public pre-fee cash flow;
- whether every negative outcome balance becomes zero or positive.

Do not label a positive remaining losing-token balance as unexplained or valuable.  Do not infer a
fee-adjusted result from Data API `usdcSize`.

## Prehistory resolution criterion

- `PREHISTORY_GAP_CLOSED` only if aggregate minimum unexplained inflow falls from 1,459.025539 to
  exactly zero and all five conditions have no negative outcome balance;
- otherwise `PREHISTORY_GAP_REMAINS`, with the exact residual reported.

This criterion tests inventory completeness only.  It cannot label the strategy profitable.

## Stopping and immutable outputs

The broader lifecycle study remains `COLLECTING` at 5/30 resolved conditions.  A new output
directory must not pre-exist.  Preserve raw targeted activity, normalized activity, pre-epoch rows,
outcome ledgers, condition summaries, comparison rows, aggregate summary and a manifest binding
input/output SHA256 plus contract and code commits.  Validation failure withholds a clean manifest.
