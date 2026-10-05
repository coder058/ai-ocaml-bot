"""Prospective first regular-session readings, distinct from first-ever bars.

No network, credentials, trading or rewriting of the original candle journal.
The date/symbol/frame/source-bar identity freezes the actual first session
reading even when no candidate or usable quote exists. Later revisions cannot
repair that opportunity. Quote outcomes remain research references, not fills.
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from decision_quote_capture import quote_time
from forward_pattern_audit import FRAME_SECONDS, observation
from forward_quote_audit import read_quotes
from forward_features import forward_reading
from stock_quote_audit import cohort_report, load_manifest, read_iex_quotes, validate_manifest, window_at

# SOURCE: exact published original protocol bytes, frozen 2026-10-05 06:03 UTC.
BASE_SHA256 = "6dc7d3b44459f6bf1a236f6237c9ca22272631acfccfe650c1dc718d39a40b75"
# SOURCE: exact prospective protocol bytes created 2026-10-05T08:14:37.718943Z.
PROTOCOL_SHA256 = "6d1300c7fc54d5ab3f19e78d97cd446b45bd189b9a271e13edd505227d2fa033"
METHOD = "first_regular_session_reading_per_source_bar"
ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "research/cohorts/stock-20261005-06.json"
PROTOCOL_PATH = ROOT / "research/cohorts/stock-session-opportunities-20261005-06.json"


def protocol(base_path=BASE_PATH, protocol_path=PROTOCOL_PATH, expected=PROTOCOL_SHA256):
    base, _ = load_manifest(base_path, BASE_SHA256)
    raw = protocol_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected:
        raise ValueError("session opportunity protocol differs from pinned bytes")
    value = json.loads(raw)
    windows = validate_manifest(base)
    if (value.get("schema") != "stock_session_opportunity_protocol_v1"
            or value.get("baseManifestSha256") != BASE_SHA256
            or value.get("selection") != METHOD
            or value.get("orderAuthority") is not False
            or value.get("winProbability") is not None
            or not quote_time(base["createdAt"]) <= quote_time(value["createdAt"]) < windows[0]["open"]):
        raise ValueError("invalid prospective session opportunity protocol")
    return base, value, digest


def prepare(result, clock, seen, base, spec, digest):
    """Pure selection. Commit returned cache keys only after durable append."""
    observed = quote_time(result["retrievedAt"])
    window = window_at(validate_manifest(base), observed)
    if window is None or clock.get("is_open") is not True:
        return [], {}
    clock_at = quote_time(clock["timestamp"])
    if (not window["open"] <= clock_at <= observed < window["close"]
            or quote_time(spec["createdAt"]) > observed
            or result.get("engineSha256") != base["engineSha256"]
            or result.get("policy") != base["policy"]
            or quote_time(result["asOf"]) > observed):
        raise ValueError("session reading has inconsistent actual producer or clock")
    records, updates, identities = [], {}, set()
    for market in result["markets"]:
        if market["venue"] != base["venue"] or market["symbol"] not in base["symbols"]:
            continue
        for frame in base["frames"]:
            reading = market["frames"].get(frame, {})
            start = reading.get("lastBarStart")
            if start is None:
                continue
            key = "|".join((window["date"], market["symbol"], frame))
            if key in identities:
                raise ValueError("duplicate session slot in actual analyzer response")
            identities.add(key)
            start_at = quote_time(start)
            # SOURCE: native frame closure and source ordering, not a guessed
            # maximum candle age. Ready/stale status retains actual engine logic.
            if start_at % FRAME_SECONDS[frame] or start_at + FRAME_SECONDS[frame] > quote_time(result["asOf"]):
                raise ValueError("session opportunity candle is still open")
            prior = seen.get(key)
            if prior is not None and start_at <= quote_time(prior):
                continue
            record = {"schema": "stock_session_opportunity_v1", "selection": METHOD,
                      "protocolSha256": digest, "sessionDate": window["date"],
                      "observedAt": result["retrievedAt"], "asOf": result["asOf"],
                      "brokerClockAt": clock["timestamp"], "brokerSessionOpen": True,
                      "venue": market["venue"], "symbol": market["symbol"], "frame": frame,
                      "policy": result["policy"], "engineSha256": result["engineSha256"],
                      "reading": forward_reading(reading), "orderAuthority": False,
                      "winProbability": None}
            row = observation(record)
            if row is None or row["start"] != float(start_at):
                raise ValueError("session reading lacks its actual matching source candle")
            records.append(record)
            updates[key] = start
    return records, updates


def read_journal(path, base, digest):
    first, invalid, blocked, counts = {}, set(), set(), Counter()
    sha = hashlib.sha256()
    windows = validate_manifest(base)
    try:
        with path.open("rb") as source:
            size = path.stat().st_size
            while source.tell() < size:
                raw = source.readline(size-source.tell()); sha.update(raw)
                if not raw.endswith(b"\n"):
                    counts["partialFinalLine"] += 1; break
                counts["lines"] += 1
                key = None
                try:
                    r = json.loads(raw)
                    if (r.get("schema") != "stock_session_opportunity_v1" or r.get("selection") != METHOD
                            or r.get("protocolSha256") != digest or r.get("orderAuthority") is not False
                            or r.get("winProbability") is not None or r.get("brokerSessionOpen") is not True
                            or r.get("venue") != base["venue"] or r.get("symbol") not in base["symbols"]
                            or r.get("frame") not in base["frames"]):
                        raise ValueError("outside prospective session evidence")
                    key = (r["sessionDate"], r["symbol"], r["frame"], r["reading"]["lastBarStart"])
                    window = window_at(windows, quote_time(r["observedAt"]))
                    if (window is None or window["date"] != r["sessionDate"]
                            or not window["open"] <= quote_time(r["brokerClockAt"]) <= quote_time(r["observedAt"])
                            or quote_time(r["asOf"]) > quote_time(r["observedAt"])):
                        raise ValueError("opportunity clock/session mismatch")
                    start_at = quote_time(key[-1])
                    if start_at % FRAME_SECONDS[r["frame"]] or start_at + FRAME_SECONDS[r["frame"]] > quote_time(r["asOf"]):
                        raise ValueError("source candle is not closed on its exact native grid")
                    row = observation(r)
                    if row is None or row["start"] != float(quote_time(key[-1])):
                        raise ValueError("missing matching actual source candle")
                    if key in first:
                        if first[key][0] != r:
                            blocked.add(key); counts["conflictingOpportunityIdentity"] += 1
                        else:
                            counts["identicalDuplicates"] += 1
                    else:
                        first[key] = (r, row)
                except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
                    counts["invalidRecords"] += 1
                    if key is not None:
                        invalid.add(key)
        rows = [row for key, (_, row) in first.items() if key not in invalid and key not in blocked]
        return rows, {**dict(counts), "inputBytes": size, "sha256": sha.hexdigest(),
                      "source": path.name, "status": "read", "usableOpportunities": len(rows)}
    except FileNotFoundError:
        return [], {"source": path.name, "status": "absent", "inputBytes": None,
                    "sha256": None, "usableOpportunities": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("journal", "rest_quotes", "capture_root", "output"):
        parser.add_argument("--"+key.replace("_", "-"), type=Path, required=True)
    args = parser.parse_args()
    base, spec, digest = protocol()
    rows, feature_input = read_journal(args.journal, base, digest)
    rest, rest_input = read_quotes(args.rest_quotes)
    windows = validate_manifest(base)
    targets = {}
    for row in rows:
        at = quote_time(row["observedAtText"]); window = window_at(windows, at)
        due = at + FRAME_SECONDS[row["frame"]] * base["horizonBars"]
        if window and due < window["close"] and row["symbol"] in base["streamSymbols"]:
            targets.setdefault(row["symbol"], []).append(due)
    stream, stream_input = read_iex_quotes([args.capture_root/(s["date"]+".jsonl") for s in base["sessions"]],
                                          set(base["streamSymbols"]), targets, base["maxExitLagSeconds"])
    as_of = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result = {"generatedAt": as_of, "manifestSha256": digest, "baseManifestSha256": BASE_SHA256,
              "selection": METHOD, "frameInput": feature_input, "streamInput": stream_input,
              "restInput": rest_input, "streamExitAudit": cohort_report(rows, stream, base, as_of),
              "restExitAudit": cohort_report(rows, rest, base, as_of), "orderAuthority": False,
              "winProbability": None, "brokerPnl": None}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"generatedAt": as_of, "selection": METHOD, "opportunities": len(rows),
                      "streamLabels": result["streamExitAudit"]["labelCount"],
                      "restLabels": result["restExitAudit"]["labelCount"], "orderAuthority": False}))


if __name__ == "__main__":
    main()
