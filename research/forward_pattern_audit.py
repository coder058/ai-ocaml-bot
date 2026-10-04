"""Audit first-observed pattern features against later actual candle outcomes.

These are price-movement labels, NOT fills, trades, P&L or winning probabilities.
Entry is the open of the first whole candle starting after observation; no price
from the signal candle can be an entry. Missing horizon candles reject a label.
All comparisons remain exploratory and have no order authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# SOURCE: user's requested native frames, expressed in seconds per minute/hour.
FRAME_SECONDS = {"1m": 60, "5m": 5 * 60, "30m": 30 * 60,
                 "1h": 60 * 60, "4h": 4 * 60 * 60}
# SOURCE: one basis point is 1/10,000 of a relative price movement.
BPS = 10_000


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone-aware timestamps required")
    return parsed.timestamp()


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def observation(record):
    frame = record.get("frame")
    if frame not in FRAME_SECONDS:
        raise ValueError("Unsupported frame")
    reading = record["reading"]
    suite = reading.get("technicalSuite", {})
    evidence = reading.get("technicalEvidence", {})
    candle = evidence.get("lastCandle") or (suite.get("bars") or [None])[-1]
    if not candle:
        return None
    observed = instant(record["observedAt"])
    start = instant(candle["t"])
    step = FRAME_SECONDS[frame]
    op, hi, lo, close, volume = (float(candle[k]) for k in ("o", "h", "l", "c", "v"))
    if (start % step or start + step > observed or
            not all(math.isfinite(v) for v in (op, hi, lo, close, volume)) or
            not 0 < lo <= min(op, close) <= max(op, close) <= hi or volume < 0):
        raise ValueError("Invalid or not yet closed candle")
    # SOURCE: older forward records contain the full suite; newer ones contain
    # only first-observed features. Neither is reconstructed from today's cache.
    patterns = evidence.get("patternValues")
    if patterns is None:
        patterns = {name: row.get("value") for name, row in suite.get("patterns", {}).items()}
    if not isinstance(patterns, dict) or any(value is not None and
            (not isinstance(value, int) or isinstance(value, bool)) for value in patterns.values()):
        raise ValueError("Invalid pattern features")
    return {"venue": record["venue"], "symbol": record["symbol"], "frame": frame,
            "start": start, "observed": observed, "o": op, "c": close,
            "patterns": patterns, "status": reading.get("status"),
            "source": evidence.get("source") or suite.get("source")}


def read_journal(path):
    """Stream a frozen file prefix; ignore only an unfinished final append."""
    first = {}
    counts = Counter()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        size = path.stat().st_size
        while source.tell() < size:
            raw = source.readline(size - source.tell())
            digest.update(raw)
            if not raw.endswith(b"\n"):
                counts["partialFinalLine"] += 1
                break
            counts["lines"] += 1
            try:
                row = observation(json.loads(raw))
                if row is None:
                    counts["withoutTechnicalCandle"] += 1
                    continue
            except (ValueError, KeyError, TypeError, OverflowError):
                counts["invalidRecords"] += 1
                continue
            key = (row["venue"], row["symbol"], row["frame"], row["start"])
            prior = first.get(key)
            if prior is not None:
                counts["duplicates"] += 1
            # SOURCE: preserve the earliest actual observation, even if it had
            # no pattern values. Later historical revisions cannot create alpha.
            if prior is None or row["observed"] < prior["observed"]:
                first[key] = row
    return list(first.values()), {**dict(counts), "uniqueCandles": len(first),
                                  "inputBytes": size, "sha256": digest.hexdigest()}


def labels(rows, horizon_bars, split_at):
    if isinstance(horizon_bars, bool) or not isinstance(horizon_bars, int) or horizon_bars <= 0:
        raise ValueError("Explicit positive integer horizon required")
    grouped = defaultdict(dict)
    for row in rows:
        key = (row["venue"], row["symbol"], row["frame"])
        grouped[key][row["start"]] = row
    rejected = Counter()
    outcomes = []
    for key, candles in grouped.items():
        step = FRAME_SECONDS[key[-1]]
        for row in sorted(candles.values(), key=lambda r: r["observed"]):
            if row["status"] not in ("ready", "candidate"):
                rejected["signalNotReady"] += 1
                continue
            if not any(value is not None for value in row["patterns"].values()):
                rejected["noFirstObservedPatternValues"] += 1
                continue
            # SOURCE: next full future candle, not the current already-open one.
            entry_at = (math.floor(row["observed"] / step) + 1) * step
            required = [entry_at + offset * step for offset in range(horizon_bars)]
            if any(start not in candles for start in required):
                rejected["missingFutureHorizonCandles"] += 1
                continue
            future = [candles[start] for start in required]
            # SOURCE: a future bar can only label a prior observation when it
            # was received later, with the entire horizon present and closed.
            if any(part["observed"] <= row["observed"] for part in future):
                rejected["futureCandleReceiptBeforeSignal"] += 1
                continue
            exit_at = required[-1] + step
            outcome_known = max(part["observed"] for part in future)
            if row["observed"] < split_at <= max(exit_at, outcome_known):
                rejected["crossesChronologicalSplit"] += 1
                continue
            fold = "discovery" if row["observed"] < split_at else "validation"
            outcomes.append({**row, "fold": fold, "entryAt": utc(entry_at),
                "exitAt": utc(exit_at), "outcomeKnownAt": utc(outcome_known),
                "grossLongMoveBps": (future[-1]["c"] / future[0]["o"] - 1) * BPS})
    return outcomes, dict(rejected)


def summary(values):
    if not values:
        return {"count": 0, "meanGrossMoveBps": None, "positiveFraction": None}
    return {"count": len(values), "meanGrossMoveBps": sum(values) / len(values),
            "positiveFraction": sum(value > 0 for value in values) / len(values)}


def report(rows, horizon_bars, split_at):
    outcomes, rejected = labels(rows, horizon_bars, split_at)
    controls = defaultdict(list)
    signals = defaultdict(list)
    for row in outcomes:
        key = (row["venue"], row["symbol"], row["frame"], row["fold"])
        controls[key].append(row["grossLongMoveBps"])
        for name, value in row["patterns"].items():
            if value:
                # GUESS: # UNCALIBRATED GUESS — mechanically interpret a signed
                # pattern code as direction to test, never as a calibrated edge.
                # Several candle formations describe indecision, not direction.
                direction = "positive_code" if value > 0 else "negative_code"
                signs = 1 if value > 0 else -1
                signals[(*key, name, direction)].append(signs * row["grossLongMoveBps"])
    comparisons = []
    for key, values in sorted(signals.items()):
        venue, symbol, frame, fold, name, direction = key
        sign = 1 if direction == "positive_code" else -1
        baseline = summary([sign * value for value in controls[key[:4]]])
        measured = summary(values)
        comparisons.append({"venue": venue, "symbol": symbol, "frame": frame,
            "fold": fold, "pattern": name, "codeDirection": direction,
            "patternLabels": measured, "sameMarketFrameFoldBaseline": baseline,
            "grossDifferenceFromBaselineBps": measured["meanGrossMoveBps"] - baseline["meanGrossMoveBps"]})
    return {"schema": "first_observed_pattern_audit_v1", "orderAuthority": False,
        "horizonBars": horizon_bars, "splitAt": utc(split_at), "labelCount": len(outcomes),
        "foldCounts": dict(Counter(row["fold"] for row in outcomes)), "rejected": rejected,
        "comparisonCount": len(comparisons), "comparisons": comparisons,
        "executionModel": None, "netPnl": None, "winProbability": None,
        "method": "Earliest journal features; next wholly future candle open to horizon close; exact contiguous future bars",
        "limits": ["Gross candle labels are not executable returns or paper fills",
            "No spread, fees, funding, slippage, latency, short availability or market impact model",
            "Positive fraction is an empirical price-label statistic, not calibrated winning probability",
            "Overlapping horizons and related markets are dependent observations",
            "All pattern comparisons are exploratory; no multiple-testing correction or policy selection",
            "Sparse equity/session gaps reject labels; no fabricated session candles",
            "Historical inputs loaded before receipt cannot produce retrospective signals",
            "Paper results do not establish live profitability"],
        "observationRange": {"from": utc(min(row["observed"] for row in rows)) if rows else None,
                             "to": utc(max(row["observed"] for row in rows)) if rows else None}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--horizon-bars", type=int, required=True)
    parser.add_argument("--split-at", required=True, help="Freeze this chronological boundary before interpreting validation")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    observed, provenance = read_journal(args.journal)
    result = report(observed, args.horizon_bars, instant(args.split_at))
    result["input"] = provenance
    result["generatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    args.output.write_text(json.dumps(result, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("labelCount", "foldCounts", "rejected", "comparisonCount", "observationRange", "input")}))
