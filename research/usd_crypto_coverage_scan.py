"""Read-only same-day historical-bar coverage for paper-tradable USD crypto.

The retrieval timestamp is explicit. Historical bars may contain later
revisions, so this scan is only for choosing what to observe prospectively.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))

from export_telemetry import ENV_PATH, paper_get, read_env  # noqa: E402

# SOURCE: https://docs.alpaca.markets/us/reference/cryptobars-1
API = "https://data.alpaca.markets/v1beta3/crypto/us/bars"
TIMEFRAME = "5Min"  # SOURCE: the existing frozen Markov candle research frame.
PAGE_SIZE = 1000  # SOURCE: Alpaca's documented historical bars default limit.
# GUESS: # UNCALIBRATED GUESS — bound a stalled research request at 15 seconds.
TIMEOUT_SECONDS = 15
BAR_DURATION = timedelta(minutes=5)  # SOURCE: the requested five-minute frame.


def fetch(symbol: str, auth: dict[str, str], start: datetime,
          end: datetime) -> list[dict]:
    query = urllib.parse.urlencode({"symbols": symbol, "timeframe": TIMEFRAME,
                                   "start": start.isoformat(), "end": end.isoformat(),
                                   "limit": str(PAGE_SIZE), "sort": "asc"})
    request = urllib.request.Request(API + "?" + query, headers={
        "APCA-API-KEY-ID": auth["APCA_API_KEY_ID"],
        "APCA-API-SECRET-KEY": auth["APCA_API_SECRET_KEY"],
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        document = json.load(response)
    if document.get("next_page_token"):
        raise ValueError(f"{symbol}: scan page limit reached; do not report incomplete coverage")
    bars = document.get("bars", {}).get(symbol, [])
    if not isinstance(bars, list):
        raise ValueError(f"{symbol}: unexpected bars response")
    return bars


def count_coverage(bars: list[dict], as_of: datetime) -> dict:
    starts = []
    for bar in bars:
        started = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
        if started.tzinfo is None:
            raise ValueError("bar lacks timezone")
        started = started.astimezone(timezone.utc)
        if started + BAR_DURATION <= as_of:
            starts.append(started)
    if starts != sorted(set(starts)):
        raise ValueError("bars are duplicated or unsorted")
    gaps = sum(int((right - left) / BAR_DURATION) - 1
               for left, right in zip(starts, starts[1:]))
    return {"closedBars": len(starts), "missingSlotsBetweenFirstAndLast": gaps,
            "lastClosedBarStart": starts[-1].isoformat() if starts else None}


def main() -> None:
    auth = read_env(ENV_PATH)
    assets = paper_get("/v2/assets?status=active&asset_class=crypto", auth)
    if not isinstance(assets, list):
        raise ValueError("asset catalog was not an array")
    symbols = sorted(str(asset["symbol"]) for asset in assets
                     if asset.get("tradable") is True and asset.get("status") == "active"
                     and str(asset.get("symbol", "")).endswith("/USD"))
    as_of = datetime.now(timezone.utc)
    # SOURCE: one complete UTC calendar-day interval for a same-day feed audit;
    # this is not a signal lookback window.
    start = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = []
    for symbol in symbols:
        result = count_coverage(fetch(symbol, auth, start, as_of), as_of)
        rows.append({"symbol": symbol, **result})
    print(json.dumps({"source": API, "asOf": as_of.isoformat(),
                      "intervalStart": start.isoformat(), "timeframe": TIMEFRAME,
                      "pairCount": len(symbols), "rows": rows,
                      "pointInTimeBacktest": False, "tradeProbability": None}, indent=2))


if __name__ == "__main__":
    main()
