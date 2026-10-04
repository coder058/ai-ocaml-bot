"""Synthetic messages verify public journal boundaries, not actual executions."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
import paper_order_capture as p

class OrderCaptureTests(unittest.TestCase):
    def test_only_owned_orders_are_retained_and_protected_stock_is_private(self):
        self.assertTrue(p.owned({'symbol':'ETHUSD','client_order_id':'jsbotmtfexample'}))
        self.assertTrue(p.owned({'symbol':'QQQ','client_order_id':'aibotstkExample'}))
        self.assertFalse(p.owned({'symbol':'AAPL','client_order_id':'aibotstkProtected'}))
        self.assertFalse(p.owned({'symbol':'BTCUSD','client_order_id':'manual'}))
        self.assertEqual(p.URL,'wss://paper-api.alpaca.markets/stream')
    def test_account_fields_are_not_in_public_order_projection(self):
        row={'stream':'trade_updates','data':{'event':'fill','secret':'synthetic_private',
            'order':{'symbol':'BTCUSD','client_order_id':'jsbotbtcExample','account_id':'synthetic_private'}}}
        projected=p.public_event(row);self.assertEqual(projected['event'],'fill')
        self.assertNotIn('synthetic_private',str(projected));self.assertIsNone(p.public_event({'stream':'authorization'}))

if __name__=='__main__':unittest.main()
