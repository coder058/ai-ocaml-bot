"""Fetch the existing public paper projection over SSH, without copying API keys.

No order endpoint is called. The SSH session invokes only the read-only snapshot
functions already installed on Dublin. Failed fetches retain the last good file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

# GUESS: # UNCALIBRATED GUESS — synchronize the local execution monitor each
# minute; fee-history cache retains its existing five-minute cadence. Measure
# full-history fetch duration/API usage as the account history grows.
REFRESH_SECONDS = 60
# GUESS: # UNCALIBRATED GUESS — allow two minutes for full broker pagination;
# measured checks took tens of seconds. Recalibrate as the history grows.
FETCH_TIMEOUT_SECONDS = 120
# SOURCE: the Dublin host/key and exporter path used in the verified SSH checks.
DEFAULT_HOST = "ubuntu@52.17.192.36"
DEFAULT_KEY = Path.home() / ".ssh" / "lightsail-eu-west-1.pem"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / ".local" / "telemetry.json"

REMOTE_PROGRAM = """
import json
import sys
sys.path.insert(0, '/home/ubuntu/ocaml-paper-market-lab/deploy')
import export_telemetry as exporter
# SOURCE: the measured account already exceeds the exporter's twenty activity
# pages. Complete local pagination is bounded by the SSH caller's timeout and
# the existing no-progress checks, rather than silently truncating history.
exporter.MAX_FILL_PAGES = sys.maxsize
credentials = exporter.read_env(exporter.ENV_PATH)
events, complete, decisions = exporter.journal()
service = exporter.service_state(credentials)
document = exporter.snapshot(credentials, service, events, complete, decisions,
                             cache_fees=True)
print(json.dumps(document, separators=(',', ':'), sort_keys=True))
"""


def validate_snapshot(document: object) -> dict:
    if not isinstance(document, dict):
        raise ValueError("snapshot is not an object")
    # SOURCE: the installed exporter and PaperTelemetry declare schema version 1.
    if document.get("version") != 1 or document.get("source") != "Dublin OCaml paper service":
        raise ValueError("unexpected snapshot source/version")
    if not isinstance(document.get("generatedAt"), str):
        raise ValueError("snapshot has no timestamp")
    for field in ("orders", "fills", "positions", "journal"):
        if not isinstance(document.get(field), list):
            raise ValueError(f"snapshot has no {field} array")
    for field in ("ordersComplete", "fillsComplete", "journalComplete"):
        if not isinstance(document.get(field), bool):
            raise ValueError(f"snapshot lacks {field}")
    # SOURCE: publish only BTC and other crypto symbols with actual lab orders;
    # unrelated holdings and AAPL must not cross the SSH boundary.
    def crypto_symbol(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9]+/?USD", value):
            return None
        compact = value.replace("/", "")
        return compact[:-len("USD")] + "/USD" if len(compact) > len("USD") else None

    def symbol(value):
        return crypto_symbol(value) or (value if isinstance(value,str) and value!="AAPL"
            and re.fullmatch(r"[A-Z0-9][A-Z0-9.-]*",value) else None)

    public_symbols = {"BTC/USD"} | {symbol(row.get("symbol"))
        for row in document["orders"] if isinstance(row, dict) and
        (str(row.get("clientOrderId", "")).startswith("jsbotmtf") and crypto_symbol(row.get("symbol")) is not None or
         str(row.get("clientOrderId", "")).startswith("aibotstk") and symbol(row.get("symbol")) is not None)}
    for field in ("orders", "fills", "positions"):
        if any(not isinstance(row, dict) or symbol(row.get("symbol")) not in public_symbols
               for row in document[field]):
            raise ValueError("snapshot includes non-public holdings")
    pipeline = document.get("marketPipeline")
    if pipeline is not None:
        if (not isinstance(pipeline, dict) or pipeline.get("orderAuthority") is not False
                or pipeline.get("winProbability") is not None
                or not isinstance(pipeline.get("markets"), list)):
            raise ValueError("unexpected analysis projection")
        for market in pipeline["markets"]:
            if (not isinstance(market, dict) or market.get("venue") not in
                    ("Alpaca crypto", "Alpaca equities", "Hyperliquid HIP-3")
                    or not isinstance(market.get("symbol"), str)
                    or not isinstance(market.get("frames"), dict)):
                raise ValueError("unexpected analysis market")
    experiment = document.get("multiPaper")
    if experiment is not None:
        if (not isinstance(experiment, dict) or experiment.get("calibrated") is not False
                or experiment.get("winProbability") is not None
                or experiment.get("mode") not in ("OBSERVE", "PAPER_EXPERIMENT")
                or not isinstance(experiment.get("activeTickets"), list)):
            raise ValueError("unexpected experimental paper projection")
        for ticket in experiment["activeTickets"]:
            if (not isinstance(ticket, dict) or crypto_symbol(ticket.get("symbol")) is None
                    or crypto_symbol(ticket.get("symbol")) == "BTC/USD"
                    or not str(ticket.get("entryClientOrderId", "")).startswith("jsbotmtf")):
                raise ValueError("unexpected experimental paper ticket")
    return document


def fetch_snapshot(output: Path, host: str, key: Path) -> dict:
    result = subprocess.run(
        ["ssh", "-T", "-i", str(key), "-o", "BatchMode=yes", "-o",
         "StrictHostKeyChecking=yes", host, "sudo -n python3 -"],
        input=REMOTE_PROGRAM.encode("utf-8"), capture_output=True,
        timeout=FETCH_TIMEOUT_SECONDS, check=False,
    )
    if result.returncode:
        # Do not log raw remote output: only the public JSON is meant to cross
        # the SSH boundary, and unexpected errors could include private fields.
        raise RuntimeError(f"read-only SSH snapshot failed (exit {result.returncode})")
    document = validate_snapshot(json.loads(result.stdout))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(result.stdout)
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print(f"local snapshot: {document['generatedAt']}, {len(document['orders'])} orders, "
          f"{len(document['fills'])} fills, complete_fills={document['fillsComplete']}, "
          f"{len(result.stdout)} bytes", flush=True)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--delay-first", action="store_true",
                        help="Wait one heartbeat after an initial separate fetch")
    args = parser.parse_args()
    if args.delay_first and args.loop:
        time.sleep(REFRESH_SECONDS)
    while True:
        try:
            fetch_snapshot(args.output, args.host, args.key)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            print(f"local snapshot unavailable: {type(error).__name__}; "
                  "last good file retained", flush=True)
            if not args.loop:
                return 1
        if not args.loop:
            return 0
        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
