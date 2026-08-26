# Stage 3B — First Real Join Runbook

Purpose: join the preserved prospective Bonereaper observer evidence to the independently
captured Polymarket `events.jsonl` without allowing accidental artifact substitution.

No live trading or COPY/WATCH/SKIP decision is authorized by this runbook.

## 1. Use the frozen SmartCopy implementation

```bash
git fetch origin
git checkout main
git pull --ff-only
git rev-parse HEAD
```

Stage 3B executable-state joining is already in `main`. The deterministic finalized-capture
selector was merged as `2fa3bde4ccdca9916efe5d6ae9e0ac3b5b96c5e0`.

## 2. Preserve the Stage 3A wallet evidence

```bash
mkdir -p /home/al/workspace/smartcopy-evidence/stage3a-2026-08-26

gh run download 32971365532 \
  -R martis0990-netizen/polymarket-smartcopy \
  -n live-wallet-observer-v1-smoke \
  -D /home/al/workspace/smartcopy-evidence/stage3a-2026-08-26
```

The file consumed by Stage 3B is frozen to:

```text
live_activity.jsonl
SHA256 e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb
77 LIVE_OBSERVED rows
```

Verify it:

```bash
printf '%s  %s\n' \
  e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb \
  /home/al/workspace/smartcopy-evidence/stage3a-2026-08-26/live_activity.jsonl \
  | sha256sum -c -
```

Do not continue if this check fails.

## 3. Wait for PM Capture v2 clean finalize

The first real confirmatory join must not read the currently growing 72-hour production file.
The PM run is eligible only after its normal clean-finalize path writes its final sibling
`PM_CAPTURE_V2_MANIFEST.json` and the TradingLab completion gate has verified the artifacts.

Do not copy, trim, concatenate, sort, or snapshot the active `events.jsonl` merely to run
Stage 3B earlier. That would create a different evidence artifact.

## 4. Select the PM capture automatically

Point only to the capture root; do not choose `events.jsonl` manually.

```bash
CAPTURE_ROOT=/home/al/workspace/tradinglab-captures
SELECTION=/home/al/workspace/smartcopy-evidence/stage3b-capture-selection.json
rm -f "$SELECTION"

python -m smartcopy.capture_selector \
  --capture-root "$CAPTURE_ROOT" \
  --wallet-activity /home/al/workspace/smartcopy-evidence/stage3a-2026-08-26/live_activity.jsonl \
  --output "$SELECTION"
```

The selector accepts a capture only when all of the following are true:

- a sibling `PM_CAPTURE_V2_MANIFEST.json` exists and is valid JSON;
- normalized Polymarket rows have real timezone-aware `receive_ts`;
- the file covers the complete Stage 3A observation interval;
- at least one exact CLOB token id overlaps the 77 wallet observations;
- exactly one finalized capture satisfies those conditions.

Zero matches, multiple matches, or corruption in a finalized candidate is a hard failure.
An active run without its final manifest is reported as unfinished and cannot be selected.

Extract the exact selected path and its already-computed SHA256 from the immutable selection
artifact:

```bash
PM_EVENTS=$(python - <<'PY'
import json
from pathlib import Path
p = json.loads(Path('/home/al/workspace/smartcopy-evidence/stage3b-capture-selection.json').read_text())
print(p['selected']['path'])
PY
)

PM_SHA256=$(python - <<'PY'
import json
from pathlib import Path
p = json.loads(Path('/home/al/workspace/smartcopy-evidence/stage3b-capture-selection.json').read_text())
print(p['selected']['sha256'])
PY
)

printf 'PM_EVENTS=%s\nPM_SHA256=%s\n' "$PM_EVENTS" "$PM_SHA256"
```

Do not substitute another file after this point.

## 5. Run exactly one Stage 3B join

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

## 6. Independent verification gate

```bash
python - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path('/home/al/workspace/smartcopy-evidence/stage3b-first-real-join')
manifest = json.loads((root / 'join_manifest.json').read_text())
rows = [json.loads(line) for line in (root / 'executable_state_join.jsonl').read_text().splitlines()]
selection = json.loads(Path('/home/al/workspace/smartcopy-evidence/stage3b-capture-selection.json').read_text())

assert manifest['schema_version'] == 'smartcopy-executable-state-join-v1'
assert manifest['wallet_rows'] == 77
assert manifest['joined_rows'] + manifest['no_executable_state_rows'] == 77
assert manifest['inputs']['wallet_activity']['sha256'] == \
    'e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb'
assert manifest['inputs']['wallet_activity']['sha256'] == \
    manifest['inputs']['wallet_activity']['expected_sha256']
assert manifest['inputs']['market_events']['sha256'] == selection['selected']['sha256']
assert manifest['inputs']['market_events']['sha256'] == \
    manifest['inputs']['market_events']['expected_sha256']
assert len(rows) == 77
assert all(row['status'] in {'JOINED', 'NO_EXECUTABLE_STATE'} for row in rows)

raw = (root / 'executable_state_join.jsonl').read_bytes()
assert hashlib.sha256(raw).hexdigest() == manifest['artifacts']['executable_state_join.jsonl']['sha256']
print(json.dumps(manifest, indent=2, sort_keys=True))
PY
```

If this gate passes, preserve the selection artifact and the entire Stage 3B output directory
unchanged and record their hashes.

## 7. What may be concluded

The first real result may answer only:

- how many of the 77 prospectively observed wallet rows can be exact-token joined to a
  post-observation executable PM side with evidenced size;
- how long `first_observed_time -> executable state` takes;
- total `source_event_time -> executable state` delay;
- signed source-price deterioration by the time the state is available.

Do **not** select a profitable deterioration threshold, infer causality, or promote rows to
COPY/WATCH/SKIP from this run. A residual-edge contract comes only after this gate is
reviewed and frozen evidence is preserved.
