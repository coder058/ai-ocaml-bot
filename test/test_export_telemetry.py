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
)


class DecisionHistoryTests(unittest.TestCase):
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
            path.write_text(json.dumps({"kind": "DECISION", "clientOrderId": "jsbotmtfone",
                "policy": "trend_candle_confluence_v1", "frame": "4h", "signalBar": "synthetic",
                "reason": "Synthetic reason", "reading": {"ema20": 100, "ema50": 99,
                    "candleShapes": ["hammer_shape"], "triggerBid": 101}}) + "\n")
            evidence = multi_order_evidence([
                {"id": "one", "clientOrderId": "jsbotmtfone", "symbol": "ETHUSD"},
                {"id": "two", "clientOrderId": "jsbotmtftwo", "symbol": "ETHUSD"}], path)
            self.assertEqual(set(evidence), {"one"})
            self.assertEqual(evidence["one"]["frame"], "4h")
            self.assertEqual(evidence["one"]["trigger_bid"], "101")

    def test_nonbtc_received_asset_fee_keeps_its_own_unit(self):
        rows = [{"id": "ethfee", "description": "Coin Pair Transaction Fee (Non USD)",
                 "symbol": "ETHUSD", "qty": "-0.001", "price": "100"}]
        with patch("export_telemetry.paper_get", side_effect=[rows, []]):
            fees = broker_crypto_fees({}, True, owned_symbols={"BTC/USD", "ETH/USD"})
        self.assertTrue(fees["attributedToBot"])
        self.assertEqual(fees["btcFeeQty"], "0")
        self.assertEqual(fees["assetFees"]["ETH/USD"]["qty"], "-0.001")

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
        self.assertEqual(history["one"]["reference_quote_time"],
                         "2026-09-26T23:59:30Z")
        self.assertEqual(history["one"]["receive_to_decision_ms"], "5.3")
        self.assertEqual(history["one"]["reference_bid"], "99.5")
        self.assertEqual(history["one"]["current_ask"], "100.2")
        self.assertEqual(history["one"]["cross_direction"], "up")
        self.assertEqual(history["one"]["trigger_move_bps"], "10.00000000")
        self.assertNotIn("other", str(history))


class PublicProjectionTests(unittest.TestCase):
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
