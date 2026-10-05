"""Actual POSIX cross-router exclusion; no real broker credentials."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_multi_paper_runtime as multi
import test_stock_paper_runtime as stock


@unittest.skipUnless(multi.ENGINE.exists() and stock.ENGINE.exists() and os.name=='posix',
                     'requires real Linux OCaml paper routers and POSIX locking')
class PortfolioCycle(unittest.TestCase):
    def stock_pending(self,side='buy'):
        # SOURCE: minimal existing stock reservation fields, synthetic intent.
        return {'orders':[{'clientOrderId':'aibotstkUnresolvedFixture',
                          'side':side,'state':'pending'}]}

    def test_shared_account_lock_blocks_both_routers_before_account_or_ledger_work(self):
        import fcntl
        for engine in (multi.ENGINE,stock.ENGINE):
            with self.subTest(engine=engine.name),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                # SOURCE: absence of credentials/transport makes ordering
                # observable: neither credential validation nor HTTP may occur.
                env={k:v for k,v in os.environ.items() if not k.startswith('APCA_')}
                env['PAPER_STATE_DIR']=str(root)
                with (root/'alpaca-paper-portfolio.lock').open('w') as held:
                    fcntl.lockf(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    result=subprocess.run([str(engine)],env=env,capture_output=True,text=True,timeout=30)
                    self.assertNotEqual(result.returncode,0)
                    self.assertIn('portfolio cycle is busy',result.stderr)
                    self.assertNotIn('credentials',result.stderr)
                    self.assertFalse((root/'stock-paper-ledger.json').exists())
                    self.assertFalse((root/'multi-paper-ledger.json').exists())
                # SOURCE: kernel releases the advisory lock when its fd closes.
                # Each router resumes its normal path. The empty, unarmed
                # crypto observer can publish without credentials; the stock
                # router requires account reads even without an order request.
                result=subprocess.run([str(engine)],env=env,capture_output=True,text=True,timeout=30)
                self.assertNotIn('portfolio cycle is busy',result.stderr)
                if engine==multi.ENGINE:
                    self.assertEqual(result.returncode,0,result.stderr)
                    snapshot=json.loads((root/'multi-paper.json').read_text())
                    self.assertEqual(snapshot['mode'],'OBSERVE')
                    self.assertEqual(snapshot['activeTickets'],[])
                    self.assertEqual(snapshot['lastActions'],[])
                else:
                    self.assertNotEqual(result.returncode,0)
                    self.assertIn('credentials',result.stderr)

    def test_stock_pending_or_corruption_blocks_crypto_entries_until_cleared(self):
        runtime=multi.RuntimeTests()
        for counterpart in (self.stock_pending(),self.stock_pending('sell'),{'orders':None}):
            with self.subTest(counterpart=counterpart),tempfile.TemporaryDirectory() as directory:
                root=runtime.setup_fixture(directory)
                ledger=root/'stock-paper-ledger.json'
                ledger.write_text(json.dumps(counterpart))
                snapshot=runtime.run_engine(root)
                self.assertEqual(runtime.posts(root),[])
                self.assertTrue(any('new exposure blocked' in r['reason'] or
                    'blocks new exposure' in r['reason'] for r in snapshot['abstentions']))
                # SOURCE: isolated fixture clearance, not resetting real state.
                ledger.write_text(json.dumps({'orders':[]}))
                # SOURCE: entry candidates must be the most recent closed
                # candle; an actual frame rollover invalidates the old fixture.
                runtime.refresh_signal(root)
                snapshot=runtime.run_engine(root)
                self.assertEqual(len(runtime.posts(root)),1,snapshot['abstentions'])

    def test_counterpart_pending_does_not_disable_owned_crypto_exit(self):
        runtime=multi.RuntimeTests()
        with tempfile.TemporaryDirectory() as directory:
            root=runtime.setup_fixture(directory)
            runtime.run_engine(root)
            (root/'stock-paper-ledger.json').write_text(json.dumps(self.stock_pending()))
            runtime.update_broker(root,bid=98,ask=99)
            runtime.run_engine(root,new_entries=False)
            self.assertEqual([r['side'] for r in runtime.posts(root)],['buy','sell'])

    def test_actual_uncertain_crypto_intent_blocks_stock_buy_until_broker_reconciliation(self):
        crypto=multi.RuntimeTests();equities=stock.StockRuntime()
        with tempfile.TemporaryDirectory() as directory:
            root=crypto.setup_fixture(directory,uncertain_before_accept=True)
            crypto.run_engine(root)
            before=len(crypto.posts(root))
            original_broker=(root/'broker.json').read_text()
            (root/'curl').write_text(stock.FAKE)
            (root/'broker.json').write_text('{}')
            result=equities.buy(root,ok=False)
            self.assertIn('Unresolved owned crypto order',result.stderr)
            self.assertEqual(len(equities.posts(root)),before)
            pending=json.loads((root/'multi-paper-ledger.json').read_text())['tickets'][0]['pending']
            # SOURCE: fake broker terminal response for that exact durable ID;
            # no client-side ledger deletion or invented broker execution.
            (root/'curl').write_text(multi.FAKE_CURL)
            broker=json.loads(original_broker)
            broker['orders']={pending['clientOrderId']:{'client_order_id':pending['clientOrderId'],
                'symbol':'ETHUSD','side':'buy','status':'canceled','filled_qty':'0','filled_avg_price':None}}
            (root/'broker.json').write_text(json.dumps(broker))
            crypto.run_engine(root,new_entries=False)
            self.assertIsNone(json.loads((root/'multi-paper-ledger.json').read_text())['tickets'][0]['pending'])
            (root/'curl').write_text(stock.FAKE);(root/'broker.json').write_text('{}')
            equities.buy(root)
            self.assertEqual(len(equities.posts(root)),before+1)

    def test_corrupt_crypto_counterpart_blocks_stock_buy(self):
        runtime=stock.StockRuntime()
        with tempfile.TemporaryDirectory() as directory:
            root=runtime.fixture(directory)
            (root/'multi-paper-ledger.json').write_text('{')
            result=runtime.buy(root,ok=False)
            self.assertIn('new exposure blocked',result.stderr)
            self.assertEqual(runtime.posts(root),[])

    def test_counterpart_failure_does_not_disable_owned_stock_exit(self):
        runtime=stock.StockRuntime()
        with tempfile.TemporaryDirectory() as directory:
            root=runtime.fixture(directory)
            runtime.buy(root)
            (root/'multi-paper-ledger.json').write_text('{')
            runtime.run_router(root,'--sell','QQQ','--amount','1',
                               '--client-id','aibotstkOwnedExit','--execute')
            self.assertEqual([r['side'] for r in runtime.posts(root)],['buy','sell'])


if __name__=='__main__':unittest.main()
