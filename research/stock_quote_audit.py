"""Frozen prospective stock quote references; no network, broker or order path.

Read original first features and actual IEX/REST receipts. Missing data stays
missing. These are long price references, not a stop-managed execution model.
"""
import argparse
import hashlib
import json
import re
from collections import Counter
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from archived_quote_reference import receipt_text
from decision_quote_capture import normalize_at, quote_time
from forward_pattern_audit import FRAME_SECONDS, read_journal
from forward_quote_audit import read_quotes, reference, report

# SOURCE: calendar open/close fields from actual Alpaca US market sessions.
NEW_YORK = ZoneInfo("America/New_York")
POLICY = "trend_candle_confluence_v1"  # SOURCE: existing frozen OCaml candidate.


def validate_manifest(value):
    if (not isinstance(value, dict) or value.get("schema") != "stock_quote_cohort_v1"
            or value.get("orderAuthority") is not False or value.get("winProbability") is not None
            or value.get("policy") != POLICY or value.get("side") != "long"
            or value.get("venue") != "Alpaca equities" or value.get("feed") != "iex"
            or value.get("frames") != list(FRAME_SECONDS)
            or value.get("horizonBars") != 1 or isinstance(value.get("horizonBars"), bool)
            or value.get("maxExitLagSeconds") != 120 or isinstance(value.get("maxExitLagSeconds"), bool)):
        # SOURCE: one frame / 120s inherited from the documented frozen audit.
        # GUESS: # UNCALIBRATED GUESS — these remain exploratory, not optimized.
        raise ValueError("manifest is outside the frozen descriptive protocol")
    symbols = value.get("symbols")
    streamed = value.get("streamSymbols")
    if (not isinstance(symbols, list) or not symbols or len(set(symbols)) != len(symbols)
            or any(not isinstance(s, str) or not re.fullmatch(r"[A-Z]+", s) or s == "AAPL" for s in symbols)
            or not isinstance(streamed, list) or len(set(streamed)) != len(streamed)
            or not set(streamed) <= set(symbols)):
        raise ValueError("invalid or protected instrument scope")
    if not re.fullmatch(r"[0-9a-f]{64}", value.get("engineSha256", "")):
        raise ValueError("actual engine fingerprint missing")
    created = quote_time(value["createdAt"])
    receipt = quote_time(value["calendarReceivedAt"])
    sessions = value.get("sessions")
    # SOURCE: the declared two folds, never interchangeable or chosen by results.
    if not isinstance(sessions, list) or len(sessions) != 2:
        raise ValueError("both chronological sessions required")
    windows = []
    for row, fold in zip(sessions, ("discovery", "validation")):
        if row.get("fold") != fold:
            raise ValueError("chronological folds cannot be relabeled")
        times = []
        for key in ("open", "close"):
            local = datetime.strptime(row["date"] + " " + row[key], "%Y-%m-%d %H:%M").replace(tzinfo=NEW_YORK)
            text = local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            times.append(quote_time(text))
        start, end = times
        if start >= end or windows and start <= windows[-1]["close"]:
            raise ValueError("invalid or overlapping session calendar")
        windows.append({"date": row["date"], "fold": fold, "open": start, "close": end})
    if not receipt <= created < windows[0]["open"]:
        raise ValueError("calendar and manifest must be frozen before first session")
    return windows


def load_manifest(path, expected_sha256):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("manifest changed from its explicitly pinned bytes")
    value = json.loads(raw)
    validate_manifest(value)
    return value, digest


def window_at(windows, at):
    # SOURCE: actual regular session, close excluded (no after-close fill claim).
    return next((row for row in windows if row["open"] <= at < row["close"]), None)


def read_iex_quotes(paths, symbols, targets=None, max_exit_lag=None):
    """Dedicated stock-capture schema; crypto archives cannot become IEX data."""
    rows, counts, sources, identities, ambiguous = [], Counter(), [], {}, set()
    winners, last, blocked = {}, {}, set()
    wanted = {symbol: sorted(set(times)) for symbol, times in targets.items()} if targets is not None else None
    if wanted is not None and (not isinstance(max_exit_lag, int) or isinstance(max_exit_lag, bool) or max_exit_lag < 0):
        raise ValueError("bounded selection requires the frozen exit lag")
    for path in paths:
        try:
            with path.open("rb") as handle:
                size = path.stat().st_size
                digest = hashlib.sha256()
                while handle.tell() < size:
                    raw = handle.readline(size - handle.tell()); digest.update(raw)
                    counts["lines"] += 1
                    if not raw.endswith(b"\n"):
                        counts["partialFinalLine"] += 1; break
                    try:
                        value = json.loads(raw); event = value["event"]
                        if event.get("T") != "q":
                            counts["nonQuoteEvents"] += 1; continue
                        if (event.get("S") not in symbols or "feed" in value
                                or not isinstance(value.get("session"), str) or not value["session"]
                                or not isinstance(value.get("sequence"), int) or isinstance(value["sequence"], bool)
                                or value["sequence"] <= 0):
                            raise ValueError("outside actual stock archive schema/subscription")
                        quote = reference(normalize_at(event, receipt_text(value["receivedAtNs"]),
                                                       "Alpaca equities", event["S"]))
                        if wanted is not None:
                            symbol, receipt = quote["symbol"], quote["received"]
                            previous = last.get(symbol)
                            if previous and (receipt < previous["received"] or receipt == previous["received"] and quote != previous):
                                blocked.add(symbol)
                                counts["ambiguousOrDecreasingInstrumentClock"] += 1
                            last[symbol] = quote
                            times = wanted.get(symbol, ())
                            lower = bisect_left(times, receipt-max_exit_lag)
                            upper = bisect_right(times, min(receipt, quote["at"]))
                            for due in times[lower:upper]:
                                key = (symbol, due)
                                prior = winners.get(key)
                                if prior is None or receipt < prior["received"]:
                                    winners[key] = quote
                            continue
                        identity = (quote["symbol"], quote["received"])
                        if identity in identities:
                            if identities[identity] != quote:
                                ambiguous.add(identity)
                                counts["conflictingReceiptIdentities"] += 1
                            else:
                                counts["identicalReceiptDuplicates"] += 1
                        else:
                            identities[identity] = quote
                    except (ValueError, KeyError, TypeError, OverflowError, AttributeError):
                        counts["unusableReferences"] += 1
            sources.append({"file": path.name, "status": "read", "inputBytes": size, "sha256": digest.hexdigest()})
        except FileNotFoundError:
            sources.append({"file": path.name, "status": "absent", "inputBytes": None, "sha256": None})
    if wanted is None:
        rows = [quote for identity, quote in identities.items() if identity not in ambiguous]
    else:
        # SOURCE: retain only first actual fresh reception for each frozen due
        # time. Memory follows observed horizons, not all daily quote events.
        # Any ambiguous/decreasing clock blocks the entire instrument; later
        # retained quotes cannot repair the uncertain earlier exit selection.
        selected = {(q["symbol"],q["received"]):q for q in winners.values() if q["symbol"] not in blocked}
        rows = list(selected.values())
    return rows, {**dict(counts), "usableReferences": len(rows), "sources": sources,
                  "selection": "first_frozen_horizon_receptions" if wanted is not None else "all_fixture_receptions",
                  "blockedInstruments": sorted(blocked)}


def cohort_report(frames, quotes, manifest, as_of):
    windows = validate_manifest(manifest)
    known = quote_time(as_of)
    if known < quote_time(manifest["createdAt"]):
        raise ValueError("report precedes frozen protocol")
    symbols = set(manifest["symbols"])
    selected, rejected = [], Counter()
    coverage = {(symbol, frame): Counter() for symbol in manifest["symbols"] for frame in manifest["frames"]}
    for row in frames:
        if row["venue"] != "Alpaca equities" or row["symbol"] not in symbols:
            rejected["outsideStockScope"] += 1; continue
        if row["frame"] not in manifest["frames"]:
            rejected["outsideFrameScope"] += 1; continue
        observed = quote_time(row["observedAtText"])
        window = window_at(windows, observed)
        if window is None or observed > known:
            rejected["outsideActualSessionOrFuture"] += 1; continue
        slot = coverage[row["symbol"], row["frame"]]
        slot["firstObservedCandles"] += 1
        slot["status_" + str(row.get("status"))] += 1
        if row.get("engineSha256") != manifest["engineSha256"] or row.get("policy") != POLICY:
            rejected["unverifiedFrozenProducer"] += 1; continue
        slot["frozenProducerCandles"] += 1
        if row.get("candidate") == "long":
            slot["recordedLongCandidates"] += 1
        due = observed + FRAME_SECONDS[row["frame"]] * manifest["horizonBars"]
        if due >= window["close"]:
            rejected["horizonOutsideRegularSession"] += 1; continue
        # SOURCE: entry source and reception must both be inside this session;
        # report() independently rejects stale/future/mismatched original data.
        try:
            entry = reference(row.get("quoteReference"))
            if not window["open"] <= entry["at"] <= entry["received"] <= observed:
                raise ValueError("entry predates actual session")
        except (ValueError, KeyError, TypeError):
            rejected["noOriginalSessionEntryQuote"] += 1; continue
        selected.append(row)
    eligible_quotes = [q for q in quotes if q["venue"] == "Alpaca equities" and q["symbol"] in symbols
                       and (window := window_at(windows, q["received"])) is not None
                       and window["open"] <= q["at"] <= q["received"]]
    split = datetime.fromtimestamp(float(windows[1]["open"]), timezone.utc).isoformat().replace("+00:00", "Z")
    result = report(selected, eligible_quotes, horizon_bars=manifest["horizonBars"],
                    max_exit_lag_seconds=manifest["maxExitLagSeconds"], split_at=split,
                    # PLACEHOLDER: unused argument of the inherited function;
                    # equities only, no crypto fee scenario or zero-cost claim.
                    crypto_taker_bps=0, as_of=as_of)
    result["cryptoTakerBpsScenario"] = None
    for label in result["labels"]:
        slot = coverage[label["symbol"], label["frame"]]
        slot["quoteReferences"] += 1
        slot["fold_" + label["fold"]] += 1
    result.update({"schema": "prospective_stock_quote_reference_v1", "generatedAt": as_of,
                   "protocolRejected": dict(rejected),
                   "coverage": [{"symbol": symbol, "frame": frame, **dict(counts)}
                                for (symbol, frame), counts in coverage.items()],
                   "sessionState": "complete" if known >= windows[-1]["close"] else
                                   "awaiting_first_session" if known < windows[0]["open"] else "collecting",
                   "equityNetCosts": None, "executionModel": None,
                   "limits": result["limits"] + [
                       "Two predetermined sessions are an uncalibrated exploratory design, not sufficient evidence of edge",
                       "Original policy labels require the frozen analyzer fingerprint; older observations cannot be repaired",
                       "Fingerprint is a local artifact identity, not signed deployment attestation or TA-library parity",
                       "Native frame alignment/warmup may leave 4h or sparse products without eligible labels",
                       "No next-session substitution for missing regular-session exit references",
                       "REST and stream reports retain the same features; sources cannot be switched for the best outcome"]})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("manifest", "journal", "rest_quotes", "capture_root", "output"):
        parser.add_argument("--" + key.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    manifest, digest = load_manifest(args.manifest, args.manifest_sha256)
    frames, feature_input = read_journal(args.journal)
    rest, rest_input = read_quotes(args.rest_quotes)
    windows = validate_manifest(manifest)
    # SOURCE: bounded archive retention uses the existing observed first feature
    # times, never guesses future signals or chooses a better exit price.
    targets = {}
    for row in frames:
        if row["venue"] == "Alpaca equities" and row["symbol"] in manifest["streamSymbols"]:
            at = quote_time(row["observedAtText"])
            window = window_at(windows, at)
            due = at+FRAME_SECONDS[row["frame"]]*manifest["horizonBars"]
            if window and due < window["close"]:
                targets.setdefault(row["symbol"], []).append(due)
    stream, stream_input = read_iex_quotes([args.capture_root / (s["date"] + ".jsonl")
                                         for s in manifest["sessions"]], set(manifest["streamSymbols"]),
                                         targets, manifest["maxExitLagSeconds"])
    as_of = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    baseline = cohort_report(frames, rest, manifest, as_of)
    primary = cohort_report(frames, stream, manifest, as_of)
    result = {"generatedAt": as_of, "manifestSha256": digest, "frameInput": feature_input,
              "streamInput": stream_input, "restInput": rest_input, "streamExitAudit": primary,
              "restExitAudit": baseline, "orderAuthority": False, "winProbability": None, "brokerPnl": None}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"generatedAt": as_of, "manifestSha256": digest, "state": primary["sessionState"],
                      "streamLabels": primary["labelCount"], "restLabels": baseline["labelCount"],
                      "coverageSlots": len(primary["coverage"]), "orderAuthority": False}))


if __name__ == "__main__":
    main()
