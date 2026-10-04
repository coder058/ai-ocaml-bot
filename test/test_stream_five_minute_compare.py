"""Ensure stream comparison refuses to fill a missing minute."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from stream_five_minute_compare import compare  # noqa: E402


class StreamCompareTests(unittest.TestCase):
    def test_only_complete_groups_are_compared(self) -> None:
        # SOURCE: synthetic equal OHLC values test five-slot aggregation.
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "bars.jsonl"
            events = [{"event": {"T": "b", "S": "BTC/USD",
                                 "t": f"2026-09-27T00:{minute:02d}:00Z", "c": 100}}
                      for minute in (0, 1, 2, 3, 4, 5, 6, 8, 9)]
            capture.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
            rest = {"symbol": "BTC/USD", "timeframe": "5Min", "bars": [
                {"t": "2026-09-27T00:00:00Z", "c": 100},
                {"t": "2026-09-27T00:05:00Z", "c": 100}]}
            result = compare(capture, rest)
        self.assertEqual(result["completeStreamGroups"], 1)
        self.assertEqual(result["comparedGroups"], 1)
        self.assertEqual(result["medianAbsoluteCloseDifferenceBps"], 0)


if __name__ == "__main__":
    unittest.main()
