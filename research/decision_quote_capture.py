"""Record actual bid/ask context for future research, never synthetic fills.

Sources: https://docs.alpaca.markets/us/reference/stocklatestquotes-1 and
https://docs.alpaca.markets/us/reference/cryptolatestquotes-1 .
"""
import math
import re
import urllib.parse
from decimal import Decimal
from datetime import datetime, timezone

# SOURCE: official provider batch GET endpoints, no order submission endpoint.
STOCK_QUOTES = "https://data.alpaca.markets/v2/stocks/quotes/latest"
CRYPTO_QUOTES = "https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes"
# SOURCE: inherited five-second freshness guard of the existing paper routers.
# This is an operational guard, not calibrated fill latency or a holding period.
MAX_QUOTE_AGE_SECONDS = 5
# SOURCE: one basis point is 1/10,000 of a relative price movement.
BPS = 10_000


def utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize(raw, received_at, venue, symbol):
    result = {"venue": venue, "symbol": symbol, "receivedAt": utc(received_at),
              "feed": "iex" if venue == "Alpaca equities" else "Alpaca crypto US",
              "purpose": "observed_quote_reference_not_execution", "orderAuthority": False,
              "winProbability": None, "status": "missing"}
    if raw is None:
        return result
    try:
        parts = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)", raw["t"])
        if not parts:
            raise ValueError("quote timezone missing")
        base = datetime.fromisoformat(parts[1] + parts[3].replace("Z", "+00:00"))
        # SOURCE: Python 3.10 datetime accepts microseconds, while Alpaca quotes
        # have nanoseconds. Keep the original text and compare exact decimal
        # seconds, including quotes just after the measured reception time.
        quote_seconds = Decimal(int(base.timestamp())) + Decimal("0." + (parts[2] or "0"))
        # SOURCE: 1,000,000 microseconds per second in datetime's clock value.
        received_seconds = Decimal(int(received_at.replace(microsecond=0).timestamp())) + Decimal(received_at.microsecond) / Decimal(1_000_000)
        bid, ask = float(raw["bp"]), float(raw["ap"])
        sizes = [float(raw[k]) for k in ("bs", "as")]
        if not all(math.isfinite(n) for n in (bid, ask, *sizes)) or not 0 < bid <= ask or any(n <= 0 for n in sizes):
            raise ValueError("invalid or empty quote")
        age = float(received_seconds - quote_seconds)
        result.update({"quoteAt": raw["t"], "bid": bid, "ask": ask,
            "bidSizeRaw": sizes[0], "askSizeRaw": sizes[1],
            "sizeUnits": "provider reported; no stock round-lot normalization",
            "quoteAgeSecondsAtReceipt": age, "spreadBps": (ask - bid) / ((ask + bid) / 2) * BPS,
            "status": "future" if age < 0 else "stale" if age > MAX_QUOTE_AGE_SECONDS else "fresh"})
    except (ValueError, KeyError, TypeError, OverflowError):
        result["status"] = "invalid"
    return result


def collect(request, universes, credentials, now=lambda: datetime.now(timezone.utc)):
    result, errors = {}, []
    for venue, symbols in universes.items():
        if venue not in ("Alpaca crypto", "Alpaca equities"):
            continue  # No market price is invented for unconnected providers.
        if "AAPL" in symbols or venue == "Alpaca crypto" and any(s not in ("BTC/USD", "ETH/USD", "SOL/USD") for s in symbols):
            raise ValueError("protected or excluded quote scope")
        if not symbols:
            continue
        query = {"symbols": ",".join(symbols)}
        if venue == "Alpaca equities":
            query["feed"] = "iex"
        try:
            payload = request((STOCK_QUOTES if venue == "Alpaca equities" else CRYPTO_QUOTES) + "?" + urllib.parse.urlencode(query), credentials)
            received_at = now()
            if not isinstance(payload, dict) or not isinstance(payload.get("quotes"), dict):
                raise ValueError("quote mapping missing")
            if any(symbol not in symbols for symbol in payload["quotes"]):
                raise ValueError("unexpected quote instrument")
            for symbol in symbols:
                result[venue + "|" + symbol] = normalize(payload["quotes"].get(symbol), received_at, venue, symbol)
        except Exception as error:
            errors.append({"venue": venue, "stage": "quote_reference", "error": type(error).__name__})
            received_at = now()
            for symbol in symbols:
                result[venue + "|" + symbol] = {**normalize(None, received_at, venue, symbol), "status": "retrieval_error"}
    return result, errors
