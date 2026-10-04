"""Inspect spacing and basic OHLC integrity of a saved Alpaca bar file."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

# SOURCE: Alpaca historical crypto bars documents these timeframe units.
FRAME = {"1Min": timedelta(minutes=1), "5Min": timedelta(minutes=5),
         "1Hour": timedelta(hours=1), "1Day": timedelta(days=1)}


def audit(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    timeframe = document["timeframe"]
    step = FRAME[timeframe]
    bars = document["bars"]
    times = [datetime.fromisoformat(bar["t"].replace("Z", "+00:00")) for bar in bars]
    if times != sorted(set(times)):
        raise ValueError("timestamps are unsorted or duplicated")
    gaps = []
    for previous, current in zip(times, times[1:]):
        if current - previous != step:
            gaps.append({"after": previous.isoformat(), "before": current.isoformat(),
                         "missingIntervals": (current - previous) // step - 1})
    invalid_ohlc = 0
    for bar in bars:
        open_price, high, low, close = (float(bar[key]) for key in ("o", "h", "l", "c"))
        if not (0 < low <= min(open_price, close) <= max(open_price, close) <= high):
            invalid_ohlc += 1
    return {"path": str(path), "timeframe": timeframe, "bars": len(bars),
            "first": bars[0]["t"] if bars else None, "last": bars[-1]["t"] if bars else None,
            "gapCount": len(gaps), "gaps": gaps, "invalidOhlc": invalid_ohlc,
            "scope": "Spacing and OHLC checks only. Historical bars may contain quote midpoints and later revisions; no point-in-time execution or signal claim."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bar_file", type=Path)
    print(json.dumps(audit(parser.parse_args().bar_file), indent=2))
