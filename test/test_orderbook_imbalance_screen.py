"""Guard chronological, fee-aware order-book imbalance screening."""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from orderbook_imbalance_screen import (  # noqa: E402
    DAY_NS,
    MINUTE_NS,
    epoch_ns,
    load_events,
    minute_samples,
    screen,
)


class OrderBookImbalanceTests(unittest.TestCase):
    def test_reads_gzip_capture(self) -> None:
        # SOURCE: a synthetic compressed quote validates archived input only.
        event = {"T": "q", "S": "BTC/USD", "t": "2026-09-29T00:00:00Z",
                 "bp": 99, "ap": 101}
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.jsonl.gz"
            with gzip.open(capture, "wt", encoding="utf-8") as output:
                output.write(json.dumps({"receivedAtNs": 1_790_640_000_000_000_000,
                                         "sessionId": "session-a", "event": event}) + "\n")
            quotes, features, counts = load_events([capture])
        self.assertEqual(len(quotes), 1)
        self.assertEqual(features, [])
        self.assertEqual(counts["event_q"], 1)

    def test_reconstruction_waits_for_reset_and_replays_deltas(self) -> None:
        # SOURCE: synthetic book levels exercise reset and delta handling only.
        base_ns = 1_790_640_000_000_000_000
        events = [
            {"T": "o", "S": "BTC/USD", "t": "2026-09-29T00:00:00Z",
             "r": False, "b": [{"p": "99", "s": "1"}], "a": []},
            {"T": "o", "S": "BTC/USD", "t": "2026-09-29T00:00:01Z",
             "r": True, "b": [{"p": "99", "s": "3"}],
             "a": [{"p": "101", "s": "1"}]},
            {"T": "o", "S": "BTC/USD", "t": "2026-09-29T00:00:02Z",
             "b": [{"p": "99", "s": "1"}], "a": []},
            {"T": "q", "S": "BTC/USD", "t": "2026-09-29T00:00:03Z",
             "bp": 99, "ap": 101},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.jsonl"
            capture.write_text("\n".join(json.dumps({
                "receivedAtNs": base_ns + offset * 1_000_000_000,
                "sessionId": "session-a", "event": event,
            }) for offset, event in enumerate(events)) + "\n", encoding="utf-8")
            quotes, features, counts = load_events([capture])
        self.assertEqual(counts["bookUpdatesBeforeReset"], 1)
        self.assertEqual(counts["fullBookResets"], 1)
        self.assertEqual(len(features), 2)
        self.assertAlmostEqual(features[-1][2], 0.0)
        self.assertEqual(len(quotes), 1)

    def test_minute_sample_uses_only_features_received_before_boundary(self) -> None:
        # SOURCE: synthetic one-minute ordering fixture, not a live threshold.
        import orderbook_imbalance_screen as screen_module

        start = 1_790_640_000 * screen_module.NS_PER_SECOND
        features = [
            (start + 20_000_000_000, 0, 0.1, 2.0),
            (start + 50_000_000_000, 0, 0.4, 2.5),
            (start + 60_000_000_000, 0, 0.9, 3.0),
        ]
        samples = minute_samples(features)
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0]["imbalance"], 0.4)
        self.assertEqual(samples[0]["featureReceivedNs"], start + 50_000_000_000)

    def test_screen_applies_published_fees_to_executable_quotes(self) -> None:
        # SOURCE: synthetic quotes and imbalances test fee application only.
        import orderbook_imbalance_screen as screen_module

        day_ns = screen_module.DAY_NS
        training_day = epoch_ns("2026-09-28T00:00:00Z") // day_ns
        holdout_day = epoch_ns("2026-09-29T00:00:00Z") // day_ns
        samples = []
        minutes_per_day = DAY_NS // MINUTE_NS
        for day in (training_day, holdout_day):
            for minute in range(10):
                slot = day * minutes_per_day + minute
                samples.append({"slot": slot, "decisionNs": (slot + 1) * screen_module.MINUTE_NS,
                               "imbalance": 0.2 if day == 20_800 else 0.9,
                               "spreadBps": 2.0})
        quotes = []
        for day in (training_day, holdout_day):
            for minute in range(12):
                received = day * day_ns + minute * screen_module.MINUTE_NS + 1
                quotes.append((received, received, 99.0, 100.0))
        result = screen(samples, quotes, horizons=(1,))
        self.assertEqual(result["holdoutUtcDate"], "2026-09-29")
        horizon = result["byHorizon"]["1m"]
        self.assertEqual(horizon["executedNonOverlappingPaperTrades"], 5)
        self.assertAlmostEqual(horizon["medianGrossBpsAfterSpreadBeforeFees"], -100.0)
        self.assertLess(horizon["meanNetBpsPerTrade"], -50)
        self.assertEqual(horizon["trades"][0]["signalAtUtc"], "2026-09-29T00:01:00.000000000Z")
        self.assertEqual(horizon["trades"][0]["entryQuoteReceivedAtUtc"],
                         "2026-09-29T00:01:00.000000001Z")

    def test_prospective_cutoff_excludes_prior_latest_day_samples(self) -> None:
        # SOURCE: synthetic timestamps verify the holdout boundary only.
        day_ns = DAY_NS
        training_day = epoch_ns("2026-09-28T00:00:00Z") // day_ns
        holdout_day = epoch_ns("2026-09-29T00:00:00Z") // day_ns
        samples = []
        minutes_per_day = DAY_NS // MINUTE_NS
        for day in (training_day, holdout_day):
            for minute in range(10):
                slot = day * minutes_per_day + minute
                samples.append({"slot": slot,
                                "decisionNs": (slot + 1) * MINUTE_NS,
                                "imbalance": 0.2 if day == training_day else 0.9,
                                "spreadBps": 2.0})
        quotes = []
        for day in (training_day, holdout_day):
            for minute in range(12):
                received = day * day_ns + minute * MINUTE_NS + 1
                quotes.append((received, received, 99.0, 100.0))
        result = screen(samples, quotes, horizons=(1,),
                        holdout_after="2026-09-29T00:05:00Z")
        self.assertEqual(result["holdoutAfterUtc"], "2026-09-29T00:05:00Z")
        self.assertEqual(result["holdoutSamples"], 5)
        self.assertEqual(result["trainingPositiveImbalanceSamples"], 10)
        self.assertEqual(result["byHorizon"]["1m"]["executedNonOverlappingPaperTrades"], 3)

    def test_prospective_cutoff_must_belong_to_latest_utc_date(self) -> None:
        # SOURCE: synthetic UTC dates guard against a misplaced holdout cutoff.
        day_ns = DAY_NS
        training_day = epoch_ns("2026-09-28T00:00:00Z") // day_ns
        holdout_day = epoch_ns("2026-09-29T00:00:00Z") // day_ns
        samples = []
        minutes_per_day = DAY_NS // MINUTE_NS
        for day in (training_day, holdout_day):
            slot = day * minutes_per_day
            samples.append({"slot": slot, "decisionNs": (slot + 1) * MINUTE_NS,
                            "imbalance": 0.2, "spreadBps": 2.0})
        quotes = []
        for day in (training_day, holdout_day):
            received = day * day_ns + MINUTE_NS + 1
            quotes.append((received, received, 99.0, 100.0))
        with self.assertRaisesRegex(ValueError, "latest capture UTC date"):
            screen(samples, quotes, horizons=(1,),
                   holdout_after="2026-09-28T23:59:00Z")

    def test_measured_entry_latency_uses_later_ask_and_restarts_horizon(self) -> None:
        # SOURCE: synthetic quote path tests latency placement, not a return estimate.
        day_ns = epoch_ns("2026-09-29T00:00:00Z")
        training_day = epoch_ns("2026-09-28T00:00:00Z") // DAY_NS
        holdout_day = day_ns // DAY_NS
        samples = []
        for day, imbalance in ((training_day, 0.2), (holdout_day, 0.9)):
            slot = day * (DAY_NS // MINUTE_NS)
            samples.append({"slot": slot, "decisionNs": (slot + 1) * MINUTE_NS,
                            "imbalance": imbalance, "spreadBps": 2.0})
        quote_rows = [
            (day_ns + MINUTE_NS + 1, 0, 100.0, 101.0),
            (day_ns + MINUTE_NS + 250_000_000, 0, 101.0, 102.0),
            (day_ns + MINUTE_NS + 600_000_000, 0, 102.0, 103.0),
            (day_ns + 2 * MINUTE_NS + 2, 0, 104.0, 105.0),
            (day_ns + 2 * MINUTE_NS + 600_000_001, 0, 99.0, 100.0),
        ]
        zero = screen(samples, quote_rows, horizons=(1,))
        delayed = screen(samples, quote_rows, horizons=(1,), entry_latency_ms=500.0)
        zero_gross = zero["byHorizon"]["1m"]["medianGrossBpsAfterSpreadBeforeFees"]
        delayed_gross = delayed["byHorizon"]["1m"]["medianGrossBpsAfterSpreadBeforeFees"]
        self.assertNotEqual(zero_gross, delayed_gross)
        self.assertEqual(delayed["entryLatencyMs"], 500.0)

    def test_negative_entry_latency_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            screen([{"slot": 0, "decisionNs": 1, "imbalance": 1}],
                   [(2, 2, 1.0, 2.0)], entry_latency_ms=-1.0)


if __name__ == "__main__":
    unittest.main()
