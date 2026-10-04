"""Real OCaml stock router with synthetic curl; no network or market claims.

SOURCE: all numbers below are synthetic failure fixtures, not calibrated policy.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / '_build/default/bin/stock_paper_main.exe'
FAKE = r'''#!/usr/bin/env python3
import sys,os,json
from pathlib import Path
from decimal import Decimal
r=Path(os.environ['SYNTHETIC_STOCK_DIR']); d=json.loads((r/'broker.json').read_text())
sys.stdin.read()
a=sys.argv[1:]; url=a[-1]; method=a[a.index('-X')+1]
def finish(body,code=200):
 print(json.dumps(body));print('__HTTP_STATUS__:'+str(code));sys.exit(0)
if method=='POST':
 assert url=='https://paper-api.alpaca.markets/v2/orders'
 b=json.loads(a[a.index('--data-binary')+1]); assert b['type']=='market' and b['time_in_force']=='day'
 rows=json.loads((r/'stock-paper-ledger.json').read_text())['orders']
 assert any(x['clientOrderId']==b['client_order_id'] and x['state']=='pending' for x in rows)
 with (r/'posts.jsonl').open('a') as f:f.write(json.dumps(b)+'\n')
 if d.get('reject'):finish({'message':'synthetic rejected'},422)
 if d.get('unknown_before'):sys.exit(7)
 q=Decimal('1') if b['side']=='buy' else Decimal(b['qty'])
 q*=Decimal(d.get('fraction','1'))
 pos=Decimal(d.get('position','0'));pos+=q if b['side']=='buy' else -q;d['position']=str(pos)
 o={'symbol':'QQQ','side':b['side'],'client_order_id':b['client_order_id'],
    'status':'canceled' if d.get('fraction') else 'filled','filled_qty':str(q),'filled_avg_price':'100'}
 d.setdefault('orders',{})[b['client_order_id']]=o;(r/'broker.json').write_text(json.dumps(d))
 if d.get('unknown_after'):sys.exit(7)
 if d.get('wrong_ack'):o['symbol']='AAPL'
 finish(o)
if '/orders:by_client_order_id?' in url:
 k=url.split('client_order_id=')[1]
 if k not in d.get('orders',{}):finish({'message':'not found'},404)
 finish(d['orders'][k])
if url.endswith('/v2/account'):finish({'status':'ACTIVE','trading_blocked':False,
 'crypto_status':'INACTIVE','non_marginable_buying_power':'100000'})
if url.endswith('/v2/clock'):finish({'is_open':d.get('open',True),'next_open':'synthetic calendar'})
if url.endswith('/v2/assets/QQQ'):finish({'symbol':'QQQ','class':'us_equity','status':'active','tradable':True,'fractionable':True})
if url.endswith('/v2/positions'):
 rows=[{'symbol':'AAPL','side':'long','qty':'100'}]
 if Decimal(d.get('position','0'))>0:rows.append({'symbol':'QQQ','side':'long','qty':d['position']})
 finish(rows)
if url.endswith('/v2/orders?status=open'):finish(d.get('open_orders',[]))
if url.startswith('https://data.alpaca.markets/v2/stocks/quotes/latest?feed=iex&symbols='):finish({'quotes':{}})
raise AssertionError('unexpected path '+url)
'''

@unittest.skipUnless(ENGINE.exists() and os.name=='posix','requires Linux OCaml build')
class StockRuntime(unittest.TestCase):
    def fixture(self, directory, **data):
        root=Path(directory); (root/'curl').write_text(FAKE);(root/'curl').chmod(0o700)
        (root/'broker.json').write_text(json.dumps(data));return root
    def run_router(self,root,*args,armed=True,ok=True):
        env={**os.environ,'PATH':str(root)+':'+os.environ['PATH'],'PAPER_STATE_DIR':str(root),
             'SYNTHETIC_STOCK_DIR':str(root),'APCA_API_KEY_ID':'SYNTHETIC',
             'APCA_API_SECRET_KEY':'SYNTHETIC','PAPER_ORDERS':'1','STOCK_PAPER_ORDERS':'1' if armed else '0'}
        result=subprocess.run([str(ENGINE),*args],env=env,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode==0,ok,result.stderr);return result
    def buy(self,root,**opts):return self.run_router(root,'--buy','QQQ','--amount','100','--client-id','aibotstkBuy','--execute',**opts)
    def posts(self,root):
        p=root/'posts.jsonl';return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
    def update(self,root,**changes):
        p=root/'broker.json';d=json.loads(p.read_text());d.update(changes);p.write_text(json.dumps(d))
    def test_owned_fractional_buy_sell_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.fixture(d);self.buy(r);self.buy(r)
            self.run_router(r,'--sell','QQQ','--amount','1','--client-id','aibotstkSell','--execute')
            self.assertEqual(len(self.posts(r)),2);self.assertEqual(self.posts(r)[0]['notional'],'100.000000000')
            self.assertEqual(self.posts(r)[1]['qty'],'1.000000000')
    def test_partial_fill_canceled_owns_only_actual_fill(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.fixture(d,fraction='0.4');self.buy(r)
            self.run_router(r,'--sell','QQQ','--amount','0.5','--client-id','aibotstkSell','--execute',ok=False)
            self.assertEqual(len(self.posts(r)),1)
    def test_accepted_timeout_reconciles_without_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.fixture(d,unknown_after=True);self.buy(r);self.buy(r)
            self.assertEqual(len(self.posts(r)),1)
            self.assertEqual(json.loads((r/'stock-paper-ledger.json').read_text())['orders'][0]['state'],'resolved')
    def test_unaccepted_timeout_retains_pending(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.fixture(d,unknown_before=True);self.buy(r);self.buy(r)
            self.assertEqual(len(self.posts(r)),1)
            self.assertEqual(json.loads((r/'stock-paper-ledger.json').read_text())['orders'][0]['state'],'pending')
    def test_closed_session_disarmed_and_unowned_position(self):
        for state,armed in [({'open':False},True),({},False),({'position':'1'},True),({'open_orders':[{'symbol':'QQQ'}]},True)]:
            with self.subTest(state=state),tempfile.TemporaryDirectory() as d:
                r=self.fixture(d,**state);self.buy(r,armed=armed,ok=False);self.assertEqual(self.posts(r),[])
    def test_protected_inventory_and_dry_run(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.fixture(d)
            self.run_router(r,'--sell','AAPL','--amount','1','--client-id','aibotstkSell','--execute',ok=False)
            self.run_router(r,'--buy','QQQ','--amount','100','--client-id','aibotstkBuy')
            self.assertEqual(self.posts(r),[])
    def test_wrong_ack_keeps_durable_pending(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.fixture(d,wrong_ack=True);self.buy(r,ok=False)
            self.assertEqual(json.loads((r/'stock-paper-ledger.json').read_text())['orders'][0]['state'],'pending')
    def test_rejection_is_recorded_without_retry(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.fixture(d,reject=True);self.buy(r);self.buy(r)
            self.assertEqual(len(self.posts(r)),1)
            self.assertEqual(json.loads((r/'stock-paper-ledger.json').read_text())['orders'][0]['state'],'rejected')
    def test_corrupted_duplicate_ledger_cannot_create_double_ownership(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.fixture(d);self.buy(r)
            p=r/'stock-paper-ledger.json';ledger=json.loads(p.read_text());ledger['orders']*=2;p.write_text(json.dumps(ledger))
            self.run_router(r,ok=False);self.assertEqual(len(self.posts(r)),1)
    def test_wrong_identity_in_resolved_ledger_halts(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.fixture(d);self.buy(r)
            p=r/'stock-paper-ledger.json';ledger=json.loads(p.read_text());ledger['orders'][0]['broker']['symbol']='NVDA'
            p.write_text(json.dumps(ledger));self.run_router(r,ok=False);self.assertEqual(len(self.posts(r)),1)

if __name__=='__main__':unittest.main()
