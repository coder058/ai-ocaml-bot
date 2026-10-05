"""Causality and provider history transport; fixtures are not market results."""
import sys
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from market_pipeline import RestBudget, alpaca_bars, merge, normalize, session_slots, relevant_calendar, request, HL_INFO  # noqa: E402

# SOURCE: synthetic UTC minute OHLC fixture for boundary validation.
ROW = {"t": "2026-10-01T12:00:00Z", "o": 100, "h": 101, "l": 99, "c": 100, "v": 1}
NOW = datetime(2026, 10, 1, 12, 1, tzinfo=timezone.utc)


class PipelineTests(unittest.TestCase):
    def test_native_primary_requests_use_documented_budget_without_intraday_key_error(self):
        # SOURCE: synthetic 52-week ranges validate default weight 20 +
        # ceil(estimated maximum rows / documented 60), no network calls.
        for interval, expected in (("1w", 21), ("1d", 27)):
            with patch("market_pipeline.HL_BUDGET.acquire") as acquire, patch("market_pipeline.urllib.request.urlopen", return_value=io.StringIO("[]")) as transport:
                result = request(HL_INFO, body={"type":"candleSnapshot", "req":{
                    "coin":"xyz:EUR", "interval":interval, "startTime":0,
                    "endTime":52*7*24*60*60*1_000}})
                acquire.assert_called_once_with(expected)
                transport.assert_called_once()
                self.assertEqual(result, [])

    def test_calendar_window_keeps_session_adjacency_missing_bars_and_latest_expectation(self):
        from murphy_analysis import contiguous
        # SOURCE: synthetic actual-session slots and gaps, not broker observations.
        a=int(datetime(2026,10,1,19,58,tzinfo=timezone.utc).timestamp())//60
        b=int(datetime(2026,10,2,13,30,tzinfo=timezone.utc).timestamp())//60
        slots={"1m":[a-10,a-1,a,a+1,b,b+1,b+2]}
        rows=[{**ROW,"t":"2026-10-01T19:59:00Z"},{**ROW,"t":"2026-10-02T13:30:00Z"}]
        trimmed=relevant_calendar({"1m":rows},slots)
        self.assertEqual(trimmed["1m"],[a+1,b,b+1,b+2])
        at="2026-10-02T13:33:00Z"
        self.assertEqual(contiguous(rows,1,at,slots["1m"]),contiguous(rows,1,at,trimmed["1m"]))
        gap=rows+[{**ROW,"t":"2026-10-02T13:32:00Z"}]
        self.assertEqual(len(contiguous(gap,1,at,trimmed["1m"])),1)
        self.assertEqual(trimmed["1m"][-1],slots["1m"][-1])
        self.assertEqual(relevant_calendar({},slots),slots)
        self.assertEqual(relevant_calendar({"1m":[{**ROW,"t":"2026-10-03T00:00:00Z"}]},slots),slots)

    def test_open_future_invalid_and_misaligned_bars_never_become_signal_input(self):
        self.assertIsNotNone(normalize(ROW, 1, NOW))
        self.assertIsNone(normalize(ROW, 5, NOW))
        with self.assertRaises(ValueError):
            normalize({**ROW, "t": "2026-10-01T12:01:00Z"}, 5, NOW)
        with self.assertRaises(ValueError):
            normalize({**ROW, "l": 102}, 1, NOW)
        with self.assertRaises(ValueError):
            normalize({**ROW, "v": float("nan")}, 1, NOW)

    def test_native_four_hour_candle_does_not_depend_on_missing_minute_stream(self):
        start_ms = int(datetime(2026, 10, 1, 12, tzinfo=timezone.utc).timestamp() * 1_000)
        # SOURCE: 4h duration in milliseconds; HIP-3 T is inclusive.
        candle = {**ROW, "t": start_ms, "T": start_ms + 4 * 60 * 60 * 1_000 - 1}
        close = datetime(2026, 10, 1, 16, tzinfo=timezone.utc)
        self.assertEqual(normalize(candle, 240, close, hip3=True), ROW)
        with self.assertRaises(ValueError):
            normalize({**candle, "T": start_ms}, 240, close, hip3=True)

    def test_native_bar_pages_are_followed_and_nonadvancing_tokens_rejected(self):
        credentials = {"APCA_API_KEY_ID": "synthetic", "APCA_API_SECRET_KEY": "synthetic"}
        pages = [{"bars": {"BTC/USD": [ROW]}, "next_page_token": "next"},
                 {"bars": {"ETH/USD": [ROW]}, "next_page_token": None}]
        with patch("market_pipeline.request", side_effect=pages) as request:
            rows = alpaca_bars(["BTC/USD", "ETH/USD"], "1m", NOW, NOW, credentials)
            self.assertEqual(set(rows), {"BTC/USD", "ETH/USD"})
            self.assertEqual(len(rows["ETH/USD"]), 1)
            self.assertIn("page_token=next", request.call_args.args[0])
        with patch("market_pipeline.request", side_effect=[pages[0], pages[0]]):
            with self.assertRaises(ValueError):
                alpaca_bars(["BTC/USD"], "1m", NOW, NOW, credentials)

    def test_cache_merges_new_retrievals_without_duplicate_bar_starts(self):
        # SOURCE: revised values represent newly retrieved context only.
        revised = {**ROW, "c": 101}
        self.assertEqual(merge([ROW], [revised]), [revised])

    def test_actual_calendar_controls_daylight_saving_and_half_day_slots(self):
        # SOURCE: synthetic regular and early-close New York sessions.
        winter = session_slots([{"date": "2026-01-05", "open": "09:30", "close": "16:00"}], 1)
        summer = session_slots([{"date": "2026-07-06", "open": "09:30", "close": "13:00"}], 1)
        self.assertEqual(datetime.fromtimestamp(winter[0] * 60, timezone.utc).hour, 14)
        self.assertEqual(datetime.fromtimestamp(summer[0] * 60, timezone.utc).hour, 13)
        self.assertEqual(len(winter), 390)
        self.assertEqual(len(summer), 210)

    def test_public_rest_budget_survives_restart_and_waits_before_over_limit(self):
        # SOURCE: artificial clock tests the documented 1,200-weight/60s budget.
        clock = [1_000.0]
        slept = []
        def sleep(seconds):
            slept.append(seconds)
            clock[0] += seconds
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            RestBudget(path, lambda: clock[0], sleep).acquire(1_200)
            RestBudget(path, lambda: clock[0], sleep).acquire(20)
            self.assertEqual(slept, [60])


if __name__ == "__main__":
    unittest.main()
