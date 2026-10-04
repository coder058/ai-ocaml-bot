"""Read-only markout audit of orders in the public signed paper monitor."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import date
from pathlib import Path
from urllib.request import urlopen

from order_quote_audit import audit

# SOURCE: this project's public paper-monitor API.
MONITOR_URL = "http://127.0.0.1:3000/api/live"
# SOURCE: match the existing exporter and fee-check bounded HTTPS reads.
REQUEST_TIMEOUT_SECONDS = 15


def snapshot_for_fill_date(snapshot: dict, fill_date: str | None) -> tuple[dict, int]:
    """Return an isolated snapshot with fills restricted to one UTC date."""
    telemetry = snapshot.get("telemetry", snapshot)
    fills = telemetry.get("fills", [])
    if fill_date is None:
        return snapshot, len(fills)
    # SOURCE: ISO-8601 calendar date format for the broker's UTC timestamp prefix.
    date.fromisoformat(fill_date)
    scoped_fills = [fill for fill in fills
                    if str(fill.get("transactionTime", "")).startswith(fill_date)]
    result = copy.deepcopy(snapshot)
    result_telemetry = result.get("telemetry", result)
    result_telemetry["fills"] = scoped_fills
    return result, len(scoped_fills)


def public_markout(captures: list[Path], url: str = MONITOR_URL,
                   fill_date: str | None = None) -> dict:
    with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        snapshot = json.load(response)
    snapshot, fill_count = snapshot_for_fill_date(snapshot, fill_date)
    result = audit(captures, None, snapshot)
    return {
        "snapshotAt": result["snapshotAt"],
        "fillDateUtc": fill_date,
        "fillsInScope": fill_count,
        "matchedHotOrders": result["matchedHotOrders"],
        "botOrdersWithoutDecisionTrace": result["botOrdersWithoutDecisionTrace"],
        "unmatchedHotOrderIds": result["unmatchedHotOrderIds"],
        "brokerStatuses": result["brokerStatuses"],
        "canceledWithPartialFill": result["canceledWithPartialFill"],
        "canceledWithoutFill": result["canceledWithoutFill"],
        "minQuoteCrossingBps": result["minQuoteCrossingBps"],
        "medianQuoteCrossingBps": result["medianQuoteCrossingBps"],
        "maxQuoteCrossingBps": result["maxQuoteCrossingBps"],
        "fillMidpointResponse": result["fillMidpointResponse"],
        "feeAwareExecutableMarkout": result["fillMidpointResponse"]["feeAwareExecutableMarkout"],
        "scope": result["scope"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", nargs="+", type=Path)
    parser.add_argument("--url", default=MONITOR_URL)
    parser.add_argument("--fill-date", help="limit markout fills to a UTC date, YYYY-MM-DD")
    args = parser.parse_args()
    print(json.dumps(public_markout(args.capture, args.url, args.fill_date), indent=2))


if __name__ == "__main__":
    main()
