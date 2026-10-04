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
        now = datetime.now(timezone.utc)
        minute = now.replace(second=0, microsecond=0)
        # SOURCE: a four-hour fixture avoids a minute rollover during real
        # subprocess tests; pure policy tests cover all five frame boundaries.
        frame_start = now.replace(hour=now.hour//4*4, minute=0, second=0, microsecond=0)-timedelta(hours=4)
        stamp = lambda at: at.isoformat().replace('+00:00', 'Z')
        reading = {'status': 'candidate', 'candidate': 'long', 'trend': 'rising',
                   'candleShapes': ['hammer_shape'], 'close': 100, 'invalidationLevel': 99,
                   'lastBarStart': stamp(frame_start),
                   'orderAuthority': False, 'winProbability': None}
        reading.update(changes)
        doc = {'policy': 'trend_candle_confluence_v1', 'asOf': stamp(minute),
               'retrievedAt': stamp(now), 'orderAuthority': False,
               'markets': [{'symbol': symbol, 'venue': venue, 'frames': {'4h': reading}}]}
        (root/'market-pipeline.json').write_text(json.dumps(doc))

    def environment(self, root, armed=True, entries=True):
        return {**os.environ, 'TZ': 'UTC', 'PATH': str(root)+':'+os.environ['PATH'],
                'PAPER_STATE_DIR': str(root), 'SYNTHETIC_STOCK_DIR': str(root),
                'APCA_API_KEY_ID': 'SYNTHETIC', 'APCA_API_SECRET_KEY': 'SYNTHETIC',
                'PAPER_ORDERS': '1', 'STOCK_PAPER_ORDERS': '1',
                'STOCK_AUTO_ORDERS': '1' if armed else '0',
                'STOCK_AUTO_NEW_ENTRIES': '1' if entries else '0'}

    def run_auto(self, root, armed=True, entries=True, ok=True):
        result = subprocess.run([str(ENGINE), '--execute'], env=self.environment(root, armed, entries),
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
            self.assertEqual(decisions[0]['detail']['reading']['candleShapes'], ['hammer_shape'])
            self.assertEqual(decisions[1]['detail']['originEntryId'], decisions[0]['clientOrderId'])
            self.assertFalse(decisions[1]['detail']['preflight']['buyingPowerChecked'])

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
