"""Synthetic geometry and library parity, not profitability evidence."""
import sys
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import talib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from murphy_analysis import CANDLES, analyze_frame, contiguous, enrich, geometry, pivots, forward_reading, swing_divergences


def fixture(count=150):
    # SOURCE: deterministic synthetic OHLCV fixture; no market results.
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(count):
        close = 100 + np.sin(i) + i / 100
        rows.append({"t": (start + timedelta(minutes=i)).isoformat().replace("+00:00", "Z"),
                     "o": close + .1, "h": close + 1, "l": close - 1, "c": close, "v": float(i+1)})
    return rows, (start + timedelta(minutes=count)).isoformat().replace("+00:00", "Z")


class MurphyTests(unittest.TestCase):
    def test_double_top_and_head_shoulders_require_actual_neckline_close(self):
        # SOURCE: hand-constructed OHLC paths with confirmed peaks and troughs.
        def path(closes):
            rows, _ = fixture(len(closes))
            return [{**row, "o": close, "h": close + .5, "l": close - .5, "c": close}
                    for row, close in zip(rows, closes, strict=True)]
        double = path([10,11,12,15,12,11,9,11,12,15,12,8,7])
        self.assertIn("double_top_neckline_break", geometry(double)["chartShapes"])
        no_break = [{**r, "o": 10, "c": 10, "h": 10.5, "l": 9.5} if i >= 11 else r for i, r in enumerate(double)]
        self.assertNotIn("double_top_neckline_break", geometry(no_break)["chartShapes"])
        head = path([10,11,12,15,12,11,9,11,13,18,13,11,9,11,12,15,12,8,7])
        self.assertIn("head_shoulders_neckline_break", geometry(head)["chartShapes"])
        # SOURCE: exact price reflection reverses peaks/troughs for inverse fixtures.
        def reflection(rows):
            return [{**r, "o":30-r["o"], "c":30-r["c"], "h":30-r["l"], "l":30-r["h"]} for r in rows]
        self.assertIn("double_bottom_neckline_break", geometry(reflection(double))["chartShapes"])
        self.assertIn("inverse_head_shoulders_neckline_break", geometry(reflection(head))["chartShapes"])

    def test_divergence_is_known_only_after_confirming_candle_close(self):
        closes = [10,11,12,15,12,11,9,11,13,18,13,11,10]
        rows, _ = fixture(len(closes))
        rows = [{**r, "o":c, "c":c, "h":c+.5, "l":c-.5} for r,c in zip(rows,closes,strict=True)]
        oscillator = np.array([5.] * len(rows))
        oscillator[3], oscillator[9] = 8, 6
        before = swing_divergences(rows[:11], {"MACD": oscillator[:11]}, 1)
        self.assertEqual(before, [])
        after = swing_divergences(rows[:12], {"MACD": oscillator[:12]}, 1)
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0]["direction"], "bearish")
        self.assertEqual(after[0]["confirmationCloseAt"], rows[12]["t"])
        self.assertEqual(swing_divergences(rows, {"MACD": oscillator}, 1), after)
        reflected = [{**r, "o":30-r["o"], "c":30-r["c"], "h":30-r["l"], "l":30-r["h"]} for r in rows]
        bullish = swing_divergences(reflected, {"MACD": -oscillator}, 1)
        self.assertEqual(bullish[0]["direction"], "bullish")
        oscillator[9] = 10
        self.assertEqual(swing_divergences(rows, {"MACD": oscillator}, 1), [])
        oscillator[9] = np.nan
        self.assertEqual(swing_divergences(rows, {"MACD": oscillator}, 1), [])
        with self.assertRaises(ValueError): swing_divergences(rows, {"MACD": oscillator[:-1]}, 1)

    def test_every_catalog_pattern_matches_installed_c_library(self):
        rows, as_of = fixture()
        reading = analyze_frame(rows, 1, as_of)
        self.assertEqual(set(reading["patterns"]), set(talib.get_function_groups()["Pattern Recognition"]))
        arrays = [np.array([r[key] for r in rows]) for key in ("o", "h", "l", "c")]
        for name, function in CANDLES.items():
            self.assertEqual(reading["patterns"][name]["value"], int(getattr(talib, name)(*arrays)[-1]))
        self.assertFalse(reading["orderAuthority"])
        self.assertIsNone(reading["winProbability"])
        json.dumps(reading, allow_nan=False)

    def test_open_future_and_invalid_candles_fail_closed(self):
        rows, as_of = fixture()
        for modified in ([*rows, {**rows[-1], "t": as_of}],
                         [{**rows[0], "v": float("nan")}],
                         [{**rows[0], "l": rows[0]["h"] + 1}]):
            with self.assertRaises(ValueError):
                analyze_frame(modified, 1, as_of)

    def test_gap_resets_warmup_and_calendar_session_gap_is_valid(self):
        rows, as_of = fixture()
        gapped = rows[:3] + rows[4:]
        self.assertEqual(contiguous(gapped, 1, as_of), rows[4:])
        starts = [int(datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp()) // 60 for r in gapped]
        self.assertEqual(contiguous(gapped, 1, as_of, starts), gapped)
        short = analyze_frame(rows[-1:], 1, as_of)
        self.assertEqual(short["patterns"]["CDLHAMMER"]["status"], "warming")
        self.assertIsNone(short["patterns"]["CDLHAMMER"]["value"])

    def test_swing_points_have_later_confirmation_and_no_future_pivots(self):
        rows, _ = fixture()
        self.assertTrue(pivots(rows))
        for point in pivots(rows):
            self.assertGreater(point["confirmedAt"], point["time"])
            self.assertEqual(point["price"], rows[point["index"]]["h" if point["kind"] == "high" else "l"])
        last_confirm = rows[-1]["t"]
        self.assertTrue(all(p["confirmedAt"] <= last_confirm for p in geometry(rows)["pivots"]))

    def test_chart_keeps_real_history_across_gap_without_bridging_indicator_warmup(self):
        rows, as_of = fixture()
        gapped = rows[:-3] + rows[-2:]
        suite = analyze_frame(gapped, 1, as_of)
        self.assertEqual(suite["contiguousBars"], 2)
        self.assertGreater(len(suite["bars"]), suite["contiguousBars"])
        self.assertNotIn(rows[-3]["t"], [b["t"] for b in suite["bars"]])
        self.assertTrue(all(v is None for v in suite["overlays"]["EMA50"]))
        self.assertIsNone(suite["patterns"]["CDLHAMMER"]["value"])
        self.assertEqual(len(suite["overlays"]["EMA20"]), len(suite["bars"]))

    def test_murphy_coverage_keeps_missing_inputs_explicit(self):
        rows, as_of = fixture()
        result = {"asOf": as_of, "markets": [{"venue": "Alpaca crypto", "frames": {
            "1m": {"trend": "rising", "status": "ready", "lastBarStart": rows[-1]["t"]}}}]}
        enrich(result, [{"frames": {"1m": rows}}], {"1m": 1})
        suite = result["markets"][0]["frames"]["1m"]["technicalSuite"]
        self.assertEqual(len(suite["murphy"]), 10)
        self.assertEqual(suite["murphy"][0]["status"], "partial")
        self.assertEqual(suite["murphy"][-1]["status"], "partial")
        self.assertFalse(result["technicalCoverage"]["completeMurphyBook"])
        self.assertFalse(result["technicalCoverage"]["orderAuthority"])
        # SOURCE: synthetic native context must be retained as descriptive
        # evidence, never turned into order authority by the enrichment path.
        context = {"source": "synthetic", "retrievedAt": as_of, "frames": {"1Week": {"status": "warming"}}, "orderAuthority": False, "winProbability": None}
        enrich(result, [{"frames": {"1m": rows}, "primaryContext": context}], {"1m": 1})
        current = result["markets"][0]["frames"]["1m"]
        self.assertEqual(current["technicalSuite"]["murphy"][0]["evidence"]["primaryContext"], context)
        self.assertEqual(forward_reading(current)["technicalEvidence"]["primaryContext"], context)
        # SOURCE: synthetic received observation is distinct from a historical
        # OI/price confirmation and must survive first-feature projection.
        derivative = {"source": "synthetic public context", "receivedAt": as_of,
            "openInterestRaw": "50.00", "historicalSeries": False,
            "orderAuthority": False, "winProbability": None}
        enrich(result, [{"frames": {"1m": rows}, "currentDerivativeContext": derivative}], {"1m": 1})
        current = result["markets"][0]["frames"]["1m"]
        volume_law = current["technicalSuite"]["murphy"][-1]
        self.assertEqual(volume_law["status"], "partial")
        self.assertIsNone(volume_law["evidence"]["openInterest"])
        self.assertEqual(volume_law["evidence"]["currentDerivativeContext"], derivative)
        self.assertEqual(forward_reading(current)["technicalEvidence"]["currentDerivativeContext"], derivative)
        short_result = {"asOf": as_of, "markets": [{"venue": "fixture", "frames": {"1m": {"trend": "warming"}}}]}
        enrich(short_result, [{"frames": {"1m": rows[-2:]}}], {"1m": 1})
        short_laws = short_result["markets"][0]["frames"]["1m"]["technicalSuite"]["murphy"]
        self.assertEqual(short_laws[5]["status"], "warming")
        self.assertEqual(short_laws[7]["status"], "warming")
        self.assertEqual(short_laws[6]["evidence"]["RSI"]["status"], "warming")

    def test_forward_evidence_retains_actual_features_without_repeated_chart_history(self):
        rows, as_of = fixture()
        suite = analyze_frame(rows, 1, as_of)
        reading = {"close": rows[-1]["c"], "candidate": None, "technicalSuite": suite}
        compact = forward_reading(reading)
        self.assertNotIn("technicalSuite", compact)
        self.assertEqual(compact["close"], reading["close"])
        evidence = compact["technicalEvidence"]
        self.assertEqual(evidence["lastCandle"], suite["bars"][-1])
        self.assertEqual(evidence["patternValues"], {k:v["value"] for k,v in suite["patterns"].items()})
        self.assertFalse(evidence["orderAuthority"])
        self.assertLess(len(json.dumps(compact)), len(json.dumps(reading)))


if __name__ == "__main__": unittest.main()
