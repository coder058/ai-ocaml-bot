"""Read-only inventory of existing Pattern Forge recordings and Info Desk.

Never converts a historical contract into an Alpaca instrument, interpolates
missing candles, exports editorial notes or grants a model/order authority.
"""
import argparse
import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# SOURCE: recordings/catalog.json declares native hourly Unix millisecond bars.
HOUR_MS = 60 * 60 * 1000


def stamp(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace('+00:00','Z')


def recordings(public_root):
    catalog=json.loads((public_root/'recordings/catalog.json').read_text(encoding='utf-8'))
    result=[]
    for item in catalog:
        path=(public_root/item['path'].lstrip('/')).resolve()
        if not path.is_relative_to(public_root.resolve()):
            raise ValueError('catalog path leaves public recording directory')
        raw=path.read_bytes();document=json.loads(raw);rows=document['candles']
        if document['metadata']!=item or item['interval']!='1h' or not rows:
            raise ValueError('recording metadata differs from original catalog')
        starts=[r['t'] for r in rows]
        if starts!=sorted(set(starts)) or len(rows)!=item['count']:
            raise ValueError('recording has duplicate/nonchronological times or wrong count')
        for row in rows:
            if (row['closed'] is not True or row['t']%HOUR_MS
                    or row['closeTime']!=row['t']+HOUR_MS or row['closeTime']>item['asOf']
                    or not all(isinstance(row[k],(int,float)) and not isinstance(row[k],bool)
                               and math.isfinite(row[k]) for k in ('o','h','l','c','v'))
                    or not 0<row['l']<=min(row['o'],row['c'])<=max(row['o'],row['c'])<=row['h']
                    or row['v']<0):
                raise ValueError('recording has invalid, forming or future candle')
        deltas=[b-a for a,b in zip(starts,starts[1:])]
        if any(d%HOUR_MS for d in deltas):raise ValueError('recording gap is not an hourly boundary')
        result.append({'symbol':item['symbol'],'venue':item['venue'],'interval':item['interval'],
            'candles':len(rows),'firstStart':stamp(starts[0]),'lastClose':stamp(rows[-1]['closeTime']),
            'gapIntervals':sum(d>HOUR_MS for d in deltas),'missingHours':sum(d//HOUR_MS-1 for d in deltas),
            'jsonBytes':len(raw),'jsonSha256':hashlib.sha256(raw).hexdigest(),
            'originalSourceSha256':item['sourceSha256'],'executionQuotesAvailable':False,
            'firstReceiptHistoryAvailable':False,'alpacaInstrumentEquivalenceVerified':False})
    return result


def documents(database):
    # SOURCE: SQLite URI mode=ro prohibits modification of the existing evidence
    # workspace. Only source/receipt counts are selected, never bodies or notes.
    connection=sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        rows=connection.execute('SELECT source_id,COUNT(*),MIN(first_seen),MAX(first_seen) '
                                'FROM live_documents GROUP BY source_id').fetchall()
        versions=connection.execute('SELECT COUNT(*),MIN(received_at),MAX(received_at) FROM live_versions').fetchone()
        return {'documents':sum(r[1] for r in rows),'versions':versions[0],
            'earliestReceipt':versions[1],'latestReceipt':versions[2],
            'sources':[{'sourceId':r[0],'documents':r[1],'firstSeen':r[2],'lastFirstSeen':r[3]} for r in rows],
            'scope':'metadata only; verification database and editorial drafts/notes excluded',
            'freshNewsFeed':False,'tradingSignalLabelsAvailable':False}
    finally:connection.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pattern-forge-public',type=Path,required=True)
    parser.add_argument('--info-desk-database',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    history=recordings(args.pattern_forge_public);news=documents(args.info_desk_database)
    first_news=datetime.fromisoformat(news['earliestReceipt']) if news['earliestReceipt'] else None
    overlap=[r['symbol'] for r in history if first_news and
             datetime.fromisoformat(r['lastClose'].replace('Z','+00:00'))>=first_news]
    result={'schema':'related_market_news_inventory_v1',
        'observedAt':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        'recordings':history,'totalCandles':sum(r['candles'] for r in history),'infoDesk':news,
        'recordingsWithPossibleNewsReceiptOverlap':overlap,
        'orderAuthority':False,'winProbability':None,
        'limitation':'Historical hourly contract recordings lack executable quotes and original receipt history. '
                     'News first received after a candle cannot be a feature for that earlier decision. '
                     'Neither inventory establishes predictive edge, live data or an execution connection.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'recordings':len(history),'candles':result['totalCandles'],
        'documents':news['documents'],'possibleNewsOverlap':overlap,'orderAuthority':False}))


if __name__=='__main__':main()
