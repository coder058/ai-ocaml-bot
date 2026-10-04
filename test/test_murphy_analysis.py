"""Synthetic geometry and library parity, not profitability evidence."""
import sys
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import talib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from murphy_analysis import CANDLES, analyze_frame, contiguous, enrich, geometry, pivots, forward_reading


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
