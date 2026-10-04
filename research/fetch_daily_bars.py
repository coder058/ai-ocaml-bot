"""Save historical Alpaca US BTC/USD bars privately on Dublin.

Historical bars may include quote midpoints or late revisions. This read-only
download is not a point-in-time decision archive and cannot claim an edge.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

# SOURCE: https://docs.alpaca.markets/us/reference/cryptobars-1
API = "https://data.alpaca.markets/v1beta3/crypto/us/bars"
ENV_PATH = Path("/etc/jsbot-paper.env")
OUTPUT_DIR = Path("/home/ubuntu/jsbot-paper-state/historical")
SYMBOL = "BTC/USD"  # SOURCE: the OCaml paper bot's only traded symbol.
PAGE_SIZE = 1000  # SOURCE: Alpaca's documented default page size.


def credentials() -> dict[str, str]:
    values = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def fetch(start: str, end: str, timeframe: str = "1Day") -> list[dict]:
    auth = credentials()
    result: list[dict] = []
    token = None
    while True:
        query = {"symbols": SYMBOL, "timeframe": timeframe, "start": start,
                 "end": end, "limit": str(PAGE_SIZE), "sort": "asc"}
        if token:
            query["page_token"] = token
        request = urllib.request.Request(API + "?" + urllib.parse.urlencode(query), headers={
            "APCA-API-KEY-ID": auth["APCA_API_KEY_ID"],
            "APCA-API-SECRET-KEY": auth["APCA_API_SECRET_KEY"],
            "Accept": "application/json",
        })
        # GUESS: # UNCALIBRATED GUESS — a 15-second timeout bounds one API page.
        with urllib.request.urlopen(request, timeout=15) as response:
            page = json.load(response)
        rows = page.get("bars", {}).get(SYMBOL, [])
        if not isinstance(rows, list):
            raise ValueError("Alpaca bars response had an unexpected shape")
        result.extend(rows)
        next_token = page.get("next_page_token")
        if not next_token:
            break
        if next_token == token:
            raise ValueError("Alpaca pagination token did not advance")
        token = next_token
    timestamps = [row.get("t") for row in result]
    if any(not isinstance(value, str) for value in timestamps) or timestamps != sorted(set(timestamps)):
        raise ValueError("Alpaca bars have invalid, duplicate or unsorted timestamps")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("start", type=date.fromisoformat)
    parser.add_argument("end", type=date.fromisoformat)
    # SOURCE: Alpaca historical crypto bars supports minute, hour and day frames.
    parser.add_argument("--timeframe", choices=("1Min", "5Min", "1Hour", "1Day"), default="1Day")
    args = parser.parse_args()
    if args.start >= args.end:
        parser.error("start must precede end")
    rows = fetch(args.start.isoformat(), args.end.isoformat(), args.timeframe)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = OUTPUT_DIR / f"alpaca-us-btc-{args.timeframe}-{args.start}-{args.end}.json"
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump({"source": API, "symbol": SYMBOL, "timeframe": args.timeframe,
                   "retrievedAt": datetime.now(timezone.utc).isoformat(),
                   "start": args.start.isoformat(), "end": args.end.isoformat(),
                   "bars": rows}, output, separators=(",", ":"))
        output.flush()
        os.fsync(output.fileno())
    os.chmod(temporary, 0o600)  # SOURCE: owner-only private historical data.
    os.replace(temporary, path)
    print(json.dumps({"saved": str(path), "rows": len(rows),
                      "first": rows[0]["t"] if rows else None,
                      "last": rows[-1]["t"] if rows else None}))


if __name__ == "__main__":
    main()
