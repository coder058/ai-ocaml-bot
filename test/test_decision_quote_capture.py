"""Synthetic quote transport/causality checks, not evidence of fills or returns."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from decision_quote_capture import normalize, collect

# SOURCE: artificial quote times/prices/sizes test the actual boundary checks.
NOW=datetime(2026,10,4,21,20,tzinfo=timezone.utc)
QUOTE={"t":"2026-10-04T21:19:59.123456789Z","bp":100,"ap":101,"bs":1,"as":2}


class QuoteTests(unittest.TestCase):
    def test_actual_quote_precision_is_retained_and_not_claimed_as_execution(self):
        quote=normalize(QUOTE,NOW,"Alpaca crypto","BTC/USD")
        self.assertEqual(quote["quoteAt"],QUOTE["t"])
        self.assertEqual(quote["status"],"fresh")
        self.assertEqual(quote["bid"],100)
        self.assertGreater(quote["spreadBps"],0)
        self.assertFalse(quote["orderAuthority"])
        self.assertIsNone(quote["winProbability"])
        self.assertNotIn("fillPrice",quote)

    def test_closed_session_stale_and_future_quotes_never_become_fresh(self):
        for timestamp,status in [("2026-10-02T20:00:00Z","stale"),("2026-10-04T21:20:01Z","future"),("2026-10-04T21:20:00.000000001Z","future")]:
            quote=normalize({**QUOTE,"t":timestamp},NOW,"Alpaca equities","QQQ")
            self.assertEqual(quote["status"],status)
            self.assertEqual(quote["quoteAt"],timestamp)
        self.assertEqual(normalize(None,NOW,"Alpaca equities","QQQ")["status"],"missing")

    def test_crossed_nonfinite_empty_and_naive_quotes_are_invalid(self):
        for change in [{"bp":102},{"bp":float("nan")},{"bs":0},{"as":-1},{"t":"2026-10-04T21:20:00"}, {"ap":None}]:
            self.assertEqual(normalize({**QUOTE,**change},NOW,"Alpaca crypto","BTC/USD")["status"],"invalid")

    def test_exact_read_only_batch_scopes_and_partial_missing_responses(self):
        request=Mock(side_effect=[{"quotes":{"BTC/USD":QUOTE}},{"quotes":{"QQQ":QUOTE}}])
        values,errors=collect(request,{"Alpaca crypto":["BTC/USD","ETH/USD"],"Alpaca equities":["QQQ"],"Hyperliquid HIP-3":["xyz:EUR"]},{},now=lambda:NOW)
        self.assertEqual(request.call_count,2)
        self.assertEqual(errors,[])
        self.assertEqual(values["Alpaca crypto|ETH/USD"]["status"],"missing")
        self.assertEqual(values["Alpaca equities|QQQ"]["feed"],"iex")
        self.assertIn("feed=iex",request.call_args.args[0])
        self.assertFalse(any("Hyperliquid" in key for key in values))
        for call in request.call_args_list:
            self.assertIn("data.alpaca.markets",call.args[0])
            self.assertNotIn("/orders",call.args[0])

    def test_errors_and_scope_mismatch_do_not_fabricate_quote_data(self):
        for request in [Mock(side_effect=TimeoutError),Mock(return_value={"quotes":{"AAPL":QUOTE}})]:
            values,errors=collect(request,{"Alpaca equities":["QQQ"]},{},now=lambda:NOW)
            self.assertEqual(len(errors),1)
            self.assertEqual(values["Alpaca equities|QQQ"]["status"],"retrieval_error")
            self.assertNotIn("bid",values["Alpaca equities|QQQ"])
        for scope in [{"Alpaca equities":["AAPL"]},{"Alpaca crypto":["DOGE/USD"]}]:
            with self.assertRaises(ValueError):collect(Mock(),scope,{},now=lambda:NOW)


if __name__=="__main__":unittest.main()
