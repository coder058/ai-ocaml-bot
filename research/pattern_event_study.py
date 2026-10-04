"""Descriptive next-bar rates for Pattern Forge shapes on Alpaca US BTC bars.

The output is a feature audit, not a strategy, fill model or trading policy.
Only adjacent, fully closed five-minute bars enter any label or indicator.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# SOURCE: Pattern Forge app/marketAnalysis.ts defines these display periods.
FAST_PERIOD = 20
SLOW_PERIOD = 50
# GUESS: # UNCALIBRATED GUESS — copied from Pattern Forge's exploratory
# geometric display rules, not learned as predictive thresholds.
DOJI_RATIO = 0.1
WICK_RATIO = 2.0
# GUESS: # UNCALIBRATED GUESS — the next 5-minute bar is the declared
# exploratory label horizon; it is not a recommended holding period.
STEP = timedelta(minutes=5)
# GUESS: # UNCALIBRATED GUESS — freeze a chronological split before seeing
# this study's rates. A single partial-year holdout remains weak evidence.
HOLDOUT_START = datetime(2026, 7, 1, tzinfo=timezone.utc)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def shapes(previous: dict | None, current: dict) -> list[str]:
    op, hi, lo, cl = (float(current[key]) for key in ("o", "h", "l", "c"))
    body = abs(cl - op)
    extent = hi - lo
    lower = min(op, cl) - lo
    upper = hi - max(op, cl)
    result = []
    if extent > 0 and body / extent <= DOJI_RATIO:
        result.append("Doji")
    if body > 0 and lower >= WICK_RATIO * body and upper <= body:
        result.append("Hammer shape")
    if body > 0 and upper >= WICK_RATIO * body and lower <= body:
        result.append("Shooting-star shape")
    if previous is not None:
        po, pc = float(previous["o"]), float(previous["c"])
        if pc < po and cl > op and op <= pc and cl >= po:
            result.append("Bullish engulfing")
        if pc > po and cl < op and op >= pc and cl <= po:
            result.append("Bearish engulfing")
    return result


def study(document: dict) -> dict:
    if document.get("symbol") != "BTC/USD" or document.get("timeframe") != "5Min":
        raise ValueError("expected Alpaca BTC/USD five-minute bars")
    bars = document["bars"]
    times = [parse_time(bar["t"]) for bar in bars]
    if times != sorted(set(times)):
        raise ValueError("bar timestamps are unsorted or duplicated")
    buckets: dict[str, list[float]] = defaultdict(list)
    ema_fast = ema_slow = None
    seed: list[float] = []
    gap_resets = 0
    eligible = 0
    for index, bar in enumerate(bars):
        current_time = times[index]
        if index and current_time - times[index - 1] != STEP:
            seed = []
            ema_fast = ema_slow = None
            gap_resets += 1
        close = float(bar["c"])
        seed.append(close)
        if len(seed) == FAST_PERIOD:
            ema_fast = sum(seed) / FAST_PERIOD
        elif len(seed) > FAST_PERIOD:
            # SOURCE: standard EMA recurrence, matching Pattern Forge.
            ema_fast = (close - ema_fast) * (2 / (FAST_PERIOD + 1)) + ema_fast
        if len(seed) == SLOW_PERIOD:
            ema_slow = sum(seed) / SLOW_PERIOD
        elif len(seed) > SLOW_PERIOD:
            ema_slow = (close - ema_slow) * (2 / (SLOW_PERIOD + 1)) + ema_slow
        if index + 1 == len(bars) or times[index + 1] - current_time != STEP:
            continue
        next_close = float(bars[index + 1]["c"])
        if close <= 0 or next_close <= 0:
            raise ValueError("non-positive close")
        forward_bps = (next_close / close - 1) * 10_000  # SOURCE: bps definition.
        prior = bars[index - 1] if index and current_time - times[index - 1] == STEP else None
        period = "holdout" if current_time >= HOLDOUT_START else "development"
        trend = ("rising" if ema_fast is not None and ema_slow is not None
                 and close > ema_fast > ema_slow else
                 "falling" if ema_fast is not None and ema_slow is not None
                 and close < ema_fast < ema_slow else "mixed_or_warming")
        labels = ["all bars", f"Murphy trend: {trend}"] + shapes(prior, bar)
        for label in labels:
            buckets[f"{period}|{label}"].append(forward_bps)
        eligible += 1
    return {
        "source": document.get("source"),
        "retrievedAt": document.get("retrievedAt"),
        "bars": len(bars), "eligibleAdjacentLabels": eligible,
        "gapResets": gap_resets,
        "declaredHoldoutStart": HOLDOUT_START.isoformat(),
        "groups": [{"period": key.split("|", 1)[0], "feature": key.split("|", 1)[1],
                    "n": len(values), "upRate": sum(value > 0 for value in values) / len(values),
                    "meanForwardMidpointBps": sum(values) / len(values)}
                   for key, values in sorted(buckets.items())],
        "scope": "Exploratory next-close midpoint frequencies, not calibrated probabilities of profitable fills. Historical bars may be revised; overlapping shapes, serial dependence, costs and selection bias remain. No order decision follows.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bar_file", type=Path)
    args = parser.parse_args()
    print(json.dumps(study(json.loads(args.bar_file.read_text(encoding="utf-8"))), indent=2))
