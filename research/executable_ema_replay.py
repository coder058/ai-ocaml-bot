"""Chronological, fee-aware EMA paper replay over as-received Alpaca data.

This is a research-only replay. It does not connect to a broker, predict
probabilities, or submit orders. It uses the first observed minute bar (not
later revisions), waits until a complete timeframe is available, and executes
at the first later captured quote for the selected symbol. This immediate
top-of-book fill model is optimistic: it excludes broker/network latency,
queueing, partial fills and market impact.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

# SOURCE: Pattern Forge's documented EMA display periods; not calibrated for
# trading performance. They are frozen here to avoid fitting on this capture.
FAST_PERIOD = 20
SLOW_PERIOD = 50
# SOURCE: Alpaca's tier-one crypto taker fee, checked 2026-09-29:
# https://docs.alpaca.markets/us/docs/crypto-fees
TAKER_FEE_RATE = 0.0025
# SOURCE: UTC minute and day lengths, and Unix nanosecond timestamps.
NS_PER_SECOND = 1_000_000_000
SECONDS_PER_DAY = 86_400
MINUTE_NS = 60 * NS_PER_SECOND
DAY_NS = SECONDS_PER_DAY * NS_PER_SECOND
# SOURCE: one basis point is 1/10,000 of a relative price change.
BPS = 10_000
# SOURCE: the existing OCaml order process trades only BTC/USD; other captured
# symbols are research-only and can be selected explicitly with --symbol.
DEFAULT_SYMBOL = "BTC/USD"


def epoch_ns(value: str) -> int:
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})",
        value,
    )
    if not match:
        raise ValueError("timestamp must be timezone-aware ISO-8601")
    offset = "+00:00" if match.group(3) == "Z" else match.group(3)
    parsed = datetime.fromisoformat(match.group(1) + offset)
    fraction_ns = int((match.group(2) or "")[:9].ljust(9, "0") or "0")
    return int(parsed.timestamp()) * NS_PER_SECOND + fraction_ns


def utc_day(timestamp_ns: int) -> int:
    return timestamp_ns // DAY_NS


def read_capture(paths: list[Path], symbol: str = DEFAULT_SYMBOL) -> tuple[list[dict], dict, dict]:
    """Read valid quotes and first-seen minute bars for one symbol."""
    quotes: list[dict] = []
    minute_bars: dict[int, dict] = {}
    counts: Counter[str] = Counter()
    for path in paths:
        source_context = gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")
        with source_context as source:
            for raw_line in source:
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError as error:
                    if not raw_line.endswith(b"\n"):
                        counts["partialFinalLinesIgnored"] += 1
                        continue
                    raise ValueError(f"invalid JSON in complete line of {path}") from error
                event = record.get("event", {})
                if event.get("S") != symbol:
                    continue
                kind = event.get("T")
                if kind not in ("q", "b", "u"):
                    continue
                counts[f"event_{kind}"] += 1
                received_ns = int(record["receivedAtNs"])
                event_ns = epoch_ns(str(event["t"]))
                if kind == "q":
                    bid, ask = float(event["bp"]), float(event["ap"])
                    if not (math.isfinite(bid) and math.isfinite(ask) and 0 < bid < ask):
                        counts["invalidQuotes"] += 1
                        continue
                    quotes.append({"receivedNs": received_ns, "eventNs": event_ns,
                                   "bid": bid, "ask": ask})
                elif kind == "u":
                    # SOURCE: Alpaca updatedBars may revise a prior bar; this
                    # frozen study intentionally does not rewrite old inputs.
                    counts["updatedBarsIgnored"] += 1
                else:
                    slot = event_ns // MINUTE_NS
                    if slot in minute_bars:
                        counts["duplicateFirstBarsIgnored"] += 1
                        continue
                    values = {key: float(event[key]) for key in ("o", "h", "l", "c", "v")}
                    opening, high, low, close, volume = (values[key] for key in ("o", "h", "l", "c", "v"))
                    if not (all(math.isfinite(value) for value in values.values())
                            and 0 < low <= min(opening, close) <= max(opening, close) <= high
                            and volume >= 0):
                        counts["invalidBars"] += 1
                        continue
                    minute_bars[slot] = {"slot": slot, "receivedNs": received_ns, **values}
    quotes.sort(key=lambda item: item["receivedNs"])
    if any(right["receivedNs"] < left["receivedNs"]
           for left, right in zip(quotes, quotes[1:])):
        raise ValueError("quote receipt time regressed")
    return quotes, minute_bars, dict(counts)


def aggregate_as_received(minute_bars: dict[int, dict], frame_minutes: int) -> tuple[list[dict], int]:
    """Complete groups on arrival; a late missing minute delays availability."""
    if frame_minutes <= 0:
        raise ValueError("frame must be positive")
    received = sorted(minute_bars.values(), key=lambda row: row["receivedNs"])
    known: dict[int, dict] = {}
    emitted: set[int] = set()
    results: list[dict] = []
    incomplete_groups = 0
    for row in received:
        slot = row["slot"]
        known.setdefault(slot, row)
        start = slot // frame_minutes * frame_minutes
        needed = range(start, start + frame_minutes)
        if start in emitted or not all(member in known for member in needed):
            continue
        members = [known[member] for member in needed]
        results.append({
            "slot": start,
            "availableNs": row["receivedNs"],
            "o": members[0]["o"],
            "h": max(member["h"] for member in members),
            "l": min(member["l"] for member in members),
            "c": members[-1]["c"],
            "v": sum(member["v"] for member in members),
        })
        emitted.add(start)
    # SOURCE: every UTC-aligned group whose constituent minute slots were
    # observed should have exactly one completed aggregate.
    expected_starts = {slot // frame_minutes * frame_minutes for slot in minute_bars}
    incomplete_groups = len(expected_starts - emitted)
    return results, incomplete_groups


def make_signals(bars: list[dict], fast_period: int = FAST_PERIOD,
                 slow_period: int = SLOW_PERIOD,
                 slot_step: int = 1) -> tuple[list[dict], int, int]:
    if fast_period <= 0 or slow_period <= fast_period:
        raise ValueError("EMA periods must be positive and slow must exceed fast")
    if slot_step <= 0:
        raise ValueError("bar slot step must be positive")
    fast = slow = None
    seed: list[float] = []
    previous_slot = None
    resets = 0
    current_run = longest_run = 0
    signals = []
    for bar in bars:
        if previous_slot is not None and bar["slot"] - previous_slot != slot_step:
            seed = []
            fast = slow = None
            resets += 1
            current_run = 0
        current_run += 1
        longest_run = max(longest_run, current_run)
        close = float(bar["c"])
        if not math.isfinite(close) or close <= 0:
            raise ValueError("bar close must be finite and positive")
        seed.append(close)
        if len(seed) == fast_period:
            fast = sum(seed) / fast_period
        elif len(seed) > fast_period:
            # SOURCE: standard EMA recurrence alpha=2/(period+1).
            fast += (close - fast) * (2 / (fast_period + 1))
        if len(seed) == slow_period:
            slow = sum(seed) / slow_period
        elif len(seed) > slow_period:
            # SOURCE: standard EMA recurrence alpha=2/(period+1).
            slow += (close - slow) * (2 / (slow_period + 1))
        if fast is not None and slow is not None:
            signals.append({"availableNs": bar["availableNs"],
                            "long": fast > slow, "fast": fast, "slow": slow,
                            "slot": bar["slot"]})
        previous_slot = bar["slot"]
    return signals, resets, longest_run


def simulate_day(day: int, signals: list[dict], quotes: list[dict],
                 fee_rate: float = TAKER_FEE_RATE) -> dict | None:
    quote_times = [quote["receivedNs"] for quote in quotes]
    dated_signals = []
    for signal in signals:
        if utc_day(signal["availableNs"]) != day:
            continue
        quote_index = bisect_right(quote_times, signal["availableNs"])
        if quote_index >= len(quotes) or utc_day(quotes[quote_index]["receivedNs"]) != day:
            continue
        dated_signals.append((signal, quote_index))
    if not dated_signals:
        return None
    day_quotes = [index for index, quote in enumerate(quotes)
                  if utc_day(quote["receivedNs"]) == day]
    if not day_quotes:
        return None
    final_quote_index = day_quotes[-1]
    first_quote_index = dated_signals[0][1]
    if final_quote_index <= first_quote_index:
        return None

    cash = 1.0  # SOURCE: normalized unit capital, not an account/order size.
    btc = 0.0
    entry_cash = None
    net_roundtrips_bps = []
    fee_usd_equivalent = 0.0
    executions = []
    last_execution_index = -1
    for signal, quote_index in dated_signals:
        if quote_index <= last_execution_index:
            continue
        quote = quotes[quote_index]
        if signal["long"] and btc == 0:
            entry_cash = cash
            fee_usd_equivalent += cash * fee_rate
            btc = cash / quote["ask"] * (1 - fee_rate)
            cash = 0.0
            executions.append({"side": "buy", "receivedNs": quote["receivedNs"],
                               "price": quote["ask"], "signalNs": signal["availableNs"],
                               "quoteDelayMs": (quote["receivedNs"] - signal["availableNs"]) / 1_000_000})
            last_execution_index = quote_index
        elif not signal["long"] and btc > 0:
            fee_usd_equivalent += btc * quote["bid"] * fee_rate
            cash = btc * quote["bid"] * (1 - fee_rate)
            btc = 0.0
            if entry_cash:
                net_roundtrips_bps.append((cash / entry_cash - 1) * BPS)
            entry_cash = None
            executions.append({"side": "sell", "receivedNs": quote["receivedNs"],
                               "price": quote["bid"], "signalNs": signal["availableNs"],
                               "quoteDelayMs": (quote["receivedNs"] - signal["availableNs"]) / 1_000_000})
            last_execution_index = quote_index

    liquidated = True
    if btc > 0 and final_quote_index > last_execution_index:
        quote = quotes[final_quote_index]
        fee_usd_equivalent += btc * quote["bid"] * fee_rate
        cash = btc * quote["bid"] * (1 - fee_rate)
        btc = 0.0
        if entry_cash:
            net_roundtrips_bps.append((cash / entry_cash - 1) * BPS)
        executions.append({"side": "forced_day_end_sell", "receivedNs": quote["receivedNs"],
                           "price": quote["bid"]})
    elif btc > 0:
        # SOURCE: mark an unexited position to bid; no hypothetical exit fee
        # is deducted when no later captured quote exists for the day.
        cash = btc * quotes[final_quote_index]["bid"]
        liquidated = False
    buy_hold_btc = (1.0 / quotes[first_quote_index]["ask"]) * (1 - fee_rate)
    buy_hold_end = buy_hold_btc * quotes[final_quote_index]["bid"] * (1 - fee_rate)
    end_nav = cash + btc * quotes[final_quote_index]["bid"]
    return {
        "utcDate": datetime.fromtimestamp(day * SECONDS_PER_DAY, timezone.utc).date().isoformat(),
        "signalBars": len(dated_signals),
        "entries": sum(item["side"] == "buy" for item in executions),
        "exits": sum(item["side"] in ("sell", "forced_day_end_sell") for item in executions),
        "roundTrips": len(net_roundtrips_bps),
        "candidateReturnPct": (end_nav - 1) * 100,
        "buyHoldReturnPct": (buy_hold_end - 1) * 100,
        "cashReturnPct": 0.0,
        "candidateExcessVsBuyHoldBps": (end_nav - buy_hold_end) * BPS,
        "medianClosedRoundTripNetBps": median(net_roundtrips_bps) if net_roundtrips_bps else None,
        "medianSignalToNextQuoteMs": median([item["quoteDelayMs"] for item in executions
                                              if "quoteDelayMs" in item])
            if any("quoteDelayMs" in item for item in executions) else None,
        "maxSignalToNextQuoteMs": max([item["quoteDelayMs"] for item in executions
                                        if "quoteDelayMs" in item])
            if any("quoteDelayMs" in item for item in executions) else None,
        "estimatedFeesUsdPerNormalizedUnit": fee_usd_equivalent,
        "forcedFlatAtDayEnd": liquidated,
        "executionCount": len(executions),
        "executionModel": "ask buys / bid sells at first captured quote after signal, plus official tier-one taker fee; no broker latency, queue, impact or partial fills",
    }


def audit(paths: list[Path], frames: tuple[int, ...] = (1, 5, 30, 60, 240),
          symbol: str = DEFAULT_SYMBOL) -> dict:
    quotes, minute_bars, event_counts = read_capture(paths, symbol)
    if not quotes or not minute_bars:
        raise ValueError("capture needs BTC quotes and first-seen minute bars")
    frame_results = {}
    for frame in frames:
        bars, incomplete_groups = aggregate_as_received(minute_bars, frame)
        signals, gap_resets, longest_run = make_signals(bars, slot_step=frame)
        days = sorted({utc_day(signal["availableNs"]) for signal in signals})
        daily = [result for day in days
                 if (result := simulate_day(day, signals, quotes)) is not None]
        frame_results[f"{frame}m"] = {
            "completeBars": len(bars),
            "incompleteUtcGroups": incomplete_groups,
            "signalBarsAfterEmaWarmup": len(signals),
            "indicatorGapResets": gap_resets,
            "longestContiguousBars": longest_run,
            "dailyPaperReplay": daily,
        }
    return {
        "files": [str(path) for path in paths],
        "symbol": symbol,
        "quoteCount": len(quotes),
        "firstSeenMinuteBarCount": len(minute_bars),
        "captureEventCounts": event_counts,
        "emaPeriods": {"fast": FAST_PERIOD, "slow": SLOW_PERIOD,
                       "source": "Pattern Forge display periods; fixed before this replay, not calibrated"},
        "takerFeeRateEachSide": TAKER_FEE_RATE,
        "timeframesMinutes": list(frames),
        "frames": frame_results,
        "scope": f"Chronological research replay from as-received {symbol} minute bars and exact captured {symbol} top quotes. It uses first-seen bars only, strict complete timeframe groups, ask/bid crossing, and the published tier-one taker fee. Daily samples reset to normalized cash and force a day-end liquidation. It is optimistic because it excludes broker/network latency, order acceptance, fill probability, queue, impact and live risk; a positive result is not evidence of a deployable or live edge.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", nargs="+", type=Path)
    parser.add_argument("--frames", default="1,5,30,60,240")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--symbols", nargs="+",
                        help="run the same frozen rule sequentially for research symbols")
    args = parser.parse_args()
    frames = tuple(int(item) for item in args.frames.split(","))
    if args.symbols:
        result = [audit(args.capture, frames, symbol) for symbol in args.symbols]
    else:
        result = audit(args.capture, frames, args.symbol)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
