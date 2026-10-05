"""Revision-aware reuse of closed-frame calculations; no order authority.

Cached values are an optimization only. Exact native inputs, calendar, closure
bucket, session and actual calculation identities determine eligibility. Every
published reading retains the current clock; no historical features are repaired.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def minute(stamp):
    value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if value.tzinfo is None or value.timestamp() % 60:
        raise ValueError("analysis clock must be an aware minute boundary")
    # SOURCE: all native frames and OCaml timestamps use UTC minutes.
    return int(value.timestamp()) // 60


def signature(market, frame, minutes, as_of, identity):
    return digest({"identity": identity, "venue": market["venue"],
        "symbol": market["symbol"], "frame": frame,
        "rows": market["frames"][frame],
        "expectedStarts": market.get("expectedStarts", {}).get(frame, []),
        "sessionOpen": market.get("sessionOpen", True),
        # SOURCE: open-candle validity and latest expected closes change at a
        # native frame boundary, even if a provider returned no new candle.
        "closureBucket": minute(as_of) // minutes})


def reusable(entry, fingerprint, as_of):
    return (isinstance(entry, dict) and entry.get("fingerprint") == fingerprint
            and isinstance(entry.get("value"), dict)
            and entry.get("valueSha256") == digest(entry["value"])
            and isinstance(entry.get("asOf"), str)
            and minute(entry["asOf"]) <= minute(as_of))


def save(value, fingerprint, as_of):
    value = copy.deepcopy(value)
    return {"fingerprint": fingerprint, "asOf": as_of,
            "value": value, "valueSha256": digest(value)}


def analyze(payload, engine, prior, analyzer, frames):
    """Call the frozen executable only for dirty frames; rebuild current output.

    The original executable still emits its fixed five frames for dirty markets.
    Empty arrays in non-dirty slots are discarded, never published as no_data.
    Cached age is refreshed without changing indicators or policy conditions.
    """
    engine_sha = hashlib.sha256(engine.read_bytes()).hexdigest()
    entries = prior.get("frames", {}) if isinstance(prior, dict) else {}
    if not isinstance(entries, dict):
        entries = {}
    fingerprints, dirty, requested = {}, {}, []
    for market in payload["markets"]:
        market_key = market["venue"] + "|" + market["symbol"]
        changed = []
        for frame, minutes in frames.items():
            key = market_key + "|" + frame
            fingerprint = signature(market, frame, minutes, payload["asOf"], engine_sha)
            fingerprints[key] = fingerprint
            try:
                ok = reusable(entries.get(key), fingerprint, payload["asOf"])
            except (ValueError, KeyError, TypeError):
                ok = False
            if not ok:
                changed.append(frame)
        dirty[market_key] = set(changed)
        if changed:
            requested.append({**market, "frames": {
                frame: market["frames"][frame] if frame in changed else [] for frame in frames}})
    computed = {}
    header = prior.get("header") if isinstance(prior, dict) else None
    if requested or not isinstance(header, dict) or prior.get("headerSha256") != digest(header):
        fresh, actual_sha = analyzer({**payload, "markets": requested}, engine)
        if actual_sha != engine_sha:
            raise RuntimeError("shared OCaml analyzer changed before incremental invocation")
        header = {key: value for key, value in fresh.items() if key not in ("markets", "asOf")}
        computed = {market["venue"] + "|" + market["symbol"]: market for market in fresh["markets"]}
    result = {**header, "asOf": payload["asOf"], "markets": []}
    next_entries = {}
    for market in payload["markets"]:
        market_key = market["venue"] + "|" + market["symbol"]
        readings = {}
        for frame, minutes in frames.items():
            key = market_key + "|" + frame
            if frame in dirty[market_key]:
                value = copy.deepcopy(computed[market_key]["frames"][frame])
                next_entries[key] = save(value, fingerprints[key], payload["asOf"])
            else:
                value = copy.deepcopy(entries[key]["value"])
                next_entries[key] = entries[key]
                if "ageMinutesAfterClose" in value:
                    value["ageMinutesAfterClose"] = minute(payload["asOf"]) - minute(value["lastBarStart"]) - minutes
            readings[frame] = value
        result["markets"].append({"symbol": market["symbol"], "venue": market["venue"], "frames": readings})
    if hashlib.sha256(engine.read_bytes()).hexdigest() != engine_sha:
        raise RuntimeError("shared OCaml analyzer changed during incremental scan")
    count = sum(len(value) for value in dirty.values())
    return result, engine_sha, {"header": header, "headerSha256": digest(header), "frames": next_entries}, {
        "computedFrames": count, "reusedFrames": len(next_entries) - count,
        "invokedMarkets": len(requested), "scope": "OCaml native closed-frame calculations"}
