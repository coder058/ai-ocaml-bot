"""Exercise the real OCaml OMS with a synthetic curl, never the network.

All quantities/prices/balances here are synthetic failure fixtures, not
observed market results or strategy calibration.
"""
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "_build/default/bin/multi_paper_main.exe"

FAKE_CURL = r'''#!/usr/bin/env python3
import sys,os,json
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
root=Path(os.environ['SYNTHETIC_OMS_DIR'])
data=json.loads((root/'broker.json').read_text())
sys.stdin.read()  # Discard synthetic credential configuration, never log it.
args=sys.argv[1:]; url=args[-1]; method=args[args.index('-X')+1]
def finish(body,code=200):
    print(json.dumps(body));print('__HTTP_STATUS__:'+str(code));sys.exit(0)
if method=='POST':
    assert url=='https://paper-api.alpaca.markets/v2/orders'
    body=json.loads(args[args.index('--data-binary')+1])
    ledger=json.loads((root/'multi-paper-ledger.json').read_text())
    pending=next(t['pending'] for t in ledger['tickets'] if t['symbol']==body['symbol'])
    assert pending['clientOrderId']==body['client_order_id']  # durable BEFORE POST
    assert body['symbol']==data.get('symbol','ETH/USD') and body['time_in_force']=='ioc'
    with (root/'posts.jsonl').open('a') as stream: stream.write(json.dumps(body)+'\n')
    if data.get('reject'):
        finish({'message':'synthetic rejection'},422)
    if data.get('uncertain_before_accept'): sys.exit(7)
    fraction=Decimal('0.4') if body['side']=='buy' else Decimal(data.get('exit_fraction','1'))
    filled=Decimal(body['qty'])*fraction
    qty=Decimal(data.get('position','0'))
    if body['side']=='buy': qty+=filled-Decimal('0.001')  # synthetic received-asset fee
    else: qty-=filled
    data['position']=str(qty)
    order={'client_order_id':body['client_order_id'],'symbol':data.get('symbol','ETH/USD').replace('/',''),
        'side':body['side'],'status':'canceled','filled_qty':str(filled),
        'filled_avg_price':body.get('limit_price','100')}
    data.setdefault('orders',{})[body['client_order_id']]=order
    (root/'broker.json').write_text(json.dumps(data))
    if data.get('uncertain_after_accept'): sys.exit(7)
    finish(order)
if '/orders:by_client_order_id?' in url:
    key=url.split('client_order_id=')[1]
    if key not in data.get('orders',{}): finish({'message':'not found'},404)
    finish(data['orders'][key])
if url.endswith('/v2/account'):
    finish({'status':'ACTIVE','trading_blocked':False,'crypto_status':'ACTIVE',
            'non_marginable_buying_power':'100000'})
if url.endswith('/v2/assets/'+data.get('symbol','ETH/USD').replace('/','')):
    finish({'symbol':data.get('symbol','ETH/USD'),'class':'crypto','status':'active','tradable':True,
            'price_increment':'0.01','min_trade_increment':'0.000000001','min_order_size':'0.01'})
if url.endswith('/v2/positions'):
    rows=[{'symbol':'AAPL','qty':'100','asset_class':'us_equity'}]
    if Decimal(data.get('position','0'))>0: rows.append({'symbol':data.get('symbol','ETH/USD').replace('/',''),'qty':data['position']})
    finish(rows)
if url.endswith('/v2/orders?status=open'): finish(data.get('open_orders',[]))
if url.startswith('https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes?symbols='):
    at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    finish({'quotes':{data.get('symbol','ETH/USD'):{'t':at,'bp':data.get('bid',99.9),'ap':data.get('ask',100)}}})
raise AssertionError('Unexpected synthetic HTTP path: '+url)
'''


@unittest.skipUnless(ENGINE.exists() and os.name == "posix", "requires built Linux OCaml engine")
class RuntimeTests(unittest.TestCase):
    def setup_fixture(self, directory, **broker):
        root = Path(directory)
        executable = root / "curl"
        executable.write_text(FAKE_CURL)
        executable.chmod(0o700)
        (root / "broker.json").write_text(json.dumps(broker))
        self.refresh_signal(root)
        return root

    def refresh_signal(self, root):
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        bar = now - timedelta(minutes=now.minute % 5 + 5)
        (root / "market-pipeline.json").write_text(json.dumps({
            "asOf": now.isoformat().replace("+00:00", "Z"),
            "policy": "trend_candle_confluence_v1", "orderAuthority": False,
            "markets": [{"venue": "Alpaca crypto", "symbol": "ETH/USD", "frames": {
                "5m": {"status": "candidate", "candidate": "long", "close": 100,
                    "lastBarStart": bar.isoformat().replace("+00:00", "Z"),
                    "invalidationLevel": 90, "orderAuthority": False, "winProbability": None}}}]}))

    def run_engine(self, root, armed=True, new_entries=True, wind_down=False):
        environment = {**os.environ, "PATH": str(root)+":"+os.environ["PATH"],
            "TZ": "UTC", "PAPER_STATE_DIR": str(root), "SYNTHETIC_OMS_DIR": str(root),
            "PAPER_ORDERS": "1", "MULTI_PAPER_ORDERS": "1" if armed else "0",
            "MULTI_PAPER_NEW_ENTRIES": "1" if new_entries else "0",
            "MULTI_PAPER_WIND_DOWN_EXCLUDED": "1" if wind_down else "0",
            "APCA_API_KEY_ID": "SYNTHETIC", "APCA_API_SECRET_KEY": "SYNTHETIC"}
        result = subprocess.run([str(ENGINE), "--execute"], env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads((root / "multi-paper.json").read_text())

    def posts(self, root):
        path = root / "posts.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def update_broker(self, root, **updates):
        path = root / "broker.json"
        data = json.loads(path.read_text()); data.update(updates); path.write_text(json.dumps(data))

    def test_partial_entry_exit_fees_and_restart_are_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_fixture(directory)
            first = self.run_engine(root)
            self.assertEqual(first["mode"], "PAPER_EXPERIMENT")
            self.assertEqual(len(self.posts(root)), 1)
            self.assertEqual(first["activeTickets"][0]["ownedMaximumQty"], 0.4)
            self.run_engine(root)  # restart/same signal must not add another buy
            self.assertEqual(len(self.posts(root)), 1)
            self.update_broker(root, bid=89, ask=89.1, exit_fraction="0.5")
            self.run_engine(root)
            self.assertEqual(self.posts(root)[-1]["side"], "sell")
            self.assertEqual(self.posts(root)[-1]["qty"], "0.399000000")
            self.update_broker(root, exit_fraction="1")
            self.run_engine(root)
            final = self.run_engine(root)
            self.assertEqual(final["activeTickets"], [])
            self.assertTrue(all(post["symbol"] == "ETH/USD" for post in self.posts(root)))

    def test_excluded_crypto_wind_down_is_owned_market_sell(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.setup_fixture(directory)
            self.run_engine(root)
            path=root/'multi-paper-ledger.json';ledger=json.loads(path.read_text())
            ledger['tickets'][0]['symbol']='BONK/USD';path.write_text(json.dumps(ledger))
            self.update_broker(root,symbol='BONK/USD')
            self.run_engine(root,new_entries=False,wind_down=True)
            last=self.posts(root)[-1]
            self.assertEqual(last['symbol'],'BONK/USD');self.assertEqual(last['side'],'sell')
            self.assertEqual(last['type'],'market');self.assertNotIn('limit_price',last)
            self.run_engine(root,new_entries=False,wind_down=True)
            self.assertEqual(len(self.posts(root)),2)

    def test_unknown_accepted_response_reconciles_without_duplicate_post(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_fixture(directory, uncertain_after_accept=True)
            first = self.run_engine(root)
            self.assertIsNotNone(first["activeTickets"][0]["pending"])
            second = self.run_engine(root)
            self.assertIsNone(second["activeTickets"][0]["pending"])
            self.assertEqual(len(self.posts(root)), 1)

    def test_unknown_missing_response_is_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_fixture(directory, uncertain_before_accept=True)
            self.run_engine(root)
            result = self.run_engine(root)
            self.assertEqual(len(self.posts(root)), 1)
            self.assertIsNotNone(result["activeTickets"][0]["pending"])

    def test_rejected_signal_not_repeated_and_unowned_inventory_not_sold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_fixture(directory, reject=True)
            self.run_engine(root); self.run_engine(root)
            self.assertEqual(len(self.posts(root)), 1)
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_fixture(directory, position="0.2", bid=89, ask=89.1)
            self.run_engine(root)
            self.assertEqual(self.posts(root), [])

    def test_disarmed_and_open_order_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_fixture(directory)
            self.assertEqual(self.run_engine(root, armed=False)["mode"], "OBSERVE")
            self.assertEqual(self.posts(root), [])
            self.update_broker(root, open_orders=[{"symbol":"ETHUSD"}])
            self.run_engine(root)
            self.assertEqual(self.posts(root), [])

    def test_paused_entries_preserve_owned_exit_management(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_fixture(directory)
            paused = self.run_engine(root, new_entries=False)
            self.assertFalse(paused["newEntriesEnabled"])
            self.assertEqual(self.posts(root), [])
            self.run_engine(root)
            self.assertEqual(len(self.posts(root)), 1)
            self.update_broker(root, bid=89, ask=89.1)
            self.run_engine(root, new_entries=False)
            self.assertEqual([p["side"] for p in self.posts(root)], ["buy", "sell"])
            self.assertEqual(self.run_engine(root, new_entries=False)["activeTickets"], [])

    def test_paused_entries_still_reconcile_uncertain_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_fixture(directory, uncertain_after_accept=True)
            self.run_engine(root)
            paused = self.run_engine(root, new_entries=False)
            self.assertIsNone(paused["activeTickets"][0]["pending"])
            self.assertEqual(len(self.posts(root)), 1)
