"""Cross-check the event tape against the independently reproduced fixed-window paper."""
import contextlib
import decimal
import io
import json
import runpy

with contextlib.redirect_stdout(io.StringIO()):
    scope=runpy.run_path('replay_hourly_event_trigger.py')
conn=scope['conn']
expand=scope['expand']
inputs=scope['inputs']
state=scope['state']
fixed=json.load(open('limitless_hourly_fixed_windows_2026-10-07.json'))['rows']
events=json.load(open('limitless_hourly_event_trigger_2026-10-08.json'))['rows']

compared=0
max_p_error=0.0
reference_mismatches=[]
missing=[]
for row in fixed:
    if row['p_up'] is None:continue
    ep=state['episodes'][row['condition']]
    market=state['markets'][ep['slug']]
    source=conn.execute('SELECT * FROM books WHERE slug=? AND sha256=?',
                        (ep['slug'],row['source_book_line_sha256'])).fetchone()
    if not source:
        missing.append(row['condition']);continue
    source=expand(source)
    p,_,_,minute,hour=inputs(market,source['observed_at'])
    compared+=1
    max_p_error=max(max_p_error,abs(p-row['p_up']))
    if (minute['artifact'],minute['line'],hour['artifact'],hour['line']) != (
        row['minute_reference_artifact'],row['minute_reference_line'],
        row['hour_reference_artifact'],row['hour_reference_line']):
        reference_mismatches.append(row['condition'])

chronology_errors=[]
for row in events:
    decision,entry,pair=row['decision'],row['entry'],row['pair_quote']
    if entry and (not decision or entry['requested_at']<decision['observed_at']+1.5
                  or entry['requested_at']>decision['observed_at']+30):
        chronology_errors.append((row['condition'],'entry'))
    if pair and (not entry or pair['requested_at']<entry['observed_at']
                 or decimal.Decimal(pair['combined_quoted_cost_usdc'])>=
                    decimal.Decimal(pair['guaranteed_payout_at_quoted_sizes'])):
        chronology_errors.append((row['condition'],'pair'))

assert len(events)==162
assert compared>=500 and max_p_error<1e-12
assert not missing and not reference_mismatches and not chronology_errors
out={'schema':'limitless-hourly-event-verification-v1',
     'fixed_window_valid_forecasts_crosschecked':compared,
     'max_probability_difference':max_p_error,
     'reference_pointer_mismatches':reference_mismatches,
     'missing_source_books':missing,
     'chronology_or_pair_constraint_errors':chronology_errors,
     'condition_rows':len(events)}
with open('limitless_hourly_event_verification_2026-10-08.json','w') as output:
    json.dump(out,output,indent=2)
print(json.dumps(out,indent=2))
