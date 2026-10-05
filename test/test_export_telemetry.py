"""Decision history must join a broker order by its encoded quote timestamp."""

from __future__ import annotations

import sys
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))

from export_telemetry import (  # noqa: E402
    broker_fills,
    broker_crypto_fees,
    broker_orders,
    decision_history,
    market_research_state,
    public_journal,
    public_positions,
    multi_order_evidence,
    stock_order_evidence,
    operational_snapshot,
    quote_audit_summary,
    stock_quote_audit_summary,
    service_state,
)


class DecisionHistoryTests(unittest.TestCase):
    def test_native_input_projection_retains_hashes_without_private_files_or_inventing_old_proof(self):
        import hashlib
        from export_telemetry import native_input_evidence
        # SOURCE: synthetic deterministic SHA-256 values, no actual order claim.
        sha=hashlib.sha256(b"synthetic input").hexdigest()
        proof={"schema":"native_closed_frame_input_v1","inputSha256":sha,"engineSha256":sha,
            "technicalAnalysisSha256":sha,"analysisAsOf":"2026-10-05T13:31:00Z",
            "nativeInputArchive":"retained","orderAuthority":False,
            "privateFile":"/private/state/secret.json","secret":"never export"}
        projected=native_input_evidence({"dataEvidence":proof})
        self.assertEqual(projected["input_sha256"],sha)
        self.assertEqual(projected["native_input_archive"],"retained")
        self.assertNotIn("private",json.dumps(projected)); self.assertNotIn("secret",json.dumps(projected))
        self.assertEqual(native_input_evidence({}),{})
        self.assertEqual(native_input_evidence({"dataEvidence":{**proof,"inputSha256":"fake"}}),{})
        verified={"verified":True,"orderAuthority":False,"inputSha256":sha,"engineSha256":sha,
            "analysisAsOf":proof['analysisAsOf'],"verifiedAt":"2026-10-05T13:31:02Z","seconds":0.05}
        with patch('export_telemetry.datetime') as clock:
            clock.fromisoformat.side_effect=datetime.fromisoformat
            clock.now.return_value=datetime(2026,10,5,13,32,tzinfo=timezone.utc)
            value=native_input_evidence({"dataEvidence":proof},verified)
            self.assertTrue(value['native_input_verified'])
            for change in ({'inputSha256':'wrong'},{'seconds':True},{'verifiedAt':'private'},
                           {'verifiedAt':'2099-01-01T00:00:00Z'},{'verified':False}):
                value=native_input_evidence({'dataEvidence':proof},{**verified,**change})
                self.assertNotIn('native_input_verified',value)

    def test_separate_session_protocol_is_pinned_and_exposes_only_checked_per_frame_counts(self):
        import hashlib
        from datetime import timedelta
        root=Path(__file__).resolve().parents[1]/"research/cohorts"
        bp=root/"stock-20261005-06.json"; mp=root/"stock-session-opportunities-20261005-06.json"
        base=json.loads(bp.read_bytes()); spec=json.loads(mp.read_bytes()); digest=hashlib.sha256(mp.read_bytes()).hexdigest()
        # SOURCE: synthetic report one second after the actual protocol freeze.
        generated=(datetime.fromisoformat(spec['createdAt'].replace('Z','+00:00'))+timedelta(seconds=1)).isoformat().replace('+00:00','Z')
        audit={"schema":"prospective_stock_quote_reference_v1","generatedAt":generated,
            "sessionState":"awaiting_first_session","orderAuthority":False,"winProbability":None,"brokerPnl":None,
            "equityNetCosts":None,"executionModel":None,"labelCount":0,"foldCounts":{},
            "coverage":[{"symbol":s,"frame":f} for s in base['symbols'] for f in base['frames']],
            "labels":[{"private":"PRIVATE"}],"frozenPolicySubset":{"policy":base['policy'],"side":"long",
                "orderAuthority":False,"winProbability":None,"referenceCount":0}}
        raw={"generatedAt":generated,"manifestSha256":digest,"baseManifestSha256":spec['baseManifestSha256'],
             "selection":spec['selection'],"streamExitAudit":audit,"restExitAudit":audit,
             "orderAuthority":False,"winProbability":None,"brokerPnl":None}
        with tempfile.TemporaryDirectory() as d:
            rp=Path(d)/'report.json'; rp.write_text(json.dumps(raw))
            safe=stock_quote_audit_summary(mp,rp,digest,bp)
            self.assertEqual(safe['protocolFrozenAt'],spec['createdAt'])
            self.assertEqual(set(safe['stream']['frameCounts']),set(base['frames']))
            self.assertEqual(safe['stream']['frameCounts']['4h'],{'frozenFeatureCount':0,'quoteReferences':0})
            self.assertNotIn('PRIVATE',json.dumps(safe))
            for changes in ({'baseManifestSha256':'changed'},{'selection':'first_ever_candle'},
                            {'orderAuthority':True},{'manifestSha256':spec['baseManifestSha256']}):
                rp.write_text(json.dumps({**raw,**changes}));self.assertIsNone(stock_quote_audit_summary(mp,rp,digest,bp))

    def test_pinned_stock_audit_coverage_does_not_publish_quotes_returns_private_fields_or_authority(self):
        import hashlib
        # SOURCE: synthetic prospective manifest/report, not broker observations.
        manifest={"createdAt":"2026-10-05T05:00:00Z","symbols":["QQQ"],"frames":["1m"],"streamSymbols":["QQQ"],
            "policy":"trend_candle_confluence_v1","sessions":[
                {"date":"2026-10-05","open":"09:30","close":"16:00","fold":"discovery"},
                {"date":"2026-10-06","open":"09:30","close":"16:00","fold":"validation"}]}
        audit={"schema":"prospective_stock_quote_reference_v1","generatedAt":"2026-10-05T05:01:00Z",
            "sessionState":"awaiting_first_session","orderAuthority":False,"winProbability":None,"brokerPnl":None,
            "equityNetCosts":None,"executionModel":None,"labelCount":0,"foldCounts":{},
            "coverage":[{"symbol":"QQQ","frame":"1m"}],"labels":[{"accountId":"PRIVATE"}],
            "summary":{"netPnl":"PRIVATE"},"frozenPolicySubset":{"policy":manifest['policy'],"side":"long",
                "orderAuthority":False,"winProbability":None,"referenceCount":0}}
        with tempfile.TemporaryDirectory() as directory:
            mp,rp=Path(directory)/"manifest.json",Path(directory)/"report.json"
            mp.write_text(json.dumps(manifest));digest=hashlib.sha256(mp.read_bytes()).hexdigest()
            raw={"manifestSha256":digest,"generatedAt":audit['generatedAt'],"orderAuthority":False,
                "winProbability":None,"brokerPnl":None,"streamExitAudit":audit,"restExitAudit":audit,"secret":"PRIVATE"}
            rp.write_text(json.dumps(raw));safe=stock_quote_audit_summary(mp,rp,digest)
            self.assertEqual(safe['frameSlots'],1);self.assertEqual(safe['stream']['labelCount'],0)
            self.assertEqual(safe['sessions'][0]['openAt'],'2026-10-05T13:30:00Z')
            self.assertNotIn('PRIVATE',json.dumps(safe));self.assertNotIn('labels',safe)
            for changes in ({"orderAuthority":True},{"winProbability":.9},{"brokerPnl":1},
                {"manifestSha256":"changed"},{"generatedAt":"2099-01-01T00:00:00Z"},
                {"streamExitAudit":{**audit,"labelCount":True}},
                {"streamExitAudit":{**audit,"coverage":[]}},
                {"streamExitAudit":{**audit,"labelCount":1,"foldCounts":{"discovery":1},"coverage":[{"symbol":"QQQ","frame":"1m","quoteReferences":1}]}},
                {"streamExitAudit":{**audit,"sessionState":"complete"}},
                {"streamExitAudit":{**audit,"equityNetCosts":0}}):
                rp.write_text(json.dumps({**raw,**changes}));self.assertIsNone(stock_quote_audit_summary(mp,rp,digest))
            mp.write_text(json.dumps(manifest)+"\n");self.assertIsNone(stock_quote_audit_summary(mp,rp,digest))

    def test_quote_audit_summary_is_dated_aggregate_only_without_return_or_private_fields(self):
        # SOURCE: synthetic aggregate fields exercise publication boundaries only.
        raw={"schema":"first_observed_long_quote_reference_v1","generatedAt":"2026-10-04T22:00:00Z",
            "orderAuthority":False,"winProbability":None,"brokerPnl":None,"labelCount":2,
            "foldCounts":{"validation":2},"comparisonCount":1,"horizonBars":1,"maxExitLagSeconds":120,
            "splitAt":"2026-10-04T21:00:00Z","rejected":{"noFirstObservedFreshEntryQuote":10},
            "labels":[{"accountId":"PRIVATE"}],"summary":{"inventedPnl":"PRIVATE"},"apiSecret":"PRIVATE"}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"forward-quote-audit.json"
            with patch("export_telemetry.STATE_DIR",Path(directory)):
                path.write_text(json.dumps(raw));safe=quote_audit_summary()
                self.assertEqual(safe["labelCount"],2)
                self.assertEqual(safe["foldCounts"],{"discovery":0,"validation":2})
                self.assertEqual(safe["generatedAt"],raw["generatedAt"])
                self.assertNotIn("PRIVATE",json.dumps(safe));self.assertNotIn("summary",safe)
                for change in [{"orderAuthority":True},{"winProbability":.9},{"brokerPnl":10},{"labelCount":True},
                               {"foldCounts":{"validation":1}},{"generatedAt":"2099-01-01T00:00:00Z"}]:
                    path.write_text(json.dumps({**raw,**change}));self.assertIsNone(quote_audit_summary())
                path.unlink();self.assertIsNone(quote_audit_summary())

    def test_operational_path_reads_status_files_without_credentials_or_broker_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"market-pipeline.json").write_text(json.dumps({"asOf":"synthetic","orderAuthority":False,"winProbability":None,"markets":[]}))
            (root/"multi-paper.json").write_text(json.dumps({"asOf":"synthetic","activeTickets":[]}))
            with patch("export_telemetry.STATE_DIR",root),patch("export_telemetry.read_env",side_effect=AssertionError("credential read")),patch("export_telemetry.paper_get",side_effect=AssertionError("broker query")):
                result=operational_snapshot()
            self.assertFalse(result["marketPipeline"]["orderAuthority"])
            self.assertNotIn("positions",result);self.assertNotIn("orders",result)
            self.assertNotIn("fills",result);self.assertNotIn("journal",result)
    def test_auto_stock_evidence_retains_actual_preflight_without_private_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"stock-events.jsonl"
            # SOURCE: synthetic exact identity and timestamp fixture, not a trade.
            event={"kind":"DECISION","at":"2026-10-04T20:00:00Z","clientOrderId":"aibotstkAuto","symbol":"QQQ",
                "reason":"Synthetic confluence","detail":{"symbol":"QQQ","side":"buy","policy":"trend_candle_confluence_v1","frame":"4h",
                "signalBar":"2026-10-04T12:00:00Z","invalidationLevel":99,"accountId":"PRIVATE",
                "reading":{"ema20":100,"ema50":99,"candleShapes":["hammer_shape"]},
                "preflight":{"accountReady":True,"regularSessionOpen":True,"buyingPowerChecked":True,
                    "buyingPowerSufficient":True,"quoteTime":"2026-10-04T19:59:59Z","bid":100,"ask":101,"secret":"PRIVATE"}}}
            path.write_text(json.dumps(event)+"\n"+json.dumps([])+"\n")
            result=stock_order_evidence([{"id":"exact","clientOrderId":"aibotstkAuto","symbol":"QQQ","side":"buy","submittedAt":"2026-10-04T20:00:01Z"},
                {"id":"neighbor","clientOrderId":"aibotstkOther","symbol":"QQQ"}],path)
            self.assertEqual(set(result),{"exact"})
            self.assertEqual(result["exact"]["policy"],"trend_candle_confluence_v1")
            self.assertEqual(result["exact"]["trigger_quote_time"],"2026-10-04T19:59:59Z")
            self.assertTrue(json.loads(result["exact"]["preflight_evidence"])["accountReady"])
            self.assertNotIn("PRIVATE",json.dumps(result))
    def test_capture_health_uses_configured_unit_without_publishing_private_name(self):
        # SOURCE: synthetic service outcomes verify deployment-name mapping only.
        import subprocess
        with patch("export_telemetry.subprocess.run",return_value=subprocess.CompletedProcess([],0)) as run:
            result=service_state({"PAPER_ORDERS":"1","AI_OCAML_CAPTURE_SERVICE":"configured-capture.service"})
        self.assertTrue(result["captureActive"])
        self.assertEqual(run.call_args_list[1].args[0][-1],"configured-capture.service")
        self.assertNotIn("configured-capture.service",json.dumps(result))
        with self.assertRaises(ValueError):
            with patch("export_telemetry.subprocess.run",return_value=subprocess.CompletedProcess([],0)):
                service_state({"AI_OCAML_CAPTURE_SERVICE":"--invalid.service"})

    def test_retired_legacy_process_does_not_hide_a_healthy_paper_scheduler(self):
        import subprocess
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/'multi-paper.json'
            credentials={'PAPER_ORDERS':'1','AI_OCAML_MULTI_PAPER_TIMER':'configured-paper.timer'}
            def status(args, **kwargs):
                return subprocess.CompletedProcess(args,0 if args[-1]=='configured-paper.timer' else 1)
            for stamp, mode, expected in [
                (datetime.now(timezone.utc).isoformat(),'PAPER_EXPERIMENT','PAPER_ORDER'),
                (datetime.now(timezone.utc).isoformat(),'OBSERVE','MONITOR'),
                ((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),'PAPER_EXPERIMENT','STOPPED'),
                ((datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'PAPER_EXPERIMENT','STOPPED'),
                ('invalid','PAPER_EXPERIMENT','STOPPED'),
            ]:
                path.write_text(json.dumps({'asOf':stamp,'mode':mode}))
                with patch('export_telemetry.STATE_DIR',root),patch('export_telemetry.subprocess.run',side_effect=status):
                    result=service_state(credentials)
                self.assertEqual(result['mode'],expected)
                self.assertEqual(result['active'],expected!='STOPPED')
                self.assertNotIn('configured-paper.timer',json.dumps(result))

    def test_stock_scope_requires_owned_namespace_and_keeps_aapl_private(self):
        rows=[{"id":"owned","client_order_id":"aibotstkExample","symbol":"QQQ","asset_class":"us_equity"},
              {"id":"private","client_order_id":"aibotstkProtected","symbol":"AAPL","asset_class":"us_equity"},
              {"id":"external","client_order_id":"manual","symbol":"NVDA","asset_class":"us_equity"}]
        with patch("export_telemetry.paper_get",return_value=rows):orders,complete,_=broker_orders({})
        self.assertTrue(complete);self.assertEqual([r["id"] for r in orders],["owned"])
        positions=public_positions([{"symbol":"QQQ","qty":"1"},{"symbol":"AAPL","qty":"100"},
                                   {"symbol":"NVDA","qty":"2"}],{"QQQ"})
        self.assertEqual([p["symbol"] for p in positions],["QQQ"])

    def test_multicrypto_public_scope_still_excludes_private_positions(self):
        positions = [{"symbol": "ETHUSD", "qty": "1"}, {"symbol": "AAPL", "qty": "100"},
                     {"symbol": "SOLUSD", "qty": "2"}, {"symbol": "BTCUSD", "qty": "0.1"}]
        projection = public_positions(positions, {"BTC/USD", "ETH/USD"})
        self.assertEqual([row["symbol"] for row in projection], ["ETHUSD", "BTCUSD"])

    def test_multi_order_scope_includes_external_conflicts_but_not_other_holdings(self):
        rows = [{"id": "eth", "client_order_id": "jsbotmtfexample", "symbol": "ETH/USD", "asset_class": "crypto"},
                {"id": "conflict", "client_order_id": "manual", "symbol": "ETHUSD", "asset_class": "crypto"},
                {"id": "private", "client_order_id": "manual", "symbol": "AAPL", "asset_class": "us_equity"}]
        with patch("export_telemetry.paper_get", return_value=rows):
            orders, complete, attributed = broker_orders({})
        self.assertTrue(complete)
        self.assertFalse(attributed)
        self.assertEqual([row["id"] for row in orders], ["eth", "conflict"])

    def test_multiframe_reason_joins_exact_client_order_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(json.dumps({"kind": "DECISION", "clientOrderId": "jsbotmtfone", "at": "2026-10-04T19:49:59Z","symbol":"ETH/USD","side":"buy",
                "policy": "trend_candle_confluence_v1", "frame": "4h", "signalBar": "synthetic",
                "reason": "Synthetic reason", "reading": {"ema20": 100, "ema50": 99,
                    "candleShapes": ["hammer_shape"], "triggerBid": 101}}) + "\n")
            evidence = multi_order_evidence([
                {"id": "one", "clientOrderId": "jsbotmtfone", "symbol": "ETHUSD","side":"buy","submittedAt":"2026-10-04T19:50:00Z"},
                {"id": "two", "clientOrderId": "jsbotmtftwo", "symbol": "ETHUSD"}], path)
            self.assertEqual(set(evidence), {"one"})
            self.assertEqual(evidence["one"]["frame"], "4h")
            self.assertEqual(evidence["one"]["trigger_bid"], "101")
            self.assertEqual(evidence["one"]["observedAt"], "2026-10-04T19:49:59Z")

    def test_nonbtc_received_asset_fee_keeps_its_own_unit(self):
        rows = [{"id": "ethfee", "description": "Coin Pair Transaction Fee (Non USD)",
                 "symbol": "ETHUSD", "qty": "-0.001", "price": "100"}]
        with patch("export_telemetry.paper_get", side_effect=[rows, []]):
            fees = broker_crypto_fees({}, True, owned_symbols={"BTC/USD", "ETH/USD"})
        self.assertTrue(fees["attributedToBot"])
        self.assertEqual(fees["btcFeeQty"], "0")
        self.assertEqual(fees["assetFees"]["ETH/USD"]["qty"], "-0.001")

    def test_stock_and_multiframe_evidence_reject_ambiguous_identity_side_and_causal_clocks(self):
        # SOURCE: synthetic exact nanosecond boundary and corrupted journals;
        # ordering cannot choose one of contradictory retained decisions.
        for fn,cid,symbol in [(stock_order_evidence,'aibotstkExact','QQQ'),(multi_order_evidence,'jsbotmtfExact','ETH/USD')]:
            with self.subTest(route=cid),tempfile.TemporaryDirectory() as directory:
                p=Path(directory)/'events.jsonl'
                order={'id':'exact','clientOrderId':cid,'symbol':symbol,'side':'buy','submittedAt':'2026-10-04T20:00:01.123456789Z'}
                row={'kind':'DECISION','clientOrderId':cid,'symbol':symbol,'side':'buy','at':'2026-10-04T20:00:01.123456Z',
                    'policy':'trend_candle_confluence_v1','reading':{},'detail':{'symbol':symbol,'side':'buy'}}
                def run(rows,orders=None):
                    p.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
                    return fn(orders or [order],p)
                self.assertEqual(set(run([row,row])),{'exact'})
                self.assertEqual(run([row,{**row,'reason':'contradiction'}]),{})
                for change in [{'symbol':'NVDA'},{'side':'sell','detail':{'symbol':symbol,'side':'sell'}},
                    {'at':'2026-10-04T20:00:01.123456790Z'},{'at':'2026-10-04T20:00:01Z'},
                    {'at':'missing'},{'symbol':None},{'detail':[],'side':None}]:
                    with self.subTest(change=change):self.assertEqual(run([{**row,**change}]),{})
                self.assertEqual(run([row],[order,{**order,'id':'other'}]),{})
                self.assertEqual(run([row],[{**order,'side':None}]),{})
                self.assertEqual(run([row],[{**order,'submittedAt':None}]),{})
                for malformed in [[],{'candleShapes':[1]},{'candleShapes':'hammer'}]:
                    change={'detail':{**row['detail'],'reading':malformed}} if fn==stock_order_evidence else {'reading':malformed}
                    self.assertEqual(run([{**row,**change}]),{})

    def test_market_projection_omits_private_capture_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shadow.json"
            frames = {name: {"completeBars": 1, "contiguousTailBars": 1,
                             "lastBarStart": "2026-09-27T23:00:00Z", "trend": None,
                             "candleShapes": []}
                      for name in ("1m", "5m", "30m", "60m", "240m")}
            path.write_text(json.dumps({"asOf": "2026-09-27T23:01:00Z",
                                        "captureFiles": ["/private/market.jsonl"],
                                        "orderAuthority": False,
                                        "symbols": [{"symbol": "BTC/USD", "frames": frames}]}),
                            encoding="utf-8")
            projection = market_research_state(path)
            self.assertNotIn("captureFiles", projection)
            self.assertNotIn("/private", json.dumps(projection))
            self.assertFalse(projection["orderAuthority"])

    def test_old_decision_is_joined_without_nearest_event_guess(self) -> None:
        # SOURCE: synthetic quote values chosen to encode an exact 10 bp upward cross.
        events = [
            {"at": "2026-09-27T00:00:00Z", "message":
             "HOT_SAMPLE reference_quote_time=2026-09-26T23:59:30Z "
             "quote_time=2026-09-27T00:00:00Z window_ms=30000 candidate=true "
             "policy=quote_cross_30s_v1"},
            {"at": "2026-09-27T00:00:00Z", "message":
             "HOT_DECISION quote_time=2026-09-27T00:00:00Z "
             "receive_to_decision_ms=5.3 candidate=true "
             "policy=quote_cross_30s_v1 trend=falling probability=unknown "
             "reference_bid=99.5 reference_ask=100 current_bid=100.1 "
             "current_ask=100.2 cross_direction=up trigger_move_bps=10.00000000"},
            {"at": "2026-09-27T00:00:01Z", "message":
             "HOT_DECISION quote_time=2026-09-27T00:00:01Z policy=other"},
        ]
        orders = [{"id": "one", "clientOrderId": "jsbotbtcbuy20260927T000000Z",
                   "side": "buy"},
                  {"id": "outside", "clientOrderId": "manual", "side": "buy"}]
        history = decision_history(events, orders)
        self.assertEqual(set(history), {"one"})
        self.assertEqual(history["one"]["policy"], "quote_cross_30s_v1")
        self.assertEqual(history["one"]["observedAt"], "2026-09-27T00:00:00Z")
        self.assertEqual(history["one"]["reference_quote_time"],
                         "2026-09-26T23:59:30Z")
        self.assertEqual(history["one"]["receive_to_decision_ms"], "5.3")
        self.assertEqual(history["one"]["reference_bid"], "99.5")
        self.assertEqual(history["one"]["current_ask"], "100.2")
        self.assertEqual(history["one"]["cross_direction"], "up")
        self.assertEqual(history["one"]["trigger_move_bps"], "10.00000000")
        self.assertNotIn("other", str(history))

    def test_btc_preflight_is_exact_prior_and_whitelisted_never_nearest_or_future(self):
        # SOURCE: synthetic microsecond/nanosecond clocks and explicit checks;
        # no broker event or risk pass is inferred from a current chart.
        quote="2026-10-05T02:00:00.123456789Z"
        client="jsbotbtcbuy20261005T020000123456789Z"
        order={"id":"exact","clientOrderId":client,"symbol":"BTC/USD","side":"buy",
            "submittedAt":"2026-10-05T02:00:01.100000000Z"}
        decision={"at":"2026-10-05T02:00:00.200000Z","message":f"HOT_DECISION quote_time={quote} policy=quote_cross_30s_v1"}
        checks={"accountReady":True,"pendingIntentClear":True,"openOrdersClear":True,"ownershipMarkerConsistent":True,
            "buyingPowerCheck":"passed","exposureCheck":"passed","requestedQty":"0.001",
            "limitPrice":"100000","sourceQuoteTime":quote,"sourceQuoteAgeNs":"776543211",
            "receiptQuoteAgeNs":"700000000","privateKey":"PRIVATE"}
        def event(values=checks,at="2026-10-05T02:00:00.900000Z",id=client,side="buy"):
            return {"at":at,"message":f"BTC_PREFLIGHT id={id} side={side} evidence="+json.dumps(values,separators=(',',':'))}
        result=decision_history([decision,event()],[order])["exact"]
        self.assertEqual(result["preflight_observed_at"],"2026-10-05T02:00:00.900000Z")
        self.assertTrue(json.loads(result["preflight_evidence"])["pendingIntentClear"])
        self.assertNotIn("PRIVATE",json.dumps(result))
        invalid=[event(at="2026-10-05T02:00:01.100000001Z"),event(at="2026-10-05T02:00:00.100000Z"),
            event(id="unrelated"),event(side="sell"),event({**checks,"accountReady":False}),
            event({**checks,"requestedQty":"NaN"}),event({**checks,"sourceQuoteAgeNs":"5000000001"}),
            event({**checks,"sourceQuoteTime":"2026-10-05T02:00:00.123456790Z"})]
        for row in invalid:
            with self.subTest(row=row):self.assertNotIn("preflight_evidence",decision_history([decision,row],[order])["exact"])
        # Same exact retained event is safe to deduplicate; conflicting dates
        # cannot be silently resolved by choosing the last retained event.
        self.assertIn("preflight_evidence",decision_history([decision,event(),event()],[order])["exact"])
        self.assertNotIn("preflight_evidence",decision_history([decision,event(),event(at="2026-10-05T02:00:00.950000Z")],[order])["exact"])
        self.assertNotIn("preflight_evidence",decision_history([decision,event()],[{**order,"symbol":"AAPL"}])["exact"])
        for malformed in ([],None,"invalid shape"):
            self.assertNotIn("preflight_evidence",decision_history([decision,event(malformed)],[order])["exact"])


class PublicProjectionTests(unittest.TestCase):
    def test_private_fee_cache_retains_only_actual_provenance_without_public_or_inferred_order_links(self):
        # SOURCE: synthetic fee provenance; creation date is intentionally later
        # than activity date and must never be used as a trade/order join.
        row={'id':'synthetic-fee','activity_type':'CFEE','description':'Coin Pair Transaction Fee (USD)',
            'net_amount':'-0.25','date':'2026-10-04','created_at':'2026-10-05T00:00:00Z',
            'currency':'USD','status':'executed','account_id':'PRIVATE','secret':'PRIVATE'}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fee-cache.json'
            with patch('export_telemetry.paper_get',side_effect=[[row],[]]):
                summary=broker_crypto_fees({},True,use_cache=True,cache_path=path)
            retained=json.loads(path.read_text())['activities'][0]
            self.assertEqual(retained['date'],row['date']);self.assertEqual(retained['created_at'],row['created_at'])
            self.assertEqual(retained['currency'],'USD');self.assertEqual(retained['status'],'executed')
            self.assertIsNone(retained['order_id']);self.assertIsNone(retained['transaction_time'])
            self.assertNotIn('PRIVATE',json.dumps(retained));self.assertNotIn('date',summary)
            self.assertNotIn('order_id',summary);self.assertNotIn('PRIVATE',json.dumps(summary))
            with patch('export_telemetry.paper_get',side_effect=AssertionError('cached rows only')):
                self.assertEqual(summary,broker_crypto_fees({},True,use_cache=True,cache_path=path))
    def test_public_positions_exclude_non_bot_holdings(self) -> None:
        # SOURCE: synthetic amounts only identify which account row is omitted.
        positions = [
            {"symbol": "BTCUSD", "qty": "0.01", "market_value": "500"},
            {"symbol": "AAPL", "qty": "10", "market_value": "3500"},
        ]
        projection = public_positions(positions)
        self.assertEqual([row["symbol"] for row in projection], ["BTCUSD"])
        self.assertNotIn("3500", json.dumps(projection))

    def test_public_orders_keep_bot_and_external_btc_only(self) -> None:
        broker_page = [
            {"id": "bot", "client_order_id": "jsbotbtcbuy1", "symbol": "BTC/USD"},
            {"id": "bot", "client_order_id": "jsbotbtcbuy1", "symbol": "BTC/USD"},
            {"id": "manual-btc", "client_order_id": "manual", "symbol": "BTCUSD"},
            {"id": "aapl", "client_order_id": "manual-stock", "symbol": "AAPL"},
        ]
        with patch("export_telemetry.paper_get", return_value=broker_page):
            orders, complete, crypto_attributable = broker_orders({})
        self.assertTrue(complete)
        self.assertFalse(crypto_attributable)
        self.assertEqual({order["id"] for order in orders}, {"bot", "manual-btc"})
        self.assertIsNone(orders[0]["requestedQty"])
        self.assertIsNone(orders[0]["requestedNotional"])
        self.assertIsNone(orders[0]["limitPrice"])

    def test_non_bot_crypto_order_blocks_fee_attribution(self) -> None:
        broker_page = [
            {"id": "bot", "client_order_id": "jsbotbtcbuy1", "symbol": "BTC/USD",
             "asset_class": "crypto"},
            {"id": "manual-eth", "client_order_id": "manual", "symbol": "ETH/USD",
             "asset_class": "crypto"},
        ]
        with patch("export_telemetry.paper_get", return_value=broker_page):
            _, complete, crypto_attributable = broker_orders({})
        self.assertTrue(complete)
        self.assertFalse(crypto_attributable)

    def test_posted_crypto_fee_summary_keeps_currency_units_separate(self) -> None:
        # SOURCE: synthetic amounts test unit handling only; they are not observed fees.
        activities = [
            {"id": "btc-fee", "description": "Coin Pair Transaction Fee (Non USD)",
             "symbol": "BTCUSD", "qty": "-0.000025", "price": "100"},
            {"id": "usd-fee", "description": "Coin Pair Transaction Fee (USD)",
             "net_amount": "-0.25", "symbol": None},
            {"id": "unrelated", "description": "Regulatory fee", "net_amount": "-1"},
        ]
        with patch("export_telemetry.paper_get", side_effect=[activities, []]):
            summary = broker_crypto_fees({}, crypto_orders_attributable=True)
        self.assertTrue(summary["pagesComplete"])
        self.assertTrue(summary["attributedToBot"])
        self.assertEqual(summary["activityRows"], 2)
        self.assertEqual(summary["usdNetAmount"], "-0.25")
        self.assertEqual(summary["btcFeeQty"], "-0.000025")
        self.assertEqual(summary["btcFeeValueAtActivityPriceUsd"], "-0.002500")
        self.assertEqual(summary["unclassifiedRows"], 0)

    def test_unclassified_fee_or_incomplete_page_never_claims_attribution(self) -> None:
        unclassified = [{"id": "other-crypto-fee",
                         "description": "Coin Pair Transaction Fee (Non USD)",
                         "symbol": "ETHUSD", "qty": "-0.01", "price": "100"}]
        with patch("export_telemetry.paper_get", side_effect=[unclassified, []]):
            summary = broker_crypto_fees({}, crypto_orders_attributable=True)
        self.assertFalse(summary["attributedToBot"])
        self.assertEqual(summary["unclassifiedRows"], 1)
        with patch("export_telemetry.paper_get", side_effect=[OSError("unavailable"), []]):
            unavailable = broker_crypto_fees({}, crypto_orders_attributable=True)
        self.assertFalse(unavailable["pagesComplete"])
        self.assertFalse(unavailable["attributedToBot"])

    def test_recent_private_fee_cache_avoids_repeating_full_account_pagination(self) -> None:
        # SOURCE: synthetic fee rows test cache behavior only; no broker data is used.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fee-cache.json"
            path.write_text(json.dumps({
                "fetchedAt": datetime.now(timezone.utc).isoformat(),
                "pagesComplete": True,
                "activities": [{"id": "fee", "activity_type": "CFEE",
                                "description": "Coin Pair Transaction Fee (USD)",
                                "net_amount": "-0.25", "created_at": "2026-09-29T00:00:00Z"}],
            }), encoding="utf-8")
            with patch("export_telemetry.paper_get", side_effect=AssertionError("cache should be used")):
                summary = broker_crypto_fees({}, crypto_orders_attributable=True,
                                             use_cache=True, cache_path=path)
        self.assertTrue(summary["pagesComplete"])
        self.assertEqual(summary["usdNetAmount"], "-0.25")
        self.assertTrue(summary["attributedToBot"])

    def test_public_fills_only_follow_retained_orders(self) -> None:
        # SOURCE: synthetic fill quantities and prices exercise ID filtering only.
        broker_page = [
            {"id": "fill-bot", "order_id": "bot", "symbol": "BTC/USD", "qty": "1", "price": "10"},
            {"id": "fill-bot", "order_id": "bot", "symbol": "BTC/USD", "qty": "1", "price": "10"},
            {"id": "fill-manual", "order_id": "manual-btc", "symbol": "BTCUSD", "qty": "1", "price": "10"},
            {"id": "fill-aapl", "order_id": "aapl", "symbol": "AAPL", "qty": "1", "price": "10"},
        ]
        orders = [
            {"id": "bot", "clientOrderId": "jsbotbtcbuy1"},
            {"id": "manual-btc", "clientOrderId": "manual"},
        ]
        with patch("export_telemetry.paper_get", return_value=broker_page):
            fills, complete = broker_fills({}, orders)
        self.assertTrue(complete)
        self.assertEqual({fill["id"] for fill in fills}, {"fill-bot", "fill-manual"})

    def test_public_journal_keeps_only_lifecycle_for_bot_order_ids(self) -> None:
        events = [
            {"at": "1", "message": "SEND paper buy BTC/USD qty=1 id=jsbotbtcbuy1"},
            {"at": "2", "message": "ACK id=jsbotbtcbuy1 status=accepted"},
            {"at": "3", "message": "reconcile id=jsbotbtcbuy1 side=buy status=filled"},
            {"at": "4", "message": "HOT_SAMPLE candidate=false policy=quote_cross_30s_v1"},
            {"at": "5", "message": "SEND paper buy AAPL qty=1 id=manual-stock"},
        ]
        orders = [{"clientOrderId": "jsbotbtcbuy1"}]
        self.assertEqual([row["at"] for row in public_journal(events, orders)],
                         ["1", "2", "3"])


if __name__ == "__main__":
    unittest.main()
