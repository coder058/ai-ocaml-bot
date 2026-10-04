"""Summarize received Hyperliquid public frames without assuming stream coverage."""

from __future__ import annotations

import json
import gzip
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from hyperliquid_capture import CAPTURE_DIR, COINS


def health(paths: list[Path]) -> dict:
    channels: Counter[str] = Counter()
    bbo: Counter[str] = Counter()
    candles: Counter[str] = Counter()
    observed_mids: set[str] = set()
    first_ns = last_ns = None
    sessions: set[str] = set()
    last_sequence: dict[str, int] = {}
    sequence_gaps = corrupt_lines = 0
    incomplete_gzip_files: list[str] = []
    for path in sorted(paths):
        opener = gzip.open if path.suffix == ".gz" else Path.open
        try:
            with opener(path, "rt", encoding="utf-8") as source:
                for line in source:
                    try:
                        row = json.loads(line)
                        received = row["receivedAtNs"]
                        session = row["sessionId"]
                        sequence = row["sequence"]
                        message = row["message"]
                    except (json.JSONDecodeError, KeyError, TypeError):
                        corrupt_lines += 1
                        continue
                    first_ns = received if first_ns is None else min(first_ns, received)
                    last_ns = received if last_ns is None else max(last_ns, received)
                    sessions.add(session)
                    previous = last_sequence.get(session)
                    if previous is not None and sequence > previous + 1:
                        sequence_gaps += sequence - previous - 1
                    last_sequence[session] = max(sequence, previous or sequence)
                    channel = message.get("channel")
                    channels[channel] += 1
                    data = message.get("data")
                    if channel == "allMids" and isinstance(data, dict):
                        observed_mids.update(data.get("mids", {}))
                    elif channel == "bbo" and isinstance(data, dict):
                        bbo[data.get("coin", "unknown")] += 1
                    elif channel == "candle":
                        for candle in data if isinstance(data, list) else [data]:
                            if isinstance(candle, dict):
                                candles[candle.get("s", "unknown")] += 1
        except EOFError:
            # The active gzip writer has flushed frames but has not written its
            # final trailer. Keep the readable prefix and report it as partial.
            if path.suffix != ".gz":
                raise
            incomplete_gzip_files.append(str(path))
    return {"files": [str(path) for path in paths], "firstReceivedAtNs": first_ns,
            "lastReceivedAtNs": last_ns, "channels": dict(channels),
            "sessions": len(sessions), "localSequenceGaps": sequence_gaps,
            "corruptLines": corrupt_lines,
            "incompleteGzipFiles": incomplete_gzip_files,
            "distinctMidSymbols": len(observed_mids),
            "midsForSelected": sorted(observed_mids.intersection(COINS)),
            "bboCounts": dict(bbo), "candleUpdateCounts": dict(candles),
            "orderAuthority": False}


if __name__ == "__main__":
    day = datetime.now(timezone.utc).date().isoformat()
    paths = [*CAPTURE_DIR.glob(f"{day}-*.jsonl.gz"), CAPTURE_DIR / f"{day}.jsonl"]
    paths = [path for path in paths if path.exists()]
    if not paths:
        raise SystemExit(f"no Hyperliquid captures found for {day}")
    print(json.dumps(health(paths), indent=2))
