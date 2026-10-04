"""Read-only Alpaca PAPER trade_updates; REST remains the reconciliation source."""
import asyncio,json,os,time,uuid,re
from pathlib import Path
from websockets.asyncio.client import connect
from stream_capture import credentials
from oanda_practice import atomic,stamp

# SOURCE: Alpaca Websocket Streaming trading-account paper endpoint.
URL='wss://paper-api.alpaca.markets/stream'
STATE=Path('/home/ubuntu/jsbot-paper-state')
# GUESS: # UNCALIBRATED GUESS — five-second transport retry and health cadence.
RECONNECT_SECONDS=5
STATUS_SECONDS=5
# GUESS: # UNCALIBRATED GUESS — bound provider frames at one MiB.
MAX_MESSAGE_BYTES=1024*1024

def owned(order):
    symbol=order.get('symbol','');cid=order.get('client_order_id','')
    if not isinstance(symbol,str) or not isinstance(cid,str) or symbol=='AAPL':return False
    crypto=bool(re.fullmatch(r'[A-Z0-9]+/?USD',symbol))
    return (crypto and (cid.startswith('jsbotmtf') or cid.startswith('jsbotbtc') and symbol.replace('/','')=='BTCUSD')
        or not crypto and bool(re.fullmatch(r'[A-Z0-9][A-Z0-9.-]*',symbol)) and cid.startswith('aibotstk'))

def public_event(row):
    if row.get('stream')!='trade_updates' or not isinstance(row.get('data'),dict):return None
    data=row['data'];order=data.get('order')
    if not isinstance(order,dict) or not owned(order):return None
    return {**{k:data.get(k) for k in ('event','execution_id','timestamp','price','qty','position_qty')},
        'order':{k:order.get(k) for k in ('id','client_order_id','symbol','side','status','filled_qty',
            'filled_avg_price','submitted_at','updated_at','type','time_in_force','asset_class')}}

async def capture():
    health={'provider':'Alpaca paper order stream','connected':False,'reason':'connecting',
        'lastOrderEventAt':None,'eventCount':0,'orderAuthority':False,'restReconciliationRequired':True}
    async def publish():
        while True:
            health['asOf']=stamp();atomic(STATE/'paper-order-capture.json',health)
            await asyncio.sleep(STATUS_SECONDS)
    publisher=asyncio.create_task(publish())
    try:
      while True:
        try:
          key,secret=credentials();health.update(connected=False,reason='connecting')
          async with connect(URL,max_size=MAX_MESSAGE_BYTES) as ws:
            await ws.send(json.dumps({'action':'auth','key':key,'secret':secret}))
            authenticated=False;session=uuid.uuid4().hex;sequence=0
            async for text in ws:
              # SOURCE: paper stream uses binary JSON frames; json.loads accepts bytes.
              row=json.loads(text)
              if row.get('stream')=='authorization':
                if row.get('data',{}).get('status')!='authorized':raise ValueError('paper order stream unauthorized')
                authenticated=True;await ws.send(json.dumps({'action':'listen','data':{'streams':['trade_updates']}}))
              if row.get('stream')=='listening':
                if not authenticated or 'trade_updates' not in row.get('data',{}).get('streams',[]):
                    raise ValueError('paper order subscription incomplete')
                health.update(connected=True,reason='subscribed',session=session)
              event=public_event(row)
              if event is None:continue
              if not health['connected']:raise ValueError('order event before subscription')
              sequence+=1;health['eventCount']+=1;health['lastOrderEventAt']=event['timestamp'] or stamp()
              file=STATE/'paper-order-stream.jsonl'
              # SOURCE: private lab-only operational journal, fsynced before health publication.
              with file.open('a') as stream:
                stream.write(json.dumps({'receivedAtNs':time.time_ns(),'session':session,'sequence':sequence,
                    'data':event})+'\n');stream.flush();os.fsync(stream.fileno())
              os.chmod(file,0o640);os.chown(file,0,os.stat('/home/ubuntu').st_gid)
        except Exception as error:
          health.update(connected=False,reason='stream_error',errorClass=type(error).__name__)
          await asyncio.sleep(RECONNECT_SECONDS)
    finally:
      publisher.cancel();await asyncio.gather(publisher,return_exceptions=True)

if __name__=='__main__':asyncio.run(capture())
