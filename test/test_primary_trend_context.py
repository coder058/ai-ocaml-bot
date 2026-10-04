"""Synthetic calendar and native-bar cases, not strategy-performance evidence."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from primary_trend_context import summarize, fetch_native, collect, expected_periods, instant, ema

# SOURCE: artificial price/volume fixtures solely exercise invariants.
def row(at, close=100):
    return {"t": at, "o": close, "h": close + 1, "l": close - 1, "c": close, "v": 1}


class PrimaryTests(unittest.TestCase):
    def test_daily_midnight_uses_new_york_calendar_and_dst_not_fixed_utc_duration(self):
        start=instant("2026-03-06T05:00:00Z"); now=instant("2026-03-10T12:00:00Z")
        calendar=[{"date":"2026-03-06"},{"date":"2026-03-09"},{"date":"2026-03-10"}]
        data=[row("2026-03-06T05:00:00Z"),row("2026-03-09T04:00:00Z"),row("2026-03-10T04:00:00Z")]
        result=summarize(data,"1Day",start,now,True,calendar)
        self.assertEqual(result["contiguousBars"],2)
        self.assertEqual(result["lastBarClosedAt"],"2026-03-10T04:00:00Z")
        self.assertEqual(result["lastBarAt"],"2026-03-09T04:00:00Z")
        with self.assertRaises(ValueError):summarize([row("2026-03-09T00:00:00Z")],"1Day",start,now,True,calendar)

    def test_weekly_does_not_label_sunday_incomplete_week_as_closed(self):
        start=instant("2026-09-14T04:00:00Z"); now=instant("2026-10-04T20:00:00Z")
        calendar=[{"date":"2026-09-14"},{"date":"2026-09-21"},{"date":"2026-09-28"},{"date":"2026-10-02"}]
        result=summarize([row("2026-09-14T04:00:00Z"),row("2026-09-21T04:00:00Z"),row("2026-09-28T04:00:00Z")],"1Week",start,now,True,calendar)
        self.assertEqual(result["closedBars"],2)
        self.assertEqual(result["lastBarClosedAt"],"2026-09-28T04:00:00Z")
        self.assertEqual(result["expectedLatestBarAt"],"2026-09-21T04:00:00Z")

    def test_crypto_utc_missing_days_reset_warmup_and_missing_latest_is_stale(self):
        start=instant("2026-10-01T00:00:00Z"); now=instant("2026-10-04T12:00:00Z")
        result=summarize([row("2026-10-01T00:00:00Z"),row("2026-10-03T00:00:00Z"),row("2026-10-04T00:00:00Z")],"1Day",start,now,False,[])
        self.assertEqual(result["contiguousBars"],1)
        self.assertIsNone(result["ema50"])
        stale=summarize([row("2026-10-01T00:00:00Z")],"1Day",start,now,False,[])
        self.assertEqual(stale["status"],"stale"); self.assertIsNone(stale["trend"])

    def test_holidays_are_real_adjacency_and_invalid_or_duplicate_rows_fail(self):
        start=instant("2026-09-04T04:00:00Z"); now=instant("2026-09-09T04:00:00Z")
        calendar=[{"date":"2026-09-04"},{"date":"2026-09-08"}]
        data=[row("2026-09-04T04:00:00Z"),row("2026-09-08T04:00:00Z")]
        self.assertEqual(summarize(data,"1Day",start,now,True,calendar)["contiguousBars"],2)
        for invalid in ([data[0],data[0]], [{**data[0],"c":float("nan")}], [row("2026-09-07T04:00:00Z")]):
            with self.assertRaises(ValueError):summarize(invalid,"1Day",start,now,True,calendar)

    def test_all_pages_followed_and_symbol_or_token_mismatch_rejected(self):
        start=instant("2026-09-01T00:00:00Z"); now=instant("2026-10-01T00:00:00Z")
        first={"bars":{"BTC/USD":[row("2026-09-01T00:00:00Z")]},"next_page_token":"next"}
        second={"bars":{"ETH/USD":[]},"next_page_token":None}
        request=Mock(side_effect=[first,second])
        data=fetch_native(request,"https://known.example/bars",["BTC/USD","ETH/USD"],"1Day",start,now,{},False)
        self.assertEqual(len(data["BTC/USD"]),1)
        self.assertIn("page_token=next",request.call_args.args[0])
        with self.assertRaises(ValueError):fetch_native(Mock(side_effect=[first,first]),"https://known.example/bars",["BTC/USD"],"1Day",start,now,{},False)
        with self.assertRaises(ValueError):fetch_native(Mock(return_value={"bars":{"AAPL":[]}}),"https://known.example/bars",["BTC/USD"],"1Day",start,now,{},False)

    def test_ready_trend_is_descriptive_and_future_cached_reception_is_not_reused(self):
        start=instant("2026-08-01T00:00:00Z"); now=start+timedelta(days=51)
        rows=[row((start+timedelta(days=i)).isoformat(),100+i) for i in range(51)]
        result=summarize(rows,"1Day",start,now,False,[])
        self.assertEqual(result["status"],"descriptive");self.assertEqual(result["trend"],"rising")
        self.assertFalse(result["orderAuthority"]);self.assertIsNone(result["winProbability"])
        scope={"Alpaca crypto":["BTC/USD"],"Hyperliquid HIP-3":["xyz:EUR"]}
        previous={"retrievedAt":now.isoformat(),"scope":{"Alpaca crypto":["BTC/USD"]},"orderAuthority":False,"winProbability":None}
        request=Mock(return_value={"bars":{}})
        self.assertIs(collect(request,Mock(),"stock","crypto",scope,{},now,previous),previous)
        request.assert_not_called()
        future={**previous,"retrievedAt":(now+timedelta(days=1)).isoformat()}
        collect(request,Mock(),"stock","crypto",scope,{},now,future)
        self.assertEqual(request.call_count,2)
        with self.assertRaises(ValueError):collect(request,Mock(),"stock","crypto",{"Alpaca equities":["AAPL"]},{},now)
        with self.assertRaises(ValueError):collect(request,Mock(),"stock","crypto",{"Alpaca crypto":["DOGE/USD"]},{},now)


if __name__=="__main__":unittest.main()
