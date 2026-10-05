"""Real file/clock failure fixtures, not trades or strategy performance."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"research"))
from decision_quote_capture import normalize_at
from stock_quote_audit import cohort_report
from stock_session_opportunities import METHOD, PROTOCOL_SHA256, prepare, protocol, read_journal

# SOURCE: synthetic clocks/prices create held-Friday-bar/Monday-session cases.
OBSERVED = "2026-10-05T13:30:21.000002Z"
BAR = {"t": "2026-10-02T16:00:00Z", "o": 100, "h": 101, "l": 99, "c": 100, "v": 1}


class SessionOpportunityTests(unittest.TestCase):
    def setUp(self):
        self.base, self.spec, self.digest = protocol()
        quote = normalize_at({"t": "2026-10-05T13:30:20Z", "bp": 99, "ap": 100, "bs": 1, "as": 1},
                             "2026-10-05T13:30:21Z", "Alpaca equities", "QQQ")
        self.reading = {"lastBarStart": BAR["t"], "status": "ready", "candidate": None,
                        "quoteReference": quote, "technicalSuite": {"bars": [BAR], "patterns": {}}}
        self.result = {"retrievedAt": OBSERVED, "asOf": "2026-10-05T13:30:00Z",
                       "engineSha256": self.base["engineSha256"], "policy": self.base["policy"],
                       "markets": [{"venue": "Alpaca equities", "symbol": "QQQ",
                                    "frames": {"4h": self.reading}}]}
        self.clock = {"is_open": True, "timestamp": "2026-10-05T13:30:00.000001Z"}

    def prepared(self, seen=None):
        return prepare(self.result, self.clock, seen or {}, self.base, self.spec, self.digest)

    def test_actual_pinned_protocol_cannot_be_rewritten_or_trusted_by_filename(self):
        self.assertEqual(self.digest, PROTOCOL_SHA256)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"changed.json"; p.write_text(json.dumps(self.spec)+"\n")
            with self.assertRaises(ValueError): protocol(protocol_path=p)

    def test_held_closed_four_hour_bar_records_actual_new_session_and_no_candidate_is_not_skipped(self):
        records, updates = self.prepared()
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r["selection"], METHOD)
        self.assertEqual(r["sessionDate"], "2026-10-05")
        self.assertEqual(r["reading"]["lastBarStart"], BAR["t"])
        self.assertEqual(r["observedAt"], OBSERVED)
        self.assertIsNone(r["reading"]["candidate"])
        self.assertFalse(r["orderAuthority"]); self.assertIsNone(r["winProbability"])
        self.assertEqual(updates, {"2026-10-05|QQQ|4h": BAR["t"]})

    def test_original_first_reading_cannot_gain_later_candidate_or_revised_quote(self):
        records, seen = self.prepared()
        self.reading.update(candidate="long", status="candidate", quoteReference=None)
        self.assertEqual(self.prepared(seen), ([], {}))
        self.assertIsNone(records[0]["reading"]["candidate"])
        self.assertIsNotNone(records[0]["reading"]["quoteReference"])

    def test_closed_session_and_outside_frozen_dates_produce_no_records(self):
        for observed in ("2026-10-05T13:29:59Z", "2026-10-05T20:00:00Z", "2026-10-07T13:30:21Z"):
            self.result["retrievedAt"] = observed
            self.assertEqual(self.prepared(), ([], {}))
        self.result["retrievedAt"] = OBSERVED; self.clock["is_open"] = False
        self.assertEqual(self.prepared(), ([], {}))

    def test_future_nanosecond_clock_changed_engine_and_unclosed_bar_fail_without_cache_mutation(self):
        seen = {}
        self.clock["timestamp"] = "2026-10-05T13:30:21.000002001Z"
        with self.assertRaises(ValueError): self.prepared(seen)
        self.assertEqual(seen, {})
        self.clock["timestamp"] = "2026-10-05T13:29:59Z"
        with self.assertRaises(ValueError): self.prepared()
        self.clock["timestamp"] = "2026-10-05T13:30:00Z"
        self.result["engineSha256"] = "b"*64
        with self.assertRaises(ValueError): self.prepared()
        self.result["engineSha256"] = self.base["engineSha256"]
        future = {**BAR, "t": "2026-10-05T12:00:00Z"}
        self.reading.update(lastBarStart=future["t"], technicalSuite={"bars": [future], "patterns": {}})
        with self.assertRaises(ValueError): self.prepared()

    def test_next_session_has_new_identity_but_same_session_older_bar_does_not(self):
        _, seen = self.prepared()
        self.result.update(retrievedAt="2026-10-06T13:30:21Z", asOf="2026-10-06T13:30:00Z")
        self.clock["timestamp"] = "2026-10-06T13:30:00Z"
        records, updates = self.prepared(seen)
        self.assertEqual(records[0]["sessionDate"], "2026-10-06")
        self.assertIn("2026-10-06|QQQ|4h", updates)

    def test_protected_stock_and_crypto_never_enter_session_journal(self):
        for venue, symbol in (("Alpaca equities", "AAPL"), ("Alpaca crypto", "BTC/USD"), ("Hyperliquid HIP-3", "xyz:EUR")):
            self.result["markets"][0].update(venue=venue, symbol=symbol)
            self.assertEqual(self.prepared(), ([], {}))

    def test_file_reader_preserves_first_immutable_identity_and_rejects_conflicting_revisions(self):
        r = self.prepared()[0][0]
        changed = copy.deepcopy(r); changed["reading"]["candidate"] = "long"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"journal.jsonl"
            p.write_bytes(b"".join(json.dumps(x).encode()+b"\n" for x in [r, r]))
            rows, metadata = read_journal(p, self.base, self.digest)
            self.assertEqual(len(rows), 1); self.assertEqual(metadata["identicalDuplicates"], 1)
            result = cohort_report(rows, [], self.base, "2026-10-05T18:00:00Z")
            slot = next(x for x in result["coverage"] if x["symbol"] == "QQQ" and x["frame"] == "4h")
            self.assertEqual(slot["firstObservedCandles"], 1)
            self.assertNotIn("horizonOutsideRegularSession", result["protocolRejected"])
            self.assertEqual(result["labelCount"], 0); self.assertFalse(result["orderAuthority"])
            with p.open("ab") as h: h.write(json.dumps(changed).encode()+b"\n"+b"{partial")
            rows, metadata = read_journal(p, self.base, self.digest)
            self.assertEqual(rows, []); self.assertEqual(metadata["conflictingOpportunityIdentity"], 1)
            self.assertEqual(metadata["partialFinalLine"], 1)
            rows, metadata = read_journal(Path(d)/"absent", self.base, self.digest)
            self.assertEqual(rows, []); self.assertEqual(metadata["status"], "absent")

    def test_file_reader_rejects_submicrosecond_native_grid_and_future_clock_even_if_float_rounds(self):
        record=self.prepared()[0][0]
        clock=copy.deepcopy(record);clock['brokerClockAt']='2026-10-05T13:30:21.000002001Z'
        grid=copy.deepcopy(record);grid['reading']['lastBarStart']='2026-10-02T16:00:00.000000001Z'
        grid['reading']['technicalEvidence']['lastCandle']['t']=grid['reading']['lastBarStart']
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.jsonl';p.write_bytes(b''.join(json.dumps(r).encode()+b'\n' for r in [clock,grid]))
            rows,meta=read_journal(p,self.base,self.digest)
            self.assertEqual(rows,[]);self.assertEqual(meta['invalidRecords'],2)


if __name__ == "__main__":
    unittest.main()
