"""Real temporary files verify immutable research attempts, not trade outcomes."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"deploy"))
from retain_stock_audit import retain

# SOURCE: synthetic dated report identifiers; no market numbers/results.
REPORT = {"generatedAt":"2026-10-04T20:00:00.000001Z", "manifestSha256":"synthetic",
          "orderAuthority":False,"winProbability":None,"brokerPnl":None}


class RetentionTests(unittest.TestCase):
    def test_exact_bytes_are_retained_idempotently_and_conflicts_cannot_replace_an_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"report.json";raw=json.dumps(REPORT).encode()+b"\n";path.write_bytes(raw)
            target,digest=retain(path)
            self.assertEqual(target.name,"report-20261004T200000000001Z.json")
            self.assertEqual(target.read_bytes(),raw);self.assertEqual(digest,hashlib.sha256(raw).hexdigest())
            self.assertEqual(retain(path),(target,digest))
            path.write_bytes(raw+b"\n")
            with self.assertRaises(ValueError):retain(path)
            self.assertEqual(target.read_bytes(),raw)
            self.assertEqual(list(Path(directory).glob('.retain-*')),[])

    def test_invalid_future_naive_or_authoritative_report_cannot_make_a_dated_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"report.json"
            for change in ({"generatedAt":"2099-01-01T00:00:00Z"},{"generatedAt":"2026-10-04T20:00:00"},
                           {"orderAuthority":True},{"winProbability":.9},{"brokerPnl":0}):
                path.write_text(json.dumps({**REPORT,**change}))
                with self.assertRaises(ValueError):retain(path)
            self.assertEqual([p.name for p in Path(directory).iterdir()],["report.json"])


if __name__ == "__main__":unittest.main()
