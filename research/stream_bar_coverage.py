"""Measure closed-minute bar continuity in the captured Alpaca US feed."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


def minute(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.second or parsed.microsecond:
        raise ValueError("bar start is not UTC-minute aligned")
    return int(parsed.timestamp()) // 60


def audit(path: Path, symbol: str = "BTC/USD") -> dict:
    starts: set[int] = set()
    duplicates = 0
    revisions = 0
    with path.open(encoding="utf-8") as source:
        for line in source:
            event = json.loads(line)["event"]
            if event.get("S") != symbol:
                continue
            if event["T"] == "u":
                revisions += 1
            elif event["T"] == "b":
                start = minute(event["t"])
                if start in starts:
                    duplicates += 1
                starts.add(start)
    if not starts:
        return {"path": str(path), "symbol": symbol, "closedBars": 0}
    ordered = sorted(starts)
    gaps = [right - left - 1 for left, right in zip(ordered, ordered[1:])]
    missing = sum(gaps)
    streak = best = 1
    for gap in gaps:
        streak = streak + 1 if gap == 0 else 1
        best = max(best, streak)
    groups: dict[int, set[int]] = {}
    for start in ordered:
        group_start = start // 5 * 5  # SOURCE: five UTC minutes per 5m bar.
        groups.setdefault(group_start, set()).add(start)
    complete_groups = sum(
        1 for group_start, members in groups.items()
        if members == set(range(group_start, group_start + 5))
    )
    # SOURCE: the capture includes only actual closed bars; missing intervals
    # are counted, never filled with synthetic zero-volume candles.
    return {
        "path": str(path),
        "symbol": symbol,
        "firstMinute": ordered[0],
        "lastMinute": ordered[-1],
        "elapsedMinuteSlots": ordered[-1] - ordered[0] + 1,
        "closedBars": len(ordered),
        "missingMinuteSlots": missing,
        "duplicateClosedBars": duplicates,
        "updatedBars": revisions,
        "gapSizeCounts": dict(Counter(gap for gap in gaps if gap > 0)),
        "longestContiguousRun": best,
        "fiveMinuteGroupsWithAnyBar": len(groups),
        "fiveMinuteGroupsComplete": complete_groups,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--symbol", default="BTC/USD")
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.capture, arguments.symbol), indent=2))


if __name__ == "__main__":
    main()
