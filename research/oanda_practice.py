"""OANDA v20 practice-only FX connection, catalog and closed candles.

No wallet, production endpoint, order submission or credential export. Missing
credentials produce an explicit connection blocker, never simulated executions.
"""
from __future__ import annotations
import argparse
import http.client
import json
import os
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# SOURCE: OANDA v20 Development Guide practice REST origin.
ORIGIN='https://api-fxpractice.oanda.com'
ENV_PATH=Path('/etc/ai-ocaml-fx.env')
STATE=Path('/home/ubuntu/jsbot-paper-state')
# SOURCE: user's requested frame durations and OANDA CandlestickGranularity enum.
FRAMES={'1m':'M1','5m':'M5','30m':'M30','1h':'H1','4h':'H4'}
# SOURCE: EMA50 warmup plus one preceding candle, shared with the OCaml scanner.
SEED_BARS=51
# GUESS: # UNCALIBRATED GUESS — a 15s HTTP timeout bounds provider failure;
# observe real practice API latency before changing this operational setting.
TIMEOUT_SECONDS=15
# SOURCE: requested major currencies. Actual account availability is authoritative.
PREFERRED=('EUR_USD','GBP_USD','USD_JPY','USD_CHF','AUD_USD','USD_CAD',
           'NZD_USD','EUR_GBP','EUR_JPY','GBP_JPY')
_connection=None

def stamp():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def atomic(path:Path,document:dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(document,stream,allow_nan=False);stream.flush();os.fsync(stream.fileno())
    os.chmod(temporary,0o640)  # SOURCE: private operational market-data state.
    os.replace(temporary,path)

def credentials(path:Path=ENV_PATH):
    if not path.exists():return None
    # SOURCE: API tokens must not be readable by unrelated local users/groups.
    if stat.S_IMODE(path.stat().st_mode)&0o077:raise ValueError('FX credential file must be owner-only')
    values={}
    for line in path.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            name,value=line.split('=',1);values[name]=value
    token=values.get('OANDA_PRACTICE_TOKEN','');account=values.get('OANDA_PRACTICE_ACCOUNT','')
    if not token or not account:return None
    if not re.fullmatch(r'[0-9-]+',account) or any(c in token for c in '\r\n\0'):
        raise ValueError('Invalid practice credential format')
    return token,account

def get(path:str,token:str):
    global _connection
    if not path.startswith('/v3/') or '..' in path or '\n' in path:
        raise ValueError('Invalid practice resource')
    # SOURCE: OANDA recommends persistent connections and limits new connections
    # to two per second. All requests share one TLS connection to practice only.
    if _connection is None:
        _connection=http.client.HTTPSConnection('api-fxpractice.oanda.com',timeout=TIMEOUT_SECONDS)
    try:
        _connection.request('GET',path,headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
        response=_connection.getresponse();body=response.read()
        if response.status!=200:
            raise urllib.error.HTTPError(ORIGIN+path,response.status,response.reason,{},None)
        return json.loads(body)
    except Exception:
        _connection.close();_connection=None;raise

def public_instruments(document):
    rows=document.get('instruments')
    if not isinstance(rows,list):raise ValueError('FX catalog missing')
    # SOURCE: use the account-specific CURRENCY catalog, not guessed contracts.
    return [{k:r.get(k) for k in ('name','displayName','type','pipLocation',
        'displayPrecision','tradeUnitsPrecision','minimumTradeSize','maximumOrderUnits','marginRate')}
        for r in rows if r.get('type')=='CURRENCY' and re.fullmatch(r'[A-Z]{3}_[A-Z]{3}',r.get('name',''))]

def closed_candles(document,as_of:datetime):
    from market_pipeline import normalize,FRAMES as SCAN_FRAMES
    frame=document['frame'];minutes=SCAN_FRAMES[frame][0];rows=[]
    for candle in document.get('candles',[]):
        if candle.get('complete') is not True:continue
        mid=candle.get('mid')
        if not isinstance(mid,dict):raise ValueError('FX midpoint candle missing')
        row={'t':candle['time'],**{k:mid[k] for k in ('o','h','l','c')},'v':candle['volume']}
        parsed=normalize(row,minutes,as_of)
        if parsed is not None:rows.append(parsed)
    return rows

def connect(output:Path=STATE/'fx-connection.json',env_path:Path=ENV_PATH,fetch_candles=False):
    status={'asOf':stamp(),'provider':'OANDA practice','product':'Spot FX demo',
        'connected':False,'executionMode':'practice','automaticStrategy':False,
        'orderAuthority':False,'executionAdapterAvailable':False,'origin':ORIGIN,
        'reason':'practice_credentials_missing','framesRequested':list(FRAMES),'instruments':[]}
    try:
        creds=credentials(env_path)
        if creds is None:atomic(output,status);return status
        token,account=creds
        # SOURCE: no account identity or balance is included in public telemetry.
        summary=get('/v3/accounts/'+account+'/summary',token)
        if not isinstance(summary.get('account'),dict):raise ValueError('Practice account summary missing')
        instruments=public_instruments(get('/v3/accounts/'+account+'/instruments',token))
        names={r['name'] for r in instruments};watch=[s for s in PREFERRED if s in names]
        pricing=get('/v3/accounts/'+account+'/pricing?'+urllib.parse.urlencode({'instruments':','.join(watch)}),token)
        prices=[{k:r.get(k) for k in ('instrument','time','status','tradeable','bids','asks','closeoutBid','closeoutAsk')}
                for r in pricing.get('prices',[]) if r.get('instrument') in names]
        status.update(connected=True,reason='connected_data_only',instruments=instruments,
            monitoredPairs=watch,catalogCount=len(instruments),prices=prices,asOf=stamp())
        if fetch_candles:
            candles=[]
            for pair in watch:
                for frame,granularity in FRAMES.items():
                    query=urllib.parse.urlencode({'granularity':granularity,'count':SEED_BARS+1,
                        'price':'M','dailyAlignment':0,'alignmentTimezone':'UTC'})
                    raw=get('/v3/instruments/'+pair+'/candles?'+query,token)
                    rows=closed_candles({**raw,'frame':frame},datetime.now(timezone.utc))
                    candles.append({'symbol':pair,'frame':frame,'bars':rows,'retrievedAt':stamp(),
                        'priceBasis':'midpoint','volumeBasis':'price-update count','orderAuthority':False})
            atomic(output.with_name('fx-practice-candles.json'),{'asOf':stamp(),'markets':candles})
    except urllib.error.HTTPError as error:
        status.update(connected=False,reason='practice_http_'+str(error.code))
    except Exception as error:
        # SOURCE: report error class only; credential values never reach telemetry.
        status.update(connected=False,reason='practice_connection_error',errorClass=type(error).__name__)
    atomic(output,status);return status

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=STATE/'fx-connection.json')
    parser.add_argument('--candles',action='store_true');args=parser.parse_args()
    result=connect(args.output,fetch_candles=args.candles)
    print(json.dumps({k:result[k] for k in ('asOf','connected','reason')}))
