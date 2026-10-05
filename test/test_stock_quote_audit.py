"""Prospective protocol failure tests; synthetic quotes are not paper fills."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from decision_quote_capture import normalize_at, quote_time
from forward_quote_audit import reference
from stock_quote_audit import cohort_report, load_manifest, read_iex_quotes, validate_manifest

# SOURCE: synthetic timestamps/prices/scope identify causal boundary cases.
ENGINE = "a" * 64
MANIFEST = {"schema": "stock_quote_cohort_v1", "venue": "Alpaca equities", "feed": "iex",
            "policy": "trend_candle_confluence_v1", "side": "long", "orderAuthority": False,
            "winProbability": None, "frames": ["1m", "5m", "30m", "1h", "4h"],
            "symbols": ["QQQ", "NVDA"], "streamSymbols": ["QQQ"], "engineSha256": ENGINE,
            "createdAt": "2026-10-05T06:00:00Z", "calendarReceivedAt": "2026-10-05T05:59:00Z",
            "horizonBars": 1, "maxExitLagSeconds": 120,
            "sessions": [{"date": "2026-10-05", "open": "09:30", "close": "16:00", "fold": "discovery"},
                         {"date": "2026-10-06", "open": "09:30", "close": "16:00", "fold": "validation"}]}


def quote(at, bid=99, ask=100, received=None, symbol="QQQ"):
    return normalize_at({"t": at, "bp": bid, "ap": ask, "bs": 1, "as": 1},
                        received or at, "Alpaca equities", symbol)


def frame(at="2026-10-05T13:31:00Z", **updates):
    return {"venue": "Alpaca equities", "symbol": "QQQ", "frame": "1m", "observedAtText": at,
            "quoteReference": quote(at), "policy": "trend_candle_confluence_v1", "candidate": "long",
            "engineSha256": ENGINE, "status": "candidate", "patterns": {"CDLENGULFING": 100}, **updates}


class StockQuoteAuditTests(unittest.TestCase):
    def test_frozen_calendar_requires_actual_receipt_before_future_sessions_and_correct_folds(self):
        windows = validate_manifest(MANIFEST)
        self.assertEqual(windows[0]["open"], quote_time("2026-10-05T13:30:00Z"))
        self.assertEqual(windows[-1]["close"], quote_time("2026-10-06T20:00:00Z"))
        for updates in ({"createdAt": "2026-10-05T13:30:00Z"},
                        {"calendarReceivedAt": "2026-10-05T06:00:00.000000001Z"},
                        {"symbols": ["AAPL"]}, {"streamSymbols": ["AAPL"]}, {"orderAuthority": True},
                        {"winProbability": .9}, {"horizonBars": True}, {"frames": ["1m"]},
                        {"engineSha256": None}, {"sessions": list(reversed(MANIFEST["sessions"]))}):
            with self.assertRaises((ValueError, TypeError)):
                validate_manifest({**MANIFEST, **updates})

    def test_calendar_early_close_and_winter_offset_are_not_fixed_utc_or_six_hour_assumptions(self):
        manifest = {**MANIFEST, "createdAt": "2026-11-26T06:00:00Z", "calendarReceivedAt": "2026-11-26T05:59:00Z",
                    "sessions": [{"date": "2026-11-27", "open": "09:30", "close": "13:00", "fold": "discovery"},
                                 {"date": "2026-11-30", "open": "09:30", "close": "16:00", "fold": "validation"}]}
        windows = validate_manifest(manifest)
        self.assertEqual(windows[0]["open"], quote_time("2026-11-27T14:30:00Z"))
        self.assertEqual(windows[0]["close"], quote_time("2026-11-27T18:00:00Z"))

    def test_pinned_manifest_bytes_cannot_change_for_better_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            raw = json.dumps(MANIFEST).encode(); path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            self.assertEqual(load_manifest(path, digest)[0], MANIFEST)
            path.write_bytes(raw + b"\n")
            with self.assertRaises(ValueError): load_manifest(path, digest)

    def test_before_open_is_empty_and_every_slot_remains_visible(self):
        result = cohort_report([frame()], [], MANIFEST, "2026-10-05T07:00:00Z")
        self.assertEqual(result["sessionState"], "awaiting_first_session")
        self.assertEqual(len(result["coverage"]), 10)
        self.assertEqual(result["labelCount"], 0)
        self.assertEqual(result["protocolRejected"], {"outsideActualSessionOrFuture": 1})
        self.assertFalse(result["orderAuthority"])
        self.assertIsNone(result["winProbability"]); self.assertIsNone(result["brokerPnl"])
        self.assertIsNone(result["equityNetCosts"]); self.assertIsNone(result["executionModel"])

    def test_chronological_sources_and_first_receipt_control_both_folds_without_crypto_fee_claim(self):
        first = frame()
        second = frame("2026-10-06T13:31:00Z")
        quotes = [reference(quote("2026-10-05T13:32:00Z", bid=98, ask=99)),
                  reference(quote("2026-10-05T13:32:01Z", bid=110, ask=111)),
                  reference(quote("2026-10-06T13:32:00Z", bid=101, ask=102))]
        result = cohort_report([first, second], quotes, MANIFEST, "2026-10-06T20:00:00Z")
        self.assertEqual(result["foldCounts"], {"discovery": 1, "validation": 1})
        self.assertEqual(result["labels"][0]["exitBidReference"], 98)
        self.assertEqual(result["frozenPolicySubset"]["referenceCount"], 2)
        self.assertIsNone(result["cryptoTakerBpsScenario"])
        self.assertIsNone(result["summary"]["cryptoFeeScenario"])
        self.assertEqual(result["sessionState"], "complete")

    def test_missing_or_changed_frozen_producer_and_preopen_entry_cannot_be_repaired(self):
        rows = [frame(engineSha256=None), frame(engineSha256="b"*64),
                frame(policy="chosen_after_results"),
                frame(quoteReference=quote("2026-10-05T13:29:59Z", received="2026-10-05T13:30:00Z"))]
        result = cohort_report(rows, [], MANIFEST, "2026-10-05T14:00:00Z")
        self.assertEqual(result["labelCount"], 0)
        self.assertEqual(result["protocolRejected"]["unverifiedFrozenProducer"], 3)
        self.assertEqual(result["protocolRejected"]["noOriginalSessionEntryQuote"], 1)
        self.assertEqual(result["coverage"][0]["firstObservedCandles"], 4)

    def test_close_and_overnight_gaps_do_not_gain_next_session_exits_or_missing_four_hour_labels(self):
        rows = [frame("2026-10-05T19:59:00Z"), frame("2026-10-05T19:58:00Z"),
                frame("2026-10-05T16:00:00Z", frame="4h"),
                frame("2026-10-05T20:00:00Z"), frame(symbol="AAPL"),
                frame(venue="Alpaca crypto", symbol="BTC/USD")]
        future = reference(quote("2026-10-06T13:30:00Z"))
        result = cohort_report(rows, [future], MANIFEST, "2026-10-06T14:00:00Z")
        self.assertEqual(result["labelCount"], 0)
        self.assertEqual(result["protocolRejected"]["horizonOutsideRegularSession"], 2)
        self.assertEqual(result["protocolRejected"]["outsideStockScope"], 2)
        self.assertEqual(result["protocolRejected"]["outsideActualSessionOrFuture"], 1)
        self.assertEqual(result["rejected"]["noTimelyFreshExitReference"], 1)

    def test_actual_stock_archive_schema_keeps_nanoseconds_and_rejects_crypto_conflicts_and_partial_tails(self):
        # SOURCE: synthetic received nanoseconds and sequence identify exact rows.
        base = {"event": {"T": "q", "S": "QQQ", "t": "2026-10-05T13:32:00.000000001Z",
                          "bp": 99, "ap": 100, "bs": 1, "as": 1},
                "receivedAtNs": int(quote_time("2026-10-05T13:32:00Z"))*1_000_000_000+2,
                "session": "synthetic-session", "sequence": 1}
        conflict = copy.deepcopy(base); conflict["event"]["bp"] = 98
        other = copy.deepcopy(base); other["event"]["S"] = "NVDA"
        other["event"]["t"] = "2026-10-05T13:32:01.000000001Z"; other["receivedAtNs"] += 1_000_000_000
        crypto = {**other, "feed": "alpaca-us"}
        invalid = {**other, "receivedAtNs": True}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stock.jsonl"
            rows = [base, base, conflict, other, crypto, invalid]
            path.write_bytes(b"".join(json.dumps(row).encode()+b"\n" for row in rows)+b"{unfinished")
            quotes, evidence = read_iex_quotes([path, Path(directory)/"absent.jsonl"], {"QQQ", "NVDA"})
        self.assertEqual(len(quotes), 1); self.assertEqual(quotes[0]["symbol"], "NVDA")
        self.assertEqual(quotes[0]["receivedAt"], "2026-10-05T13:32:01.000000002Z")
        self.assertEqual(evidence["conflictingReceiptIdentities"], 1)
        self.assertEqual(evidence["identicalReceiptDuplicates"], 1)
        self.assertEqual(evidence["unusableReferences"], 2)
        self.assertEqual(evidence["partialFinalLine"], 1)
        self.assertEqual(evidence["sources"][1]["status"], "absent")

    def test_bounded_archive_keeps_first_due_reception_and_conflicting_or_decreasing_clock_blocks_instrument(self):
        def row(at, bid):
            return {"event":{"T":"q","S":"QQQ","t":at,"bp":bid,"ap":bid+1,"bs":1,"as":1},
                    "receivedAtNs":int(quote_time(at)*1_000_000_000),"session":"synthetic","sequence":1}
        rows=[row("2026-10-05T13:31:59Z",98),row("2026-10-05T13:32:00Z",99),row("2026-10-05T13:32:01Z",109)]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"quotes.jsonl"
            def run(values):
                path.write_text("".join(json.dumps(r)+"\n" for r in values))
                return read_iex_quotes([path],{"QQQ"},{"QQQ":[quote_time("2026-10-05T13:32:00Z")]},120)
            quotes, evidence=run(rows)
            self.assertEqual(len(quotes),1);self.assertEqual(quotes[0]["bid"],99)
            self.assertEqual(evidence["selection"],"first_frozen_horizon_receptions")
            for extra in (row("2026-10-05T13:32:01Z",110),row("2026-10-05T13:32:00Z",99)):
                quotes, evidence=run(rows+[extra])
                self.assertEqual(quotes,[]);self.assertEqual(evidence["blockedInstruments"],["QQQ"])


if __name__ == "__main__":
    unittest.main()
