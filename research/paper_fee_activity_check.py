"""Read Alpaca paper fee activity counts without exposing credentials.

Account-level fee activities cannot safely be assigned to bot fills solely by
matching the aggregate count. Zero posted activities do not prove zero fees.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from fetch_daily_bars import credentials

PAPER_ORIGIN = "https://paper-api.alpaca.markets"  # SOURCE: Alpaca paper Trading API origin.
PAGE_SIZE = 100  # SOURCE: Alpaca Account Activities maximum/default page size in existing exporter.


def fee_count(kind: str, auth: dict[str, str]) -> dict:
    if kind not in ("CFEE", "FEE"):
        raise ValueError("unsupported fee activity type")
    request = urllib.request.Request(
        PAPER_ORIGIN + "/v2/account/activities/" + kind + "?" +
        urllib.parse.urlencode({"direction": "desc", "page_size": PAGE_SIZE}),
        headers={"APCA-API-KEY-ID": auth["APCA_API_KEY_ID"],
                 "APCA-API-SECRET-KEY": auth["APCA_API_SECRET_KEY"],
                 "Accept": "application/json"})
    # GUESS: # UNCALIBRATED GUESS — bound this read-only API request at 15s.
    with urllib.request.urlopen(request, timeout=15) as response:
        rows = json.load(response)
    if not isinstance(rows, list):
        raise ValueError("fee activity response was not an array")
    return {"type": kind, "observedRows": len(rows),
            "historyComplete": len(rows) < PAGE_SIZE,
            "latestDate": rows[0].get("date") if rows else None}


if __name__ == "__main__":
    auth = credentials()
    print(json.dumps([fee_count(kind, auth) for kind in ("CFEE", "FEE")]))
