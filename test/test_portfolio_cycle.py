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


if __name__=='__main__':unittest.main()
