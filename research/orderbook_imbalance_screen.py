"""Chronological BTC top-of-book imbalance screen; no broker/order authority.

The feature is reconstructed from as-received Alpaca order-book deltas. A
training-period imbalance threshold is frozen before the latest UTC capture
day. Candidate exits use captured BTC quotes and the published taker fee. The
small current sample is exploratory and is not a promotion test.
"""

from __future__ import annotations

import gzip
import argparse
import json
import math
import re
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

# SOURCE: Alpaca's tier-one crypto taker fee, checked 2026-09-29:
# https://docs.alpaca.markets/us/docs/crypto-fees
TAKER_FEE_RATE = 0.0025
# SOURCE: UTC minute/day lengths and Unix nanosecond timestamps.
NS_PER_SECOND = 1_000_000_000
# SOURCE: one millisecond is 1,000,000 nanoseconds by definition.
NS_PER_MILLISECOND = 1_000_000
MINUTE_NS = 60 * NS_PER_SECOND
DAY_NS = 86_400 * NS_PER_SECOND
# SOURCE: the user requested 1m and 5m trading analysis horizons.
HORIZONS_MINUTES = (1, 5)
# GUESS: # UNCALIBRATED GUESS — top-decile positive imbalance is a screen only;
# later untouched sessions must validate any alternative threshold.
TRAINING_TAIL_SHARE = 0.90
# SOURCE: one basis point is 1/10,000 of relative price change.
BPS = 10_000


def epoch_ns(value: str) -> int:
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})",
        value,
    )
    if not match:
        raise ValueError("timestamp must be timezone-aware ISO-8601")
    offset = "+00:00" if match.group(3) == "Z" else match.group(3)
    instant = datetime.fromisoformat(match.group(1) + offset)
    fraction_ns = int((match.group(2) or "")[:9].ljust(9, "0") or "0")
    return int(instant.timestamp()) * NS_PER_SECOND + fraction_ns


def iso_from_epoch_ns(value: int) -> str:
    seconds, fraction_ns = divmod(value, NS_PER_SECOND)
    stamp = datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{stamp}.{fraction_ns:09d}Z"


def load_events(paths: list[Path]) -> tuple[list[tuple], list[tuple], dict]:
    """Rebuild first-seen BBO quotes and valid order-book imbalance events."""
    quotes: list[tuple] = []
    features: list[tuple] = []
    counts: Counter[str] = Counter()
    bids: dict[float, float] = {}
    asks: dict[float, float] = {}
    current_session = None
    book_initialized = False
    for path in paths:
        # SOURCE: gzip is the transport format used for archived VPS captures.
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as source:
            for raw_line in source:
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError as error:
                    if not raw_line.endswith(b"\n"):
                        counts["partialFinalLinesIgnored"] += 1
                        continue
                    raise ValueError(f"invalid complete JSON line in {path}") from error
                event = record.get("event", {})
                if event.get("S") != "BTC/USD":
                    continue
                kind = event.get("T")
                if kind not in ("q", "o"):
                    continue
                received_ns = int(record["receivedAtNs"])
                event_ns = epoch_ns(str(event["t"]))
                counts[f"event_{kind}"] += 1
                session_id = record.get("sessionId")
                if session_id is None:
                    counts["eventsWithoutSessionId"] += 1
                if session_id != current_session:
                    current_session = session_id
                    bids.clear()
                    asks.clear()
                    book_initialized = False
                    counts["sessionBoundariesObserved"] += 1
                if kind == "q":
                    bid, ask = float(event["bp"]), float(event["ap"])
                    if math.isfinite(bid) and math.isfinite(ask) and 0 < bid < ask:
                        quotes.append((received_ns, event_ns, bid, ask))
                    else:
                        counts["invalidQuotes"] += 1
                    continue

                if event.get("r") is True:
                    bids.clear()
                    asks.clear()
                    book_initialized = True
                    counts["fullBookResets"] += 1
                if not book_initialized:
                    counts["bookUpdatesBeforeReset"] += 1
                    continue
                valid_update = True
                for side, levels in ((bids, event.get("b", [])),
                                     (asks, event.get("a", []))):
                    for level in levels:
                        price, size = float(level["p"]), float(level["s"])
                        if not (math.isfinite(price) and math.isfinite(size)
                                and price > 0 and size >= 0):
                            valid_update = False
                            break
                        if size == 0:
                            side.pop(price, None)
                        else:
                            side[price] = size
                    if not valid_update:
                        break
                if not valid_update:
                    counts["invalidBookUpdates"] += 1
                    continue
                if not bids or not asks:
                    counts["emptyBooks"] += 1
                    continue
                best_bid, best_ask = max(bids), min(asks)
                bid_size, ask_size = bids[best_bid], asks[best_ask]
                if best_bid >= best_ask or bid_size + ask_size <= 0:
                    counts["crossedOrEmptyTop"] += 1
                    continue
                imbalance = (bid_size - ask_size) / (bid_size + ask_size)
                spread_bps = ((best_ask - best_bid) /
                              ((best_ask + best_bid) / 2) * BPS)
                features.append((received_ns, event_ns, imbalance, spread_bps))
    quotes.sort(key=lambda row: row[0])
    features.sort(key=lambda row: row[0])
    return quotes, features, dict(counts)


def minute_samples(features: list[tuple]) -> list[dict]:
    """Use the final book feature received inside each UTC minute, at its close."""
    latest_by_slot = {}
    for received_ns, _event_ns, imbalance, spread_bps in features:
        slot = received_ns // MINUTE_NS
        latest_by_slot[slot] = (received_ns, imbalance, spread_bps)
    return [{"slot": slot,
             "decisionNs": (slot + 1) * MINUTE_NS,
             "featureReceivedNs": row[0],
             "imbalance": row[1],
             "spreadBps": row[2]}
            for slot, row in sorted(latest_by_slot.items())]


def quantile(values: list[float], share: float) -> float:
    if not values:
        raise ValueError("training imbalance sample is empty")
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * share) - 1))
    return ordered[rank]


def screen(samples: list[dict], quotes: list[tuple],
           horizons: tuple[int, ...] = HORIZONS_MINUTES,
           holdout_after: str | None = None,
           entry_latency_ms: float = 0.0) -> dict:
    if not samples or not quotes:
        raise ValueError("screen requires book samples and executable quotes")
    if not math.isfinite(entry_latency_ms) or entry_latency_ms < 0:
        raise ValueError("entry latency must be finite and nonnegative")
    days = sorted({sample["decisionNs"] // DAY_NS for sample in samples})
    if len(days) < 2:
        raise ValueError("need earlier training days and a later holdout day")
    train_day_ids, test_day = days[:-1], days[-1]
    holdout_after_ns = epoch_ns(holdout_after) if holdout_after else None
    if holdout_after_ns is not None and holdout_after_ns // DAY_NS != test_day:
        raise ValueError("holdout cutoff must be on the latest capture UTC date")
    train = [sample for sample in samples
             if sample["decisionNs"] // DAY_NS in train_day_ids
             and sample["imbalance"] > 0]
    threshold = quantile([sample["imbalance"] for sample in train], TRAINING_TAIL_SHARE)
    test = [sample for sample in samples
            if sample["decisionNs"] // DAY_NS == test_day
            and (holdout_after_ns is None or sample["decisionNs"] > holdout_after_ns)]
    quote_times = [quote[0] for quote in quotes]
    entry_delay_ns = round(entry_latency_ms * NS_PER_MILLISECOND)
    results = {}
    for horizon in horizons:
        equity = 1.0  # SOURCE: normalized unit capital for a relative comparison.
        trade_returns = []
        gross_trade_returns = []
        trades = []
        eligible = selected = skipped_overlap = skipped_quotes = 0
        next_allowed_ns = 0
        for sample in test:
            if ((sample["slot"] + 1) % horizon) != 0:
                continue
            eligible += 1
            if sample["imbalance"] < threshold:
                continue
            selected += 1
            if sample["decisionNs"] < next_allowed_ns:
                skipped_overlap += 1
                continue
            entry_index = bisect_right(
                quote_times, sample["decisionNs"] + entry_delay_ns
            )
            if entry_index >= len(quotes):
                skipped_quotes += 1
                continue
            entry = quotes[entry_index]
            exit_target_ns = entry[0] + horizon * MINUTE_NS
            # SOURCE: an exit quote at the target time is valid for the fixed horizon.
            exit_index = bisect_left(quote_times, exit_target_ns)
            if exit_index >= len(quotes):
                skipped_quotes += 1
                continue
            exit_quote = quotes[exit_index]
            if (entry[0] // DAY_NS != test_day or exit_quote[0] // DAY_NS != test_day):
                skipped_quotes += 1
                continue
            gross_factor = exit_quote[2] / entry[3]
            gross_bps = (gross_factor - 1) * BPS
            net_factor = gross_factor * (1 - TAKER_FEE_RATE) ** 2
            net_bps = (net_factor - 1) * BPS
            equity *= net_factor
            gross_trade_returns.append(gross_bps)
            trade_returns.append(net_bps)
            trades.append({
                "signalAtUtc": iso_from_epoch_ns(sample["decisionNs"]),
                "topBookImbalance": sample["imbalance"],
                "entryQuoteReceivedAtUtc": iso_from_epoch_ns(entry[0]),
                "entryAskUsd": entry[3],
                "entryQuoteDelayFromSignalMs": (entry[0] - sample["decisionNs"])
                    / NS_PER_MILLISECOND,
                "exitQuoteReceivedAtUtc": iso_from_epoch_ns(exit_quote[0]),
                "exitBidUsd": exit_quote[2],
                "grossBpsAfterSpreadBeforeFees": gross_bps,
                "netBpsAfterModeledFees": net_bps,
            })
            next_allowed_ns = exit_quote[0]
        results[f"{horizon}m"] = {
            "eligibleHoldoutSamples": eligible,
            "trainingThreshold": threshold,
            "selectedTopPositiveImbalanceSamples": selected,
            "executedNonOverlappingPaperTrades": len(trade_returns),
            "skippedOverlappingSignals": skipped_overlap,
            "skippedUnavailableQuotes": skipped_quotes,
            "meanGrossBpsAfterSpreadBeforeFees": sum(gross_trade_returns) / len(gross_trade_returns)
                if gross_trade_returns else None,
            "medianGrossBpsAfterSpreadBeforeFees": median(gross_trade_returns)
                if gross_trade_returns else None,
            "positiveGrossTradeShareAfterSpread": sum(value > 0 for value in gross_trade_returns)
                / len(gross_trade_returns) if gross_trade_returns else None,
            "meanNetBpsPerTrade": sum(trade_returns) / len(trade_returns)
                if trade_returns else None,
            "medianNetBpsPerTrade": median(trade_returns) if trade_returns else None,
            "positiveNetTradeShare": sum(value > 0 for value in trade_returns) / len(trade_returns)
                if trade_returns else None,
            "compoundedNormalizedReturnPct": (equity - 1) * 100,
            "trades": trades,
        }
    return {
        "trainingUtcDates": [datetime.fromtimestamp(
                                 day * (DAY_NS // NS_PER_SECOND), timezone.utc
                             ).date().isoformat()
                             for day in train_day_ids],
        "holdoutUtcDate": datetime.fromtimestamp(
                              test_day * (DAY_NS // NS_PER_SECOND), timezone.utc
                          ).date().isoformat(),
        "holdoutAfterUtc": holdout_after,
        "entryLatencyMs": entry_latency_ms,
        "trainingPositiveImbalanceSamples": len(train),
        "thresholdQuantile": TRAINING_TAIL_SHARE,
        "thresholdRule": "training-period 90th percentile of positive top-level size imbalance",
        "holdoutSamples": len(test),
        "byHorizon": results,
        "executionModel": "buy at first ask strictly after decision plus configured entry latency, sell at first quote at or after the horizon from that entry, tier-one taker fee each side; no candidate-specific fill probability, order impact or shorting",
        "limitation": "The latest UTC date is a short, already-inspected capture interval. Top-of-book size imbalance is a screening feature; overlapping market regimes, unknown queue position and paper-to-live execution gap remain. No positive screen establishes an edge or order authority.",
    }


def audit(paths: list[Path], holdout_after: str | None = None,
          entry_latency_ms: float = 0.0) -> dict:
    quotes, features, counts = load_events(paths)
    samples = minute_samples(features)
    result = screen(samples, quotes, holdout_after=holdout_after,
                    entry_latency_ms=entry_latency_ms)
    return {
        "files": [str(path) for path in paths],
        "captureCounts": counts,
        "quoteSamples": len(quotes),
        "usableBookFeatureEvents": len(features),
        "utcMinuteSamples": len(samples),
        "screen": result,
        "scope": "Read-only point-in-time market-data screen; it has no credentials or order imports.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", nargs="+", type=Path)
    parser.add_argument(
        "--holdout-after",
        help="include only latest-date sample decisions strictly after this timezone-aware ISO-8601 UTC cutoff",
    )
    # SOURCE: zero-delay is reported only as an optimistic baseline comparison.
    parser.add_argument(
        "--entry-latency-ms", type=float, default=0.0,
        help="delay between the signal boundary and earliest executable entry quote; pass an observed latency",
    )
    args = parser.parse_args()
    print(json.dumps(audit(args.capture, args.holdout_after,
                           args.entry_latency_ms), indent=2))


if __name__ == "__main__":
    main()
