"""Retain exact dated research report bytes, without rewriting a prior attempt."""
import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def retain(path):
    raw = path.read_bytes()
    value = json.loads(raw)
    if (value.get("orderAuthority") is not False or value.get("winProbability") is not None
            or value.get("brokerPnl") is not None or not isinstance(value.get("manifestSha256"), str)):
        raise ValueError("not a descriptive stock research report")
    at = datetime.fromisoformat(value["generatedAt"].replace("Z", "+00:00"))
    if at.tzinfo is None or at > datetime.now(timezone.utc):
        raise ValueError("actual report receipt must be aware and not future")
    # SOURCE: actual UTC report timestamp; path comes from its parsed clock,
    # never raw text or an external output directory supplied by the report.
    target = path.with_name("report-" + at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError("dated attempt already exists with different bytes")
        return target, hashlib.sha256(raw).hexdigest()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".retain-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        # SOURCE: link creates the name atomically and cannot replace a prior
        # artifact. Temporary files are private by NamedTemporaryFile default.
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != raw:
                raise ValueError("concurrent dated attempt has different bytes")
    finally:
        if temporary is not None:
            temporary.unlink()
    return target, hashlib.sha256(raw).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    target, digest = retain(args.report)
    print(json.dumps({"artifact": target.name, "sha256": digest, "orderAuthority": False}))
