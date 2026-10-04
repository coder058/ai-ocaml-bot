"""Publish an as-retrieved Alpaca BTC/USD 5m bar snapshot for OCaml context.

Historical bars can be revised. The retrieval time travels with every snapshot;
OCaml may use it only for decisions after retrieval, never as past knowledge.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fetch_daily_bars import API, SYMBOL, fetch

OUTPUT = Path("/home/ubuntu/jsbot-paper-state/five-minute-bars.json")
FIVE_MINUTES = timedelta(minutes=5)  # SOURCE: the requested Alpaca 5Min frame.


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("bar time lacks a timezone")
    return parsed.astimezone(timezone.utc)


def main() -> None:
    now = datetime.now(timezone.utc)
    # SOURCE: a two-day UTC window includes at least the 50 bars needed by
    # Pattern Forge's slow EMA after a normal restart, if the feed has them.
    start = (now - timedelta(days=1)).date().isoformat() + "T00:00:00Z"
    rows = fetch(start, now.isoformat(), "5Min")
    retrieved_at = datetime.now(timezone.utc)
    closed = []
    previous = None
    for row in rows:
        bar_start = timestamp(row["t"])
        if bar_start.minute % 5 or bar_start.second or bar_start.microsecond:
            raise ValueError("5m bar is not UTC-aligned")
        if previous is not None and bar_start <= previous:
            raise ValueError("5m bars are duplicated or unsorted")
        previous = bar_start
        if bar_start + FIVE_MINUTES > retrieved_at:
            continue
        open_price, high, low, close, volume = (
            float(row[key]) for key in ("o", "h", "l", "c", "v")
        )
        if not all(math.isfinite(value) for value in
                   (open_price, high, low, close, volume)) or not (
            0 < low <= min(open_price, close) <= max(open_price, close) <= high
            and volume >= 0
        ):
            raise ValueError("invalid 5m OHLCV bar")
        closed.append(row)
    if not closed:
        raise ValueError("Alpaca returned no closed 5m bars")
    payload = {
        "source": API, "symbol": SYMBOL, "timeframe": "5Min",
        "retrievedAt": retrieved_at.isoformat(), "bars": closed,
    }
    temporary = OUTPUT.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as target:
        json.dump(payload, target, separators=(",", ":"))
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    # SOURCE: market-only data is readable by the ubuntu OCaml service.
    os.chown(temporary, 0, os.stat("/home/ubuntu").st_gid)
    os.chmod(temporary, 0o640)
    os.replace(temporary, OUTPUT)
    directory = os.open(OUTPUT.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    print(json.dumps({"retrievedAt": payload["retrievedAt"],
                      "closedBars": len(closed),
                      "lastBar": closed[-1]["t"]}), flush=True)


if __name__ == "__main__":
    main()
