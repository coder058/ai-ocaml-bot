"""As-received taker-flow screen with quote-side execution and modeled fees.

Research only: it has no broker credentials or order imports. Flow uses the
provider's taker-side field and receipt time, not later bar revisions. A
training-period threshold is frozen before each chronological test day.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

# SOURCE: Alpaca crypto trade schema defines tks as taker side B (buyer) or S
# (seller): https://docs.alpaca.markets/us/docs/real-time-crypto-pricing-data
# SOURCE: Alpaca tier-one crypto taker fee, verified 2026-09-29:
# https://docs.alpaca.markets/us/docs/crypto-fees
TAKER_FEE_RATE = 0.0025
# SOURCE: Unix timestamps and UTC calendar minute/day lengths.
NS_PER_SECOND = 1_000_000_000
MINUTE_NS = 60 * NS_PER_SECOND
DAY_NS = 86_400 * NS_PER_SECOND
# SOURCE: user's previously specified analysis horizons: 1m, 5m, 30m.
HORIZONS_MINUTES = (1, 5, 30)
# GUESS: # UNCALIBRATED GUESS — top decile is an exploratory training-only
# selection rule, not a tuned or validated trading threshold.
TRAINING_TAIL_SHARE = 0.90
# SOURCE: one basis point equals one ten-thousandth of relative price change.
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


def load_events(paths: list[Path], symbol: str = "BTC/USD") -> tuple[list[dict], list[dict], dict]:
    """Load received-time quotes and aggregate trade flow into UTC minutes."""
    quote_events: list[dict] = []
    flow_by_minute: dict[int, dict] = defaultdict(
        lambda: {"buyNotional": 0.0, "sellNotional": 0.0,
                 "tradeCount": 0, "unknownSideCount": 0}
    )
    counts: Counter[str] = Counter()
    prior_received_ns: int | None = None
    for path in paths:
        source_context = gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")
        with source_context as source:
            for raw_line in source:
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError as error:
                    if not raw_line.endswith(b"\n"):
                        counts["partialFinalLinesIgnored"] += 1
                        continue
                    raise ValueError(f"invalid complete JSON line in {path}") from error
                event = record.get("event", {})
                if event.get("S") != symbol or event.get("T") not in ("q", "t"):
                    continue
                received_ns = int(record["receivedAtNs"])
                if prior_received_ns is not None and received_ns < prior_received_ns:
                    raise ValueError("receipt timestamps regressed across capture files")
                prior_received_ns = received_ns
                kind = event["T"]
                counts[f"event_{kind}"] += 1
                if kind == "q":
                    bid, ask = float(event["bp"]), float(event["ap"])
                    if math.isfinite(bid) and math.isfinite(ask) and 0 < bid < ask:
                        quote_events.append({"receivedNs": received_ns,
                                             "eventNs": epoch_ns(str(event["t"])),
                                             "bid": bid, "ask": ask})
                    else:
                        counts["invalidQuotes"] += 1
                    continue
                price, size = float(event["p"]), float(event["s"])
                side = event.get("tks")
                if not (math.isfinite(price) and math.isfinite(size)
                        and price > 0 and size > 0):
                    counts["invalidTrades"] += 1
                    continue
                minute = received_ns // MINUTE_NS
                aggregate = flow_by_minute[minute]
                aggregate["tradeCount"] += 1
                notional = price * size
                if side == "B":
                    aggregate["buyNotional"] += notional
                elif side == "S":
                    aggregate["sellNotional"] += notional
                else:
                    aggregate["unknownSideCount"] += 1
                    counts["tradesWithUnknownTakerSide"] += 1

    samples = []
    for minute, aggregate in sorted(flow_by_minute.items()):
        total = aggregate["buyNotional"] + aggregate["sellNotional"]
        signed = aggregate["buyNotional"] - aggregate["sellNotional"]
        samples.append({"minute": minute, "decisionNs": (minute + 1) * MINUTE_NS,
                        "buyNotional": aggregate["buyNotional"],
                        "sellNotional": aggregate["sellNotional"],
                        "tradeCount": aggregate["tradeCount"],
                        "unknownSideCount": aggregate["unknownSideCount"],
                        "knownSideNotional": total,
                        "imbalance": signed / total if total else None})
    quote_events.sort(key=lambda quote: quote["receivedNs"])
    return quote_events, samples, dict(counts)


def quantile(values: list[float], share: float) -> float:
    if not values:
        raise ValueError("training flow sample is empty")
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * share) - 1))
    return ordered[rank]


def simulate(samples: list[dict], quotes: list[dict], horizon_minutes: int,
             threshold: float | None = None) -> dict:
    """Execute non-overlapping long samples at ask, mark exits at bid."""
    if not quotes:
        raise ValueError("screen requires valid executable quote events")
    quote_times = [quote["receivedNs"] for quote in quotes]
    equity = 1.0  # SOURCE: normalized unit capital for relative comparison only.
    returns: list[float] = []
    entry_delays_ms: list[float] = []
    exit_delays_ms: list[float] = []
    selected = skipped_overlap = skipped_quote = skipped_incomplete = 0
    next_allowed_ns = 0
    day_id = samples[0]["decisionNs"] // DAY_NS if samples else None
    for sample in samples:
        if day_id is not None and sample["decisionNs"] // DAY_NS != day_id:
            continue
        imbalance = sample["imbalance"]
        if imbalance is None or imbalance <= 0:
            continue
        if threshold is not None and imbalance < threshold:
            continue
        selected += 1
        if sample["decisionNs"] < next_allowed_ns:
            skipped_overlap += 1
            continue
        entry_index = bisect_right(quote_times, sample["decisionNs"])
        target_ns = sample["decisionNs"] + horizon_minutes * MINUTE_NS
        exit_index = bisect_left(quote_times, target_ns)
        if entry_index >= len(quotes) or exit_index >= len(quotes):
            skipped_quote += 1
            continue
        entry, exit_quote = quotes[entry_index], quotes[exit_index]
        if (entry["receivedNs"] // DAY_NS != day_id
                or exit_quote["receivedNs"] // DAY_NS != day_id):
            skipped_incomplete += 1
            continue
        factor = (exit_quote["bid"] / entry["ask"]
                  * (1 - TAKER_FEE_RATE) ** 2)
        returns.append((factor - 1) * BPS)
        equity *= factor
        entry_delays_ms.append((entry["receivedNs"] - sample["decisionNs"]) / 1_000_000)
        exit_delays_ms.append((exit_quote["receivedNs"] - target_ns) / 1_000_000)
        next_allowed_ns = exit_quote["receivedNs"]
    return {
        "positiveFlowSamplesSelected": selected,
        "completedNonOverlappingRoundTrips": len(returns),
        "skippedOverlappingSignals": skipped_overlap,
        "skippedNoQuote": skipped_quote,
        "skippedIncompleteSameDayHorizon": skipped_incomplete,
        "meanNetBps": sum(returns) / len(returns) if returns else None,
        "medianNetBps": median(returns) if returns else None,
        "positiveNetShare": sum(value > 0 for value in returns) / len(returns) if returns else None,
        "compoundedNormalizedReturnPct": (equity - 1) * 100,
        "entryQuoteDelayMsMedian": median(entry_delays_ms) if entry_delays_ms else None,
        "exitQuoteDelayMsMedian": median(exit_delays_ms) if exit_delays_ms else None,
        "maxEntryQuoteDelayMs": max(entry_delays_ms) if entry_delays_ms else None,
        "maxExitQuoteDelayMs": max(exit_delays_ms) if exit_delays_ms else None,
    }


def simulate_signed_direction(samples: list[dict], quotes: list[dict],
                              horizon_minutes: int) -> dict:
    """Diagnose whether flow sign predicts direction; shorts are hypothetical."""
    if not quotes:
        raise ValueError("screen requires valid executable quote events")
    quote_times = [quote["receivedNs"] for quote in quotes]
    equity = 1.0  # SOURCE: normalized unit capital for relative comparison only.
    returns: list[float] = []
    long_count = short_count = skipped_overlap = skipped_quote = 0
    next_allowed_ns = 0
    day_id = samples[0]["decisionNs"] // DAY_NS if samples else None
    for sample in samples:
        if day_id is not None and sample["decisionNs"] // DAY_NS != day_id:
            continue
        imbalance = sample["imbalance"]
        if imbalance is None or imbalance == 0:
            continue
        if sample["decisionNs"] < next_allowed_ns:
            skipped_overlap += 1
            continue
        entry_index = bisect_right(quote_times, sample["decisionNs"])
        target_ns = sample["decisionNs"] + horizon_minutes * MINUTE_NS
        exit_index = bisect_left(quote_times, target_ns)
        if entry_index >= len(quotes) or exit_index >= len(quotes):
            skipped_quote += 1
            continue
        entry, exit_quote = quotes[entry_index], quotes[exit_index]
        if (entry["receivedNs"] // DAY_NS != day_id
                or exit_quote["receivedNs"] // DAY_NS != day_id):
            continue
        if imbalance > 0:
            # SOURCE: a long enters at ask and exits at bid.
            factor = exit_quote["bid"] / entry["ask"] * (1 - TAKER_FEE_RATE) ** 2
            long_count += 1
        else:
            # PLACEHOLDER: short trades are a directional diagnostic only; this
            # account's short-sale support, borrow, and funding are not modeled.
            factor = entry["bid"] / exit_quote["ask"] * (1 - TAKER_FEE_RATE) ** 2
            short_count += 1
        returns.append((factor - 1) * BPS)
        equity *= factor
        next_allowed_ns = exit_quote["receivedNs"]
    return {
        "completedNonOverlappingRoundTrips": len(returns),
        "longTrades": long_count,
        "hypotheticalShortTrades": short_count,
        "skippedOverlappingSignals": skipped_overlap,
        "skippedNoQuote": skipped_quote,
        "meanNetBps": sum(returns) / len(returns) if returns else None,
        "medianNetBps": median(returns) if returns else None,
        "positiveNetShare": sum(value > 0 for value in returns) / len(returns) if returns else None,
        "compoundedNormalizedReturnPct": (equity - 1) * 100,
    }


def evaluate(quotes: list[dict], samples: list[dict], counts: dict,
             symbol: str = "BTC/USD",
             horizons: tuple[int, ...] = HORIZONS_MINUTES) -> dict:
    days = sorted({sample["decisionNs"] // DAY_NS for sample in samples})
    folds = []
    for test_day in days[1:]:
        training = [sample for sample in samples
                    if sample["decisionNs"] // DAY_NS < test_day
                    and sample["imbalance"] is not None and sample["imbalance"] > 0]
        test = [sample for sample in samples
                if sample["decisionNs"] // DAY_NS == test_day]
        if not training or not test:
            continue
        threshold = quantile([sample["imbalance"] for sample in training], TRAINING_TAIL_SHARE)
        training_selected = [sample for sample in training if sample["imbalance"] >= threshold]
        day_quotes = [quote for quote in quotes if quote["receivedNs"] // DAY_NS == test_day]
        if not day_quotes:
            continue
        test_date = datetime.fromtimestamp(
            test_day * (DAY_NS // NS_PER_SECOND), timezone.utc
        ).date().isoformat()
        fold = {
            "trainingUtcDates": sorted({datetime.fromtimestamp(
                (sample["decisionNs"] // DAY_NS) * (DAY_NS // NS_PER_SECOND),
                timezone.utc).date().isoformat()
                for sample in samples if sample["decisionNs"] // DAY_NS < test_day}),
            "testUtcDate": test_date,
            "positiveTrainingFlowMinuteSamples": len(training),
            "frozenTraining90thPercentileThreshold": threshold,
            "trainingDistinctPositiveImbalanceValues": len({
                sample["imbalance"] for sample in training
            }),
            "trainingSelectionShareAfterRetainingThresholdTies": (
                len(training_selected) / len(training)
            ),
            "testFlowMinuteSamples": len(test),
            "byHorizon": {},
        }
        for horizon in horizons:
            positive = simulate(test, day_quotes, horizon)
            selected = simulate(test, day_quotes, horizon, threshold)
            directional = simulate_signed_direction(test, day_quotes, horizon)
            first_quote, last_quote = day_quotes[0], day_quotes[-1]
            # SOURCE: executable buy-at-ask/sell-at-bid comparison with a fee on
            # both sides, using the same captured test-day window.
            buy_hold_pct = ((last_quote["bid"] / first_quote["ask"]
                             * (1 - TAKER_FEE_RATE) ** 2) - 1) * 100
            fold["byHorizon"][f"{horizon}m"] = {
                "allPositiveFlow": positive,
                "trainingQuantilePositiveFlow": selected,
                "signedFlowDirectionDiagnostic": directional,
                "wholeTestWindowBuyHoldNetPct": buy_hold_pct,
            }
        folds.append(fold)
    return {
        "symbol": symbol,
        "captureCounts": counts,
        "quoteEvents": len(quotes),
        "tradeFlowMinuteSamples": len(samples),
        "thresholdQuantile": TRAINING_TAIL_SHARE,
        "thresholdRule": "training-only empirical 90th percentile of positive buyer-signed minute notional imbalance; all ties at threshold are retained",
        "folds": folds,
        "executionModel": "first captured quote at/after minute-close signal; buy at ask, sell at bid at/after fixed horizon; tier-one taker fee each leg",
        "limitations": "Exploratory repeated-use data, not an untouched validation set. Immediate captured quote fills omit broker submission latency, acceptance, queue, partial fills and impact. The signed-flow diagnostic assumes hypothetical short trades without checking account support, borrow or funding. Receipt-time bins avoid exchange-time lookahead but do not establish a causal fill. No result grants order authority or proves live profitability.",
    }


def audit(paths: list[Path], symbol: str = "BTC/USD") -> dict:
    quotes, samples, counts = load_events(paths, symbol)
    result = evaluate(quotes, samples, counts, symbol)
    result["files"] = [str(path) for path in paths]
    result["scope"] = "Read-only research; no broker credentials or order imports."
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", nargs="+", type=Path)
    parser.add_argument("--symbol", default="BTC/USD")
    args = parser.parse_args()
    print(json.dumps(audit(args.capture, args.symbol), indent=2))


if __name__ == "__main__":
    main()
