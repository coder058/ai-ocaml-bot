"""Audit one-step candle-state transitions; never authorizes an order.

States use only the current and earlier fully closed Alpaca US BTC/USD 5m bars.
The evaluation interval was already inspected in earlier project research and
is therefore a reused, non-pristine holdout, not independent validation.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from pattern_event_study import (
    FAST_PERIOD,
    HOLDOUT_START,
    SLOW_PERIOD,
    STEP,
    parse_time,
    shapes,
)


def state(trend: str, previous: dict | None, current: dict) -> str:
    close = float(current["c"])
    prior_close = float(previous["c"]) if previous is not None else close
    direction = "up" if close > prior_close else "down" if close < prior_close else "flat"
    # SOURCE: Pattern Forge's existing geometric candle-shape definitions.
    pattern = ",".join(shapes(previous, current)) or "none"
    return "|".join((trend, direction, pattern))


def states_for_bars(document: dict) -> list[str | None]:
    """Compute each closed bar's state without looking at any later bar."""
    if document.get("symbol") != "BTC/USD" or document.get("timeframe") != "5Min":
        raise ValueError("expected Alpaca US BTC/USD five-minute bars")
    bars = document["bars"]
    times = [parse_time(bar["t"]) for bar in bars]
    if times != sorted(set(times)):
        raise ValueError("bar timestamps are unsorted or duplicated")
    result: list[str | None] = []
    seed: list[float] = []
    fast = slow = None
    for index, bar in enumerate(bars):
        if index and times[index] - times[index - 1] != STEP:
            seed = []
            fast = slow = None
        close = float(bar["c"])
        if close <= 0:
            raise ValueError("non-positive close")
        seed.append(close)
        if len(seed) == FAST_PERIOD:
            fast = sum(seed) / FAST_PERIOD
        elif len(seed) > FAST_PERIOD:
            # SOURCE: Pattern Forge's EMA recurrence.
            fast += (close - fast) * (2 / (FAST_PERIOD + 1))
        if len(seed) == SLOW_PERIOD:
            slow = sum(seed) / SLOW_PERIOD
        elif len(seed) > SLOW_PERIOD:
            # SOURCE: Pattern Forge's EMA recurrence.
            slow += (close - slow) * (2 / (SLOW_PERIOD + 1))
        if not index or times[index] - times[index - 1] != STEP:
            result.append(None)
            continue
        trend = (
            "rising" if fast is not None and slow is not None and close > fast > slow
            else "falling" if fast is not None and slow is not None and close < fast < slow
            else "mixed_or_warming"
        )
        result.append(state(trend, bars[index - 1], bar))
    return result


def observations(document: dict) -> list[tuple[str, bool, float, bool]]:
    states = states_for_bars(document)
    bars = document["bars"]
    times = [parse_time(bar["t"]) for bar in bars]
    result = []
    for index, key in enumerate(states[:-1]):
        if key is None or times[index + 1] - times[index] != STEP:
            continue
        close = float(bars[index]["c"])
        next_close = float(bars[index + 1]["c"])
        if next_close <= 0:
            raise ValueError("non-positive next close")
        # SOURCE: percentage change in basis points; the decision is at the
        # close of the current bar and the label is the next bar's close.
        forward_bps = (next_close / close - 1) * 10_000
        result.append((key, next_close > close, forward_bps,
                       times[index] >= HOLDOUT_START))
    return result


def audit(document: dict) -> dict:
    rows = observations(document)
    training = [row for row in rows if not row[3]]
    evaluation = [row for row in rows if row[3]]
    if not training or not evaluation:
        raise ValueError("both historical periods require adjacent labels")
    counts: dict[str, Counter[bool]] = defaultdict(Counter)
    for key, up, _, _ in training:
        counts[key][up] += 1
    base_rate = sum(up for _, up, _, _ in training) / len(training)
    predictions = [(counts[key][True] / sum(counts[key].values())
                    if key in counts else base_rate, up, fwd, key)
                   for key, up, fwd, _ in evaluation]
    brier = sum((p - up) ** 2 for p, up, _, _ in predictions) / len(predictions)
    baseline_brier = sum((base_rate - up) ** 2 for _, up, _, _ in predictions) / len(predictions)
    state_rows = []
    for key, transitions in sorted(counts.items()):
        matching = [fwd for _, _, fwd, state_key in predictions if state_key == key]
        state_rows.append({
            "state": key,
            "developmentCount": sum(transitions.values()),
            "developmentNextUpRate": transitions[True] / sum(transitions.values()),
            "reusedHoldoutCount": len(matching),
            "reusedHoldoutMeanForwardMidpointBps":
                sum(matching) / len(matching) if matching else None,
        })
    return {
        "source": document.get("source"),
        "retrievedAt": document.get("retrievedAt"),
        "label": "next adjacent five-minute midpoint close greater than current close",
        "developmentCount": len(training),
        "reusedHoldoutCount": len(evaluation),
        "developmentBaseUpRate": base_rate,
        "reusedHoldoutUpRate": sum(up for _, up, _, _ in predictions) / len(predictions),
        "reusedHoldoutMarkovBrier": brier,
        "reusedHoldoutConstantBaseBrier": baseline_brier,
        "reusedHoldoutMeanForwardMidpointBps":
            sum(fwd for _, _, fwd, _ in predictions) / len(predictions),
        # SOURCE: Alpaca US tier-one taker fee is 0.25% per side, or 50 bps
        # for a buy plus sell. This is an optimistic hurdle excluding spread.
        "reusedHoldoutForwardMovesAboveTierOneRoundTripFeeOnly":
            sum(fwd > 50 for _, _, fwd, _ in predictions),
        "unseenStateFallbackCount": sum(key not in counts for _, _, _, key in predictions),
        "states": state_rows,
        "limitation": "July-September was previously inspected. These midpoint transitions ignore executable bid/ask, fees, bar revisions and dependence; no size tier or order follows.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bar_file", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(json.loads(args.bar_file.read_text(encoding="utf-8"))), indent=2))
