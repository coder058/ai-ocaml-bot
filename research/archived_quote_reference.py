"""Use actual already-captured quote receipts for prospective research only.

No new WebSocket, network request, quote fabrication or order authority. A
bounded frozen file tail can miss data; missing coverage is not repaired from
older/future events. REST remains available and old feature rows are immutable.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from decision_quote_capture import MAX_QUOTE_AGE_SECONDS, normalize_at, quote_time, utc

# GUESS: # UNCALIBRATED GUESS — read at most 1 MiB per daily capture tail;
# measure event density and scanner CPU before expanding. Older omitted quotes
# cannot be assumed to exist or to be fresh.
TAIL_BYTES = 1024 * 1024
# SOURCE: nanosecond Unix receipt fields written by both existing capture tools.
NS_PER_SECOND = 1_000_000_000
CRYPTO_ALLOWED = {"BTC/USD", "ETH/USD", "SOL/USD"}  # SOURCE: user's restriction.


def receipt_text(ns):
    if isinstance(ns, bool) or not isinstance(ns, int) or ns <= 0:
        raise ValueError("invalid captured receipt nanoseconds")
    seconds, fraction = divmod(ns, NS_PER_SECOND)
    base = datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{base}.{fraction:09d}Z"


def latest_from_tail(path, venue, symbols, cutoff, limit=TAIL_BYTES):
    """Latest actual received quote per instrument, never best-price selection."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("archive read limit must be a positive integer")
    if venue not in ("Alpaca crypto", "Alpaca equities"):
        raise ValueError("unsupported captured quote venue")
    allowed = set(symbols)
    if "AAPL" in allowed or venue == "Alpaca crypto" and not allowed <= CRYPTO_ALLOWED:
        raise ValueError("protected/excluded quote scope")
    latest, offsets = {}, {}
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            end = handle.tell()  # Freeze the prefix; later appends are not read.
            start = max(0, end - limit)
            handle.seek(start)
            raw = handle.read(end - start)
    except FileNotFoundError:
        return {}, {"status": "archive_absent", "bytesRead": 0}
    except OSError:
        return {}, {"status": "archive_read_error", "bytesRead": 0}
    lines = raw.splitlines(keepends=True)
    if start:
        lines = lines[1:]  # First tail row may be a partial record.
    for line in lines:
        if not line.endswith(b"\n"):
            continue  # Never consume an in-progress append.
        try:
            record = json.loads(line)
            event = record["event"]
            symbol = event.get("S")
            if event.get("T") != "q" or symbol not in allowed:
                continue
            if venue == "Alpaca crypto" and record.get("feed") != "alpaca-us":
                continue
            ns = record["receivedAtNs"]
            receipt = receipt_text(ns)
            seconds = quote_time(receipt)
            if seconds > cutoff:
                continue
            if symbol in offsets and ns < offsets[symbol]:
                continue
            if symbol in offsets and ns == offsets[symbol] and event != latest[symbol]["event"]:
                # An ambiguous duplicated receipt cannot select a favorable row.
                latest[symbol] = {"event": {}, "receipt": receipt}
            else:
                latest[symbol] = {"event": event, "receipt": receipt}
            offsets[symbol] = ns
        except (ValueError, KeyError, TypeError, OverflowError, AttributeError):
            continue
    quotes = {symbol: normalize_at(item["event"], item["receipt"], venue, symbol)
              for symbol, item in latest.items()}
    return quotes, {"status": "read", "bytesRead": len(raw), "quotesFound": len(quotes)}


def augment(rest, universes, capture_root, as_of):
    """Select newer fresh source evidence at a fixed cutoff; no retrospective fix.

    Source quote and actual receipt must both remain within the inherited
    five-second guard at this read. A subsequent feature observation can still
    expire it; the causal audit performs its independent observation-time check.
    """
    as_of = as_of.astimezone(timezone.utc)
    cutoff = quote_time(utc(as_of))
    result, details, states = dict(rest), [], {}
    for venue, folder in (("Alpaca crypto", "us"), ("Alpaca equities", "iex")):
        symbols = universes.get(venue, ())
        latest = {}
        # SOURCE: existing captures rotate at UTC midnight. Include preceding
        # day so a fresh event just before midnight is not lost to rotation.
        for day in (as_of.date() - timedelta(days=1), as_of.date()):
            quotes, diagnostic = latest_from_tail(capture_root / folder / f"{day.isoformat()}.jsonl", venue, symbols, cutoff)
            details.append({"venue": venue, "day": day.isoformat(), **diagnostic})
            for symbol, quote in quotes.items():
                if symbol not in latest or quote_time(quote["receivedAt"]) > quote_time(latest[symbol]["receivedAt"]):
                    latest[symbol] = quote
        for symbol, quote in latest.items():
            key = venue + "|" + symbol
            states[key] = {"statusAtCaptureReceipt":quote.get("status"), "reason":quote.get("reason"),
                           "receivedAt":quote.get("receivedAt"), "quoteAt":quote.get("quoteAt"),
                           "selected":False}
            if quote.get("status") != "fresh":
                continue
            at, receipt = quote_time(quote["quoteAt"]), quote_time(quote["receivedAt"])
            states[key].update({"sourceAgeSecondsAtRead":float(cutoff-at),
                                "receiptAgeSecondsAtRead":float(cutoff-receipt)})
            if not (0 <= cutoff - at <= MAX_QUOTE_AGE_SECONDS and
                    0 <= cutoff - receipt <= MAX_QUOTE_AGE_SECONDS):
                continue
            original = result.get(key, {})
            try:
                if original.get("status") == "fresh" and at <= quote_time(original["quoteAt"]):
                    continue
            except (ValueError, TypeError, KeyError):
                continue  # A malformed purportedly-fresh REST row is not repaired.
            result[key] = {**quote, "transport": "existing_archived_websocket",
                           "referenceCheckedAt": utc(as_of)}
            states[key]["selected"] = True
    return result, {"checkedAt": utc(as_of), "archives": details,
                    "references":states,
                    "streamSelected": sum(q.get("transport") == "existing_archived_websocket" for q in result.values()),
                    "orderAuthority": False, "winProbability": None}
