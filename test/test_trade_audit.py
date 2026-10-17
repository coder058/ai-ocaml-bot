"""research/trade_audit.py on synthetic broker history; no network, no real trades."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
import trade_audit as ta  # noqa: E402

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


def order(oid, cid, symbol, side, qty, filled, price, status="filled", at="2026-10-01T10:00:00Z", **extra):
    return {"id": oid, "client_order_id": cid, "symbol": symbol, "side": side, "qty": qty,
            "filled_qty": filled, "filled_avg_price": price, "status": status, "type": "limit",
            "time_in_force": "ioc", "submitted_at": at, **extra}


def fill(fid, oid, symbol, side, qty, price, at):
    return {"id": fid, "order_id": oid, "symbol": symbol, "side": side, "qty": qty, "price": price,
            "transaction_time": at}


def snapshot(orders, fills, fees=(), positions=(), complete=True):
    return {"fetchedAt": "2026-10-17T00:00:00Z", "orders": list(orders), "fills": list(fills),
            "fees": list(fees), "positions": list(positions),
            "ordersComplete": complete, "fillsComplete": True, "feesComplete": True}


class FifoAndSummary(unittest.TestCase):
    def setUp(self):
        self.snap = snapshot(
            [order("b1", "jsbotbtcbuy1", "BTC/USD", "buy", "0.002", "0.002", "60000", at="2026-09-27T10:00:00Z"),
             order("s1", "jsbotbtcsell1", "BTC/USD", "sell", "0.001", "0.001", "61000", at="2026-09-27T11:00:00Z"),
             order("s2", "jsbotbtcsell2", "BTC/USD", "sell", "0.000995", "0.000995", "59000", at="2026-09-27T12:00:00Z"),
             order("x", "jsbotmtfnofill", "ETH/USD", "buy", "0.1", "0", "0", status="canceled"),
             order("m", "manual1", "AAPL", "buy", "10", "10", "150")],
            [fill("f1", "b1", "BTC/USD", "buy", "0.002", "60000", "2026-09-27T10:00:01Z"),
             fill("f2", "s1", "BTC/USD", "sell", "0.001", "61000", "2026-09-27T11:00:01Z"),
             fill("f3", "s2", "BTC/USD", "sell", "0.000995", "59000", "2026-09-27T12:00:01Z")],
            fees=[{"id": "c1", "description": "Coin Pair Transaction Fee (Non USD)", "symbol": "BTCUSD",
                   "qty": "-0.000005", "price": "60000"},
                  {"id": "c2", "description": "Coin Pair Transaction Fee (USD)", "net_amount": "-0.30"}],
            positions=[{"symbol": "AAPL", "qty": "10", "market_value": "1500"}])
        self.result = ta.audit(self.snap, {}, NOW)

    def test_fifo_round_trips_and_gross_pnl(self):
        legacy = self.result["strategies"]["quote_cross_30s_v1 (legacy BTC)"]
        self.assertEqual(legacy["roundTrips"], 2)
        # +0.001*(61000-60000) = +1.00 ; 0.000995*(59000-60000) = -0.995
        self.assertEqual(Decimal(legacy["grossRealizedUsd"]), Decimal("0.005"))
        self.assertEqual(legacy["grossWinningTrips"], 1)
        self.assertGreater(Decimal(legacy["estTakerFeesUsd"]), Decimal("0.5"))  # ~0.25% x 2 legs
        self.assertEqual(legacy["openLotQty"], {"BTC/USD": "0.000005"})

    def test_account_net_uses_monitor_formula_and_excludes_manual_aapl(self):
        a = self.result["account"]
        # cash flow: +61 +58.705 -120 = -0.295 ; marks exclude AAPL ; USD fees -0.30
        self.assertEqual(Decimal(a["fillCashFlowUsd"]), Decimal("-0.295"))
        self.assertEqual(Decimal(a["openPositionMarksUsd"]), Decimal("0"))
        self.assertEqual(Decimal(a["netMarkedUsd"]), Decimal("-0.595"))

    def test_buy_fee_in_asset_explains_inventory(self):
        row = next(r for r in self.result["inventory"] if r["symbol"] == "BTC/USD")
        self.assertEqual(Decimal(row["residual"]), Decimal("0"))  # 0.000005 net - 0.000005 fee = broker 0
        self.assertNotIn("inventory_residual", {a["kind"] for a in self.result["anomalies"]})

    def test_counts_and_classification(self):
        self.assertEqual(self.result["counts"]["botOrders"], 4)
        mtf = self.result["strategies"]["trend_candle_confluence_v1 (crypto multi-frame)"]
        self.assertEqual((mtf["orders"], mtf["canceledNoFill"], mtf["roundTrips"]), (1, 1, 0))
        self.assertEqual(ta.crypto_symbol("BTCUSD"), "BTC/USD")
        self.assertEqual(ta.crypto_symbol("PEPEUSD"), "PEPE/USD")
        self.assertIsNone(ta.crypto_symbol("SPY"))

    def test_reports_written(self):
        with tempfile.TemporaryDirectory() as directory:
            ta.write_reports(self.result, Path(directory))
            text = (Path(directory) / "TRADE-AUDIT.md").read_text()
            self.assertIn("quote_cross_30s_v1", text)
            self.assertIn("Net marked: -0.60", text)
            self.assertEqual(len((Path(directory) / "trades.csv").read_text().splitlines()), 6)


class Anomalies(unittest.TestCase):
    def kinds(self, snap, ledgers=None):
        return {a["kind"] for a in ta.audit(snap, ledgers or {}, NOW)["anomalies"]}

    def test_each_anomaly_is_detected(self):
        snap = snapshot(
            [order("o1", "jsbotmtfa", "PEPE/USD", "buy", "10", "11", "1"),
             order("o2", "aibotstkx", "AAPL", "buy", "1", "1", "150", type="market"),
             order("o3", "jsbotbtcbig", "BTC/USD", "buy", "0.01", "0.01", "60000"),
             order("o4", "jsbotbtcbig", "BTC/USD", "sell", "0.02", "0.02", "60000"),
             order("o5", "jsbotmtfopen", "ETH/USD", "buy", "1", "0", "0", status="accepted", at="2026-10-01T00:00:00Z"),
             order("o6", "aibottrcrej", "BTC/USD", "buy", "0.001", "0", "0", status="rejected")],
            [fill("a", "o1", "PEPE/USD", "buy", "10", "1", "t1"),
             fill("b", "o3", "BTC/USD", "buy", "0.01", "60000", "t2"),
             fill("c", "o4", "BTC/USD", "sell", "0.02", "60000", "t3"),
             fill("d", "ghost", "BTC/USD", "buy", "1", "1", "t0")],
            positions=[{"symbol": "PEPEUSD", "qty": "5", "market_value": "5"}], complete=False)
        kinds = self.kinds(snap)
        for kind in ("incomplete_history", "overfill", "fill_sum_mismatch", "protected_symbol_traded",
                     "over_order_cap", "duplicate_client_id", "sell_exceeds_owned_buys", "stale_open_order",
                     "broker_rejected", "altcoin_entry", "fills_without_order", "inventory_residual"):
            self.assertIn(kind, kinds)

    def test_ledger_reconciliation(self):
        snap = snapshot([order("o1", "aibotstkA", "SPY", "buy", None, "1", "500", type="market")],
                        [fill("f", "o1", "SPY", "buy", "1", "500", "t")])
        ledgers = {"aibotstkA": {"ledger": "stock-paper-ledger.json", "state": "pending"},
                   "aibotstkGhost": {"ledger": "stock-paper-ledger.json", "state": "pending"}}
        kinds = self.kinds(snap, ledgers)
        self.assertIn("ledger_pending_but_broker_terminal", kinds)
        self.assertIn("ledger_pending_not_at_broker", kinds)
        snap2 = snapshot([order("o2", "jsbotmtfB", "ETH/USD", "buy", "1", "1", "1")], [])
        self.assertIn("no_local_ledger_record", self.kinds(snap2, {"other": {"ledger": "x", "state": "resolved"}}))

    def test_trend_policy_classified_from_ledger(self):
        snap = snapshot([order("o1", "aibotstkT", "SPY", "buy", None, "1", "500", type="market")], [])
        result = ta.audit(snap, {"aibotstkT": {"ledger": "stock-paper-ledger.json", "state": "resolved",
                                              "policy": "monthly_trend_v1"}}, NOW)
        self.assertIn("monthly_trend_v1 (ETF trend)", result["strategies"])

    def test_load_ledgers_reads_real_schemas_and_journals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "multi-paper-ledger.json").write_text(json.dumps({"version": 1, "tickets": [
                {"entryClientOrderId": "jsbotmtfE", "pending": {"clientOrderId": "jsbotmtfP"}}]}))
            (root / "stock-paper-ledger.json").write_text(json.dumps({"orders": [
                {"clientOrderId": "aibotstkS", "state": "resolved", "analysisEvidence": {"policy": "monthly_trend_v1"}}]}))
            (root / "multi-paper-events.jsonl").write_text(json.dumps({"kind": "DECISION", "clientOrderId": "jsbotmtfX"}) + "\nbad\n")
            ledgers = ta.load_ledgers(root)
            self.assertEqual(ledgers["jsbotmtfP"]["state"], "pending")
            self.assertEqual(ledgers["aibotstkS"]["policy"], "monthly_trend_v1")
            self.assertEqual(ledgers["jsbotmtfX"]["state"], "recorded")
            self.assertIn("jsbotmtfE", ledgers)


class Pagination(unittest.TestCase):
    def test_orders_walk_back_by_time_with_overlap_dedupe(self):
        history = [order(f"o{i}", f"jsbotbtc{i}", "BTC/USD", "buy", "1", "1", "1",
                         at=f"2026-09-{1 + i // 400:02d}T00:00:{i % 60:02d}Z") for i in range(1200)]
        history.sort(key=lambda o: o["submitted_at"], reverse=True)
        calls = []

        def get(path):
            calls.append(path)
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(path).query)
            until = query.get("until", [None])[0]
            rows = [o for o in history if until is None or o["submitted_at"] <= until]
            return rows[:500]

        orders, complete = ta.fetch_orders(get)
        self.assertTrue(complete)
        self.assertEqual(len(orders), 1200)
        self.assertGreater(len(calls), 2)

    def test_full_page_without_new_rows_is_incomplete(self):
        same = [order(f"o{i}", "c", "BTC/USD", "buy", "1", "1", "1", at="2026-09-01T00:00:00Z") for i in range(500)]
        orders, complete = ta.fetch_orders(lambda path: same)
        self.assertFalse(complete)
        self.assertEqual(len(orders), 500)

    def test_activities_follow_page_tokens(self):
        rows = [{"id": f"a{i:04d}"} for i in range(250)]

        def get(path):
            from urllib.parse import parse_qs, urlparse
            token = parse_qs(urlparse(path).query).get("page_token", [None])[0]
            start = 0 if token is None else next(i for i, r in enumerate(rows) if r["id"] == token) + 1
            return rows[start:start + 100]

        result, complete = ta.fetch_activities(get, "FILL")
        self.assertTrue(complete)
        self.assertEqual(len(result), 250)


if __name__ == "__main__":
    unittest.main()
