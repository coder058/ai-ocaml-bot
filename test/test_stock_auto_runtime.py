"""SOURCE: real OCaml scheduler/router with synthetic curl, never live orders.

Synthetic prices, amounts and times test ownership, durability and guards;
none of the fixture outcomes are backtest or profitability evidence.
"""
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import test_stock_paper_runtime as stock_runtime

ROUTER = stock_runtime.ENGINE

ENGINE = ROUTER.with_name('stock_auto_main.exe')

@unittest.skipUnless(ENGINE.exists() and os.name == 'posix', 'requires Linux OCaml build')
class StockAutoRuntime(unittest.TestCase):
    fixture = stock_runtime.StockRuntime.fixture
    posts = stock_runtime.StockRuntime.posts
    update = stock_runtime.StockRuntime.update

    def analysis(self, root, symbol='QQQ', venue='Alpaca equities', **changes):
        from native_input_fixture import document
        # SOURCE: four-hour fixture avoids minute rollover; all five native
        # routing boundaries are separately covered by pure policy tests.
        doc = document(root, symbol, venue, '4h')
        reading = doc['markets'][0]['frames']['4h']
        reading.update(changes)
        (root/'market-pipeline.json').write_text(json.dumps(doc))

    def environment(self, root, armed=True, entries=True):
        return {**os.environ, 'TZ': 'UTC', 'PATH': str(root)+':'+os.environ['PATH'],
                'PAPER_STATE_DIR': str(root), 'SYNTHETIC_STOCK_DIR': str(root),
                'APCA_API_KEY_ID': 'SYNTHETIC', 'APCA_API_SECRET_KEY': 'SYNTHETIC',
                'PAPER_ORDERS': '1', 'STOCK_PAPER_ORDERS': '1',
                'STOCK_AUTO_ORDERS': '1' if armed else '0',
                'STOCK_AUTO_NEW_ENTRIES': '1' if entries else '0'}

    def run_auto(self, root, armed=True, entries=True, ok=True, extra_env=None):
        result = subprocess.run([str(ENGINE), '--execute'], env={**self.environment(root, armed, entries),**(extra_env or {})},
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        return result

    def test_owned_entry_exit_and_same_bar_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory); self.analysis(root)
            self.run_auto(root); self.run_auto(root)
            self.assertEqual(len(self.posts(root)), 1)
            self.update(root, bid=98, ask=99)
            self.run_auto(root, entries=False)
            self.assertEqual([r['side'] for r in self.posts(root)], ['buy', 'sell'])
            self.assertEqual(self.posts(root)[1]['qty'], '1.000000000')
            self.run_auto(root)
            self.assertEqual(len(self.posts(root)), 2)
            events = [json.loads(line) for line in (root/'stock-paper-events.jsonl').read_text().splitlines()]
            decisions = [row for row in events if row['kind'] == 'DECISION']
            self.assertTrue(all(row['detail']['preflight']['accountReady'] for row in decisions))
            self.assertIn('hammer_shape',decisions[0]['detail']['reading']['candleShapes'])
            self.assertTrue(decisions[0]['detail']['nativeInputVerification']['verified'])
            self.assertEqual(decisions[1]['detail']['originEntryId'], decisions[0]['clientOrderId'])
            self.assertFalse(decisions[1]['detail']['preflight']['buyingPowerChecked'])

    def test_eleventh_stock_is_not_blocked_by_the_old_ten_position_guess(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory);self.analysis(root)
            # SOURCE: ten synthetic pre-existing owned entries exercise the
            # old capacity boundary; none are real holdings or performance.
            rows=[]
            for index in range(10):
                symbol=f'TST{index}';cid=f'aibotstkFixture{index}'
                rows.append({'symbol':symbol,'side':'buy','clientOrderId':cid,'state':'resolved',
                    'request':{'symbol':symbol,'side':'buy','client_order_id':cid,
                               'type':'market','time_in_force':'day','notional':'100'},
                    'broker':{'symbol':symbol,'side':'buy','client_order_id':cid,
                              'status':'filled','filled_qty':'1','filled_avg_price':'100'}})
            (root/'stock-paper-ledger.json').write_text(json.dumps({'orders':rows}))
            self.run_auto(root)
            self.assertEqual(len(self.posts(root)),1)
            status=json.loads((root/'stock-auto.json').read_text())
            self.assertEqual(status['maxOpenPositions'],69)

    def test_quote_expiring_during_real_durable_event_write_never_reaches_http(self):
        import durable_delay
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory);self.analysis(root)
            self.run_auto(root,extra_env=durable_delay.environment(root,'stock-paper-events.jsonl'))
            self.assertEqual(self.posts(root),[])
            rows=json.loads((root/'stock-paper-ledger.json').read_text())['orders']
            self.assertEqual(rows[0]['state'],'rejected')
            events=[json.loads(line) for line in (root/'stock-paper-events.jsonl').read_text().splitlines()]
            self.assertEqual([row['kind'] for row in events],['DECISION','NOT_SENT'])
            self.run_auto(root)
            self.assertEqual(self.posts(root),[])

    def test_quote_expiring_during_final_session_read_is_certain_not_sent(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory,delay_final_session=True);self.analysis(root)
            self.run_auto(root)
            self.assertEqual(self.posts(root),[])
            rows=json.loads((root/'stock-paper-ledger.json').read_text())['orders']
            self.assertEqual(rows[0]['state'],'rejected')
            events=[json.loads(line) for line in (root/'stock-paper-events.jsonl').read_text().splitlines()]
            self.assertEqual([row['kind'] for row in events],['DECISION','NOT_SENT'])
            self.assertIn('final session validation',events[-1]['reason'])
            self.run_auto(root)
            self.assertEqual(self.posts(root),[])

    def test_closed_final_session_cannot_leave_a_never_submitted_order_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory,close_final_session=True);self.analysis(root)
            self.run_auto(root)
            self.assertEqual(self.posts(root),[])
            rows=json.loads((root/'stock-paper-ledger.json').read_text())['orders']
            self.assertEqual(rows[0]['state'],'rejected')
            events=[json.loads(line) for line in (root/'stock-paper-events.jsonl').read_text().splitlines()]
            self.assertEqual([row['kind'] for row in events],['DECISION','NOT_SENT'])
            self.assertIn('session is closed',events[-1]['reason'])
            self.run_auto(root)
            self.assertEqual(self.posts(root),[])

    def test_missing_or_changed_original_candle_proof_blocks_automatic_http(self):
        for remove in (True,False):
            with self.subTest(remove=remove),tempfile.TemporaryDirectory() as directory:
                root=self.fixture(directory);self.analysis(root)
                p=root/'market-pipeline.json';doc=json.loads(p.read_text())
                reading=doc['markets'][0]['frames']['4h']
                if remove:reading.pop('dataEvidence')
                else:reading['ema20']+=1
                p.write_text(json.dumps(doc));self.run_auto(root)
                self.assertEqual(self.posts(root),[])
                self.assertEqual(json.loads((root/'stock-paper-ledger.json').read_text())['orders'],[])

    def test_disarmed_paused_closed_and_old_quotes_cannot_submit(self):
        for state, opts in [({}, {'armed': False}), ({}, {'entries': False}), ({'open': False}, {}),
                            ({'quote_time': '2000-01-01T00:00:00Z'}, {}), ({'bid': 98, 'ask': 99}, {})]:
            with self.subTest(state=state, opts=opts), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory, **state); self.analysis(root); self.run_auto(root, **opts)
                self.assertEqual(self.posts(root), [])
                status = json.loads((root/'stock-auto.json').read_text())
                self.assertTrue(status['abstentions'])

    def test_timeout_after_acceptance_and_before_acceptance_never_duplicate(self):
        for state in [{'unknown_after': True}, {'unknown_before': True}]:
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory, **state); self.analysis(root)
                self.run_auto(root); self.run_auto(root)
                self.assertEqual(len(self.posts(root)), 1)
                ledger = json.loads((root/'stock-paper-ledger.json').read_text())['orders']
                self.assertEqual(ledger[0]['state'], 'pending' if state.get('unknown_before') else 'resolved')

    def test_partial_entry_exit_uses_only_the_actual_owned_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, fraction='0.4'); self.analysis(root); self.run_auto(root)
            self.update(root, bid=98, ask=99, fraction=None)
            self.run_auto(root, entries=False)
            self.assertEqual(self.posts(root)[1]['qty'], '0.400000000')
            broker = json.loads((root/'broker.json').read_text())
            self.assertEqual(float(broker['position']), 0)
            ledger = json.loads((root/'stock-paper-ledger.json').read_text())['orders']
            self.assertEqual(ledger[-1]['state'], 'resolved')
            self.assertEqual(ledger[-1]['broker']['status'], 'filled')

    def test_manual_or_external_inventory_is_never_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, position='1'); self.analysis(root); self.run_auto(root)
            self.assertEqual(self.posts(root), [])
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory); self.analysis(root)
            result = subprocess.run([str(ROUTER), '--buy', 'QQQ', '--amount', '100', '--client-id', 'aibotstkManual', '--execute'],
                                    env=self.environment(root), capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.update(root, bid=98, ask=99)
            self.run_auto(root)
            self.assertEqual(len(self.posts(root)), 1)
            self.assertIn('no managed policy entry', json.dumps(json.loads((root/'stock-auto.json').read_text())))

    def test_protected_and_public_only_products_never_enter_the_stock_router(self):
        for symbol, venue in [('AAPL', 'Alpaca equities'), ('xyz:EUR', 'Hyperliquid HIP-3'), ('ETH/USD', 'Alpaca crypto')]:
            with self.subTest(symbol=symbol), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory); self.analysis(root, symbol, venue); self.run_auto(root)
                self.assertEqual(self.posts(root), [])

    def test_future_and_short_candles_are_not_order_candidates(self):
        for changes in [{'candidate': 'short'}, {'lastBarStart': '2099-01-01T00:00:00Z'}]:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory); self.analysis(root, **changes); self.run_auto(root)
                self.assertEqual(self.posts(root), [])

    def test_wrong_ack_retains_pending_and_corrupt_ledger_halts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, wrong_ack=True); self.analysis(root); self.run_auto(root)
            ledger = json.loads((root/'stock-paper-ledger.json').read_text())
            self.assertEqual(ledger['orders'][0]['state'], 'pending')
            self.assertEqual(len(self.posts(root)), 1)
            ledger['orders'] *= 2
            (root/'stock-paper-ledger.json').write_text(json.dumps(ledger))
            self.run_auto(root, ok=False)
            self.assertEqual(len(self.posts(root)), 1)

if __name__ == '__main__': unittest.main()
