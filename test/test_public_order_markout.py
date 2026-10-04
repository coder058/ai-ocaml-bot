"""Verify date-scoped markout cannot mutate the full signed snapshot."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from public_order_markout import snapshot_for_fill_date  # noqa: E402


class PublicOrderMarkoutTests(unittest.TestCase):
    def test_fill_date_filter_is_utc_prefix_and_preserves_source_snapshot(self) -> None:
        # SOURCE: synthetic UTC timestamps test date scoping only.
        snapshot = {"telemetry": {"fills": [
            {"transactionTime": "2026-09-28T23:59:59Z", "id": "old"},
            {"transactionTime": "2026-09-29T00:00:00Z", "id": "today"},
            {"transactionTime": "2026-09-30T00:00:00Z", "id": "future"},
        ]}}
        scoped, count = snapshot_for_fill_date(snapshot, "2026-09-29")
        self.assertEqual(count, 1)
        self.assertEqual([row["id"] for row in scoped["telemetry"]["fills"]], ["today"])
        self.assertEqual(len(snapshot["telemetry"]["fills"]), 3)

    def test_invalid_fill_date_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            snapshot_for_fill_date({"fills": []}, "not-a-date")


if __name__ == "__main__":
    unittest.main()
