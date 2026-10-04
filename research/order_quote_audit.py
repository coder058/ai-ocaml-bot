"""Join paper orders to the exact Alpaca quote pair that triggered them.

The inputs are the Dublin raw market capture, OCaml event journal, and signed
monitor snapshot. This is an execution trace audit, not a profitability study.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from bisect import bisect_left
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median

# SOURCE: retain the existing descriptive 1s/5s/30s post-fill markouts.
# SOURCE: the user requested 1m/5m/30m technical-analysis timeframes; seconds
# are converted exactly and are not optimized evaluation windows.
MARKOUT_HORIZONS_SECONDS = (1, 5, 30, 60, 300, 1_800)
# SOURCE: one second is 1,000,000,000 nanoseconds by definition.
NS_PER_SECOND = 1_000_000_000
# SOURCE: Alpaca's tier-one marketable crypto fee, checked 2026-09-29:
# https://docs.alpaca.markets/us/docs/crypto-fees
TAKER_FEE_RATE = 0.0025


def fields(message: str) -> dict[str, str]:
    return dict(token.split("=", 1) for token in message.split()
                if "=" in token)


def clean_time(timestamp: str) -> str:
    # SOURCE: the OCaml client_id function retains only alphanumeric chars.
    return re.sub(r"[^A-Za-z0-9]", "", timestamp)


def quote_index(capture: Path | list[Path]) -> dict[str, dict]:
    quotes: dict[str, dict] = {}
    ambiguous: set[str] = set()
    captures = [capture] if isinstance(capture, Path) else capture
    for path in captures:
        stream_context = (gzip.open(path, "rt", encoding="utf-8")
                          if path.suffix == ".gz"
                          else path.open(encoding="utf-8"))
        with stream_context as stream:
            for line in stream:
                event = json.loads(line).get("event", {})
                if event.get("T") != "q" or event.get("S") != "BTC/USD":
                    continue
                timestamp = event.get("t")
                if timestamp in quotes and (quotes[timestamp]["bp"], quotes[timestamp]["ap"]) != (
                    event.get("bp"), event.get("ap")
                ):
                    ambiguous.add(timestamp)
                else:
                    quotes[timestamp] = event
    for timestamp in ambiguous:
        quotes.pop(timestamp, None)
    return quotes


def _as_epoch_ns(timestamp: str) -> int:
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})",
        timestamp,
    )
    if not match:
        raise ValueError("timestamp is not ISO-8601 with a timezone")
    offset = "+00:00" if match.group(3) == "Z" else match.group(3)
    parsed = datetime.fromisoformat(match.group(1) + offset)
    if parsed.tzinfo is None:
        raise ValueError("timestamp lacks a timezone")
    # SOURCE: captured Alpaca event timestamps carry nine fractional digits;
    # preserve that observed nanosecond precision in the horizon comparison.
    fraction_ns = int(((match.group(2) or "")[:9]).ljust(9, "0") or "0")
    return int(parsed.timestamp()) * NS_PER_SECOND + fraction_ns


def fill_midpoint_response(quotes: dict[str, dict], records: list[dict],
                           fills: list[dict]) -> dict:
    """Measure directional mid-price response after actual paper fills.

    This is a descriptive markout, not realized P&L: it excludes fees and
    simulates no live queue, impact or execution conditions.
    """
    hot_orders = {record["clientOrderId"]: record for record in records}
    hot_orders_by_broker_id = {record["brokerOrderId"]: record for record in records
                               if record.get("brokerOrderId")}
    timed_quotes = sorted((_as_epoch_ns(timestamp), event)
                          for timestamp, event in quotes.items())
    times = [item[0] for item in timed_quotes]
    per_horizon: dict[int, dict[str, list[tuple[float, float]]]] = {
        seconds: {} for seconds in MARKOUT_HORIZONS_SECONDS
    }
    total_hot_fills = 0
    missing_quote_after_horizon: Counter[int] = Counter()
    quote_delays_ms: dict[int, list[float]] = {
        seconds: [] for seconds in MARKOUT_HORIZONS_SECONDS
    }
    net_roundtrip_by_horizon: dict[int, dict[str, list[float]]] = {
        seconds: {} for seconds in MARKOUT_HORIZONS_SECONDS
    }
    for fill in fills:
        client_id = fill.get("clientOrderId")
        decision = hot_orders.get(client_id) if client_id else None
        if decision is None:
            decision = hot_orders_by_broker_id.get(fill.get("orderId"))
        if decision is None:
            continue
        client_id = decision["clientOrderId"]
        try:
            fill_at_ns = _as_epoch_ns(str(fill["transactionTime"]))
            fill_price = float(fill["price"])
            fill_qty = float(fill["qty"])
            if not fill_price > 0 or not fill_qty > 0:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        total_hot_fills += 1
        side_sign = 1. if decision["side"] == "buy" else -1.
        for horizon in MARKOUT_HORIZONS_SECONDS:
            target = fill_at_ns + horizon * NS_PER_SECOND
            index = bisect_left(times, target)
            if index >= len(timed_quotes):
                missing_quote_after_horizon[horizon] += 1
                continue
            quote_at_ns, event = timed_quotes[index]
            try:
                bid = float(event["bp"])
                ask = float(event["ap"])
                if bid <= 0 or ask < bid:
                    missing_quote_after_horizon[horizon] += 1
                    continue
                midpoint = (bid + ask) / 2.
            except (KeyError, TypeError, ValueError):
                missing_quote_after_horizon[horizon] += 1
                continue
            # SOURCE: 10,000 basis points per unit relative-price change.
            response_bps = ((midpoint / fill_price) - 1.) * 10_000. * side_sign
            order_values = per_horizon[horizon].setdefault(client_id, [0., 0.])
            order_values[0] += response_bps * fill_qty
            order_values[1] += fill_qty
            if decision["side"] == "buy":
                # Buy fee reduces credited BTC; sell fee reduces USD proceeds.
                net_factor = (bid / fill_price) * (1 - TAKER_FEE_RATE) ** 2
            else:
                # Sell markout is a hypothetical same-size buyback opportunity,
                # not the realized P&L of the position being exited.
                net_factor = (fill_price / ask) * (1 - TAKER_FEE_RATE) ** 2
            net_values = net_roundtrip_by_horizon[horizon].setdefault(
                client_id, [0., 0.]
            )
            net_values[0] += (net_factor - 1.) * 10_000. * fill_qty
            net_values[1] += fill_qty
            # SOURCE: one millisecond is 1,000,000 nanoseconds by definition.
            quote_delays_ms[horizon].append((quote_at_ns - target) / 1_000_000.)

    summaries = {}
    net_summaries = {}
    for horizon, by_order in per_horizon.items():
        order_responses = [weighted / quantity for weighted, quantity in by_order.values()
                           if quantity > 0]
        summaries[f"{horizon}s"] = {
            "filledOrdersWithQuote": len(order_responses),
            "medianSignedMidpointResponseBps": median(order_responses)
                if order_responses else None,
            "positiveOrderShare": sum(value > 0 for value in order_responses) / len(order_responses)
                if order_responses else None,
            "fillsWithoutFutureQuote": missing_quote_after_horizon[horizon],
            "quoteDelaySampleCount": len(quote_delays_ms[horizon]),
            "medianQuoteDelayAfterHorizonMs": median(quote_delays_ms[horizon])
                if quote_delays_ms[horizon] else None,
            "maxQuoteDelayAfterHorizonMs": max(quote_delays_ms[horizon])
                if quote_delays_ms[horizon] else None,
        }
        net_order_returns = [weighted / quantity
                             for weighted, quantity in net_roundtrip_by_horizon[horizon].values()
                             if quantity > 0]
        net_summaries[f"{horizon}s"] = {
            "filledOrdersWithQuote": len(net_order_returns),
            "medianNetExecutableRoundTripMarkoutBps": median(net_order_returns)
                if net_order_returns else None,
            "positiveNetOrderShare": sum(value > 0 for value in net_order_returns) /
                len(net_order_returns) if net_order_returns else None,
            "ordersWithoutFutureQuote": missing_quote_after_horizon[horizon],
        }
    return {"available": True, "hotOrderFills": total_hot_fills,
            "byHorizon": summaries,
            "feeAwareExecutableMarkout": {
                "byHorizon": net_summaries,
                "scope": "Hypothetical close or buyback at the first captured executable quote after the horizon, with tier-one taker fees on both legs. Not realized P&L; excludes order latency, queue, impact and live fee-tier confirmation.",
            },
            "scope": "Paper fill-to-midpoint response only; grouped by order, fee-free and not a profitability estimate."}


def audit(capture: Path | list[Path], journal: Path | None, snapshot: dict) -> dict:
    telemetry = snapshot.get("telemetry", snapshot)
    if not telemetry.get("ordersComplete"):
        raise ValueError("broker order pagination is incomplete")
    orders = {order["clientOrderId"]: order for order in telemetry["orders"]
              if str(order.get("clientOrderId", "")).startswith("jsbotbtc")}
    quotes = quote_index(capture)
    samples: dict[str, dict[str, str]] = {}
    sends: list[dict[str, str]] = []
    if journal is not None:
        with journal.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                message = event["message"]
                if message.startswith("HOT_SAMPLE "):
                    row = fields(message)
                    if row.get("candidate") == "true":
                        samples[row["quote_time"]] = row
                elif message.startswith("SEND paper "):
                    row = fields(message)
                    row["at"] = event["at"]
                    row["side"] = message.split()[2]
                    sends.append(row)

    joined_orders = []
    orders_without_decision_trace = 0
    public_decisions = telemetry.get("decisionHistory")
    if isinstance(public_decisions, dict) and public_decisions:
        # SOURCE: the signed monitor exporter keys its exact recorded decision
        # trace by Alpaca broker order ID; no nearest-timestamp join is used.
        for broker_order in orders.values():
            decision = public_decisions.get(broker_order.get("id"))
            if not isinstance(decision, dict):
                orders_without_decision_trace += 1
                continue
            client_id = broker_order.get("clientOrderId")
            if not isinstance(client_id, str):
                continue
            joined_orders.append((
                client_id,
                broker_order.get("side"),
                decision.get("quote_time"),
                decision.get("reference_quote_time"),
                decision,
                broker_order,
            ))
    else:
        # Legacy local journal path, retained for offline snapshots without the
        # compact signed decisionHistory projection.
        for send in sends:
            client_id = send["id"]
            sample_time = next((timestamp for timestamp in samples
                                if client_id == "jsbotbtc" + send["side"] + clean_time(timestamp)), None)
            if sample_time is None:
                # The older REST loop has no HOT_SAMPLE event and is outside scope.
                continue
            sample = samples[sample_time]
            joined_orders.append((client_id, send["side"], sample_time,
                                  sample.get("reference_quote_time"), sample,
                                  orders.get(client_id)))

    records = []
    unmatched = []
    for client_id, side, sample_time, reference_time, sample, broker_order in joined_orders:
        if not isinstance(sample_time, str) or not isinstance(reference_time, str):
            unmatched.append(client_id)
            continue
        reference = quotes.get(reference_time)
        current = quotes.get(sample_time)
        if reference is None or current is None or broker_order is None:
            unmatched.append(client_id)
            continue
        if side == "buy":
            crossing = float(current["bp"]) - float(reference["ap"])
            reference_price = float(reference["ap"])
        elif side == "sell":
            crossing = float(reference["bp"]) - float(current["ap"])
            reference_price = float(reference["bp"])
        else:
            raise ValueError("unexpected order side")
        # SOURCE: 10,000 basis points per unit price return.
        crossing_bps = crossing / reference_price * 10_000
        if crossing <= 0:
            raise ValueError(f"order {client_id} lacks its claimed quote cross")
        records.append({
            "clientOrderId": client_id,
            "brokerOrderId": broker_order.get("id"),
            "side": side,
            "brokerStatus": broker_order.get("status"),
            "submittedAt": broker_order.get("submittedAt"),
            "referenceQuoteTime": reference_time,
            "quoteTime": sample_time,
            "referenceBid": reference["bp"],
            "referenceAsk": reference["ap"],
            "currentBid": current["bp"],
            "currentAsk": current["ap"],
            "crossingBps": crossing_bps,
            "requestedQty": broker_order.get("qty"),
            "filledQty": broker_order.get("filledQty"),
            "filledAvgPrice": broker_order.get("filledAvgPrice"),
        })
    crossing_values = [record["crossingBps"] for record in records]
    fills_complete = telemetry.get("fillsComplete") is True
    fill_response = fill_midpoint_response(quotes, records, telemetry.get("fills", [])) \
        if fills_complete else {"available": False, "reason": "broker fill history is incomplete or unavailable"}
    return {
        "snapshotAt": telemetry.get("generatedAt"),
        "matchedHotOrders": len(records),
        "botOrdersWithoutDecisionTrace": orders_without_decision_trace,
        "unmatchedHotOrderIds": unmatched,
        "brokerStatuses": dict(Counter(record["brokerStatus"] for record in records)),
        "canceledWithPartialFill": sum(record["brokerStatus"] == "canceled" and
                                       float(record["filledQty"]) > 0 for record in records),
        "canceledWithoutFill": sum(record["brokerStatus"] == "canceled" and
                                    float(record["filledQty"]) == 0 for record in records),
        "minQuoteCrossingBps": min(crossing_values) if crossing_values else None,
        "medianQuoteCrossingBps": median(crossing_values) if crossing_values else None,
        "maxQuoteCrossingBps": max(crossing_values) if crossing_values else None,
        "fillMidpointResponse": fill_response,
        "orders": records,
        "scope": "Only HOT_SAMPLE-triggered OCaml paper orders are matched, using either the exact local journal or the signed decisionHistory keyed by broker order ID. Quotes are exact archived Alpaca US WebSocket events. This trigger audit does not calculate fees or net P&L.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path, nargs="+")
    parser.add_argument("journal", type=Path)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    print(json.dumps(audit(args.capture, args.journal, snapshot), indent=2))
