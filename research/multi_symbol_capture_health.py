"""Count actual as-received crypto events after a declared subscription time."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from multi_timeframe_bars import instant
from stream_capture import ARCHIVED_SYMBOLS


def audit(capture: Path, since: datetime) -> dict:
    if since.tzinfo is None:
        raise ValueError("since has no timezone")
    # SOURCE: receivedAtNs is Unix nanoseconds in the durable stream archive.
    since_ns = int(since.timestamp() * 1_000_000_000)
    counts: dict[str, Counter[str]] = {symbol: Counter() for symbol in ARCHIVED_SYMBOLS}
    latest: dict[str, int | None] = {symbol: None for symbol in ARCHIVED_SYMBOLS}
    with capture.open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            received = int(record["receivedAtNs"])
            if received < since_ns:
                continue
            event = record["event"]
            symbol = event.get("S")
            if symbol not in counts:
                continue
            counts[symbol][event["T"]] += 1
            latest[symbol] = received
    rows = [{"symbol": symbol, "events": dict(counts[symbol]),
             "lastReceivedAt": (datetime.fromtimestamp(latest[symbol] / 1_000_000_000,
                                                        timezone.utc).isoformat()
                                if latest[symbol] is not None else None)}
            for symbol in ARCHIVED_SYMBOLS]
    return {"since": since.isoformat(), "subscribedSymbols": len(ARCHIVED_SYMBOLS),
            "symbolsWithEvents": sum(bool(row["events"]) for row in rows),
            "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--since", required=True, type=instant)
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.capture, arguments.since), indent=2))
