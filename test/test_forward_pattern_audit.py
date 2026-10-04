"""Adversarial point-in-time fixtures, not market performance evidence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from forward_pattern_audit import instant, labels, observation, read_journal, report, utc


def record(start, observed=None, opening=100, close=101, code=100):
    # SOURCE: deterministic synthetic minute fixtures, never broker trades.
    if observed is None:
        observed = start + 61
    return {"venue": "fixture", "symbol": "TEST", "frame": "1m", "observedAt": utc(observed),
        "reading": {"status": "ready", "technicalEvidence": {"source": "synthetic",
            "lastCandle": {"t": utc(start), "o": opening, "h": max(opening, close) + 1,
                           "l": min(opening, close) - 1, "c": close, "v": 1},
            "patternValues": {"CDLENGULFING": code}}}}


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.start = instant("2026-10-04T18:00:00Z")

    def test_signal_close_cannot_be_used_as_entry(self):
        raw = [record(self.start, close=900), record(self.start + 60, opening=20, close=40),
               record(self.start + 120, opening=100, close=110)]
        rows = [observation(r) for r in raw]
        outcomes, _ = labels(rows, 1, self.start + 600)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["entryAt"], utc(self.start + 120))
        self.assertAlmostEqual(outcomes[0]["grossLongMoveBps"], 1000)

    def test_late_observation_cannot_retroactively_enter(self):
        rows = [observation(record(self.start, observed=self.start + 181)),
                observation(record(self.start + 120)), observation(record(self.start + 240))]
        outcomes, _ = labels(rows, 1, self.start + 600)
        self.assertEqual(next(r for r in outcomes if r["start"] == self.start)["entryAt"], utc(self.start + 240))

    def test_missing_middle_horizon_bar_and_boundary_are_rejected(self):
        rows = [observation(record(self.start + step * 60)) for step in (0, 2, 4)]
        outcomes, counts = labels(rows, 2, self.start + 600)
        self.assertEqual(outcomes, [])
        self.assertEqual(counts["missingFutureHorizonCandles"], 3)
        rows = [observation(record(self.start + step * 60)) for step in range(6)]
        outcomes, counts = labels(rows, 1, self.start + 180)
        self.assertGreater(counts.get("crossesChronologicalSplit", 0), 0)
        self.assertTrue(all(r["observed"] >= self.start + 180 for r in outcomes))

    def test_first_observation_cannot_be_revised_or_backfilled(self):
        early = record(self.start, code=None)
        late = record(self.start, observed=self.start + 300, close=500, code=100)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.jsonl"
            path.write_bytes((json.dumps(late) + "\n" + json.dumps(early) + "\n{unfinished").encode())
            rows, counts = read_journal(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["c"], 101)
        self.assertIsNone(rows[0]["patterns"]["CDLENGULFING"])
        self.assertEqual(counts["duplicates"], 1)
        self.assertEqual(counts["partialFinalLine"], 1)

    def test_unclosed_future_or_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError): observation(record(self.start, observed=self.start + 30))
        with self.assertRaises(ValueError): instant("2026-10-04T18:00:00")
        for bad in (0, -1, True, 1.5):
            with self.assertRaises(ValueError): labels([], bad, self.start)

    def test_controls_are_same_symbol_frame_and_fold_and_not_net_profit(self):
        rows = [observation(record(self.start + i * 60, code=-100 if i == 0 else 0)) for i in range(5)]
        other = [dict(row, symbol="OTHER", c=row["c"] * 2) for row in rows]
        result = report(rows + other, 1, self.start + 600)
        first = next(r for r in result["comparisons"] if r["symbol"] == "TEST")
        self.assertEqual(first["sameMarketFrameFoldBaseline"]["count"], 3)
        self.assertAlmostEqual(first["patternLabels"]["meanGrossMoveBps"], -100)
        self.assertFalse(result["orderAuthority"])
        self.assertIsNone(result["netPnl"])
        self.assertIsNone(result["winProbability"])
        json.dumps(result, allow_nan=False)


if __name__ == "__main__": unittest.main()
