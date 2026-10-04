"""Guard received-time taker-flow aggregation and executable screen ordering."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from trade_flow_screen import (  # noqa: E402
    DAY_NS,
    MINUTE_NS,
    evaluate,
    load_events,
    simulate,
    simulate_signed_direction,
)


class TradeFlowScreenTests(unittest.TestCase):
    def test_received_time_bins_use_provider_taker_side_and_not_exchange_minute(self) -> None:
        # SOURCE: synthetic records test schema handling and causal receipt bins.
        base = 1_790_640_000 * 1_000_000_000
        events = [
            {"T": "t", "S": "BTC/USD", "p": 100, "s": 2,
             "t": "2026-09-29T00:00:59.9Z", "tks": "B"},
            {"T": "t", "S": "BTC/USD", "p": 100, "s": 1,
             "t": "2026-09-29T00:00:59.9Z", "tks": "S"},
            {"T": "t", "S": "BTC/USD", "p": 100, "s": 1,
             "t": "2026-09-29T00:00:59.9Z", "tks": "?"},
            {"T": "q", "S": "BTC/USD", "bp": 99, "ap": 101,
             "t": "2026-09-29T00:01:00Z"},
        ]
        received = [base + MINUTE_NS - 1, base + MINUTE_NS - 1,
                    base + MINUTE_NS - 1, base + MINUTE_NS]
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.jsonl"
            capture.write_text("\n".join(json.dumps({
                "receivedAtNs": timestamp, "feed": "alpaca-us", "event": event
            }) for timestamp, event in zip(received, events)) + "\n", encoding="utf-8")
            quotes, samples, counts = load_events([capture])
        self.assertEqual(counts["event_t"], 3)
        self.assertEqual(counts["tradesWithUnknownTakerSide"], 1)
        self.assertEqual(len(quotes), 1)
        self.assertEqual(samples[0]["decisionNs"], base + MINUTE_NS)
        self.assertEqual(samples[0]["unknownSideCount"], 1)
        self.assertEqual(samples[0]["imbalance"], 1 / 3)

    def test_simulator_waits_for_post_signal_quote_and_charges_both_legs(self) -> None:
        # SOURCE: synthetic prices test sequencing and the documented fee formula.
        day_start = 1_790_640_000 * 1_000_000_000
        decision = day_start + MINUTE_NS
        sample = [{"decisionNs": decision, "imbalance": 0.5}]
        quotes = [
            {"receivedNs": decision, "bid": 99, "ask": 500},
            {"receivedNs": decision + 1, "bid": 99, "ask": 100},
            {"receivedNs": decision + MINUTE_NS, "bid": 101, "ask": 102},
        ]
        result = simulate(sample, quotes, horizon_minutes=1)
        gross_bps = (101 / 100 - 1) * 10_000
        self.assertEqual(result["completedNonOverlappingRoundTrips"], 1)
        self.assertAlmostEqual(
            result["meanNetBps"],
            ((101 / 100) * (1 - 0.0025) ** 2 - 1) * 10_000,
        )
        self.assertLess(result["meanNetBps"], gross_bps)
        self.assertEqual(result["entryQuoteDelayMsMedian"], 0.000001)

    def test_walk_forward_threshold_is_fit_only_on_prior_days(self) -> None:
        # SOURCE: synthetic two-day fixture verifies chronological split only.
        day_one = 1_790_640_000 * 1_000_000_000
        day_two = day_one + DAY_NS
        samples = [
            {"decisionNs": day_one + MINUTE_NS, "imbalance": 0.1},
            {"decisionNs": day_one + 2 * MINUTE_NS, "imbalance": 0.2},
            {"decisionNs": day_two + MINUTE_NS, "imbalance": 0.9},
        ]
        quotes = []
        for day_start in (day_one, day_two):
            for minute in range(4):
                received = day_start + minute * MINUTE_NS + 1
                quotes.append({"receivedNs": received, "bid": 99, "ask": 100})
        result = evaluate(quotes, samples, {}, horizons=(1,))
        self.assertEqual(len(result["folds"]), 1)
        self.assertEqual(result["folds"][0]["trainingUtcDates"], ["2026-09-29"])
        self.assertEqual(result["folds"][0]["frozenTraining90thPercentileThreshold"], 0.2)
        self.assertEqual(result["folds"][0]["byHorizon"]["1m"]["trainingQuantilePositiveFlow"]
                         ["completedNonOverlappingRoundTrips"], 1)

    def test_negative_flow_short_diagnostic_crosses_at_executable_sides(self) -> None:
        # SOURCE: synthetic short quotes test the directional diagnostic only.
        day_start = 1_790_640_000 * 1_000_000_000
        decision = day_start + MINUTE_NS
        samples = [{"decisionNs": decision, "imbalance": -0.5}]
        quotes = [
            {"receivedNs": decision + 1, "bid": 100, "ask": 101},
            {"receivedNs": decision + MINUTE_NS, "bid": 98, "ask": 99},
        ]
        result = simulate_signed_direction(samples, quotes, 1)
        self.assertEqual(result["hypotheticalShortTrades"], 1)
        self.assertEqual(result["longTrades"], 0)
        self.assertAlmostEqual(
            result["meanNetBps"],
            ((100 / 99) * (1 - 0.0025) ** 2 - 1) * 10_000,
        )


if __name__ == "__main__":
    unittest.main()
