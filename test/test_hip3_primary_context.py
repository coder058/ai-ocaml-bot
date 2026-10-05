"""Native timestamp/scope/causality cases, not strategy or performance results."""
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from hip3_primary_context import collect, summarize, milliseconds, PERIOD_MS, VENUE
from primary_trend_context import instant

# SOURCE: synthetic OHLCV, symbol and UTC times exercise actual provider shape.
AS_OF = instant("2026-10-05T01:00:00Z")
WEEK = instant("2026-09-24T00:00:00Z")


def row(at, symbol="xyz:EUR", interval="1w", close=100):
    start = milliseconds(at)
    return {"t": start, "T": start + PERIOD_MS[interval] - 1, "s": symbol, "i": interval,
            "o": str(close), "h": str(close + 1), "l": str(close - 1), "c": str(close), "v": "1"}


class NativeHip3Tests(unittest.TestCase):
    def test_actual_thursday_grid_withholds_open_week_until_next_thursday(self):
        data = [row(WEEK), row(WEEK + timedelta(weeks=1))]
        summary = summarize(data, "xyz:EUR", "1w", WEEK, AS_OF)
        self.assertEqual(summary["closedBars"], 1)
        self.assertEqual(summary["lastBarClosedAt"], "2026-10-01T00:00:00Z")
        self.assertEqual(summary["expectedLatestBarAt"], "2026-09-24T00:00:00Z")
        self.assertIn("Thursday", summary["closure"])
        boundary = summarize(data, "xyz:EUR", "1w", WEEK, instant("2026-10-08T00:00:00Z"))
        self.assertEqual(boundary["closedBars"], 2)
        with self.assertRaises(ValueError):
            summarize([row(instant("2026-09-28T00:00:00Z"))], "xyz:EUR", "1w", WEEK, AS_OF)

    def test_daily_latest_gap_and_empty_do_not_invent_trend(self):
        start = instant("2026-10-01T00:00:00Z")
        data = [row(start, interval="1d"), row(start + timedelta(days=3), interval="1d")]
        summary = summarize(data, "xyz:EUR", "1d", start, AS_OF)
        self.assertEqual(summary["contiguousBars"], 1)
        self.assertEqual(summary["status"], "warming")
        self.assertIsNone(summary["ema50"])
        self.assertEqual(summarize(data[:1], "xyz:EUR", "1d", start, AS_OF)["status"], "stale")
        self.assertEqual(summarize([], "xyz:EUR", "1d", start, AS_OF)["status"], "no_data")

    def test_ready_daily_trend_is_descriptive_without_probability_or_orders(self):
        start = instant("2026-08-15T00:00:00Z")
        data = [row(start + timedelta(days=i), interval="1d", close=100+i) for i in range(51)]
        result = summarize(data, "xyz:EUR", "1d", start, AS_OF)
        self.assertEqual(result["status"], "descriptive")
        self.assertEqual(result["trend"], "rising")
        self.assertFalse(result["orderAuthority"])
        self.assertIsNone(result["winProbability"])

    def test_scope_interval_duration_nonfinite_and_duplicate_rows_fail_closed(self):
        original = row(WEEK)
        invalid = [{**original, "s": "xyz:JPY"}, {**original, "i": "1d"},
                   {**original, "T": original["T"] + 1}, {**original, "t": True},
                   {**original, "c": "nan"}, {**original, "v": True}, {**original, "v": "-1"}]
        for bad in invalid:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                summarize([bad], "xyz:EUR", "1w", WEEK, AS_OF)
        with self.assertRaises(ValueError):
            summarize([original, original], "xyz:EUR", "1w", WEEK, AS_OF)

    def test_three_public_requests_per_scan_and_next_symbol_is_not_starved(self):
        request = Mock(side_effect=TimeoutError)
        scope = {VENUE: ["xyz:EUR", "xyz:JPY"]}
        first = collect(request, scope, AS_OF)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(len(first["markets"]["xyz:EUR"]["errors"]), 3)
        self.assertIsNone(first["markets"]["xyz:EUR"]["retrievedAt"])
        second = collect(request, scope, AS_OF + timedelta(minutes=1), first)
        self.assertEqual(request.call_count, 6)
        self.assertEqual(len(second["markets"]["xyz:JPY"]["errors"]), 3)
        last = request.call_args
        self.assertEqual(last.args, ("https://api.hyperliquid.xyz/info",))
        self.assertEqual(last.kwargs["body"]["type"], "candleSnapshot")
        self.assertEqual(last.kwargs["body"]["req"]["coin"], "xyz:JPY")
        collect(request, scope, AS_OF + timedelta(minutes=2), second)
        self.assertEqual(request.call_count, 6)

    def test_failed_refresh_keeps_original_frame_receipt_and_asof_not_attempt(self):
        scope = {VENUE: ["xyz:EUR"]}
        def provider(url, *, body):
            interval = body["req"]["interval"]
            at = (instant("2026-09-04T00:00:00Z") if interval == "1M" else WEEK)
            return [row(at, interval=interval)]
        first = collect(provider, scope, AS_OF)
        original = first["markets"]["xyz:EUR"]["frames"]
        refreshed = collect(Mock(side_effect=TimeoutError), scope, AS_OF + timedelta(hours=1), first)
        entry = refreshed["markets"]["xyz:EUR"]
        self.assertEqual(entry["frames"], original)
        self.assertNotEqual(entry["asOf"], entry["lastAttemptAt"])
        self.assertEqual(len(entry["errors"]), 3)

    def test_future_cache_attempt_and_wrong_scope_or_payload_never_become_new_data(self):
        scope = {VENUE: ["xyz:EUR"]}
        prior = {"markets": {"xyz:EUR": {"lastAttemptAt": "2026-10-06T00:00:00Z"}},
                 "orderAuthority": False, "winProbability": None}
        request = Mock(return_value={"not": "candles"})
        result = collect(request, scope, AS_OF, prior)
        self.assertEqual(request.call_count, 3)
        self.assertFalse(result["markets"]["xyz:EUR"]["frames"])
        for bad in ({VENUE: ["EUR/USD"]}, {VENUE: ["xyz:EUR", "xyz:EUR"]}):
            with self.assertRaises(ValueError):
                collect(request, bad, AS_OF)
        removed = collect(request, {VENUE: []}, AS_OF, result)
        self.assertEqual(removed["markets"], {})

    def test_native_1M_is_thirty_day_epoch_grid_not_calendar_month_and_withholds_open_block(self):
        # SOURCE: synthetic values on actual observed provider Sep4/Oct4 grid.
        start = instant("2026-09-04T00:00:00Z")
        opening = instant("2026-10-04T00:00:00Z")
        data = [row(start,interval="1M"),row(opening,interval="1M")]
        result = summarize(data,"xyz:EUR","1M",start,AS_OF)
        self.assertEqual(result["interval"],"Native1M")
        self.assertEqual(result["lastBarClosedAt"],"2026-10-04T00:00:00Z")
        self.assertEqual(result["expectedLatestBarAt"],"2026-09-04T00:00:00Z")
        self.assertEqual(result["closedBars"],1);self.assertIsNone(result["ema50"])
        self.assertEqual(result["periodKind"],"fixed_30_day_epoch_grid")
        self.assertIn("not a calendar month",result["closure"])
        for bad in (row(instant("2026-09-01T00:00:00Z"),interval="1M"),
                    {**data[0],"T":milliseconds(instant("2026-10-01T00:00:00Z"))-1}):
            with self.assertRaises(ValueError):summarize([bad],"xyz:EUR","1M",start,AS_OF)

    def test_native_1M_gaps_latest_and_fifty_bar_requirement_do_not_invent_calendar_trend(self):
        # SOURCE: synthetic 51 increasing native blocks exercise actual EMA50
        # warmup; this does not assert any real HIP-3 venue has that history.
        step = timedelta(milliseconds=PERIOD_MS["1M"])
        latest = instant("2026-09-04T00:00:00Z");start=latest-step*50
        data = [row(start+step*i,interval="1M",close=100+i) for i in range(51)]
        ready=summarize(data,"xyz:EUR","1M",start,AS_OF)
        self.assertEqual(ready["status"],"descriptive");self.assertEqual(ready["trend"],"rising")
        gap=summarize(data[:-2]+data[-1:],"xyz:EUR","1M",start,AS_OF)
        self.assertEqual(gap["contiguousBars"],1);self.assertEqual(gap["status"],"warming")
        self.assertIsNone(gap["ema50"])
        self.assertEqual(summarize(data[:-1],"xyz:EUR","1M",start,AS_OF)["status"],"stale")

    def test_two_interval_cache_seeds_new_1M_without_repairing_old_receipts_and_failure_keeps_retry_cadence(self):
        prior={"markets":{"xyz:EUR":{"lastAttemptAt":"2026-10-05T00:59:00Z","frames":{}}},
               "orderAuthority":False,"winProbability":None}
        request=Mock(side_effect=TimeoutError)
        first=collect(request,{VENUE:["xyz:EUR"]},AS_OF,prior)
        self.assertEqual(request.call_count,3)
        self.assertEqual(first["markets"]["xyz:EUR"]["intervalsAttempted"],["1d","1w","1M"])
        collect(request,{VENUE:["xyz:EUR"]},AS_OF+timedelta(minutes=1),first)
        self.assertEqual(request.call_count,3)


if __name__ == "__main__":
    unittest.main()
