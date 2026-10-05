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


def quote_time(value):
    """Exact RFC3339 decimal seconds, including Alpaca nanoseconds on Python 3.10."""
    parts = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)", value)
    if not parts:
        raise ValueError("quote timezone or timestamp precision invalid")
    base = datetime.fromisoformat(parts[1] + parts[3].replace("Z", "+00:00"))
    return Decimal(int(base.timestamp())) + Decimal("0." + (parts[2] or "0"))


def normalize(raw, received_at, venue, symbol):
    return normalize_at(raw,utc(received_at),venue,symbol)


def normalize_at(raw, received_text, venue, symbol):
    """Keep the actual clock precision of REST or previously archived stream receipts."""
    result = {"venue": venue, "symbol": symbol, "receivedAt": received_text,
              "feed": "iex" if venue == "Alpaca equities" else "Alpaca crypto US",
              "purpose": "observed_quote_reference_not_execution", "orderAuthority": False,
              "winProbability": None, "status": "missing", "reason":"provider_quote_missing"}
    if raw is None:
        return result
    try:
        # SOURCE: Python 3.10 datetime accepts microseconds, while Alpaca quotes
        # have nanoseconds. Keep the original text and compare exact decimal
        # seconds, including quotes just after the measured reception time.
        quote_seconds = quote_time(raw["t"])
        received_seconds = quote_time(received_text)
        if any(isinstance(raw[k],bool) for k in ("bp","ap","bs","as")):
            raise ValueError("boolean_quote_fields")
        bid, ask = float(raw["bp"]), float(raw["ap"])
        sizes = [float(raw[k]) for k in ("bs", "as")]
        if not all(math.isfinite(n) for n in (bid, ask, *sizes)):
            raise ValueError("nonfinite_quote_fields")
        if not 0 < bid <= ask:
            raise ValueError("nonpositive_or_crossed_bid_ask")
        if any(n <= 0 for n in sizes):
            raise ValueError("empty_or_negative_provider_size")
        age = float(received_seconds - quote_seconds)
        result.update({"quoteAt": raw["t"], "bid": bid, "ask": ask,
            "bidSizeRaw": sizes[0], "askSizeRaw": sizes[1],
            "sizeUnits": "provider reported; no stock round-lot normalization",
            "quoteAgeSecondsAtReceipt": age, "spreadBps": (ask - bid) / ((ask + bid) / 2) * BPS,
            "status": "future" if age < 0 else "stale" if age > MAX_QUOTE_AGE_SECONDS else "fresh",
            "reason":"quote_after_actual_receipt" if age<0 else "quote_older_than_receipt_guard" if age>MAX_QUOTE_AGE_SECONDS else "within_receipt_guard"})
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        result["status"] = "invalid"
        # Only known diagnostic codes may leave the boundary. Never expose raw
        # provider payloads, exception text, request URLs or credentials.
        code=str(error)
        result["reason"]=code if code in ("boolean_quote_fields","nonfinite_quote_fields","nonpositive_or_crossed_bid_ask","empty_or_negative_provider_size") else "invalid_or_missing_quote_fields"
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
                result[venue + "|" + symbol] = {**normalize(payload["quotes"].get(symbol), received_at, venue, symbol), "transport":"rest_batch"}
        except Exception as error:
            errors.append({"venue": venue, "stage": "quote_reference", "error": type(error).__name__})
            received_at = now()
            for symbol in symbols:
                result[venue + "|" + symbol] = {**normalize(None, received_at, venue, symbol), "status": "retrieval_error", "reason":"provider_request_failed"}
    return result, errors
