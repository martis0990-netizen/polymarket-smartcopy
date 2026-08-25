# TradingLab / SmartCopy Boundary

## TradingLab

TradingLab is the research and evidence laboratory. It may own:

- market data capture
- deterministic replay
- microstructure research
- detector evaluation
- wallet/market studies
- latency/execution experiments
- hypothesis testing
- reusable verified research artifacts

## SmartCopy

SmartCopy is the selective follower product. It owns:

- wallet watchlist/intelligence consumption
- source activity observation
- first-observed timestamps
- intent reconstruction
- copyability decision
- follower portfolio risk
- paper/shadow order lifecycle
- eventual live execution after gates

## Integration rule

Prefer explicit stable artifacts/contracts over shared mutable internals.

Examples of acceptable inputs from TradingLab:

- frozen dataset manifests
- verified market-family metrics
- wallet research tables
- edge-decay evidence
- execution-model calibration

SmartCopy should record the artifact/version/hash it consumed.

## Prohibited duplication

Do not create inside SmartCopy merely for convenience:

- a second general replay engine
- a second broad detector framework
- a second research orchestration system
- a second market-data lake

If SmartCopy discovers a measured research capability gap, first decide whether it belongs in TradingLab. Rule: `No measured gap -> no component.`

## Operational independence

SmartCopy production must not depend on TradingLab being online in real time. Offline research artifacts can inform versioned decision rules, while SmartCopy's observer/context/risk/execution path remains small and independently operable.
