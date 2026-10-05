"""Read-only replay gate for a prospective automatic paper entry.

No credentials, network calls or broker submission. Verify the actual archived
native bytes and original executable, then compare every native output field.
Descriptive extensions are retained evidence, not re-executed policy authority.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# SOURCE: the user's five requested native analysis frames.
FRAMES = ("1m", "5m", "30m", "1h", "4h")


def fingerprint(value):
    # SOURCE: SHA-256 hexadecimal digests contain exactly 64 lowercase digits.
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("native evidence digest is missing or invalid")
    return value


def verify(request, state_dir):
    started = time.perf_counter()
    venue, symbol, frame = (request.get(k) for k in ("venue", "symbol", "frame"))
    if frame not in FRAMES or venue not in ("Alpaca crypto", "Alpaca equities"):
        raise ValueError("native proof is outside the Alpaca execution scope")
    reading = request.get("reading")
    if not isinstance(reading, dict):
        raise ValueError("native candidate reading is missing")
    evidence = reading.get("dataEvidence", {})
    if (not isinstance(evidence, dict) or evidence.get("schema") != "native_closed_frame_input_v1"
            or evidence.get("nativeInputArchive") != "retained"
            or evidence.get("orderAuthority") is not False
            or evidence.get("analysisAsOf") != request.get("asOf")):
        raise ValueError("candidate lacks retained native input at its analysis clock")
    input_sha = fingerprint(evidence.get("inputSha256"))
    engine_sha = fingerprint(evidence.get("engineSha256"))
    fingerprint(evidence.get("technicalAnalysisSha256"))
    with gzip.open(state_dir / "decision-inputs" / (input_sha + ".json.gz"), "rb") as source:
        raw = source.read()
    if hashlib.sha256(raw).hexdigest() != input_sha:
        raise ValueError("retained native input bytes do not match their digest")
    native = json.loads(raw)
    if (native.get("schema") != evidence["schema"] or native.get("venue") != venue
            or native.get("symbol") != symbol or native.get("frame") != frame
            or native.get("dataSource") != "native_historical_as_retrieved"
            or not isinstance(native.get("bars"), list)
            or len(native["bars"]) != evidence.get("inputBars")):
        raise ValueError("retained native input does not match the intended instrument/frame")
    engine = state_dir / "frozen-analyzers" / (engine_sha + ".exe")
    if hashlib.sha256(engine.read_bytes()).hexdigest() != engine_sha:
        raise ValueError("retained native executable does not match its digest")
    payload = {"asOf": evidence["analysisAsOf"], "markets": [{"venue": venue, "symbol": symbol,
        "frames": {f: native["bars"] if f == frame else [] for f in FRAMES},
        "expectedStarts": {frame: native.get("expectedStarts", [])},
        "sessionOpen": native.get("sessionOpen", True)}]}
    # GUESS: # UNCALIBRATED GUESS — inherited scanner's 30-second executable
    # resource timeout. Actual pre-POST freshness is independently rechecked.
    process = subprocess.run([str(engine)], input=json.dumps(payload).encode(),
                             capture_output=True, check=True, timeout=30)
    if hashlib.sha256(engine.read_bytes()).hexdigest() != engine_sha:
        raise ValueError("retained native executable changed during replay")
    result = json.loads(process.stdout)
    expected = result["markets"][0]["frames"][frame]
    if result.get("policy") != "trend_candle_confluence_v1" or result.get("asOf") != request["asOf"]:
        raise ValueError("native replay policy or analysis clock differs")
    if any(key not in reading or reading[key] != value for key, value in expected.items()):
        raise ValueError("native replay differs from the proposed candidate reading")
    if expected.get("status") != "candidate" or expected.get("candidate") != "long":
        raise ValueError("native replay does not confirm an eligible long candidate")
    return {"verified": True, "inputSha256": input_sha, "engineSha256": engine_sha,
        "analysisAsOf": request["asOf"],
        "verifiedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "seconds": time.perf_counter() - started,
        "scope": "all original native output fields; no technical-extension or predictive-edge validation",
        "orderAuthority": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--request-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        response = verify(json.loads(args.request_file.read_text(encoding="utf-8")), args.state_dir)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        # Never expose raw private paths, executable stderr or broker credentials.
        reason = str(error) if type(error) is ValueError else type(error).__name__
        print(json.dumps({"verified": False, "reason": reason, "orderAuthority": False}))
        return 1
    print(json.dumps(response, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
