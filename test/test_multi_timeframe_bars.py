import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from multi_timeframe_bars import aggregate, closed_minutes, closed_minutes_many  # noqa: E402
from multi_timeframe_shadow import describe  # noqa: E402


class MultiTimeframeBarsTest(unittest.TestCase):
    def test_gap_prevents_aggregation_and_late_revision_is_not_backfilled(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "capture.jsonl"
            rows = []
            for minute in (0, 1, 2, 4):
                event = {"T": "b", "S": "ETH/USD", "t": f"2026-09-27T23:{minute:02d}:00Z",
                         "o": 100, "h": 101, "l": 99, "c": 100, "v": 1}
                rows.append({"receivedAtNs": int(datetime(2026, 9, 27, 23, minute + 1,
                                                          tzinfo=timezone.utc).timestamp() * 1e9),
                             "event": event})
            revision = {"T": "u", "S": "ETH/USD", "t": "2026-09-27T23:00:00Z",
                        "o": 100, "h": 103, "l": 99, "c": 102, "v": 2}
            rows.append({"receivedAtNs": int(datetime(2026, 9, 27, 23, 6,
                                                      tzinfo=timezone.utc).timestamp() * 1e9),
                         "event": revision})
            capture.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            early = closed_minutes(capture, "ETH/USD", datetime(2026, 9, 27, 23, 5,
                                                                 tzinfo=timezone.utc))
            self.assertEqual(len(early), 4)
            self.assertEqual(early[min(early)]["c"], 100)
            self.assertEqual(aggregate(early, 5), [])
            self.assertEqual(describe(aggregate(early, 5), 5,
                                      datetime(2026, 9, 27, 23, 5,
                                               tzinfo=timezone.utc))["trend"], None)
            later = closed_minutes(capture, "ETH/USD", datetime(2026, 9, 27, 23, 7,
                                                                 tzinfo=timezone.utc))
            self.assertEqual(later[min(later)]["c"], 102)
            both = closed_minutes_many([capture], ("BTC/USD", "ETH/USD"),
                                       datetime(2026, 9, 27, 23, 7,
                                                tzinfo=timezone.utc))
            self.assertEqual(both["BTC/USD"], {})
            self.assertEqual(len(both["ETH/USD"]), 4)


if __name__ == "__main__":
    unittest.main()
