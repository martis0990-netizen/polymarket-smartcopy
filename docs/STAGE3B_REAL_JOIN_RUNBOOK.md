# Stage 3B — First Real Join Runbook

Purpose: join the preserved prospective Bonereaper observer evidence to the independently
captured Polymarket `events.jsonl` without allowing accidental artifact substitution.

No live trading or COPY/WATCH/SKIP decision is authorized by this runbook.

## 1. Use the frozen SmartCopy implementation

```bash
git fetch origin
git checkout main
git pull --ff-only
```

Record the commit before the run:

```bash
git rev-parse HEAD
```

The first evidence-bound implementation is introduced after Stage 3B main SHA
`2e5421b9c73159f494d0bef7257fd99a9ce89e32`.

## 2. Download the preserved Stage 3A artifact

The reference artifact expires on 2026-09-25, so preserve a local copy before then.

```bash
mkdir -p /home/al/workspace/smartcopy-evidence/stage3a-2026-08-26

gh run download 32971365532 \
  -R martis0990-netizen/polymarket-smartcopy \
  -n live-wallet-observer-v1-smoke \
  -D /home/al/workspace/smartcopy-evidence/stage3a-2026-08-26
```

Verify the file that Stage 3B actually consumes:

```bash
printf '%s  %s\n' \
  e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb \
  /home/al/workspace/smartcopy-evidence/stage3a-2026-08-26/live_activity.jsonl \
  | sha256sum -c -
```

Do not continue if this check fails.

## 3. Select one immutable Polymarket capture artifact

Resolve the exact normalized TradingLab `events.jsonl` that overlaps the Stage 3A window:

- Stage 3A source/observation evidence spans approximately
  `2026-08-26T12:57:10Z` through `2026-08-26T12:58:50.648699Z`.
- The selected PM capture must contain real `receive_ts` and exact CLOB token ids.
- Do not concatenate, edit, sort, trim, or rewrite the selected file for the confirmatory
  run. If a derived slice is ever needed, it becomes a different explicitly hashed input.

Set the path only after identifying the correct immutable artifact:

```bash
PM_EVENTS=/absolute/path/to/the/frozen/events.jsonl
```

Bind its identity:

```bash
PM_SHA256=$(sha256sum "$PM_EVENTS" | awk '{print $1}')
printf 'PM events SHA256: %s\n' "$PM_SHA256"
```

Record that hash in the result note before interpreting any output.

## 4. Run exactly one Stage 3B join

Use a fresh output directory. The joiner refuses overwrite.

```bash
OUT=/home/al/workspace/smartcopy-evidence/stage3b-first-real-join
rm -rf "$OUT"

python -m smartcopy.executable_state_join \
  --wallet-activity /home/al/workspace/smartcopy-evidence/stage3a-2026-08-26/live_activity.jsonl \
  --expected-wallet-sha256 e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb \
  --market-events "$PM_EVENTS" \
  --expected-market-sha256 "$PM_SHA256" \
  --output "$OUT"
```

Any SHA mismatch, receive-time regression, invalid LIVE_OBSERVED row, or corrupt JSONL is a
hard failure. Do not remove the guard and rerun merely to obtain a result.

## 5. Verification gate

Before interpreting deterioration, independently verify:

```bash
python - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path('/home/al/workspace/smartcopy-evidence/stage3b-first-real-join')
manifest = json.loads((root / 'join_manifest.json').read_text())
rows = [json.loads(line) for line in (root / 'executable_state_join.jsonl').read_text().splitlines()]

assert manifest['schema_version'] == 'smartcopy-executable-state-join-v1'
assert manifest['wallet_rows'] == 77
assert manifest['joined_rows'] + manifest['no_executable_state_rows'] == 77
assert manifest['inputs']['wallet_activity']['sha256'] == \
    'e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb'
assert manifest['inputs']['wallet_activity']['sha256'] == \
    manifest['inputs']['wallet_activity']['expected_sha256']
assert manifest['inputs']['market_events']['sha256'] == \
    manifest['inputs']['market_events']['expected_sha256']
assert len(rows) == 77
assert all(row['status'] in {'JOINED', 'NO_EXECUTABLE_STATE'} for row in rows)

raw = (root / 'executable_state_join.jsonl').read_bytes()
assert hashlib.sha256(raw).hexdigest() == manifest['artifacts']['executable_state_join.jsonl']['sha256']
print(json.dumps(manifest, indent=2, sort_keys=True))
PY
```

If this gate passes, preserve the entire output directory unchanged and record its hashes.

## 6. What may be concluded

The first real result may answer only:

- how many of the 77 prospectively observed wallet rows can be exact-token joined to a
  post-observation executable PM side with evidenced size;
- how long `first_observed_time → executable state` takes;
- total `source_event_time → executable state` delay;
- signed source-price deterioration by the time the state is available.

Do **not** select a profitable deterioration threshold, infer causality, or promote rows to
COPY/WATCH/SKIP from this run. A residual-edge contract comes only after this gate is
reviewed and frozen evidence is preserved.
