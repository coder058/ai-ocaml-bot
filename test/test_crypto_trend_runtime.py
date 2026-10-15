"""SOURCE: real OCaml BTC trend executor with synthetic curl; never live orders.

Synthetic prices and fills test ownership, durability and gating only. They are
not backtest or profitability evidence.
"""
import json
import os
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / '_build/default/bin/crypto_trend_main.exe'
FAKE = r'''#!/usr/bin/env python3
import sys,os,json
from pathlib import Path
from decimal import Decimal
from datetime import datetime,timezone
r=Path(os.environ['SYNTHETIC_DIR']); d=json.loads((r/'broker.json').read_text())
sys.stdin.read()
a=sys.argv[1:]; url=a[-1]; method=a[a.index('-X')+1]
def finish(body,code=200):
 print(json.dumps(body));print('__HTTP_STATUS__:'+str(code));sys.exit(0)
def save():(r/'broker.json').write_text(json.dumps(d))
if method=='POST':
 assert url=='https://paper-api.alpaca.markets/v2/orders'
 b=json.loads(a[a.index('--data-binary')+1])
 assert b['symbol']=='BTC/USD' and b['type']=='limit' and b['time_in_force']=='ioc'
 assert b['client_order_id'].startswith('aibottrc')
 rows=json.loads((r/'crypto-trend-ledger.json').read_text())['orders']
 assert any(x['clientOrderId']==b['client_order_id'] and x['state']=='pending' for x in rows), 'POST before durable intent'
 with (r/'posts.jsonl').open('a') as f:f.write(json.dumps(b)+'\n')
 if d.get('reject'):finish({'message':'synthetic rejected'},422)
 if d.get('unknown_before'):sys.exit(7)
 q=Decimal(b['qty']) if not d.get('no_fill') else Decimal('0')
 pos=Decimal(d.get('position','0'))
 # SOURCE: Alpaca charges the buy fee in the received asset; model 0.25%.
 pos+= q*Decimal('0.9975') if b['side']=='buy' else -q
 d['position']=format(pos.quantize(Decimal('0.000000001'),rounding='ROUND_DOWN'),'f')
 o={'symbol':'BTC/USD','side':b['side'],'client_order_id':b['client_order_id'],
    'status':'filled' if q>0 else 'canceled','filled_qty':str(q),'filled_avg_price':str(d.get('price',60000))}
 d.setdefault('orders',{})[b['client_order_id']]=o;save()
 if d.get('unknown_after'):sys.exit(7)
 finish(o)
if '/orders:by_client_order_id?' in url:
 k=url.split('client_order_id=')[1]
 if k not in d.get('orders',{}):finish({'message':'not found'},404)
 finish(d['orders'][k])
if url.endswith('/v2/account'):finish({'status':'ACTIVE','trading_blocked':False,'non_marginable_buying_power':'100000'})
if url.endswith('/v2/assets/BTCUSD'):finish({'symbol':'BTC/USD','class':'crypto','status':'active','tradable':True,
 'price_increment':'1','min_trade_increment':'0.000000001','min_order_size':'0.0001'})
if url.endswith('/v2/positions'):
 rows=[{'symbol':'AAPL','side':'long','qty':'10'}]
 if Decimal(d.get('position','0'))>0:rows.append({'symbol':'BTCUSD','side':'long','qty':d['position']})
 finish(rows)
if url.startswith('https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes?symbols=BTC%2FUSD'):
 now=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
 p=d.get('price',60000);finish({'quotes':{'BTC/USD':{'t':now,'bp':p-5,'ap':p}}})
if url.startswith('https://data.alpaca.markets/v1beta3/crypto/us/bars?symbols=BTC%2FUSD&timeframe=1Day'):
 finish({'bars':{'BTC/USD':d['bars']},'next_page_token':None})
raise AssertionError('unexpected path '+url)
'''


def daily(direction):
    """One UTC daily bar per day through the last day of the previous month."""
    end = date.today().replace(day=1) - timedelta(days=1)
    day, rows, i = end - timedelta(days=400), [], 0
    while day <= end:
        rows.append({'t': f'{day.isoformat()}T00:00:00Z', 'c': 40000 + (50 if direction == 'up' else -50) * i})
        day += timedelta(days=1); i += 1
    return rows


now = datetime.now(timezone.utc)


@unittest.skipUnless(ENGINE.exists() and os.name == 'posix', 'requires Linux OCaml build')
@unittest.skipIf(now.day == 1 and now.hour < 13, 'executor deliberately waits until 12:00 UTC on the 1st')
class CryptoTrendRuntime(unittest.TestCase):
    def fixture(self, directory, direction='up', **data):
        root = Path(directory)
        (root/'curl').write_text(FAKE); (root/'curl').chmod(0o700)
        (root/'broker.json').write_text(json.dumps({'bars': daily(direction), **data}))
        return root

    def update(self, root, **changes):
        p = root/'broker.json'; d = json.loads(p.read_text()); d.update(changes); p.write_text(json.dumps(d))

    def run_trend(self, root, armed=True, ok=True, extra=None):
        env = {**os.environ, 'TZ': 'UTC', 'PATH': str(root)+':'+os.environ['PATH'], 'PAPER_STATE_DIR': str(root),
               'SYNTHETIC_DIR': str(root), 'APCA_API_KEY_ID': 'SYNTHETIC', 'APCA_API_SECRET_KEY': 'SYNTHETIC',
               'PAPER_ORDERS': '1', 'CRYPTO_TREND_ORDERS': '1' if armed else '0', **(extra or {})}
        result = subprocess.run([str(ENGINE), '--execute'], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        return json.loads((root/'crypto-trend.json').read_text()) if ok else None

    def posts(self, root):
        p = root/'posts.jsonl'
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def status(self, report):
        return report['status'][0]['status']

    def test_entry_hold_fee_reduced_exit_and_pnl(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, 'up')
            self.assertEqual(self.status(self.run_trend(root)), 'buy_routed')
            report = self.run_trend(root)
            self.assertEqual(self.status(report), 'hold')
            buy = self.posts(root)[0]
            self.assertEqual(buy['side'], 'buy')
            self.assertEqual(buy['qty'], '0.001666666')  # floor($100 / $60,000) on the 1e-9 grid
            self.assertEqual(buy['limit_price'], '60300.000000000')  # ask + 50 bps, tick 1
            self.update(root, bars=daily('down'), price=66000)
            self.assertEqual(self.status(self.run_trend(root)), 'sell_routed')
            sell = self.posts(root)[1]
            # Only the fee-reduced broker quantity is sold, never the gross fill.
            self.assertEqual(sell['qty'], '0.001662499')
            self.assertEqual(sell['limit_price'], '65665.000000000')  # bid - 50 bps, floored to tick
            report = self.run_trend(root)
            self.assertEqual(self.status(report), 'flat')
            self.assertEqual(len(self.posts(root)), 2)
            self.assertAlmostEqual(report['pnl']['fillCashFlowUsd'], 0.001662499 * 66000 - 0.001666666 * 60000, places=6)

    def test_configured_entry_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, 'up')
            self.run_trend(root, ok=False, extra={'CRYPTO_TREND_ENTRY_USD': '9.5'})
            self.assertEqual(self.posts(root), [])
            self.assertEqual(self.run_trend(root, extra={'CRYPTO_TREND_ENTRY_USD': '300'})['entryUsd'], 300.0)
            self.assertEqual(self.posts(root)[0]['qty'], '0.005000000')

    def test_observe_mode_never_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, 'up')
            self.assertEqual(self.status(self.run_trend(root, armed=False)), 'would_buy')
            self.assertEqual(self.posts(root), [])

    def test_does_not_adopt_other_btc(self):
        for setup in ({'position': '0.01'}, 'legacy_owned', 'multi_ticket'):
            with self.subTest(setup=setup), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory, 'up', **(setup if isinstance(setup, dict) else {}))
                if setup == 'legacy_owned':
                    (root/'owned').write_text('1')
                if setup == 'multi_ticket':
                    (root/'multi-paper-ledger.json').write_text('not json')
                self.assertEqual(self.status(self.run_trend(root)), 'abstain')
                self.assertEqual(self.posts(root), [])

    def test_dust_does_not_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, 'up', position='0.000000019')
            self.assertEqual(self.status(self.run_trend(root)), 'buy_routed')

    def test_unfilled_ioc_retries_at_most_three_times(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, 'up', no_fill=True)
            for _ in range(3):
                self.assertEqual(self.status(self.run_trend(root)), 'buy_routed')
            self.assertEqual(self.status(self.run_trend(root)), 'abstain')
            ids = [p['client_order_id'] for p in self.posts(root)]
            self.assertEqual(len(ids), 3); self.assertEqual(len(set(ids)), 3)

    def test_uncertain_response_retains_pending_then_reconciles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, 'up', unknown_after=True)
            self.assertEqual(self.status(self.run_trend(root)), 'uncertain')
            self.update(root, unknown_after=False)
            self.assertEqual(self.status(self.run_trend(root)), 'hold')
            self.assertEqual(len(self.posts(root)), 1)
            ledger = json.loads((root/'crypto-trend-ledger.json').read_text())['orders']
            self.assertEqual(ledger[0]['state'], 'resolved')

    def test_unaccepted_timeout_blocks_further_orders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, 'up', unknown_before=True)
            self.run_trend(root)
            self.assertEqual(self.status(self.run_trend(root)), 'abstain')
            self.assertEqual(len(self.posts(root)), 1)

    def test_rejection_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, 'up', reject=True)
            self.assertEqual(self.status(self.run_trend(root)), 'buy_rejected')
            ledger = json.loads((root/'crypto-trend-ledger.json').read_text())['orders']
            self.assertEqual(ledger[0]['state'], 'rejected')

    def test_other_cohort_pending_order_blocks_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, 'up')
            cid = 'aibotstkPending'
            (root/'stock-paper-ledger.json').write_text(json.dumps({'orders': [
                {'symbol': 'SPY', 'side': 'buy', 'clientOrderId': cid, 'state': 'pending'}]}))
            report = self.run_trend(root)
            self.assertEqual(self.status(report), 'abstain')
            self.assertIn('Unresolved owned stock order', report['status'][0]['reason'])
            self.assertEqual(self.posts(root), [])


if __name__ == '__main__':
    unittest.main()
