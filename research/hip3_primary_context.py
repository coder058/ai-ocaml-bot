"""Native HIP-3 primary bars, public data only and historical as retrieved.

Provider: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
Actual xyz:EUR and xyz:XYZ100 weekly responses observed 2026-10-05 use the
Unix epoch grid (Thursday UTC), unlike Alpaca's Monday weekly boundary.
Each row must validate that grid and its inclusive provider end timestamp.
Actual 1M responses use fixed 30-day epoch blocks, not calendar months.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from primary_trend_context import EMA_WINDOWS, HISTORY_WEEKS, HISTORY_MONTHS, REFRESH_SECONDS, ema, instant, utc

# SOURCE: supported native intervals and UTC duration observed in actual
# provider t/T fields. Weekly alignment is checked, never shifted to Monday.
PERIOD_MS = {"1d": 24 * 60 * 60 * 1_000, "1w": 7 * 24 * 60 * 60 * 1_000,
             # SOURCE: actual xyz:EUR/xyz:XYZ100 1M t/T on 2026-10-05:
             # Sep4-Oct4-Nov3 UTC, exactly 30-day Unix epoch blocks. This
             # provider interval is NOT a calendar month like Alpaca 1Month.
             "1M": 30 * 24 * 60 * 60 * 1_000}
DISPLAY_INTERVAL = {"1d": "1Day", "1w": "1Week", "1M": "Native1M"}
INFO_ORIGIN = "https://api.hyperliquid.xyz/info"  # SOURCE: official public info origin.
VENUE = "Hyperliquid HIP-3"
# GUESS: # UNCALIBRATED GUESS — fetch at most one instrument (three native
# requests) per serialized scan to avoid a full-universe bootstrap burst. Measure
# scanner latency and coverage before changing this operational scheduling.
SYMBOLS_PER_SCAN = 1


def milliseconds(at):
    # SOURCE: provider protocol uses integer Unix milliseconds.
    return int(at.timestamp() * 1_000)


def timestamp(value):
    return utc(datetime.fromtimestamp(value / 1_000, timezone.utc))


def summarize(rows, symbol, interval, start, as_of):
    period = PERIOD_MS[interval]
    lower, upper = milliseconds(start), milliseconds(as_of)
    latest_expected = upper // period * period - period
    tail, previous, seen, closed = [], None, None, 0
    for row in rows:
        at, end = row["t"], row["T"]
        if (isinstance(at, bool) or not isinstance(at, int) or
                isinstance(end, bool) or not isinstance(end, int) or
                at % period or end + 1 != at + period):
            raise ValueError("native HIP-3 period grid/duration mismatch")
        if row.get("s") != symbol or row.get("i") != interval:
            raise ValueError("native HIP-3 instrument/interval mismatch")
        if seen is not None and at <= seen:
            raise ValueError("native HIP-3 periods are not increasing")
        seen = at
        if any(isinstance(row[k], bool) for k in ("o", "h", "l", "c", "v")):
            raise ValueError("boolean native HIP-3 OHLCV")
        op, hi, lo, close, volume = (float(row[k]) for k in ("o", "h", "l", "c", "v"))
        if (not all(math.isfinite(n) for n in (op, hi, lo, close, volume)) or
                not 0 < lo <= min(op, close) <= max(op, close) <= hi or volume < 0):
            raise ValueError("invalid native HIP-3 OHLCV")
        if at < lower or at + period > upper:
            continue  # An API response may include its still-open native bar.
        if previous is not None and at != previous + period:
            tail = []
        tail.append(close)
        previous, closed = at, closed + 1
    fast, slow = (ema(tail, window) for window in EMA_WINDOWS)
    state = ("no_data" if not tail else "stale" if previous != latest_expected
             else "warming" if slow is None else "descriptive")
    trend = (None if state != "descriptive" else "rising" if tail[-1] > fast > slow
             else "falling" if tail[-1] < fast < slow else "mixed")
    return {"interval": DISPLAY_INTERVAL[interval], "providerInterval": interval,
            "status": state, "closedBars": closed, "contiguousBars": len(tail),
            "requiredBars": max(EMA_WINDOWS), "lastBarAt": timestamp(previous) if previous is not None else None,
            "lastBarClosedAt": timestamp(previous + period) if previous is not None else None,
            "expectedLatestBarAt": timestamp(latest_expected), "close": tail[-1] if tail else None,
            "ema20": fast, "ema50": slow, "trend": trend,
            "closure": ("next 30-day boundary on the validated Unix epoch grid; not a calendar month" if interval == "1M"
                else "next UTC midnight" if interval == "1d" else "next native Thursday 00:00 UTC (validated Unix epoch grid)"),
            "periodKind": "fixed_30_day_epoch_grid" if interval == "1M" else "fixed_native_epoch_grid",
            "source": "Hyperliquid public native candleSnapshot " + interval,
            "adjustment": "not_applicable", "knowledge": "historical_as_retrieved_not_point_in_time",
            "orderAuthority": False, "winProbability": None}


def collect(request, universes, as_of, previous=None):
    """One budgeted public symbol per scan; failures do not starve other symbols.

    Successful cached receipt timestamps remain unchanged on a failed refresh.
    lastAttemptAt is scheduling evidence, not a successful data receipt.
    """
    symbols = list(universes.get(VENUE, ()))
    if any(not isinstance(s, str) or ":" not in s for s in symbols) or len(set(symbols)) != len(symbols):
        raise ValueError("HIP-3 scope must contain unique provider-qualified instruments")
    prior = previous if isinstance(previous, dict) else {}
    if prior.get("orderAuthority") is not False or prior.get("winProbability") is not None:
        prior = {}
    markets = {s: prior.get("markets", {}).get(s, {}) for s in symbols}
    def age(entry, field):
        try:
            if not isinstance(entry.get(field), str):
                return math.inf
            elapsed = (as_of - instant(entry[field])).total_seconds()
            return elapsed if elapsed >= 0 else math.inf
        except (KeyError, ValueError, TypeError):
            return math.inf
    # SOURCE: an earlier two-interval cache is not evidence of a 1M request.
    # Record attempted interval schema even on failure, retaining retry cadence.
    due = [s for s in symbols if age(markets[s], "lastAttemptAt") >= REFRESH_SECONDS
           or markets[s].get("intervalsAttempted") != list(PERIOD_MS)]
    # Oldest real attempt first; dict order breaks ties, including initial seed.
    due.sort(key=lambda s: age(markets[s], "lastAttemptAt"), reverse=True)
    for symbol in due[:SYMBOLS_PER_SCAN]:
        old = markets[symbol]
        entry = {**old, "lastAttemptAt": utc(as_of), "errors": [],
                 "source": "Hyperliquid public native candles", "knowledge": "historical_as_retrieved_not_point_in_time",
                 "intervalsAttempted": list(PERIOD_MS),
                 "missing": "Provider 1M is a native 30-day block, not a calendar month; short histories may not warm EMA50. Public perpetual data, no spot FX or execution adapter.",
                 "orderAuthority": False, "winProbability": None}
        frames = dict(old.get("frames", {}))
        for interval, period in PERIOD_MS.items():
            # SOURCE: existing EMA50 previous/leading allowance, applied to
            # native 30-day blocks for 1M and the unchanged weekly range otherwise.
            upper = milliseconds(as_of)
            start = upper // period * period - (HISTORY_MONTHS * period if interval == "1M"
                                               else HISTORY_WEEKS * PERIOD_MS["1w"])
            try:
                rows = request(INFO_ORIGIN, body={"type": "candleSnapshot", "req": {
                    "coin": symbol, "interval": interval, "startTime": start, "endTime": upper}})
                if not isinstance(rows, list):
                    raise ValueError("native HIP-3 response must be a candle array")
                reading = summarize(rows, symbol, interval,
                                    datetime.fromtimestamp(start / 1_000, timezone.utc), as_of)
                reading["asOf"] = utc(as_of)
                reading["retrievedAt"] = utc(datetime.now(timezone.utc))
                frames[DISPLAY_INTERVAL[interval]] = reading
            except Exception as error:
                # Preserve old receipt/value, but disclose failure and the actual
                # new attempt separately. No exception payload or secrets.
                entry["errors"].append({"interval": interval, "error": type(error).__name__})
        entry["frames"] = frames
        receipts = [f.get("retrievedAt") for f in frames.values() if f.get("retrievedAt")]
        entry["retrievedAt"] = max(receipts) if receipts else None
        entry["asOf"] = max((f.get("asOf", "") for f in frames.values()), default=None)
        markets[symbol] = entry
    return {"scope": symbols, "markets": markets, "orderAuthority": False, "winProbability": None}
