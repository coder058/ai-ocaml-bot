"""Synthetic subscription checks; no claim that any market event was received."""
import sys,unittest
from pathlib import Path
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

if __name__=='__main__':unittest.main()
