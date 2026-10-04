"""Exercise Alpaca stream timestamp parsing and nanosecond deltas."""

from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from stream_audit import audit, event_time_ns  # noqa: E402


class StreamAuditTimestampTests(unittest.TestCase):
    def test_accepts_variable_fractional_precision_and_offsets(self) -> None:
        # SOURCE: fixture strings exercise Alpaca's variable RFC3339 precision;
        # timestamps are synthetic and are not latency observations.
        five_digits = event_time_ns("2026-09-29T00:03:14.69303Z")
        nine_digits = event_time_ns("2026-09-29T00:03:14.693030001+00:00")
        self.assertEqual(nine_digits - five_digits, 1)

    def test_requires_explicit_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit timezone"):
            event_time_ns("2026-09-29T00:03:14.69303")

    def test_book_state_carries_across_capture_files_with_same_session(self) -> None:
        # SOURCE: synthetic stream frames verify UTC file rotation is not a
        # socket-session reset; sizes and prices are fixtures only.
        first = [
            {"T": "o", "S": "BTC/USD", "t": "2026-09-28T23:59:58.00000Z",
             "r": True, "b": [{"p": "99", "s": "1"}],
             "a": [{"p": "101", "s": "1"}]},
        ]
        second = [
            {"T": "o", "S": "BTC/USD", "t": "2026-09-29T00:00:01.00000Z",
             "b": [{"p": "99.5", "s": "1"}], "a": []},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            paths = [Path(temporary) / "day-1.jsonl", Path(temporary) / "day-2.jsonl"]
            for index, (path, events) in enumerate(zip(paths, (first, second)), start=1):
                path.write_text("\n".join(json.dumps({
                    "feed": "alpaca-us", "sessionId": "same-session",
                    "streamSequence": index, "receivedAtNs": index * 1_000_000_000,
                    "event": event,
                }) for event in events) + "\n", encoding="utf-8")
            result = audit(paths)
        self.assertEqual(result["events"]["sessions"], 1)
        self.assertEqual(result["full_book_resets"], 1)
        self.assertEqual(result["book_updates_before_reset"], 0)
        self.assertEqual(result["streamSequenceGaps"], 0)

    def test_legacy_capture_without_session_metadata_is_not_rejected(self) -> None:
        # SOURCE: synthetic old-format record exercises backward compatibility.
        event_time = "2026-09-29T00:03:14.69303Z"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.jsonl"
            record = {
                "feed": "alpaca-us",
                "receivedAtNs": event_time_ns(event_time) + 50_000_000,
                "event": {"T": "q", "S": "BTC/USD", "t": event_time,
                          "bp": 99, "ap": 100},
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            result = audit(path)
        self.assertEqual(result["events"]["eventsWithoutSessionId"], 1)
        self.assertEqual(result["events"]["eventsWithoutStreamSequence"], 1)
        self.assertAlmostEqual(
            result["event_to_receipt_seconds_by_type"]["q"]["median"], 0.05
        )


if __name__ == "__main__":
    unittest.main()
