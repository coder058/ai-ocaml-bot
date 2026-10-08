"""SOURCE: real OCaml trend scheduler/router with synthetic curl; never live orders.

Synthetic closes test ownership, gating and intent verification only. They are
not backtest or profitability evidence.
"""
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
import test_stock_paper_runtime as stock_runtime

ROUTER = stock_runtime.ENGINE
ENGINE = ROUTER.with_name('monthly_trend_main.exe')
FAKE = stock_runtime.FAKE.replace(
    "raise AssertionError('unexpected path '+url)",
    "if url.startswith('https://data.alpaca.markets/v2/stocks/bars?') and 'symbols=QQQ' in url:\n"
    " finish({'bars':{'QQQ':d['bars']},'next_page_token':None})\n"
    "raise AssertionError('unexpected path '+url)")


def closes(direction):
    """Weekday bars through the end of the previous calendar month."""
    today = date.today()
    end = today.replace(day=1) - timedelta(days=1)
    day, rows = end - timedelta(days=420), []
    while day <= end:
        if day.weekday() < 5:
            rows.append(day)
        day += timedelta(days=1)
    step = 0.1 if direction == 'up' else -0.1
    return [{'t': f'{d.isoformat()}T04:00:00Z', 'c': 300 + step * i} for i, d in enumerate(rows)]


@unittest.skipUnless(ENGINE.exists() and os.name == 'posix', 'requires Linux OCaml build')
class MonthlyTrendRuntime(unittest.TestCase):
    def fixture(self, directory, direction='up'):
        root = Path(directory)
        (root/'curl').write_text(FAKE); (root/'curl').chmod(0o700)
        (root/'broker.json').write_text(json.dumps({'bars': closes(direction)}))
        return root

    def set_bars(self, root, direction):
        p = root/'broker.json'; d = json.loads(p.read_text()); d['bars'] = closes(direction); p.write_text(json.dumps(d))

    def env(self, root, armed=True):
        return {**os.environ, 'TZ': 'UTC', 'PATH': str(root)+':'+os.environ['PATH'],
                'PAPER_STATE_DIR': str(root), 'SYNTHETIC_STOCK_DIR': str(root),
                'APCA_API_KEY_ID': 'SYNTHETIC', 'APCA_API_SECRET_KEY': 'SYNTHETIC',
                'PAPER_ORDERS': '1', 'STOCK_PAPER_ORDERS': '1', 'TREND_SYMBOLS': 'QQQ',
                'TREND_AUTO_ORDERS': '1' if armed else '0'}

    def run_trend(self, root, armed=True):
        result = subprocess.run([str(ENGINE), '--execute'], env=self.env(root, armed),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads((root/'monthly-trend.json').read_text())

    posts = stock_runtime.StockRuntime.posts

    def test_entry_hold_exit_and_monthly_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, 'up')
            self.assertEqual(self.run_trend(root)['symbols'][0]['status'], 'buy_routed')
            self.assertEqual(self.run_trend(root)['symbols'][0]['status'], 'hold')
            self.assertEqual([p['side'] for p in self.posts(root)], ['buy'])
            self.assertEqual(self.posts(root)[0]['notional'], '100.000000000')
            self.set_bars(root, 'down')
            self.assertEqual(self.run_trend(root)['symbols'][0]['status'], 'sell_routed')
            self.assertEqual(self.run_trend(root)['symbols'][0]['status'], 'flat')
            self.assertEqual([p['side'] for p in self.posts(root)], ['buy', 'sell'])
            self.assertEqual(self.posts(root)[1]['qty'], '1.000000000')
            # Same month turning up again cannot re-enter with the used entry identity.
            self.set_bars(root, 'up')
            self.assertEqual(self.run_trend(root)['symbols'][0]['status'], 'abstain')
            self.assertEqual(len(self.posts(root)), 2)
            events = [json.loads(x) for x in (root/'stock-paper-events.jsonl').read_text().splitlines()]
            decisions = [e for e in events if e['kind'] == 'DECISION']
            self.assertEqual([e['detail']['reading']['decision'] for e in decisions], ['hold', 'flat'])

    def test_observe_mode_never_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, 'up')
            self.assertEqual(self.run_trend(root, armed=False)['symbols'][0]['status'], 'would_buy')
            self.assertEqual(self.posts(root), [])

    def route(self, root, direction, gate='1'):
        bars = [[b['t'][:10], b['c']] for b in closes(direction)]
        # Same derivation as Stock_policy.client_id [symbol; month; side; origin; policy].
        cid = 'aibotstk' + hashlib.md5(f"QQQ|{bars[-1][0][:7]}|buy||monthly_trend_v1".encode()).hexdigest()
        intent = {'symbol': 'QQQ', 'side': 'buy', 'clientOrderId': cid, 'policy': 'monthly_trend_v1', 'bars': bars}
        (root/'intent.json').write_text(json.dumps(intent))
        return subprocess.run([str(ROUTER), '--buy', 'QQQ', '--amount', '100', '--client-id', cid,
                               '--evidence-file', str(root/'intent.json'), '--execute'],
                              env={**self.env(root), 'TREND_AUTO_ORDERS': gate}, capture_output=True, text=True, timeout=30)

    def test_router_recomputes_the_rule_from_intent_bars(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            result = self.route(root, 'down')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('no longer holds', result.stderr)
            self.assertEqual(self.posts(root), [])
            self.assertEqual(self.route(root, 'up').returncode, 0)
            self.assertEqual([p['side'] for p in self.posts(root)], ['buy'])

    def test_router_requires_trend_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            result = self.route(root, 'up', gate='0')
            self.assertIn('trend paper gate is not armed', result.stderr)
            self.assertEqual(self.posts(root), [])

if __name__ == '__main__':
    unittest.main()
