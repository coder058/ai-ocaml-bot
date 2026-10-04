"""Persist IEX stock quotes and bars; no trading authority or private inventory."""
import asyncio,json,os,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from websockets.asyncio.client import connect
from stream_capture import credentials
from oanda_practice import atomic,stamp

# SOURCE: Alpaca real-time stock market data endpoint, free IEX feed.
URL='wss://stream.data.alpaca.markets/v2/iex'
STATE=Path('/home/ubuntu/jsbot-paper-state')
# SOURCE: Alpaca Basic supports 30 stock WS symbols; requested index, energy,
# currency ETFs and popular stocks are selected explicitly, not by fitted alpha.
SYMBOLS=('DIA','QQQ','SPY','IWM','XLE','XOP','USO','UNG','BNO','OIH',
         'UUP','FXE','FXY','FXB','FXC','FXA','FXF','TSLA','NVDA','MSFT',
         'AMZN','GOOGL','META','AMD','AVGO','JPM','GS','XOM','CVX','GLD')
# GUESS: # UNCALIBRATED GUESS — same five-second reconnect as crypto capture.
RECONNECT_SECONDS=5
# GUESS: # UNCALIBRATED GUESS — refresh operational status every five seconds.
STATUS_SECONDS=5
# GUESS: # UNCALIBRATED GUESS — stop if less than 5 GiB storage remains.
MIN_FREE_BYTES=5*1024*1024*1024
# GUESS: # UNCALIBRATED GUESS — bound a provider WS frame at 4 MiB.
MAX_MESSAGE_BYTES=4*1024*1024

def subscription():return {'action':'subscribe','quotes':list(SYMBOLS),'bars':list(SYMBOLS),'updatedBars':list(SYMBOLS)}
def confirmed(row):return all(set(SYMBOLS)<=set(row.get(channel,[])) for channel in ('quotes','bars','updatedBars'))
def valid(row):return row.get('T') in ('q','b','u') and row.get('S') in SYMBOLS and isinstance(row.get('t'),str)

async def capture():
    directory=STATE/'market-capture'/'iex';directory.mkdir(parents=True,exist_ok=True)
    # SOURCE: OCaml runs as ubuntu and needs group read access to market archives.
    group=os.stat('/home/ubuntu').st_gid;os.chown(directory,0,group);os.chmod(directory,0o750)
    health={'provider':'Alpaca IEX','product':'US stocks / ETF','feed':'iex','connected':False,
        'symbols':list(SYMBOLS),'symbolLimit':len(SYMBOLS),'quoteCount':0,'barCount':0,
        'orderAuthority':False,'fullNbbo':False,'lastMarketEventAt':None}
    handle=None;day=None;last_status=0.;sequence=0
    async def publish_health():
      while True:
        # SOURCE: this is process/connection liveness, distinct from lastMarketEventAt.
        health['asOf']=stamp();atomic(STATE/'stock-capture.json',health)
        await asyncio.sleep(STATUS_SECONDS)
    publisher=asyncio.create_task(publish_health())
    try:
      while True:
        try:
          key,secret=credentials();health.update(connected=False,reason='connecting',asOf=stamp())
          atomic(STATE/'stock-capture.json',health)
          async with connect(URL,max_size=MAX_MESSAGE_BYTES) as ws:
            await ws.send(json.dumps({'action':'auth','key':key,'secret':secret}))
            authenticated=False;session=uuid.uuid4().hex
            async for text in ws:
              rows=json.loads(text)
              if not isinstance(rows,list):raise ValueError('non-array stock frame')
              for row in rows:
                if row.get('T')=='error':
                  health['providerErrorCode']=row.get('code');raise ValueError('stock provider error')
                if row.get('T')=='success' and row.get('msg')=='authenticated':
                  authenticated=True;await ws.send(json.dumps(subscription()))
                if row.get('T')=='subscription':
                  if not authenticated or not confirmed(row):raise ValueError('stock subscription incomplete')
                  health.update(connected=True,reason='subscribed',session=session,asOf=stamp())
                  atomic(STATE/'stock-capture.json',health)
                if not valid(row):continue
                if not health['connected']:raise ValueError('market event before verified subscription')
                space=os.statvfs(directory)
                if space.f_bavail*space.f_frsize<MIN_FREE_BYTES:raise OSError('capture disk guard')
                received=time.time_ns();today=datetime.now(timezone.utc).date().isoformat()
                if day!=today:
                  if handle:handle.flush();os.fsync(handle.fileno());handle.close()
                  file=directory/(today+'.jsonl');handle=file.open('a');os.chmod(file,0o640);os.chown(file,0,group);day=today
                sequence+=1
                handle.write(json.dumps({'event':row,'receivedAtNs':received,'session':session,'sequence':sequence})+'\n')
                health['quoteCount' if row['T']=='q' else 'barCount']+=1
                health['lastMarketEventAt']=row['t']
              if time.monotonic()-last_status>=STATUS_SECONDS:
                if handle:handle.flush()
                health['asOf']=stamp();atomic(STATE/'stock-capture.json',health);last_status=time.monotonic()
        except Exception as error:
          # SOURCE: exception class only; provider auth payloads and keys stay private.
          health.update(connected=False,reason='stream_error',errorClass=type(error).__name__,asOf=stamp())
          atomic(STATE/'stock-capture.json',health)
          await asyncio.sleep(RECONNECT_SECONDS)
    finally:
      publisher.cancel();await asyncio.gather(publisher,return_exceptions=True)
      if handle:handle.flush();os.fsync(handle.fileno());handle.close()

if __name__=='__main__':asyncio.run(capture())
