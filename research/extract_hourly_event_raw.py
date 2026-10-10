"""Stream the observed REST event tape into SQLite, without loading all candles."""
import datetime as dt
import glob
import gzip
import hashlib
import json
import sqlite3
import zipfile
import zlib

source=json.load(open('limitless_hourly_all_decisions_2026-10-07.json'))['rows']
path,=glob.glob('attachments/**/github-actions-artifact-11470560416.zip',recursive=True)
state=json.loads(zipfile.ZipFile(path).read('state.json'))['paper']
slugs={state['episodes'][row['condition']]['slug'] for row in source}
markets={slug:state['markets'][slug] for slug in slugs}
start=min(m['start'] for m in markets.values())-120
end=max(m['end'] for m in markets.values())
symbols={market['symbol'] for market in markets.values()}
conn=sqlite3.connect('hourly_event_raw.sqlite')
conn.execute('PRAGMA journal_mode=OFF')
conn.execute('PRAGMA synchronous=OFF')
conn.executescript('''
DROP TABLE IF EXISTS books;
DROP TABLE IF EXISTS statuses;
DROP TABLE IF EXISTS refs;
CREATE TABLE books(slug TEXT,kind TEXT,requested REAL,observed REAL,
                   artifact INTEGER,line INTEGER,sha256 TEXT,raw BLOB);
CREATE TABLE statuses(slug TEXT,observed REAL,status TEXT,artifact INTEGER,line INTEGER);
CREATE TABLE refs(symbol TEXT,kind TEXT,requested REAL,observed REAL,
                  artifact INTEGER,line INTEGER,raw BLOB);
''')


def ts(value):
    return dt.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


counts={'books':0,'statuses':0,'refs':0}
for item in json.load(open('archive_manifest.json')):
    aid=item['artifact']
    zip_path,=glob.glob(f'attachments/**/github-actions-artifact-{aid}.zip',recursive=True)
    with zipfile.ZipFile(zip_path) as archive,gzip.GzipFile(fileobj=archive.open('capture.jsonl.gz')) as capture:
        for line_number,line in enumerate(capture,1):
            if not line.startswith((b'{"kind":"book"',b'{"kind":"request_error"',
                                    b'{"kind":"market"',b'{"kind":"binance_1m"',
                                    b'{"kind":"binance_1h"')):continue
            row=json.loads(line)
            kind=row['kind']
            if kind.startswith('binance_'):
                symbol=(row.get('params') or {}).get('symbol')
                if symbol not in symbols:continue
                observed=ts(row['observed_at'])
                if not start<=observed<=end:continue
                conn.execute('INSERT INTO refs VALUES(?,?,?,?,?,?,?)',
                    (symbol,kind,ts(row['requested_at']),observed,aid,line_number,
                     zlib.compress(json.dumps(row.get('raw'),separators=(',',':')).encode(),3)))
                counts['refs']+=1
                continue
            slug=row.get('slug')
            if slug not in slugs:continue
            if kind=='market':
                conn.execute('INSERT INTO statuses VALUES(?,?,?,?,?)',
                    (slug,ts(row['observed_at']),(row.get('raw') or {}).get('status'),aid,line_number))
                counts['statuses']+=1
            elif kind=='book' or row.get('operation')=='book':
                requested=ts(row['requested_at'])
                if not markets[slug]['start']<=requested<markets[slug]['end']:continue
                conn.execute('INSERT INTO books VALUES(?,?,?,?,?,?,?,?)',
                    (slug,kind,requested,ts(row['observed_at']),aid,line_number,
                     hashlib.sha256(line.rstrip(b'\n')).hexdigest(),
                     zlib.compress(json.dumps(row.get('raw'),separators=(',',':')).encode(),3)))
                counts['books']+=1
    conn.commit()

conn.executescript('''
CREATE INDEX books_slug_observed ON books(slug,observed,artifact,line);
CREATE INDEX books_slug_requested ON books(slug,requested,observed,artifact,line);
CREATE INDEX statuses_slug_observed ON statuses(slug,observed,artifact,line);
CREATE INDEX refs_symbol_kind_observed ON refs(symbol,kind,observed,artifact,line);
''')
assert conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'
conn.close()
print(counts)
