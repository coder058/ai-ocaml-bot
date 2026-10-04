"""Archive raw Alpaca US crypto market events for later point-in-time research.

This process cannot submit orders. It sends credentials only to Alpaca's TLS
market-data WebSocket, never writes them to a capture or log, and records both
exchange and local receipt timestamps. Captured data stays private on Dublin.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from websockets.asyncio.client import connect

# SOURCE: https://docs.alpaca.markets/us/docs/real-time-crypto-pricing-data
STREAM_URL = "wss://stream.data.alpaca.markets/v1beta3/crypto/us"
ENV_PATH = Path("/etc/jsbot-paper.env")
CAPTURE_DIR = Path("/home/ubuntu/jsbot-paper-state/market-capture/us")
HOT_SOCKET = Path("/home/ubuntu/jsbot-paper-state/alpaca-hot.sock")
SYMBOL = "BTC/USD"  # SOURCE: the OCaml paper bot's only traded symbol.
# SOURCE: Pattern Forge follows ETH and SOL; the remaining symbols had zero
# 5m historical gaps in the 2026-09-27 23:30 UTC same-day account scan.
# This is a data-coverage selection, not evidence of profitable signals.
# All remain research-only; none receives OCaml paper order authority.
RESEARCH_SYMBOLS = (
    "AAVE/USD", "ADA/USD", "ARB/USD", "AVAX/USD", "DOT/USD", "ETH/USD",
    "FIL/USD", "GRT/USD", "LDO/USD", "ONDO/USD", "RENDER/USD", "SOL/USD",
    "SUSHI/USD", "WIF/USD",
)
ARCHIVED_SYMBOLS = (SYMBOL, *RESEARCH_SYMBOLS)
# GUESS: # UNCALIBRATED GUESS — stop collecting before the 49 GB free disk
# observed on Dublin is nearly exhausted. Replace with measured capacity alert.
MIN_FREE_BYTES = 5 * 1024 * 1024 * 1024
# GUESS: # UNCALIBRATED GUESS — check capacity every 1,000 received events.
DISK_CHECK_EVENTS = 1_000
# GUESS: # UNCALIBRATED GUESS — bound a full book frame at 4 MiB; observe real
# reset sizes and reconnect behavior before revising.
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
# GUESS: # UNCALIBRATED GUESS — reconnect after a transport failure in 5 seconds.
RECONNECT_SECONDS = 5


class CaptureGuardError(Exception):
    """A storage or feed-integrity condition requiring operator review."""


def subscription_request() -> dict:
    return {"action": "subscribe", "quotes": list(ARCHIVED_SYMBOLS),
            "trades": [SYMBOL], "orderbooks": [SYMBOL],
            "bars": list(ARCHIVED_SYMBOLS), "updatedBars": list(ARCHIVED_SYMBOLS)}


def valid_subscription(item: dict) -> bool:
    request = subscription_request()
    return all(set(symbols).issubset(set(item.get(channel, [])))
               for channel, symbols in request.items() if channel != "action")


def valid_market_event(item: dict) -> bool:
    symbol = item.get("S")
    kind = item.get("T")
    return (isinstance(item.get("t"), str)
            and (symbol == SYMBOL and kind in ("q", "t", "o", "b", "u")
                 or symbol in RESEARCH_SYMBOLS and kind in ("q", "b", "u")))


def should_fanout(event: dict) -> bool:
    """Only the existing BTC quote/bar channel reaches the OCaml order process."""
    return event.get("S") == SYMBOL and event.get("T") in ("q", "b", "u")


def credentials() -> tuple[str, str]:
    values = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values["APCA_API_KEY_ID"], values["APCA_API_SECRET_KEY"]


class Archive:
    def __init__(self) -> None:
        # SOURCE: the archive contains market events only. The OCaml process
        # needs group read access for point-in-time indicator warmup.
        self.reader_group = os.stat("/home/ubuntu").st_gid
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True, mode=0o750)
        os.chown(CAPTURE_DIR, 0, self.reader_group)
        os.chmod(CAPTURE_DIR, 0o750)
        self.day = ""
        self.handle: int | None = None
        self.events = 0
        self.session_id = ""
        self.stream_sequence = 0

    def begin_session(self) -> None:
        # SOURCE: a new Alpaca WebSocket connection is a distinct capture session.
        self.session_id = uuid.uuid4().hex
        self.stream_sequence = 0

    def close(self) -> None:
        if self.handle is not None:
            os.fsync(self.handle)
            os.close(self.handle)
            self.handle = None

    def write(self, event: dict) -> dict:
        received_ns = time.time_ns()
        day = datetime.fromtimestamp(received_ns / 1_000_000_000, timezone.utc).date().isoformat()
        if day != self.day:
            self.close()
            path = CAPTURE_DIR / f"{day}.jsonl"
            self.handle = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o640)
            os.fchown(self.handle, 0, self.reader_group)
            os.fchmod(self.handle, 0o640)
            self.day = day
        self.events += 1
        if self.events % DISK_CHECK_EVENTS == 0:
            stats = os.statvfs(CAPTURE_DIR)
            if stats.f_bavail * stats.f_frsize < MIN_FREE_BYTES:
                raise CaptureGuardError("market capture stopped: free disk below safety reserve")
        self.stream_sequence += 1
        record = {"receivedAtNs": received_ns, "feed": "alpaca-us",
                  "sessionId": self.session_id, "streamSequence": self.stream_sequence,
                  "event": event}
        assert self.handle is not None
        os.write(self.handle, (json.dumps(record, separators=(",", ":")) + "\n").encode())
        return record


class LocalFanout:
    """Nonblocking local datagrams for an OCaml consumer; archive stays primary."""

    def __init__(self) -> None:
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.hot_sequence = 0
        self.sent = 0
        self.dropped = 0
        self.last_report = time.monotonic()

    def close(self) -> None:
        self.socket.close()

    def send(self, record: dict) -> None:
        if not should_fanout(record["event"]):
            return
        self.hot_sequence += 1
        hot_record = {**record, "hotSequence": self.hot_sequence}
        try:
            self.socket.sendto(json.dumps(hot_record, separators=(",", ":")).encode(), str(HOT_SOCKET))
            self.sent += 1
        except OSError:
            # SOURCE: archival continues when the optional local consumer is absent.
            self.dropped += 1

    def report(self) -> None:
        now = time.monotonic()
        # GUESS: # UNCALIBRATED GUESS — report fanout counters once per minute to
        # avoid one log line per market update; adjust after observing operations.
        if now - self.last_report >= 60:
            print(f"hot fanout session_sent={self.sent} session_dropped={self.dropped}", flush=True)
            self.last_report = now


async def session(archive: Archive, fanout: LocalFanout) -> None:
    archive.begin_session()
    fanout.hot_sequence = 0
    fanout.sent = 0
    fanout.dropped = 0
    fanout.last_report = time.monotonic()
    key, secret = credentials()
    async with connect(STREAM_URL, max_size=MAX_MESSAGE_BYTES) as socket:
        await socket.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
        authenticated = False
        subscribed = False
        async for message in socket:
            items = json.loads(message)
            if not isinstance(items, list):
                raise ValueError("stream frame was not an array")
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("stream event was not an object")
                kind = item.get("T")
                if kind == "error":
                    # SOURCE: Alpaca stream error codes; never log auth payload.
                    raise RuntimeError(f"Alpaca stream error code={item.get('code')}")
                if kind == "success" and item.get("msg") == "authenticated":
                    authenticated = True
                    await socket.send(json.dumps(subscription_request()))
                elif kind == "subscription":
                    expected = valid_subscription(item)
                    if not authenticated or not expected:
                        raise CaptureGuardError("Alpaca stream subscription was incomplete")
                    subscribed = True
                    print(f"market capture: authenticated; BTC execution feed and {len(ARCHIVED_SYMBOLS)} research quote/bar symbols", flush=True)
                elif kind in ("q", "t", "o", "b", "u"):
                    if not subscribed or not valid_market_event(item):
                        raise CaptureGuardError("unexpected stream market event")
                    fanout.send(archive.write(item))
                    fanout.report()


async def main() -> None:
    archive = Archive()
    fanout = LocalFanout()
    try:
        while True:
            try:
                await session(archive, fanout)
                raise ConnectionError("market stream closed")
            except (ConnectionError, OSError, TimeoutError) as error:
                print(f"market capture: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
                archive.close()
                await asyncio.sleep(RECONNECT_SECONDS)
    finally:
        archive.close()
        fanout.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (CaptureGuardError, RuntimeError, ValueError) as error:
        print(f"market capture halted for review: {error}", file=sys.stderr, flush=True)
        # SOURCE: sysexits.h EX_CONFIG=78; systemd does not restart this exit.
        raise SystemExit(78) from error
