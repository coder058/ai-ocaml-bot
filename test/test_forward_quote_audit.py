"""Causal quote-reference fixtures; no broker performance evidence."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
from decision_quote_capture import normalize, quote_time
from forward_quote_audit import reference, read_quotes, read_stream_quotes, report
from forward_pattern_audit import read_journal
from test_forward_pattern_audit import record, instant

# SOURCE: all times, prices and fees below are synthetic boundary fixtures.
START="2026-10-04T22:00:00Z"
SPLIT="2026-10-04T21:00:00Z"
ASOF="2026-10-05T01:00:00Z"

def quote(at=START, received=START, bid=99, ask=100, venue="Alpaca crypto", symbol="BTC/USD"):
    return normalize({"t":at,"bp":bid,"ap":ask,"bs":1,"as":1},datetime.fromisoformat(received.replace("Z","+00:00")),venue,symbol)

def frame(observed=START, entry=None, **updates):
    return {"status":"ready","venue":"Alpaca crypto","symbol":"BTC/USD","frame":"1m",
            "observedAtText":observed,"patterns":{"CDLENGULFING":100},
            "quoteReference":entry if entry is not None else quote(),**updates}

def audit(frames=None, exits=None, **updates):
    settings={"horizon_bars":1,"max_exit_lag_seconds":120,"split_at":SPLIT,"crypto_taker_bps":25,"as_of":ASOF}
    settings.update(updates)
    return report([frame()] if frames is None else frames,
        [reference(quote("2026-10-04T22:01:00Z","2026-10-04T22:01:01Z",bid=110,ask=111))] if exits is None else exits,**settings)

class QuoteAuditTests(unittest.TestCase):
    def test_archived_entry_requires_earlier_actual_read_as_well_as_original_receipt(self):
        entry={**quote(),"transport":"existing_archived_websocket","referenceCheckedAt":START}
        result=audit([frame(entry=entry)])
        self.assertEqual(result["labelCount"],1)
        self.assertEqual(result["entryTransportCounts"],{"existing_archived_websocket":1})
        late={**entry,"referenceCheckedAt":"2026-10-04T22:00:00.000000001Z"}
        self.assertEqual(audit([frame(entry=late)])["labelCount"],0)
        for bad in ({k:v for k,v in entry.items() if k!="referenceCheckedAt"},
                    {**entry,"referenceCheckedAt":"2026-10-04T21:59:59Z"}):
            self.assertEqual(audit([frame(entry=bad)])["labelCount"],0)

    def test_spread_and_received_asset_fee_scenario_are_explicit_not_pnl(self):
        result=audit()
        self.assertEqual(result["labelCount"],1)
        row=result["labels"][0]
        self.assertAlmostEqual(row["longQuoteReferenceMoveBps"],1000)
        self.assertAlmostEqual(row["modeledCryptoAfterFeeBps"],(1.1*.9975*.9975-1)*10000)
        self.assertEqual(row["holdingSeconds"],61)
        self.assertFalse(result["orderAuthority"])
        self.assertIsNone(result["winProbability"])
        self.assertIsNone(result["brokerPnl"])
        self.assertIn("meanModeledAfterFeeBps",result["summary"]["cryptoFeeScenario"])
        self.assertNotIn("meanGrossMoveBps",result["summary"]["cryptoFeeScenario"])
        json.dumps(result,allow_nan=False)

    def test_first_received_exit_is_used_instead_of_best_future_price(self):
        early=reference(quote("2026-10-04T22:01:00Z","2026-10-04T22:01:01Z",bid=90,ask=91))
        later=reference(quote("2026-10-04T22:01:05Z","2026-10-04T22:01:06Z",bid=120,ask=121))
        row=audit(exits=[later,early])["labels"][0]
        self.assertEqual(row["exitBidReference"],90)
        self.assertAlmostEqual(row["longQuoteReferenceMoveBps"],-1000)

    def test_entry_must_be_fresh_at_feature_observation_not_only_receipt(self):
        for entry in [None,quote("2026-10-04T21:59:54Z",START),
                      quote("2026-10-04T21:59:59Z","2026-10-04T21:59:59Z"),
                      quote(START,"2026-10-04T22:00:01Z"),
                      quote("2026-10-04T22:00:00.000000001Z",START)]:
            row=frame();row["quoteReference"]=entry
            if entry and entry["receivedAt"]=="2026-10-04T21:59:59Z":row["observedAtText"]="2026-10-04T22:00:05Z"
            result=audit([row])
            self.assertEqual(result["labelCount"],0)
            self.assertEqual(result["rejected"]["noFirstObservedFreshEntryQuote"],1)

    def test_future_receipts_delayed_exits_and_old_source_times_reject(self):
        for exits,asof in [([],ASOF),([reference(quote("2026-10-04T22:03:01Z","2026-10-04T22:03:01Z"))],ASOF),
                           ([reference(quote("2026-10-04T22:00:59.999999999Z","2026-10-04T22:01:01Z"))],ASOF),
                           ([reference(quote("2026-10-04T22:01:00Z","2026-10-04T22:01:01Z"))],"2026-10-04T22:01:00Z")]:
            result=audit(exits=exits,as_of=asof)
            self.assertEqual(result["labelCount"],0)
            self.assertEqual(result["rejected"]["noTimelyFreshExitReference"],1)

    def test_split_purges_outcome_receipt_even_when_quote_time_precedes_split(self):
        result=audit(split_at="2026-10-04T22:01:00.500Z")
        self.assertEqual(result["labelCount"],0)
        self.assertEqual(result["rejected"]["crossesChronologicalSplit"],1)
        result=audit(split_at=START)
        self.assertEqual(result["foldCounts"],{"validation":1})

    def test_scope_feed_authority_and_invalid_prices_cannot_be_salvaged(self):
        for changes in [{"venue":"Hyperliquid HIP-3"},{"symbol":"DOGE/USD"},{"symbol":"AAPL","venue":"Alpaca equities"},
                        {"feed":"sip"},{"orderAuthority":True},{"winProbability":.9},{"bid":101},{"bidSizeRaw":0},
                        {"receivedAt":"2026-10-04T22:00:00"}]:
            with self.assertRaises((ValueError,KeyError,TypeError)):reference({**quote(),**changes})
        row=frame(entry=quote(venue="Alpaca equities",symbol="QQQ"))
        self.assertEqual(audit([row])["labelCount"],0)

    def test_equity_net_costs_unknown_and_negative_codes_are_not_shorts(self):
        entry=quote(venue="Alpaca equities",symbol="QQQ")
        row=frame(entry=entry,venue="Alpaca equities",symbol="QQQ",patterns={"CDLENGULFING":-100})
        exit_quote=reference(quote("2026-10-04T22:01:00Z","2026-10-04T22:01:01Z",bid=110,ask=111,venue="Alpaca equities",symbol="QQQ"))
        result=audit([row],exits=[exit_quote])
        self.assertIsNone(result["labels"][0]["modeledCryptoAfterFeeBps"])
        self.assertIsNone(result["summary"]["cryptoFeeScenario"])
        self.assertEqual(result["comparisons"][0]["signedCode"],"negative_code")
        self.assertGreater(result["labels"][0]["longQuoteReferenceMoveBps"],0)

    def test_first_observed_features_do_not_gain_later_quotes(self):
        start=instant(START)-60
        early=record(start,observed=start+60)
        early.update(venue="Alpaca crypto",symbol="BTC/USD")
        late=copy.deepcopy(early);late["observedAt"]="2026-10-04T22:00:02Z";late["reading"]["quoteReference"]=quote()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"features.jsonl"
            path.write_text(json.dumps(late)+"\n"+json.dumps(early)+"\n")
            frames,metadata=read_journal(path)
        self.assertEqual(metadata["duplicates"],1)
        self.assertIsNone(frames[0]["quoteReference"])
        self.assertEqual(audit(frames)["labelCount"],0)

    def test_frozen_quote_prefix_reports_hash_and_ignores_unfinished_append(self):
        raw=(json.dumps(quote())+"\n"+json.dumps({**quote(),"status":"stale"})+"\n{unfinished").encode()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"quotes.jsonl";path.write_bytes(raw)
            rows,metadata=read_quotes(path)
        self.assertEqual(len(rows),1)
        self.assertEqual(metadata["unusableReferences"],1)
        self.assertEqual(metadata["partialFinalLine"],1)
        self.assertEqual(metadata["inputBytes"],len(raw))
        self.assertEqual(metadata["sha256"],hashlib.sha256(raw).hexdigest())

    def test_explicit_parameter_boundaries_and_missing_features(self):
        for settings in [{"horizon_bars":True},{"horizon_bars":0},{"max_exit_lag_seconds":True},
                         {"max_exit_lag_seconds":-1},{"crypto_taker_bps":float("nan")},{"crypto_taker_bps":True},
                         {"crypto_taker_bps":10000},{"split_at":"2026-10-04T21:00:00"}]:
            with self.assertRaises(ValueError):audit(**settings)
        self.assertEqual(audit([frame(patterns={"CDLENGULFING":None})])["rejected"],{"noFirstObservedPatternValues":1})
        self.assertEqual(quote_time("2026-10-04T22:00:00.000000001Z")-quote_time(START),__import__("decimal").Decimal(".000000001"))

    def test_existing_stream_receipt_nanoseconds_are_exact_and_scope_is_not_expanded(self):
        # SOURCE: synthetic stream clock, events and prices, not market data.
        ns=int(quote_time(START)*1_000_000_000)+123456789
        event={"T":"q","S":"BTC/USD","t":"2026-10-04T22:00:00.123456788Z","bp":99,"ap":100,"bs":1,"as":1}
        good={"feed":"alpaca-us","receivedAtNs":ns,"event":event}
        bad=[{**good,"feed":"other"},{**good,"event":{**event,"S":"DOGE/USD"}},
             {**good,"receivedAtNs":True},{**good,"event":{**event,"t":"2026-10-04T22:00:00.123456790Z"}}]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"2026-10-04.jsonl"
            raw=("\n".join(json.dumps(v) for v in [good,*bad,{**good,"event":{**event,"T":"b"}}])+"\n{unfinished").encode()
            path.write_bytes(raw);rows,metadata=read_stream_quotes([path])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["receivedAt"],"2026-10-04T22:00:00.123456789Z")
        self.assertEqual(rows[0]["received"]-rows[0]["at"],__import__("decimal").Decimal(".000000001"))
        self.assertEqual(metadata["unusableReferences"],4)
        self.assertEqual(metadata["nonQuoteEvents"],1)
        self.assertEqual(metadata["partialFinalLine"],1)
        self.assertEqual(metadata["sources"][0]["sha256"],hashlib.sha256(raw).hexdigest())

    def test_stream_outcome_does_not_repair_missing_original_entry(self):
        entry=frame();entry["quoteReference"]=None
        self.assertEqual(audit([entry])["labelCount"],0)

    def test_frozen_policy_subset_requires_original_exact_policy_and_long_candidate(self):
        rows=[frame(policy="trend_candle_confluence_v1",candidate="long"),
              frame(policy="trend_candle_confluence_v1",candidate="short"),frame(candidate="long"),
              frame(policy="another_policy",candidate="long")]
        result=audit(rows);subset=result["frozenPolicySubset"]
        self.assertEqual(result["labelCount"],4)
        self.assertEqual(subset["referenceCount"],1)
        self.assertEqual(subset["foldCounts"],{"validation":1})
        self.assertEqual(subset["matchedBaselines"][0]["references"]["longQuoteReferences"]["count"],4)
        self.assertFalse(subset["orderAuthority"]);self.assertIsNone(subset["executionModel"])

if __name__=="__main__":unittest.main()
