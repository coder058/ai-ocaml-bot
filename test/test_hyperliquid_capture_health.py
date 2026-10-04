"""The live gzip member is readable but lacks a trailer until rotation."""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from hyperliquid_capture_health import health  # noqa: E402


class HyperliquidCaptureHealthTests(unittest.TestCase):
    def test_counts_flushed_prefix_and_marks_open_gzip_as_incomplete(self) -> None:
        # SOURCE: synthetic single BBO envelope exercises the active-file read path.
        row = {"receivedAtNs": 1, "sessionId": "session", "sequence": 1,
               "message": {"channel": "bbo", "data": {"coin": "xyz:EUR"}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hour.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as capture:
                capture.write(json.dumps(row) + "\n")
            path.write_bytes(path.read_bytes()[:-8])

            result = health([path])

        self.assertEqual(result["bboCounts"], {"xyz:EUR": 1})
        self.assertEqual(result["corruptLines"], 0)
        self.assertEqual(len(result["incompleteGzipFiles"]), 1)


if __name__ == "__main__":
    unittest.main()
