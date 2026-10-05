"""Native closed-candle warmup and shared OCaml market/frame analysis.

REST history is knowledge only after retrieval, never a point-in-time backtest.
This scanner cannot submit orders. A cache makes slower frames incremental;
native provider bars prevent a lost 1m stream message from erasing a 4h frame.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from hyperliquid_capture import COINS
from stream_capture import credentials as stream_credentials
from murphy_analysis import enrich, required_seed_bars, forward_reading
from primary_trend_context import collect as collect_primary_context
from hip3_primary_context import collect as collect_hip3_primary_context
from hip3_asset_context import collect as collect_hip3_asset_context
from decision_quote_capture import collect as collect_decision_quotes
from archived_quote_reference import augment as augment_archived_quotes
from stock_session_opportunities import protocol as stock_opportunity_protocol, prepare as prepare_stock_opportunities

# SOURCE: requested timeframes and official Alpaca / Hyperliquid interval names.
FRAMES = {"1m": (1, "1Min"), "5m": (5, "5Min"), "30m": (30, "30Min"),
          "1h": (60, "1Hour"), "4h": (240, "4Hour")}
# SOURCE: Pattern Forge EMA50 requires 50 closes; one additional candle retains
# a preceding shape context. This is an initialization minimum, not calibration.
SEED_BARS = max(51, required_seed_bars())
# GUESS: # UNCALIBRATED GUESS — keep at most 1,000 bars per market/frame in the
# operational cache. Measure RAM and disk as the universe grows.
MAX_CACHE_BARS = 1_000
# SOURCE: provider URLs from the official API documentation.
CRYPTO_BARS = "https://data.alpaca.markets/v1beta3/crypto/us/bars"
STOCK_BARS = "https://data.alpaca.markets/v2/stocks/bars"
HL_INFO = "https://api.hyperliquid.xyz/info"
PAPER_ORIGIN = "https://paper-api.alpaca.markets"
# SOURCE: user requested popular stocks, Dow/Nasdaq and energy; these listed ETF
# proxies are explicit instruments, not cash indices or physical energy prices.
EQUITIES = ("DIA", "QQQ", "SPY", "IWM", "VTI", "VOO", "XLK", "XLF", "XLV", "XLI",
            "XLY", "XLP", "XLU", "XLB", "XLRE", "SMH", "SOXX", "ARKK", "TLT", "IEF",
            "HYG", "LQD", "GLD", "SLV", "XLE", "XOP", "USO", "UNG", "BNO", "OIH",
            "UUP", "FXE", "FXY", "FXB", "FXC", "FXA", "FXF", "TSLA", "NVDA", "MSFT",
            "AMZN", "GOOGL", "META", "AMD", "AVGO", "NFLX", "INTC", "MU", "ORCL",
            "CRM", "ADBE", "PLTR", "JPM", "BAC", "GS", "V", "MA", "XOM", "CVX",
            "COP", "OXY", "SLB", "WMT", "COST", "KO", "PEP", "MCD", "CAT", "BA")
CRYPTO_ALLOWED = {"BTC/USD", "ETH/USD", "SOL/USD"}  # SOURCE: user's crypto restriction.
CURRENCY_ETFS = {"UUP", "FXE", "FXY", "FXB", "FXC", "FXA", "FXF"}  # SOURCE: listed FX ETF proxies.
ENERGY_ETFS = {"XLE", "XOP", "USO", "UNG", "BNO", "OIH"}  # SOURCE: listed sector/commodity ETF proxies.
# SOURCE: the old HIP-3 watchlist plus additional energy contracts verified in
# the live xyz meta catalog on 2026-10-01. Availability is rechecked each run.
HIP3_REQUESTED = (*COINS, "xyz:CL", "xyz:NATGAS", "xyz:XLE", "xyz:GOLD", "xyz:SILVER")
STATE = Path("/home/ubuntu/jsbot-paper-state")
ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "_build/default/bin/analyze_frames_main.exe"
# GUESS: # UNCALIBRATED GUESS — bound each external fetch and OCaml batch at
# 30 seconds; measure timeouts and processing as the market universe grows.
TIMEOUT_SECONDS = 30
# SOURCE: Hyperliquid REST weight 1200/minute, candleSnapshot base 20 plus one
# per 60 returned bars. Pace after the measured response weight to respect the
# documented budget; existing WS capture does not spend that REST budget.
HL_WEIGHT_PER_MINUTE = 1_200
HL_BASE_WEIGHT = 20
HL_ROWS_PER_WEIGHT = 60
# SOURCE: Hyperliquid candleSnapshot supports native daily/weekly bars. Keep
# transport durations separate from the user's five analyzed intraday frames.
HL_NATIVE_MINUTES = {name:minutes for name,(minutes,_) in FRAMES.items()} | {"1d":24*60,"1w":7*24*60,
    # SOURCE: actual provider 1M t/T observed 2026-10-05: 30-day epoch blocks,
    # not calendar months. Used for documented request-weight reservation.
    "1M":30*24*60}
# SOURCE: Alpaca documents a maximum of 10,000 total bars per response page.
ALPACA_PAGE_LIMIT = 10_000
# SOURCE: US stock exchange calendar sessions are expressed in New York time.
NEW_YORK = ZoneInfo("America/New_York")


class RestBudget:
    """Persist a sliding-window public REST budget across one-shot scans."""

    def __init__(self, path: Path, clock=time.time, sleep=time.sleep):
        self.path, self.clock, self.sleep = path, clock, sleep

    def acquire(self, weight: int) -> None:
        if not 0 < weight <= HL_WEIGHT_PER_MINUTE:
            raise ValueError("request cannot fit the documented REST budget")
        entries = json.loads(self.path.read_text()) if self.path.exists() else []
        while True:
            now = self.clock()
            # SOURCE: Hyperliquid's documented per-minute sliding IP budget.
            entries = [entry for entry in entries if entry[0] + 60 > now]
            used = sum(entry[1] for entry in entries)
            if used + weight <= HL_WEIGHT_PER_MINUTE:
                entries.append([now, weight])
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(json.dumps(entries), encoding="utf-8")
                os.chmod(temporary, 0o640)  # SOURCE: private operational budget.
                os.replace(temporary, self.path)
                return
            delay = min(entry[0] for entry in entries) + 60 - now
            self.sleep(max(0, delay))


HL_BUDGET = RestBudget(STATE / "hip3-rest-budget.json")


def instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def request(url: str, credentials: dict | None = None, body: dict | None = None) -> object:
    headers = {"Accept": "application/json"}
    if credentials:
        headers.update({"APCA-API-KEY-ID": credentials["APCA_API_KEY_ID"],
                        "APCA-API-SECRET-KEY": credentials["APCA_API_SECRET_KEY"]})
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if url == HL_INFO:
        weight = HL_BASE_WEIGHT
        if body and body.get("type") == "candleSnapshot":
            req = body["req"]
            duration = HL_NATIVE_MINUTES[req["interval"]] * 60_000
            maximum_rows = math.ceil((req["endTime"] - req["startTime"]) / duration) + 1
            weight += math.ceil(maximum_rows / HL_ROWS_PER_WEIGHT)
        HL_BUDGET.acquire(weight)
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers),
                                timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def normalize(row: dict, minutes: int, as_of: datetime, *, hip3: bool = False) -> dict | None:
    started = (datetime.fromtimestamp(int(row["t"]) / 1_000, timezone.utc)
               if hip3 else instant(row["t"]))
    if started.timestamp() % (minutes * 60):
        raise ValueError("bar is not frame aligned")
    if hip3 and int(row["T"]) + 1 != int(started.timestamp() * 1_000) + minutes * 60_000:
        raise ValueError("HIP-3 duration does not match frame")
    if started + timedelta(minutes=minutes) > as_of:
        return None
    values = {key: float(row[key]) for key in ("o", "h", "l", "c", "v")}
    op, hi, lo, close, volume = (values[k] for k in ("o", "h", "l", "c", "v"))
    if (not all(math.isfinite(value) for value in values.values()) or
            not 0 < lo <= min(op, close) <= max(op, close) <= hi or volume < 0):
        raise ValueError("invalid OHLCV")
    return {"t": utc(started), **values}


def paper_get(path: str, credentials: dict) -> object:
    # SOURCE: only catalog, clock and calendar reads are needed by this scanner;
    # its broker origin is hardcoded paper and request() never posts to it.
    if not (path.startswith("/v2/assets?") or path.startswith("/v2/calendar?") or path == "/v2/clock"):
        raise ValueError("scanner broker path is outside the read-only allowlist")
    return request(PAPER_ORIGIN + path, credentials)


def analyze_fingerprinted(payload: dict, engine: Path):
    """Retain actual analyzer identity; a concurrent replacement fails closed."""
    engine_sha256 = hashlib.sha256(engine.read_bytes()).hexdigest()
    proc = subprocess.run([str(engine)], input=json.dumps(payload).encode(),
                          capture_output=True, timeout=TIMEOUT_SECONDS, check=False)
    if proc.returncode:
        raise RuntimeError("shared OCaml analysis failed")
    if hashlib.sha256(engine.read_bytes()).hexdigest() != engine_sha256:
        raise RuntimeError("shared OCaml analyzer changed during the scan")
    return json.loads(proc.stdout), engine_sha256


def merge(prior: list[dict], new: list[dict]) -> list[dict]:
    by_start = {row["t"]: row for row in prior}
    by_start.update({row["t"]: row for row in new})
    return [by_start[key] for key in sorted(by_start)[-MAX_CACHE_BARS:]]


def category(symbol: str, venue: str) -> str:
    if venue == "Alpaca crypto":
        return "Crypto"
    if venue == "Alpaca equities" and symbol in CURRENCY_ETFS:
        return "Currency ETF proxies"
    if venue == "Alpaca equities" and symbol in ENERGY_ETFS:
        return "Energy"
    name = symbol.removeprefix("xyz:")
    if name in ("EUR", "GBP", "JPY"):
        return "FX-like perps"
    if name in ("XYZ100", "SP500", "DIA", "QQQ", "SPY"):
        return "Index proxies"
    if name in ("BRENTOIL", "CL", "NATGAS", "XLE", "XOP"):
        return "Energy"
    if name in ("GOLD", "SILVER"):
        return "Metals"
    return "Stocks" if venue == "Alpaca equities" else "Equity perps"


def alpaca_bars(symbols: list[str], frame: str, start: datetime, as_of: datetime,
                credentials: dict, *, equities: bool = False) -> dict[str, list[dict]]:
    minutes, interval = FRAMES[frame]
    query = {"symbols": ",".join(symbols), "timeframe": interval, "start": utc(start),
             "end": utc(as_of), "sort": "asc", "limit": str(ALPACA_PAGE_LIMIT)}
    if equities:
        # SOURCE: free paper/IEX feed; not the consolidated SIP equities feed.
        query.update({"feed": "iex", "adjustment": "raw"})
    result = {symbol: [] for symbol in symbols}
    tokens: set[str] = set()
    while True:
        payload = request((STOCK_BARS if equities else CRYPTO_BARS) + "?" +
                          urllib.parse.urlencode(query), credentials)
        if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
            raise ValueError("provider bars response missing")
        for symbol, rows in payload["bars"].items():
            if symbol not in result or not isinstance(rows, list):
                raise ValueError("unexpected provider symbol or bars")
            for row in rows:
                normalized = normalize(row, minutes, as_of)
                if normalized is not None:
                    result[symbol].append(normalized)
        token = payload.get("next_page_token")
        if not token:
            return result
        if not isinstance(token, str) or token in tokens:
            raise ValueError("bar pagination did not advance")
        tokens.add(token)
        query["page_token"] = token


def session_slots(calendar: list[dict], minutes: int) -> list[int]:
    slots = set()
    for session in calendar:
        opened = datetime.fromisoformat(session["date"] + "T" + session["open"]).replace(tzinfo=NEW_YORK)
        closed = datetime.fromisoformat(session["date"] + "T" + session["close"]).replace(tzinfo=NEW_YORK)
        first = int(opened.timestamp()) // (minutes * 60) * minutes
        last = (int(closed.timestamp()) - 1) // (minutes * 60) * minutes
        slots.update(range(first, last + minutes, minutes))
    return sorted(slots)


def relevant_calendar(frames: dict, slots: dict) -> dict:
    """Drop only calendar history preceding this instrument's retained candles.

    Keep all later expected slots, including missing bars and future sessions,
    so adjacency and missing-latest checks cannot be relaxed by the projection.
    """
    result={}
    for frame,starts in slots.items():
        rows=frames.get(frame,[])
        if rows:
            # SOURCE: session_slots and the OCaml engine use UTC minutes. Native
            # cache rows are sorted by merge; retain the first candle's slot.
            first=int(instant(rows[0]["t"]).timestamp())//60
            trimmed=starts[bisect_left(starts,first):]
            # Preserve original behavior if the candle lies outside this
            # calendar; an empty array would switch OCaml to its 24/7 fallback.
            result[frame]=trimmed or starts
        else:
            result[frame]=starts
    return result


def hip3_bars(symbol: str, frame: str, start: datetime, as_of: datetime) -> list[dict]:
    minutes, _ = FRAMES[frame]
    payload = request(HL_INFO, body={"type": "candleSnapshot", "req": {
        "coin": symbol, "interval": frame, "startTime": int(start.timestamp() * 1_000),
        "endTime": int(as_of.timestamp() * 1_000)}})
    if not isinstance(payload, list):
        raise ValueError("HIP-3 candle response is not an array")
    rows = []
    for row in payload:
        if row.get("s") != symbol or row.get("i") != frame:
            raise ValueError("HIP-3 response symbol or interval mismatch")
        normalized = normalize(row, minutes, as_of, hip3=True)
        if normalized is not None:
            rows.append(normalized)
    return rows


def atomic(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as target:
        json.dump(document, target, separators=(",", ":"), allow_nan=False)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    os.chmod(temporary, 0o640)  # SOURCE: private market-only owner/group snapshot.
    if os.name == "posix":
        # SOURCE: the separate OCaml paper service runs as the state-directory
        # owner's group, and must read market-only snapshots without root.
        os.chown(temporary, -1, path.parent.stat().st_gid)
    os.replace(temporary, path)


def scan(cache_path: Path, output: Path, engine: Path = ENGINE) -> dict:
    started = time.monotonic()
    # SOURCE: measured monotonic elapsed seconds per scanner phase. These are
    # operational timings, not exchange-to-order latency or fitted thresholds.
    timings = {}
    phase_started = started
    def elapsed(name):
        nonlocal phase_started
        now = time.monotonic()
        timings[name] = now - phase_started
        phase_started = now
    as_of = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    key, secret = stream_credentials()
    credentials = {"APCA_API_KEY_ID": key, "APCA_API_SECRET_KEY": secret}
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {"markets": {}}
    markets = cache["markets"]
    errors = []
    assets = paper_get("/v2/assets?status=active&asset_class=crypto", credentials)
    if not isinstance(assets, list):
        raise ValueError("paper asset catalog missing")
    crypto = sorted(a["symbol"] for a in assets if a.get("tradable") is True and
                    a.get("status") == "active" and a.get("symbol") in CRYPTO_ALLOWED)
    stock_assets = paper_get("/v2/assets?status=active&asset_class=us_equity", credentials)
    if not isinstance(stock_assets, list):
        raise ValueError("stock/ETF asset catalog missing")
    tradeable_stocks = {a["symbol"]: a for a in stock_assets
        if a.get("tradable") is True and a.get("status") == "active" and a.get("class") == "us_equity"}
    equities = [symbol for symbol in EQUITIES if symbol in tradeable_stocks and symbol != "AAPL"]
    atomic(output.with_name("instrument-catalog.json"), {
        "asOf": utc(as_of), "provider": "Alpaca paper", "catalogOnly": True,
        "stockEtfCount": len(tradeable_stocks), "monitoredStocks": equities,
        "unavailableRequestedStocks": [s for s in EQUITIES if s not in tradeable_stocks],
        "cryptoAllowed": crypto, "protectedStocks": ["AAPL"],
        "assets": [{k: a.get(k) for k in ("symbol", "name", "exchange", "fractionable", "shortable")}
                   for _, a in sorted(tradeable_stocks.items())]})
    hl_meta, derivative_contexts, context_errors = collect_hip3_asset_context(request)
    errors.extend(context_errors)
    active_hl = {a["name"] for a in hl_meta["universe"] if not a.get("isDelisted")}
    hip3 = [symbol for symbol in HIP3_REQUESTED if symbol in active_hl]
    # GUESS: # UNCALIBRATED GUESS — request two calendar days per seed bar to
    # cover weekends/holidays; actual returned sessions define all adjacency.
    calendar_start = (as_of - timedelta(days=SEED_BARS * 2)).date().isoformat()
    calendar_query = urllib.parse.urlencode({"start": calendar_start, "end": as_of.date().isoformat()})
    calendar = paper_get("/v2/calendar?" + calendar_query, credentials)
    clock = paper_get("/v2/clock", credentials)
    equity_slots = {name: session_slots(calendar, minutes) for name, (minutes, _) in FRAMES.items()}
    universes = {"Alpaca crypto": crypto, "Alpaca equities": equities,
                 "Hyperliquid HIP-3": hip3}
    elapsed("catalog_and_session")
    for venue, symbols in universes.items():
        for symbol in symbols:
            markets.setdefault(f"{venue}|{symbol}", {"symbol": symbol, "venue": venue,
                "category": category(symbol, venue), "frames": {}, "fetches": {}})
    # SOURCE: slower frames first; fetch 1m last so the short horizon is freshest
    # after bootstrap. Native intervals are queried independently, not fabricated.
    for frame in reversed(FRAMES):
        frame_changed = False
        minutes, _ = FRAMES[frame]
        for venue, symbols in universes.items():
            # SOURCE: each provider batch uses its current retrieval boundary;
            # bootstrap of slower frames must not freeze all later 1m requests.
            as_of = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            bucket = int(as_of.timestamp()) // (minutes * 60)
            due = [s for s in symbols if markets[f"{venue}|{s}"]["fetches"].get(frame, {}).get("bucket") != bucket]
            if not due:
                continue
            seed_start = as_of - timedelta(minutes=(SEED_BARS + 1) * minutes)
            if venue == "Alpaca equities":
                eligible = [slot for slot in equity_slots[frame] if slot * 60 <= as_of.timestamp()]
                if eligible:
                    seed_start = datetime.fromtimestamp(eligible[-min(len(eligible), SEED_BARS + 1)] * 60, timezone.utc)
            oldest = []
            for symbol in due:
                prior = markets[f"{venue}|{symbol}"]["frames"].get(frame, [])
                oldest.append(instant(prior[-1]["t"]) if len(prior) >= SEED_BARS else seed_start)
            start = min(oldest)
            fetched: dict[str, list[dict]] = {}
            boundaries = {symbol: as_of for symbol in due}
            if venue.startswith("Alpaca"):
                try:
                    fetched = alpaca_bars(due, frame, start, as_of, credentials,
                                          equities=venue == "Alpaca equities")
                except Exception as error:
                    errors.append({"venue": venue, "frame": frame, "error": type(error).__name__})
            else:
                for symbol in due:
                    try:
                        current_boundary = datetime.now(timezone.utc).replace(second=0, microsecond=0)
                        fetched[symbol] = hip3_bars(symbol, frame, start, current_boundary)
                        boundaries[symbol] = current_boundary
                    except Exception as error:
                        errors.append({"venue": venue, "symbol": symbol, "frame": frame,
                                       "error": type(error).__name__})
            for symbol, new_rows in fetched.items():
                frame_changed = True
                market = markets[f"{venue}|{symbol}"]
                if venue == "Alpaca equities":
                    allowed = set(equity_slots[frame])
                    new_rows = [row for row in new_rows if int(instant(row["t"]).timestamp()) // 60 in allowed]
                market["frames"][frame] = merge(market["frames"].get(frame, []), new_rows)
                market["fetches"][frame] = {"bucket": int(boundaries[symbol].timestamp()) // (minutes * 60),
                    "requestedAsOf": utc(boundaries[symbol]), "retrievedAt": utc(datetime.now(timezone.utc))}
        # Persist completed frames during slow initial seed, so a failed/restarted
        # seed can resume. Missing symbols/frames still report no data explicitly.
        # Persist every changed frame for restart-safe warmup. Unchanged slower
        # frames do not need another identical multi-megabyte JSON checkpoint.
        if frame_changed:
            atomic(cache_path, cache)
    elapsed("native_history_and_cache")
    try:
        cache["primaryContext"] = collect_primary_context(request, paper_get, STOCK_BARS, CRYPTO_BARS,
            universes, credentials, datetime.now(timezone.utc), cache.get("primaryContext"))
    except (ValueError, KeyError, TypeError) as error:
        # A failed primary-context refresh must not stop the existing intraday
        # data/OMS path or silently present an old context as newly retrieved.
        errors.append({"stage": "primary_context", "error": type(error).__name__})
    primary_context = cache.get("primaryContext", {})
    try:
        cache["hip3PrimaryContext"] = collect_hip3_primary_context(request, universes,
            datetime.now(timezone.utc), cache.get("hip3PrimaryContext"))
    except (ValueError, KeyError, TypeError) as error:
        errors.append({"stage": "hip3_primary_context", "error": type(error).__name__})
    hip3_primary_context = cache.get("hip3PrimaryContext", {})
    elapsed("native_primary_context")
    final_as_of = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    requested = [{**markets[f"{venue}|{symbol}"],
                  "frames": {name: markets[f"{venue}|{symbol}"]["frames"].get(name, [])
                             for name in FRAMES},
                  **({"expectedStarts": relevant_calendar(markets[f"{venue}|{symbol}"]["frames"],equity_slots), "sessionOpen": clock.get("is_open") is True}
                     if venue == "Alpaca equities" else {})}
                 for venue, symbols in universes.items() for symbol in symbols]
    for market in requested:
        key = market["venue"] + "|" + market["symbol"]
        if market["venue"] == "Hyperliquid HIP-3":
            market["currentDerivativeContext"] = derivative_contexts.get(market["symbol"], {
                "status": "unavailable", "receivedAt": None, "historicalSeries": False,
                "orderAuthority": False, "winProbability": None,
                "confirmation": "Current public context unavailable; no historical OI confirmation"})
        market["primaryContext"] = ({**hip3_primary_context.get("markets", {}).get(market["symbol"], {}),
            "missing": "Public daily/weekly/native 1M context seeds one instrument per scan and may be warming. Provider 1M is a 30-day block, not calendar-month history.",
            "orderAuthority": False, "winProbability": None}
            if market["venue"] == "Hyperliquid HIP-3" else {**primary_context.get("markets", {}).get(key, {}),
            "asOf": primary_context.get("asOf"), "retrievedAt": primary_context.get("retrievedAt"),
            "missing": primary_context.get("missing", "Native primary context unavailable"),
            "errors": primary_context.get("errors", []), "orderAuthority": False, "winProbability": None})
    payload = {"asOf": utc(final_as_of), "markets": requested}
    # SOURCE: fingerprint the actual deployed analyzer before and after use;
    # subsequent first observations retain it without repairing old journals.
    result, engine_sha256 = analyze_fingerprinted(payload, engine)
    elapsed("shared_ocaml_analysis")
    enrich(result, requested, {name: minutes for name, (minutes, _) in FRAMES.items()})
    elapsed("descriptive_technical_analysis")
    quote_references, quote_errors = collect_decision_quotes(request, universes, credentials)
    elapsed("quote_reference_requests")
    quote_references, archive_quote_coverage = augment_archived_quotes(quote_references, universes,
        STATE / "market-capture", datetime.now(timezone.utc))
    elapsed("captured_quote_reference")
    errors.extend(quote_errors)
    seen_quotes = cache.setdefault("recordedQuoteReferences", {})
    with output.with_name("market-quotes-reference.jsonl").open("a", encoding="utf-8") as target:
        for key, quote in quote_references.items():
            identity = (quote.get("quoteAt"), quote.get("bid"), quote.get("ask"))
            if quote.get("quoteAt") and seen_quotes.get(key) != list(identity):
                target.write(json.dumps(quote, separators=(",", ":"), allow_nan=False) + "\n")
                seen_quotes[key] = list(identity)
        target.flush()
        os.fsync(target.fileno())
    for row, original in zip(result["markets"], requested, strict=True):
        row["category"] = original["category"]
        row["fetches"] = original["fetches"]
        row["execution"] = "Alpaca paper quote_cross_30s_v1" if row["symbol"] == "BTC/USD" else "analysis_only"
        row["dataSource"] = "native_historical_as_retrieved"
        quote = quote_references.get(row["venue"] + "|" + row["symbol"],
            {"status": "unconnected", "purpose": "observed_quote_reference_not_execution", "orderAuthority": False, "winProbability": None})
        for reading in row["frames"].values():
            # Freeze actual bid/ask known at this scan. Never backfill the
            # previous first-observed feature row with a later market price.
            reading["quoteReference"] = quote
    result.update({"retrievedAt": utc(datetime.now(timezone.utc)), "errors": errors,
                   "processingSeconds": time.monotonic() - started,
                   "marketsAnalyzed": len(requested),
                   "framesRequested": list(FRAMES), "brokerOrderSymbols": ["BTC/USD"],
                   "pipeline": ["Data", "Closed candles", "OCaml analysis", "Evidence and risk", "Paper orders"]})
    # SOURCE: preserve the first observed decision for a particular closed bar.
    # Later historical revisions do not overwrite that forward decision record.
    emitted = cache.setdefault("emitted", {})
    decisions = []
    for market in result["markets"]:
        for frame, reading in market["frames"].items():
            bar_start = reading.get("lastBarStart")
            key = f"{market['venue']}|{market['symbol']}|{frame}|{result['policy']}"
            if bar_start and emitted.get(key, "") < bar_start:
                decisions.append({"observedAt": result["retrievedAt"], "asOf": result["asOf"],
                    "venue": market["venue"], "symbol": market["symbol"], "frame": frame,
                    "policy": result["policy"], "engineSha256": engine_sha256,
                    "reading": forward_reading(reading), "orderAuthority": False})
                emitted[key] = bar_start
    if decisions:
        # SOURCE: append-only operational forward evidence, not broker executions.
        with output.with_name("market-frame-decisions.jsonl").open("a", encoding="utf-8") as target:
            for decision in decisions:
                target.write(json.dumps(decision, separators=(",", ":"), allow_nan=False) + "\n")
            target.flush()
            os.fsync(target.fileno())
    # SOURCE: a separate prospective session cohort. First-ever candle records
    # above remain immutable, including candles first seen after market close.
    # Freeze all first regular-session statuses/quotes, not just later signals.
    try:
        stock_base, stock_spec, stock_digest = stock_opportunity_protocol()
        result["engineSha256"] = engine_sha256
        stock_seen = cache.setdefault("stockSessionOpportunities", {})
        stock_records, stock_updates = prepare_stock_opportunities(result, clock, stock_seen,
                                                                   stock_base, stock_spec, stock_digest)
        stock_journal = output.with_name("stock-session-opportunities.jsonl")
        if stock_records or not stock_journal.exists():
            with stock_journal.open("a", encoding="utf-8") as target:
                for record in stock_records:
                    target.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
                target.flush()
                os.fsync(target.fileno())
        stock_seen.update(stock_updates)
        result["stockSessionOpportunities"] = {"selection": stock_spec["selection"],
            "protocolSha256": stock_digest, "createdAt": stock_spec["createdAt"],
            "newReadings": len(stock_records), "trackedSessionSlots": len(stock_seen),
            "orderAuthority": False, "winProbability": None}
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append({"stage": "stock_session_opportunities", "error": type(error).__name__})
        result["stockSessionOpportunities"] = {"status": "unavailable", "orderAuthority": False,
                                                "winProbability": None}
    atomic(cache_path, cache)
    elapsed("evidence_and_cache_write")
    result["timingsSeconds"] = timings
    result["archiveQuoteCoverage"] = archive_quote_coverage
    result["newFrameDecisions"] = len(decisions)
    result["engineSha256"] = engine_sha256
    result["currentCandidates"] = sum(reading.get("candidate") is not None
        for market in result["markets"] for reading in market["frames"].values())
    atomic(output, result)
    print(json.dumps({"asOf": result["asOf"], "markets": len(requested), "errors": len(errors),
                      "processingSeconds": result["processingSeconds"],"timingsSeconds":timings}), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=STATE / "market-pipeline-cache.json")
    parser.add_argument("--output", type=Path, default=STATE / "market-pipeline.json")
    parser.add_argument("--engine", type=Path, default=ENGINE)
    args = parser.parse_args()
    scan(args.cache, args.output, args.engine)
