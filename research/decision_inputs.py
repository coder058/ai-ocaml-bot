"""Content-addressed actual native inputs for prospective candidate evidence.

Retain candidates only, not invented signals or executions. All readings expose
their native input digest. The archive plus the recorded analysis clock allows
the original native calculation to be replayed without today's revised history.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def retain(directory: Path, raw: bytes, fingerprint: str):
    # SOURCE: private owner/group access follows the surrounding state directory.
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    if os.name == "posix":
        os.chown(directory, -1, directory.parent.stat().st_gid)
    path = directory / (fingerprint + ".json.gz")
    if path.exists():
        # A previous crash/corruption cannot silently certify retained evidence.
        with gzip.open(path, "rb") as source:
            if source.read() != raw:
                raise ValueError("candidate archive does not match native input digest")
        return
    fd, temporary = tempfile.mkstemp(prefix=".candidate-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as target:
            # SOURCE: zero gzip metadata time makes compression deterministic;
            # actual observation/analysis times remain in decision evidence.
            with gzip.GzipFile(fileobj=target, mode="wb", mtime=0) as compressed:
                compressed.write(raw)
            target.flush()
            os.fsync(target.fileno())
            # SOURCE: private owner/group read, matching market state snapshots.
            if os.name == "posix":
                os.fchmod(target.fileno(), 0o640)
                os.fchown(target.fileno(), -1, directory.stat().st_gid)
        os.replace(temporary, path)
        if os.name == "posix":
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def attach(result, requested, directory, engine_sha256, technical_sha256):
    retained = 0
    for market, original in zip(result["markets"], requested, strict=True):
        for frame, reading in market["frames"].items():
            document = {"schema": "native_closed_frame_input_v1",
                "venue": market["venue"], "symbol": market["symbol"], "frame": frame,
                "dataSource": "native_historical_as_retrieved",
                "bars": original["frames"][frame],
                "expectedStarts": original.get("expectedStarts", {}).get(frame, []),
                "sessionOpen": original.get("sessionOpen", True)}
            raw = canonical(document)
            fingerprint = hashlib.sha256(raw).hexdigest()
            candidate = reading.get("status") == "candidate" and reading.get("candidate") in ("long", "short")
            if candidate:
                retain(directory, raw, fingerprint)
                retained += 1
            reading["dataEvidence"] = {"schema": document["schema"],
                "inputSha256": fingerprint, "inputBars": len(document["bars"]),
                "analysisAsOf": result["asOf"], "engineSha256": engine_sha256,
                "technicalAnalysisSha256": technical_sha256,
                "frameFetchRetrievedAt": original.get("fetches", {}).get(frame, {}).get("retrievedAt"),
                "nativeInputArchive": "retained" if candidate else "not_retained_non_candidate",
                "scope": "native candles/calendar/session; primary context stays in recorded reading",
                "orderAuthority": False}
    return retained
