"""The research feed must not send other symbols into the BTC order bot."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from stream_capture import (  # noqa: E402
    ARCHIVED_SYMBOLS,
    should_fanout,
    subscription_request,
    valid_market_event,
    valid_subscription,
)


class StreamCaptureTest(unittest.TestCase):
    def test_research_symbols_are_not_trade_or_book_subscriptions(self):
        request = subscription_request()
        self.assertEqual(request["quotes"], list(ARCHIVED_SYMBOLS))
        self.assertEqual(request["trades"], ["BTC/USD"])
        self.assertEqual(request["orderbooks"], ["BTC/USD"])
        self.assertTrue(valid_subscription(request))
        incomplete = {**request, "bars": ["BTC/USD"]}
        self.assertFalse(valid_subscription(incomplete))

    def test_only_btc_is_forwarded_to_order_bot(self):
        for symbol in ARCHIVED_SYMBOLS:
            event = {"T": "q", "S": symbol, "t": "2026-09-27T23:00:00Z"}
            self.assertTrue(valid_market_event(event))
            self.assertEqual(should_fanout(event), symbol == "BTC/USD")
        self.assertFalse(valid_market_event({"T": "o", "S": "ETH/USD", "t": "2026-09-27T23:00:00Z"}))
        self.assertFalse(should_fanout({"T": "t", "S": "BTC/USD"}))


if __name__ == "__main__":
    unittest.main()
