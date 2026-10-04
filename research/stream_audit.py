"""Audit a private Alpaca US stream capture; never infer trading edge from it."""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path


def quantile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    # SOURCE: nearest-rank empirical quantile over observed events.
    return ordered[math.ceil(len(ordered) * share) - 1]


def summary(values: list[float]) -> dict[str, float | None]:
    return {
        "median": statistics.median(values) if values else None,
        "p90": quantile(values, 0.90),  # SOURCE: empirical 90th percentile.
        "max": max(values) if values else None,
    }


def event_time_ns(value: str) -> int:
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})",
        value,
    )
    if not match:
        raise ValueError("timestamp is not ISO-8601 with an explicit timezone")
    offset = "+00:00" if match.group(3) == "Z" else match.group(3)
    parsed = datetime.fromisoformat(match.group(1) + offset)
    # SOURCE: Alpaca event timestamps can use variable fractional precision;
    # preserve up to the nine digits recorded by its stream.
    fraction_ns = int((match.group(2) or "")[:9].ljust(9, "0") or "0")
    return int(parsed.timestamp()) * 1_000_000_000 + fraction_ns


def audit(path: Path | list[Path], symbol: str = "BTC/USD") -> dict:
    paths = [path] if isinstance(path, Path) else path
    counts: Counter[str] = Counter()
    latencies: dict[str, list[float]] = {kind: [] for kind in ("q", "t", "o")}
    bar_delivery_lags: dict[str, list[float]] = {kind: [] for kind in ("b", "u")}
    quote_spreads: list[float] = []
    book_spreads: list[float] = []
    bids: dict[float, float] = {}
    asks: dict[float, float] = {}
    resets = crossed_books = invalid_quotes = updates_before_reset = invalid_bars = 0
    sequence_gaps = sequence_regressions = session_book_resets = 0
    received_first = received_last = None
    book_initialized = False
    current_session = None
    previous_sequence = None
    line_number = 0
    for path in paths:
        with path.open(encoding="utf-8") as source:
            for line in source:
                line_number += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"invalid JSON at line {line_number}; do not treat capture as complete") from error
                event = record["event"]
                kind = event["T"]
                if record["feed"] != "alpaca-us" or kind not in (*latencies, *bar_delivery_lags):
                    raise ValueError(f"unexpected feed or event type at line {line_number}")
                session_id = record.get("sessionId")
                if session_id is None:
                    counts["eventsWithoutSessionId"] += 1
                if session_id != current_session:
                    current_session = session_id
                    previous_sequence = None
                    bids.clear()
                    asks.clear()
                    book_initialized = False
                    counts["sessions"] += 1
                    session_book_resets += 1
                if record.get("streamSequence") is None:
                    counts["eventsWithoutStreamSequence"] += 1
                    previous_sequence = None
                else:
                    sequence = int(record["streamSequence"])
                    if previous_sequence is not None:
                        if sequence > previous_sequence + 1:
                            sequence_gaps += sequence - previous_sequence - 1
                        elif sequence <= previous_sequence:
                            sequence_regressions += 1
                    previous_sequence = sequence
                if event.get("S") != symbol:
                    continue
                received_ns = int(record["receivedAtNs"])
                if received_first is None:
                    received_first = received_ns
                if received_last is not None and received_ns < received_last:
                    raise ValueError(f"receipt time regressed at line {line_number}")
                received_last = received_ns
                # SOURCE: receivedAtNs is Unix time in nanoseconds; event.t is RFC 3339.
                # For bars, event.t marks the bar START, so this is delivery lag
                # relative to the start, never quote/network latency.
                delta = (received_ns - event_time_ns(event["t"])) / 1_000_000_000
                (latencies if kind in latencies else bar_delivery_lags)[kind].append(delta)
                counts[kind] += 1
                if kind == "q":
                    bid, ask = float(event["bp"]), float(event["ap"])
                    if not 0 < bid < ask:
                        invalid_quotes += 1
                    else:
                        # SOURCE: one basis point is 1/10,000 of the midpoint.
                        quote_spreads.append((ask - bid) / ((ask + bid) / 2) * 10_000)
                elif kind == "o":
                    if event.get("r") is True:
                        bids.clear()
                        asks.clear()
                        book_initialized = True
                        resets += 1
                    if not book_initialized:
                        updates_before_reset += 1
                        continue
                    for side, levels in ((bids, event.get("b", [])), (asks, event.get("a", []))):
                        for level in levels:
                            price, size = float(level["p"]), float(level["s"])
                            if size == 0:
                                side.pop(price, None)
                            else:
                                side[price] = size
                    if bids and asks:
                        best_bid, best_ask = max(bids), min(asks)
                        if best_bid >= best_ask:
                            crossed_books += 1
                        else:
                            book_spreads.append((best_ask - best_bid) / ((best_ask + best_bid) / 2) * 10_000)
                elif kind in bar_delivery_lags:
                    open_price, high, low, close = (float(event[field]) for field in ("o", "h", "l", "c"))
                    if not (0 < low <= min(open_price, close) <= max(open_price, close) <= high):
                        invalid_bars += 1
    return {
        "paths": [str(item) for item in paths],
        "symbol": symbol,
        "events": dict(counts),
        "streamSequenceGaps": sequence_gaps,
        "streamSequenceRegressions": sequence_regressions,
        "bookResetsOnSocketSessionChange": session_book_resets,
        "first_received_ns": received_first,
        "last_received_ns": received_last,
        "event_to_receipt_seconds_by_type": {kind: summary(values) for kind, values in latencies.items()},
        "bar_start_to_receipt_seconds_by_type": {kind: summary(values) for kind, values in bar_delivery_lags.items()},
        "quote_spread_bps": summary(quote_spreads),
        "reconstructed_book_spread_bps": summary(book_spreads),
        "full_book_resets": resets,
        "book_updates_before_reset": updates_before_reset,
        "crossed_book_events": crossed_books,
        "invalid_quote_events": invalid_quotes,
        "invalid_bar_events": invalid_bars,
        "scope": "Descriptive feed-integrity sample. The VPS reports NTP synchronization, but exchange and VPS clock offsets are not independently calibrated; deltas are not one-way network latency. No fill or profitability inference.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", nargs="+", type=Path)
    parser.add_argument("--symbol", default="BTC/USD")
    args = parser.parse_args()
    print(json.dumps(audit(args.capture, args.symbol), indent=2))


if __name__ == "__main__":
    main()
