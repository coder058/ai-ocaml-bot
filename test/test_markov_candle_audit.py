"""Boundary checks for the read-only candle transition audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from markov_candle_audit import observations  # noqa: E402


def bar(timestamp: str, close: float) -> dict:
    return {"t": timestamp, "o": close, "h": close, "l": close, "c": close}


class CandleTransitionTests(unittest.TestCase):
    def test_gap_never_receives_a_next_bar_label(self) -> None:
        document = {
            "symbol": "BTC/USD", "timeframe": "5Min",
            "bars": [
                bar("2026-06-30T23:50:00Z", 100),
                bar("2026-06-30T23:55:00Z", 101),
                bar("2026-07-01T00:00:00Z", 102),
                bar("2026-07-01T00:10:00Z", 200),
                bar("2026-07-01T00:15:00Z", 201),
                bar("2026-07-01T00:20:00Z", 202),
            ],
        }
        rows = observations(document)
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0][3])
        self.assertTrue(rows[1][3])
        self.assertAlmostEqual(rows[0][2], (102 / 101 - 1) * 10_000)
        self.assertAlmostEqual(rows[1][2], (202 / 201 - 1) * 10_000)

    def test_duplicate_time_is_rejected(self) -> None:
        document = {
            "symbol": "BTC/USD", "timeframe": "5Min",
            "bars": [bar("2026-07-01T00:00:00Z", 100)] * 2,
        }
        with self.assertRaisesRegex(ValueError, "duplicated"):
            observations(document)


if __name__ == "__main__":
    unittest.main()
