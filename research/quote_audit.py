"""Audit observed BTC quote freshness and spreads from signed monitor telemetry.

This is a descriptive quality check, not a trading signal or a backtest.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import sys
import urllib.request
from datetime import datetime, timezone

# SOURCE: This project's public, signed-snapshot monitor API.
MONITOR_URL = "http://127.0.0.1:3000/api/live"
# SOURCE: OCaml event journal format in bin/paper_crypto_main.ml.
QUOTE = re.compile(r"^QUOTE BTC/USD t=(\S+) bid=([\d.]+) ask=([\d.]+) spread_bps=([\d.]+)$")


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def percentile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    # SOURCE: nearest-rank empirical quantile, using the observed sample only.
    rank = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * share) - 1))
    return ordered[rank]


def audit(document: dict) -> dict:
    telemetry = document.get("telemetry")
    if not isinstance(telemetry, dict):
        raise ValueError("Signed telemetry is absent")
    journal = telemetry.get("journal", [])
    readings = []
    for event in journal:
        matched = QUOTE.fullmatch(str(event.get("message", "")))
        if not matched:
            continue
        quote_at, bid, ask, spread = matched.groups()
        reading_age = (timestamp(event["at"]) - timestamp(quote_at)).total_seconds()
        readings.append((quote_at, float(bid), float(ask), float(spread), reading_age))
    ages = [row[4] for row in readings]
    spreads = [row[3] for row in readings]
    unique_timestamps = {row[0] for row in readings}
    return {
        "snapshot_at": telemetry.get("generatedAt"),
        "journal_complete": telemetry.get("journalComplete"),
        "quote_log_rows": len(readings),
        "distinct_quote_timestamps": len(unique_timestamps),
        "repeated_quote_rows": len(readings) - len(unique_timestamps),
        "approx_quote_age_seconds": {
            "median": statistics.median(ages) if ages else None,
            "p90": percentile(ages, 0.90),
            "max": max(ages) if ages else None,
            "min": min(ages) if ages else None,
        },
        "observed_spread_bps": {
            "median": statistics.median(spreads) if spreads else None,
            "p90": percentile(spreads, 0.90),
            "max": max(spreads) if spreads else None,
        },
        "scope": "Journal timestamps have second precision; ages are approximate. Repeated snapshots are not independent market observations.",
    }


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else MONITOR_URL
    with urllib.request.urlopen(url) as response:
        document = json.load(response)
    print(json.dumps(audit(document), indent=2))


if __name__ == "__main__":
    main()
