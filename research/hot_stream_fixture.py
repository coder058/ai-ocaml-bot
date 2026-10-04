"""Send synthetic quotes to an isolated read-only OCaml integration test.

The path must end in fixture.sock. Never point this script at the production
Alpaca socket or describe its events as market observations.
"""

from __future__ import annotations

import argparse
import json
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("socket_path", type=Path)
    args = parser.parse_args()
    if args.socket_path.name != "fixture.sock":
        raise ValueError("fixture sender requires an isolated fixture.sock")
    if not args.socket_path.is_socket():
        raise ValueError("fixture consumer socket is absent")
    first = datetime.now(timezone.utc)
    second = first + timedelta(microseconds=1)
    # SOURCE: these are synthetic branch fixtures, never market observations.
    events = [
        {"T": "q", "S": "BTC/USD", "bp": 100.0, "ap": 101.0,
         "bs": 1.0, "as": 1.0, "t": first.isoformat()},
        {"T": "q", "S": "BTC/USD", "bp": 102.0, "ap": 103.0,
         "bs": 1.0, "as": 1.0, "t": second.isoformat()},
        {"T": "q", "S": "BTC/USD", "bp": 102.0, "ap": 103.0,
         "bs": 1.0, "as": 1.0, "t": second.isoformat()},
    ]
    sender = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        for sequence, event in enumerate(events, start=1):
            payload = {"receivedAtNs": time.time_ns(),
                       "sessionId": "synthetic-fixture",
                       "hotSequence": sequence, "event": event}
            sender.sendto(json.dumps(payload).encode(), str(args.socket_path))
            time.sleep(0.1)  # GUESS: # UNCALIBRATED GUESS — let the worker run.
    finally:
        sender.close()
    print("sent synthetic fixture quotes only", flush=True)


if __name__ == "__main__":
    main()
