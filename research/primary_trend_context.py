"""Native daily/weekly context, descriptive only; no orders or winning probability.

Historical bars are known only at retrieval, not point-in-time backtest inputs.
Provider references: https://docs.alpaca.markets/us/reference/stockbars and
https://docs.alpaca.markets/us/reference/cryptobars-1 .
"""
from __future__ import annotations

import math
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# SOURCE: provider native aggregation names; never derive these from 4h candles.
INTERVALS = ("1Day", "1Week")
# SOURCE: existing shared OCaml Pattern Forge EMA windows.
EMA_WINDOWS = (20, 50)
# SOURCE: EMA50 plus a preceding observation and one leading period allowance.
HISTORY_WEEKS = max(EMA_WINDOWS) + 2
# GUESS: # UNCALIBRATED GUESS — an hourly read-only refresh limits REST work;
# measure coverage/latency before changing this operational cadence.
REFRESH_SECONDS = 60 * 60
# SOURCE: documented Alpaca maximum total rows per page, not per symbol.
PAGE_LIMIT = 10_000
NEW_YORK = ZoneInfo("America/New_York")


def instant(value):
    at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if at.tzinfo is None:
        raise ValueError("native candle timestamp has no timezone")
    return at.astimezone(timezone.utc)


def utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def start_of_week(day):
    return day - timedelta(days=day.weekday())


def period_end(start, interval):
    # SOURCE: calendar-date arithmetic preserves NY midnight across DST. A
    # stock daily bar can include after-hours prints; do not close it at 16:00.
    return start + timedelta(days=1 if interval == "1Day" else 7)


def expected_periods(start, as_of, interval, equities, calendar):
    zone = NEW_YORK if equities else timezone.utc
    first, last = start.astimezone(zone).date(), as_of.astimezone(zone).date()
    if equities:
        # SOURCE: actual broker calendar, including weekends and holidays.
        dates = {datetime.fromisoformat(s["date"]).date() for s in calendar}
        dates = {d for d in dates if first <= d <= last}
    else:
        dates = set()
        day = first
        while day <= last:
            dates.add(day)
            day += timedelta(days=1)
    if interval == "1Week":
        dates = {start_of_week(day) for day in dates}
    return [at for day in sorted(dates)
            if (at := datetime.combine(day, datetime.min.time(), zone)) >= start
            and period_end(at, interval) <= as_of]


def ema(closes, window):
    if len(closes) < window:
        return None
    # SOURCE: conventional EMA with initial SMA and alpha=2/(window+1), as
    # used by the existing OCaml EMA implementation. No calibrated threshold.
    value = sum(closes[:window]) / window
    alpha = 2 / (window + 1)
    for close in closes[window:]:
        value += alpha * (close - value)
    return value


def summarize(rows, interval, start, as_of, equities, calendar):
    if interval not in INTERVALS:
        raise ValueError("unsupported primary interval")
    zone = NEW_YORK if equities else timezone.utc
    expected = expected_periods(start, as_of, interval, equities, calendar)
    allowed = set(expected)
    successor = dict(zip(expected, expected[1:]))
    tail, previous, closed_count = [], None, 0
    for row in rows:
        at = instant(row["t"]).astimezone(zone)
        if at.time() != datetime.min.time() or interval == "1Week" and at.weekday() != 0:
            raise ValueError("native daily/weekly timestamp is not period-aligned")
        values = [float(row[key]) for key in ("o", "h", "l", "c", "v")]
        op, hi, lo, close, volume = values
        if not all(math.isfinite(n) for n in values) or not 0 < lo <= min(op, close) <= max(op, close) <= hi or volume < 0:
            raise ValueError("invalid native OHLCV")
        if previous is not None and at <= previous:
            raise ValueError("native periods are not increasing")
        if period_end(at, interval) > as_of:
            continue  # API end can include a still-open native aggregation.
        if at < start:
            continue
        if at not in allowed:
            raise ValueError("native stock period missing from broker calendar")
        if previous is not None and successor.get(previous) != at:
            tail = []  # Actual missing periods reset indicator warmup.
        tail.append(close)
        previous, closed_count = at, closed_count + 1
    latest_expected = expected[-1] if expected else None
    stale = latest_expected is not None and previous != latest_expected
    fast, slow = (ema(tail, window) for window in EMA_WINDOWS)
    state = "no_data" if not tail else "stale" if stale else "warming" if slow is None else "descriptive"
    # SOURCE: descriptive EMA ordering and close location; no trade authority.
    trend = None if state != "descriptive" else "rising" if tail[-1] > fast > slow else "falling" if tail[-1] < fast < slow else "mixed"
    return {"interval": interval, "status": state, "closedBars": closed_count,
            "contiguousBars": len(tail), "requiredBars": max(EMA_WINDOWS),
            "lastBarAt": utc(previous) if previous else None,
            "lastBarClosedAt": utc(period_end(previous, interval)) if previous else None,
            "expectedLatestBarAt": utc(latest_expected) if latest_expected else None,
            "close": tail[-1] if tail else None, "ema20": fast, "ema50": slow,
            "trend": trend, "closure": "next native midnight / Monday midnight; conservative weekly boundary",
            "orderAuthority": False, "winProbability": None}


def fetch_native(request, url, symbols, interval, start, as_of, credentials, equities):
    query = {"symbols": ",".join(symbols), "timeframe": interval,
             "start": utc(start), "end": utc(as_of), "sort": "asc", "limit": PAGE_LIMIT}
    if equities:
        query.update({"feed": "iex", "adjustment": "raw"})
    result, tokens = {symbol: [] for symbol in symbols}, set()
    while True:
        payload = request(url + "?" + urllib.parse.urlencode(query), credentials)
        if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
            raise ValueError("native bars response missing")
        for symbol, rows in payload["bars"].items():
            if symbol not in result or not isinstance(rows, list):
                raise ValueError("native bar scope mismatch")
            result[symbol].extend(rows)
        token = payload.get("next_page_token")
        if not token:
            return result
        if not isinstance(token, str) or token in tokens:
            raise ValueError("native bar pagination did not advance")
        tokens.add(token)
        query["page_token"] = token


def collect(request, paper_get, stock_url, crypto_url, universes, credentials, as_of, previous=None):
    """Called in the existing serialized scan; never adds a separate orderer."""
    if "AAPL" in universes.get("Alpaca equities", ()) or any(s not in ("BTC/USD", "ETH/USD", "SOL/USD") for s in universes.get("Alpaca crypto", ())):
        raise ValueError("protected or excluded Alpaca instrument")
    if previous and previous.get("orderAuthority") is False and previous.get("winProbability") is None:
        age = (as_of - instant(previous["retrievedAt"])).total_seconds()
        same_scope = previous.get("scope") == {v: list(s) for v, s in universes.items() if v.startswith("Alpaca")}
        if 0 <= age < REFRESH_SECONDS and same_scope:
            return previous
    markets, errors = {}, []
    scope = {v: list(s) for v, s in universes.items() if v.startswith("Alpaca")}
    for venue, symbols in scope.items():
        equities = venue == "Alpaca equities"
        zone = NEW_YORK if equities else timezone.utc
        monday = start_of_week(as_of.astimezone(zone).date())
        start = datetime.combine(monday - timedelta(weeks=HISTORY_WEEKS), datetime.min.time(), zone)
        calendar = []
        try:
            if equities:
                params = {"start": start.date().isoformat(), "end": as_of.astimezone(zone).date().isoformat()}
                calendar = paper_get("/v2/calendar?" + urllib.parse.urlencode(params), credentials)
                if not isinstance(calendar, list):
                    raise ValueError("primary context calendar missing")
            for interval in INTERVALS:
                try:
                    rows = fetch_native(request, stock_url if equities else crypto_url, symbols,
                                        interval, start, as_of, credentials, equities)
                    for symbol in symbols:
                        key = venue + "|" + symbol
                        entry = markets.setdefault(key, {"source": "Alpaca IEX raw" if equities else "Alpaca crypto US",
                            "knowledge": "historical_as_retrieved_not_point_in_time", "frames": {},
                            "orderAuthority": False, "winProbability": None})
                        try:
                            entry["frames"][interval] = summarize(rows[symbol], interval, start, as_of, equities, calendar)
                        except (ValueError, KeyError, TypeError) as error:
                            entry["frames"][interval] = {"status": "invalid", "reason": type(error).__name__, "orderAuthority": False, "winProbability": None}
                except Exception as error:
                    errors.append({"venue": venue, "interval": interval, "error": type(error).__name__})
        except Exception as error:
            errors.append({"venue": venue, "error": type(error).__name__})
    return {"asOf": utc(as_of), "retrievedAt": utc(datetime.now(timezone.utc)), "scope": scope,
            "markets": markets, "errors": errors, "orderAuthority": False, "winProbability": None,
            "missing": "Monthly history and primary context outside Alpaca remain unavailable"}
