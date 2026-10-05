"""Synthetic subscription checks; no claim that any market event was received."""
import asyncio,json,os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
import stock_stream_capture as s

class StockCaptureTests(unittest.TestCase):
    def test_free_feed_limit_and_explicit_subscription(self):
        self.assertEqual(len(s.SYMBOLS),30);self.assertEqual(s.URL,'wss://stream.data.alpaca.markets/v2/iex')
        self.assertTrue(s.confirmed(s.subscription()));self.assertFalse(s.confirmed({'quotes':['QQQ']}))
        self.assertNotIn('AAPL',s.SYMBOLS)
    def test_unsubscribed_or_control_rows_are_not_archived(self):
        self.assertTrue(s.valid({'T':'q','S':'QQQ','t':'synthetic'}))
        self.assertFalse(s.valid({'T':'q','S':'AAPL','t':'synthetic'}))
        self.assertFalse(s.valid({'T':'error','S':'QQQ','t':'synthetic'}))

class StockIdleArchiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_quote_is_readable_before_next_message_or_heartbeat_and_no_orders_are_sent(self):
        idle=asyncio.Event();sent=[]
        # SOURCE: synthetic market frame and local-only fake WS handshake;
        # no broker subscription, credentials or actual quote implied.
        quote={'T':'q','S':'QQQ','t':'2026-10-05T13:30:00Z','bp':99,'ap':100,'bs':1,'as':1}
        rows=[{'T':'success','msg':'authenticated'}, {'T':'subscription',**s.subscription()}, quote]
        class Socket:
            def __aiter__(self):return self
            async def __anext__(self):
                if rows:return json.dumps([rows.pop(0)])
                idle.set();await asyncio.Future()
            async def send(self,message):sent.append(json.loads(message))
        class Connection:
            async def __aenter__(self):return Socket()
            async def __aexit__(self,*args):return False
        original_stat=os.stat
        def stat(path,*args,**kwargs):
            return SimpleNamespace(st_gid=0) if str(path)=='/home/ubuntu' else original_stat(path,*args,**kwargs)
        with tempfile.TemporaryDirectory() as directory, patch.object(s,'STATE',Path(directory)), \
             patch.object(s,'connect',return_value=Connection()), patch.object(s,'credentials',return_value=('fixture-key','fixture-secret')), \
             patch.object(s.os,'chown',create=True), patch.object(s.os,'stat',side_effect=stat), \
             patch.object(s.os,'statvfs',return_value=SimpleNamespace(f_bavail=s.MIN_FREE_BYTES+1,f_frsize=1),create=True):
            task=asyncio.create_task(s.capture())
            try:
                # GUESS: # UNCALIBRATED GUESS — one-second test failure bound;
                # never a market/capture latency performance measurement.
                await asyncio.wait_for(idle.wait(),timeout=1)
                paths=list((Path(directory)/'market-capture/iex').glob('*.jsonl'))
                self.assertEqual(len(paths),1)
                data=json.loads(paths[0].read_text())
                self.assertEqual(data['event'],quote);self.assertEqual(data['sequence'],1)
                self.assertIsInstance(data['receivedAtNs'],int)
                self.assertEqual([m['action'] for m in sent],['auth','subscribe'])
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task

if __name__=='__main__':unittest.main()
