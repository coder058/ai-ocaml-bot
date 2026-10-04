"""Compare timely captured one-minute bars with later REST five-minute bars.

The stream bars are as received; REST bars can contain later revisions. This
only assesses whether stream aggregation is suitable for a forward shadow
study. It never generates orders or infers a trading edge.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def minute_number(stamp: str) -> int:
    instant = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.second or instant.microsecond:
        raise ValueError("bar time is not a UTC minute")
    return int(instant.timestamp()) // 60  # SOURCE: seconds per UTC minute.


def compare(capture: Path, document: dict) -> dict:
    if document.get("symbol") != "BTC/USD" or document.get("timeframe") != "5Min":
        raise ValueError("expected BTC/USD five-minute REST snapshot")
    groups: dict[int, dict[int, dict]] = defaultdict(dict)
    duplicates = 0
    with capture.open(encoding="utf-8") as source:
        for line in source:
            event = json.loads(line)["event"]
            if event.get("T") != "b":
                continue
            if event.get("S") != "BTC/USD":
                continue
            minute = minute_number(event["t"])
            # SOURCE: UTC 5Min framing. No missing one-minute slot is filled.
            group = minute // 5 * 5
            if minute in groups[group]:
                duplicates += 1
            groups[group][minute] = event
    rest = {minute_number(bar["t"]): bar for bar in document["bars"]}
    differences = []
    complete = 0
    absent_rest = 0
    for start, members in groups.items():
        if set(members) != set(range(start, start + 5)):
            continue
        complete += 1
        if start not in rest:
            absent_rest += 1
            continue
        close = float(members[start + 4]["c"])
        rest_close = float(rest[start]["c"])
        if close <= 0 or rest_close <= 0:
            raise ValueError("non-positive close")
        # SOURCE: absolute midpoint difference in basis points.
        differences.append(abs(close / rest_close - 1) * 10_000)
    ordered = sorted(differences)
    return {"streamFiveMinuteGroups": len(groups),
            "completeStreamGroups": complete, "duplicateMinuteBars": duplicates,
            "completeGroupsAbsentFromRest": absent_rest,
            "comparedGroups": len(ordered),
            "medianAbsoluteCloseDifferenceBps": statistics.median(ordered) if ordered else None,
            # SOURCE: empirical nearest-rank 90th percentile, if available.
            "p90AbsoluteCloseDifferenceBps": ordered[(9 * len(ordered) - 1) // 10] if ordered else None,
            "maxAbsoluteCloseDifferenceBps": ordered[-1] if ordered else None,
            "limitation": "Later REST bars may be revised; only fully present streamed one-minute groups are compared. No order or return evaluation follows."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("rest_snapshot", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.capture,
                             json.loads(args.rest_snapshot.read_text(encoding="utf-8"))), indent=2))
