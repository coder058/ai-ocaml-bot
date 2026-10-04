"""Read-only, point-in-time closed candles from the as-received crypto capture.

Bars are grouped only when every constituent minute exists. A later updatedBar
is visible only when it was received by the requested as-of instant. This
reports data coverage, not trade probabilities or order instructions.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

# SOURCE: the user's requested 1m, 5m, 30m, 1h and 4h analyses.
FRAMES = (1, 5, 30, 60, 240)


def instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def closed_minutes_many(captures: list[Path], symbols: tuple[str, ...],
                        as_of: datetime) -> dict[str, dict[int, dict]]:
    if as_of.tzinfo is None:
        raise ValueError("as-of timestamp has no timezone")
    as_of = as_of.astimezone(timezone.utc)
    bars: dict[str, dict[int, dict]] = {symbol: {} for symbol in symbols}
    for capture in captures:
        if not capture.exists():
            continue
        with capture.open(encoding="utf-8") as source:
            for line in source:
                record = json.loads(line)
                event = record["event"]
                symbol = event.get("S")
                if symbol not in bars or event.get("T") not in ("b", "u"):
                    continue
                received_at = datetime.fromtimestamp(record["receivedAtNs"] / 1_000_000_000,
                                                     timezone.utc)
                if received_at > as_of:
                    continue
                started_at = instant(event["t"])
                if started_at.second or started_at.microsecond:
                    raise ValueError("minute bar is not UTC aligned")
                if started_at + timedelta(minutes=1) > as_of:
                    continue
                opening, high, low, closing, volume = (
                    float(event[key]) for key in ("o", "h", "l", "c", "v")
                )
                if (not all(math.isfinite(value) for value in
                            (opening, high, low, closing, volume))
                        or not (0 < low <= min(opening, closing)
                                <= max(opening, closing) <= high and volume >= 0)):
                    raise ValueError(f"invalid {symbol} minute bar")
                # SOURCE: stream 'u' is Alpaca's later revision of a minute bar;
                # overwrite only after its recorded receipt time, never retroactively.
                slot = int(started_at.timestamp()) // 60
                bars[symbol][slot] = event
    return bars


def closed_minutes(capture: Path, symbol: str, as_of: datetime) -> dict[int, dict]:
    return closed_minutes_many([capture], (symbol,), as_of)[symbol]


def aggregate(bars: dict[int, dict], frame_minutes: int) -> list[dict]:
    if frame_minutes not in FRAMES:
        raise ValueError("unsupported frame")
    result = []
    for frame_start in sorted({slot // frame_minutes * frame_minutes for slot in bars}):
        slots = range(frame_start, frame_start + frame_minutes)
        if not all(slot in bars for slot in slots):
            continue
        members = [bars[slot] for slot in slots]
        result.append({
            "t": datetime.fromtimestamp(frame_start * 60, timezone.utc).isoformat(),
            "o": float(members[0]["o"]),
            "h": max(float(bar["h"]) for bar in members),
            "l": min(float(bar["l"]) for bar in members),
            "c": float(members[-1]["c"]),
            "v": sum(float(bar["v"]) for bar in members),
        })
    return result


def coverage(capture: Path, symbol: str, as_of: datetime) -> dict:
    bars = closed_minutes(capture, symbol, as_of)
    frames = {}
    for minutes in FRAMES:
        complete = aggregate(bars, minutes)
        frames[f"{minutes}m"] = {
            "completeBars": len(complete),
            "lastBarStart": complete[-1]["t"] if complete else None,
        }
    return {"symbol": symbol, "asOf": as_of.isoformat(),
            "receivedClosedMinuteBars": len(bars), "frames": frames,
            "orderAuthority": False,
            "winProbability": None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--as-of", type=instant,
                        default=datetime.now(timezone.utc))
    arguments = parser.parse_args()
    print(json.dumps(coverage(arguments.capture, arguments.symbol, arguments.as_of), indent=2))
