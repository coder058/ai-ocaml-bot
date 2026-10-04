"""Test point-in-time aggregation and execution accounting in the EMA replay."""

from __future__ import annotations

import sys
import gzip
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from executable_ema_replay import (  # noqa: E402
    aggregate_as_received,
    make_signals,
    read_capture,
    simulate_day,
)


class ExecutableEmaReplayTests(unittest.TestCase):
    def test_gzip_capture_reads_quotes_and_first_seen_bars(self) -> None:
        # SOURCE: synthetic compressed stream fixture tests input handling only.
        records = [
            {"receivedAtNs": 1790494087876850255,
             "event": {"T": "q", "S": "ETH/USD", "t": "2026-09-27T07:28:07.833016531Z",
                       "bp": 99, "ap": 101}},
            {"receivedAtNs": 1790494087876850255,
             "event": {"T": "b", "S": "ETH/USD", "t": "2026-09-27T07:28:00Z",
                       "o": 100, "h": 102, "l": 98, "c": 101, "v": 1}},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.jsonl.gz"
            with gzip.open(capture, "wt", encoding="utf-8") as output:
                for record in records:
                    output.write(json.dumps(record) + "\n")
            quotes, bars, counts = read_capture([capture], "ETH/USD")
        self.assertEqual(len(quotes), 1)
        self.assertEqual(len(bars), 1)
        self.assertEqual(counts["event_q"], 1)
        self.assertEqual(counts["event_b"], 1)

    def test_missing_minute_delays_aggregate_until_observed(self) -> None:
        # SOURCE: synthetic two-minute bars exercise strict complete grouping;
        # these timestamps and prices are fixtures, not market measurements.
        minute_bars = {
            0: {"slot": 0, "receivedNs": 10, "o": 10, "h": 11, "l": 9, "c": 10, "v": 1},
            1: {"slot": 1, "receivedNs": 30, "o": 10, "h": 12, "l": 10, "c": 12, "v": 2},
            2: {"slot": 2, "receivedNs": 20, "o": 12, "h": 13, "l": 11, "c": 12, "v": 3},
        }
        bars, incomplete = aggregate_as_received(minute_bars, 2)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["availableNs"], 30)
        self.assertEqual(bars[0]["c"], 12)
        self.assertEqual(incomplete, 1)

    def test_indicator_resets_on_gap_and_waits_for_warmup(self) -> None:
        # SOURCE: artificial period values make this fixture small; production
        # defaults remain fixed to Pattern Forge's 20/50 display periods.
        bars = [
            {"slot": slot, "availableNs": slot + 1, "c": close}
            for slot, close in [(0, 10), (1, 11), (2, 12), (4, 13), (5, 14)]
        ]
        signals, resets, longest = make_signals(bars, fast_period=2, slow_period=3)
        self.assertEqual(resets, 1)
        self.assertEqual(longest, 3)
        self.assertEqual([signal["slot"] for signal in signals], [2])

    def test_multi_minute_bar_spacing_is_not_treated_as_a_gap(self) -> None:
        # SOURCE: synthetic five-minute slot spacing tests frame-aware gaps.
        bars = [
            {"slot": slot, "availableNs": slot + 1, "c": close}
            for slot, close in [(0, 10), (5, 11), (10, 12)]
        ]
        signals, resets, longest = make_signals(
            bars, fast_period=1, slow_period=2, slot_step=5
        )
        self.assertEqual(resets, 0)
        self.assertEqual(longest, 3)
        self.assertEqual([signal["slot"] for signal in signals], [5, 10])

    def test_simulation_uses_quote_after_signal_and_charges_two_sides(self) -> None:
        # SOURCE: a synthetic complete day checks execution ordering and the
        # fee formula; prices are deliberately invented test fixtures.
        ns = 1_000_000_000
        day = 0
        signals = [
            {"availableNs": 60 * ns, "long": True},
            {"availableNs": 120 * ns, "long": False},
        ]
        quotes = [
            {"receivedNs": 60 * ns - 1, "bid": 1.0, "ask": 1.0},
            {"receivedNs": 60 * ns + 1, "bid": 99.0, "ask": 100.0},
            {"receivedNs": 120 * ns + 1, "bid": 110.0, "ask": 111.0},
            {"receivedNs": 180 * ns, "bid": 108.0, "ask": 109.0},
        ]
        result = simulate_day(day, signals, quotes, fee_rate=0.0025)
        self.assertIsNotNone(result)
        self.assertEqual(result["entries"], 1)
        self.assertEqual(result["exits"], 1)
        self.assertEqual(result["roundTrips"], 1)
        self.assertGreater(result["candidateReturnPct"], 0)
        self.assertEqual(result["medianSignalToNextQuoteMs"], 0.000001)
        self.assertEqual(result["maxSignalToNextQuoteMs"], 0.000001)


if __name__ == "__main__":
    unittest.main()
