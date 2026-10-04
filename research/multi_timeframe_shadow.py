"""Write a minute-cadence, read-only Pattern Forge-style market snapshot.

This process reads only the received crypto archive. It has no broker imports,
credentials, network calls or order path. Candle labels and EMA trends are
descriptive; no winning probability or stop distance is emitted.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from multi_timeframe_bars import FRAMES, aggregate, closed_minutes_many, instant
from pattern_event_study import FAST_PERIOD, SLOW_PERIOD, shapes
from stream_capture import ARCHIVED_SYMBOLS


CAPTURE_DIR = Path("/home/ubuntu/jsbot-paper-state/market-capture/us")
OUTPUT = Path("/home/ubuntu/jsbot-paper-state/multi-timeframe-shadow.json")


def contiguous_tail(bars: list[dict], minutes: int) -> list[dict]:
    if not bars:
        return []
    tail = [bars[-1]]
    for candidate in reversed(bars[:-1]):
        if instant(tail[-1]["t"]) - instant(candidate["t"]) != timedelta(minutes=minutes):
            break
        tail.append(candidate)
    return list(reversed(tail))


def ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    value = sum(closes[:period]) / period
    # SOURCE: standard EMA recurrence; periods come from Pattern Forge.
    for close in closes[period:]:
        value += (close - value) * 2 / (period + 1)
    return value


def describe(bars: list[dict], minutes: int, as_of: datetime) -> dict:
    tail = contiguous_tail(bars, minutes)
    if not tail:
        return {"completeBars": 0, "contiguousTailBars": 0,
                "lastBarStart": None, "ageSecondsAfterClose": None,
                "trend": None, "candleShapes": []}
    current = tail[-1]
    previous = tail[-2] if len(tail) > 1 else None
    closes = [float(bar["c"]) for bar in tail]
    fast, slow = ema(closes, FAST_PERIOD), ema(closes, SLOW_PERIOD)
    trend = None
    if fast is not None and slow is not None:
        close = closes[-1]
        trend = ("rising" if close > fast > slow else
                 "falling" if close < fast < slow else "mixed")
    ended_at = instant(current["t"]) + timedelta(minutes=minutes)
    return {"completeBars": len(bars), "contiguousTailBars": len(tail),
            "lastBarStart": current["t"],
            "ageSecondsAfterClose": (as_of - ended_at).total_seconds(),
            "trend": trend, "candleShapes": shapes(previous, current)}


def snapshot(as_of: datetime) -> dict:
    day = as_of.date()
    # SOURCE: two UTC capture days straddle a midnight 4h research candle.
    captures = [CAPTURE_DIR / f"{(day - timedelta(days=1)).isoformat()}.jsonl",
                CAPTURE_DIR / f"{day.isoformat()}.jsonl"]
    minutes = closed_minutes_many(captures, ARCHIVED_SYMBOLS, as_of)
    rows = []
    for symbol in ARCHIVED_SYMBOLS:
        readings = {}
        for frame in FRAMES:
            readings[f"{frame}m"] = describe(aggregate(minutes[symbol], frame), frame, as_of)
        rows.append({"symbol": symbol, "frames": readings})
    return {"asOf": as_of.isoformat(), "captureFiles": [str(path) for path in captures
                                                       if path.exists()],
            "symbols": rows, "orderAuthority": False,
            "winProbability": None, "stopDistance": None,
            "scope": "Received closed candles only; patterns and trends are descriptive."}


def main() -> None:
    as_of = datetime.now(timezone.utc)
    started = time.monotonic()
    result = snapshot(as_of)
    result["processingSeconds"] = time.monotonic() - started
    if not result["captureFiles"]:
        raise ValueError("no UTC capture file found")
    temporary = OUTPUT.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as target:
        json.dump(result, target, separators=(",", ":"))
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    os.chmod(temporary, 0o640)  # SOURCE: private owner/group research data.
    os.replace(temporary, OUTPUT)
    print(json.dumps({"asOf": result["asOf"],
                      "symbols": len(result["symbols"]),
                      "processingSeconds": result["processingSeconds"]}), flush=True)


if __name__ == "__main__":
    main()
