"""Verify the paper order audit joins the actual trigger quote pair."""

from __future__ import annotations

import json
import gzip
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from order_quote_audit import _as_epoch_ns, audit, quote_index  # noqa: E402


class OrderQuoteAuditTests(unittest.TestCase):
    def test_quote_index_reads_gzip_market_capture(self) -> None:
        # SOURCE: synthetic compressed quote is only a reader fixture.
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.jsonl.gz"
            with gzip.open(capture, "wt", encoding="utf-8") as output:
                output.write(json.dumps({"event": {
                    "T": "q", "S": "BTC/USD", "t": "2026-09-27T00:00:00Z",
                    "bp": 99, "ap": 100,
                }}) + "\n")
            quotes = quote_index(capture)
        self.assertEqual(quotes["2026-09-27T00:00:00Z"]["bp"], 99)

    def test_quote_cross_and_broker_status_are_joined(self) -> None:
        # SOURCE: synthetic quote prices and times test ID and inequality
        # matching only; they are not observed data or trading thresholds.
        prior = "2026-09-27T00:00:00Z"
        current = "2026-09-27T00:01:00Z"
        client_id = "jsbotbtcbuy20260927T000100Z"
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.jsonl"
            journal = Path(temporary) / "events.jsonl"
            capture.write_text("\n".join(json.dumps({"event": event}) for event in [
                {"T": "q", "S": "BTC/USD", "t": prior, "bp": 99, "ap": 100},
                {"T": "q", "S": "BTC/USD", "t": current, "bp": 101, "ap": 102},
            ]), encoding="utf-8")
            journal.write_text("\n".join(json.dumps({"at": current, "message": message})
                                         for message in [
                f"HOT_SAMPLE reference_quote_time={prior} quote_time={current} candidate=true policy=quote_cross_30s_v1",
                f"SEND paper buy BTC/USD qty=1 limit=102 id={client_id}",
            ]), encoding="utf-8")
            snapshot = {"generatedAt": current, "ordersComplete": True, "orders": [
                {"id": "order", "clientOrderId": client_id, "status": "filled",
                 "qty": "1", "filledQty": "1", "filledAvgPrice": "102"},
            ]}
            result = audit(capture, journal, snapshot)
        self.assertEqual(result["matchedHotOrders"], 1)
        self.assertEqual(result["brokerStatuses"], {"filled": 1})
        self.assertEqual(result["orders"][0]["referenceAsk"], 100)
        self.assertEqual(result["orders"][0]["currentBid"], 101)

    def test_incomplete_broker_orders_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            empty = Path(temporary) / "empty.jsonl"
            empty.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                audit(empty, empty, {"ordersComplete": False})

    def test_orders_join_quotes_across_daily_capture_files(self) -> None:
        # SOURCE: synthetic prior/current quotes model an order across midnight.
        prior = "2026-09-27T23:59:30Z"
        current = "2026-09-28T00:00:00Z"
        client_id = "jsbotbtcbuy20260928T000000Z"
        with tempfile.TemporaryDirectory() as temporary:
            previous_capture = Path(temporary) / "previous.jsonl"
            current_capture = Path(temporary) / "current.jsonl"
            journal = Path(temporary) / "events.jsonl"
            previous_capture.write_text(json.dumps({"event": {
                "T": "q", "S": "BTC/USD", "t": prior, "bp": 99, "ap": 100,
            }}), encoding="utf-8")
            current_capture.write_text(json.dumps({"event": {
                "T": "q", "S": "BTC/USD", "t": current, "bp": 101, "ap": 102,
            }}), encoding="utf-8")
            journal.write_text("\n".join(json.dumps({"at": current, "message": message})
                for message in [
                    f"HOT_SAMPLE reference_quote_time={prior} quote_time={current} candidate=true policy=quote_cross_30s_v1",
                    f"SEND paper buy BTC/USD qty=1 limit=102 id={client_id}",
                ]), encoding="utf-8")
            result = audit([previous_capture, current_capture], journal, {
                "ordersComplete": True, "orders": [{"id": "order",
                    "clientOrderId": client_id, "status": "filled", "qty": "1",
                    "filledQty": "1", "filledAvgPrice": "102"}],
            })

        self.assertEqual(result["matchedHotOrders"], 1)
        self.assertEqual(result["unmatchedHotOrderIds"], [])

    def test_signed_decision_history_joins_by_broker_order_id(self) -> None:
        # SOURCE: synthetic signed projection tests exact order-ID matching;
        # quote values are fixtures, not market observations.
        prior = "2026-09-27T00:00:00Z"
        current = "2026-09-27T00:00:01Z"
        client_id = "jsbotbtcbuy20260927T000001Z"
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.jsonl"
            capture.write_text("\n".join(json.dumps({"event": event}) for event in [
                {"T": "q", "S": "BTC/USD", "t": prior, "bp": 99, "ap": 100},
                {"T": "q", "S": "BTC/USD", "t": current, "bp": 101, "ap": 102},
            ]), encoding="utf-8")
            snapshot = {
                "ordersComplete": True,
                "fillsComplete": True,
                "decisionHistory": {"broker-id": {
                    "quote_time": current,
                    "reference_quote_time": prior,
                }},
                "orders": [{"id": "broker-id", "clientOrderId": client_id,
                            "side": "buy", "status": "filled", "qty": "1",
                            "filledQty": "1", "filledAvgPrice": "102"}],
                "fills": [],
            }
            result = audit(capture, None, snapshot)
        self.assertEqual(result["matchedHotOrders"], 1)
        self.assertEqual(result["unmatchedHotOrderIds"], [])

    def test_fill_midpoint_response_uses_first_quote_after_each_horizon(self) -> None:
        # SOURCE: synthetic quote/fill times exercise forward-only 1s/5s/30s
        # sampling; the horizons are descriptive, not trading parameters.
        prior = "2026-09-27T00:00:00Z"
        decision_time = "2026-09-27T00:00:01Z"
        client_id = "jsbotbtcbuy20260927T000001Z"
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.jsonl"
            journal = Path(temporary) / "events.jsonl"
            quotes = [
                (prior, 99, 100),
                (decision_time, 101, 102),
                ("2026-09-27T00:00:02.3Z", 102, 104),
                ("2026-09-27T00:00:07Z", 103, 105),
            ]
            capture.write_text("\n".join(json.dumps({"event": {
                "T": "q", "S": "BTC/USD", "t": at, "bp": bid, "ap": ask,
            }}) for at, bid, ask in quotes), encoding="utf-8")
            journal.write_text("\n".join(json.dumps({"at": decision_time, "message": message})
                for message in [
                    f"HOT_SAMPLE reference_quote_time={prior} quote_time={decision_time} candidate=true policy=quote_cross_30s_v1",
                    f"SEND paper buy BTC/USD qty=1 limit=102 id={client_id}",
                ]), encoding="utf-8")
            result = audit(capture, journal, {
                "ordersComplete": True, "fillsComplete": True,
                "orders": [{"id": "order", "clientOrderId": client_id,
                    "status": "filled", "qty": "1", "filledQty": "1",
                    "filledAvgPrice": "102"}],
                "fills": [{"orderId": "order",
                    "side": "buy", "qty": "1", "price": "102",
                    "transactionTime": "2026-09-27T00:00:01.3Z"}],
            })

        response = result["fillMidpointResponse"]
        self.assertTrue(response["available"])
        self.assertEqual(response["hotOrderFills"], 1)
        self.assertAlmostEqual(response["byHorizon"]["1s"]["medianSignedMidpointResponseBps"],
                               ((103 / 102) - 1) * 10_000)
        self.assertAlmostEqual(response["byHorizon"]["5s"]["medianSignedMidpointResponseBps"],
                               ((104 / 102) - 1) * 10_000)
        self.assertAlmostEqual(response["byHorizon"]["5s"]["medianQuoteDelayAfterHorizonMs"],
                               700)
        self.assertEqual(response["byHorizon"]["30s"]["fillsWithoutFutureQuote"], 1)
        fee_aware = response["feeAwareExecutableMarkout"]["byHorizon"]
        expected_one_second = ((102 / 102 * (1 - 0.0025) ** 2) - 1) * 10_000
        expected_five_seconds = ((103 / 102 * (1 - 0.0025) ** 2) - 1) * 10_000
        self.assertAlmostEqual(
            fee_aware["1s"]["medianNetExecutableRoundTripMarkoutBps"],
            expected_one_second,
        )
        self.assertAlmostEqual(
            fee_aware["5s"]["medianNetExecutableRoundTripMarkoutBps"],
            expected_five_seconds,
        )

    def test_nanosecond_timestamps_are_compared_without_losing_fraction(self) -> None:
        first = _as_epoch_ns("2026-09-27T07:28:07.833016531+00:00")
        second = _as_epoch_ns("2026-09-27T07:28:07.833016532Z")
        self.assertEqual(second - first, 1)


if __name__ == "__main__":
    unittest.main()
