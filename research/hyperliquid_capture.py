"""Archive public Hyperliquid HIP-3 market data; no wallet or order path.

The archive records local receipt time because WebSocket mids have no exchange
timestamp. Candle updates can be revised and must not be treated as closed
until their T timestamp has passed at the time of a later decision.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


# SOURCE: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket
URL = "wss://api.hyperliquid.xyz/ws"
# SOURCE: HIP-3 meta inventory checked against mainnet on 2026-09-27 UTC.
# These are perpetual contracts; EUR/JPY/GBP are FX-like, not spot FX.
COINS = (
    "xyz:EUR", "xyz:JPY", "xyz:GBP", "xyz:XYZ100", "xyz:SP500",
    "xyz:TSLA", "xyz:NVDA", "xyz:AAPL", "xyz:MSFT", "xyz:AMZN",
    "xyz:GOOGL", "xyz:META", "xyz:AMD", "xyz:BRENTOIL",
)
# SOURCE: official WebSocket subscriptions support 1m candles and bbo.
INTERVAL = "1m"
CAPTURE_DIR = Path("/home/ubuntu/jsbot-paper-state/hyperliquid-capture")
# GUESS: # UNCALIBRATED GUESS — keep a 5 GiB disk reserve; recalibrate from
# measured daily archive growth and the VPS's actual free space.
MIN_FREE_BYTES = 5 * 1024**3
# GUESS: # UNCALIBRATED GUESS — inspect disk after 1,000 frames.
DISK_CHECK_FRAMES = 1_000
# GUESS: # UNCALIBRATED GUESS — 4 MiB bounds a WebSocket frame; measure real
# xyz allMids and BBO frame sizes before increasing.
MAX_FRAME_BYTES = 4 * 1024**2
# GUESS: # UNCALIBRATED GUESS — retry a failed public connection after 5s.
RECONNECT_SECONDS = 5
# GUESS: # UNCALIBRATED GUESS — hourly rotation bounds individual compressed
# files; tune from measured event volume and operational recovery needs.
ROTATE_MS = 60 * 60 * 1000
# SOURCE: prior hlbot/capture/ws.py flushes its capture writer every 2,000
# records; retain that durability/visibility cadence for this separate feed.
FLUSH_EVERY = 2_000


def subscriptions() -> list[dict]:
    # SOURCE: a single xyz allMids subscription covers the active HIP-3 dex.
    items = [{"type": "allMids", "dex": "xyz"}]
    for coin in COINS:
        items.append({"type": "bbo", "coin": coin})
        items.append({"type": "candle", "coin": coin, "interval": INTERVAL})
    return items


class Archive:
    def __init__(self) -> None:
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.day = ""
        self.slot: int | None = None
        self.handle: TextIO | None = None
        self.session_id = ""
        self.sequence = 0
        self.since_flush = 0

    def begin_session(self) -> None:
        self.close()
        self.day = ""
        self.slot = None
        self.session_id = uuid.uuid4().hex
        self.sequence = 0
        self.since_flush = 0

    def close(self) -> None:
        if self.handle is not None:
            self.handle.flush()
            os.fsync(self.handle.fileno())
            self.handle.close()
            self.handle = None
            self.slot = None

    def write(self, message: dict) -> None:
        received_ns = time.time_ns()
        day = datetime.fromtimestamp(received_ns / 1_000_000_000, timezone.utc).date().isoformat()
        slot = received_ns // (ROTATE_MS * 1_000_000)
        if self.handle is None or slot != self.slot:
            self.close()
            # Session IDs make each gzip member path unique. A killed process
            # can damage its final member without poisoning a later restart.
            path = CAPTURE_DIR / f"{day}-{slot}-{self.session_id}.jsonl.gz"
            self.handle = gzip.open(path, "wt", encoding="utf-8")
            self.day = day
            self.slot = slot
        self.sequence += 1
        if self.sequence % DISK_CHECK_FRAMES == 0:
            stats = os.statvfs(CAPTURE_DIR)
            if stats.f_bavail * stats.f_frsize < MIN_FREE_BYTES:
                raise RuntimeError("Hyperliquid capture stopped: disk reserve breached")
        record = {"feed": "hyperliquid-mainnet-public", "receivedAtNs": received_ns,
                  "sessionId": self.session_id, "sequence": self.sequence,
                  "message": message}
        assert self.handle is not None
        self.handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        self.since_flush += 1
        if self.since_flush >= FLUSH_EVERY:
            self.handle.flush()
            self.since_flush = 0


async def session(archive: Archive) -> None:
    archive.begin_session()
    requested = subscriptions()
    acked: set[str] = set()
    async with connect(URL, max_size=MAX_FRAME_BYTES) as socket:
        for item in requested:
            await socket.send(json.dumps({"method": "subscribe", "subscription": item}))
        async for raw in socket:
            message = json.loads(raw)
            if not isinstance(message, dict):
                continue
            channel = message.get("channel")
            if channel == "subscriptionResponse":
                acked.add(json.dumps(message.get("data"), sort_keys=True))
                if len(acked) == len(requested):
                    print(f"subscriptions_acknowledged={len(acked)}", flush=True)
            elif channel == "error":
                raise RuntimeError(f"Hyperliquid subscription error: {message}")
            if channel in ("subscriptionResponse", "allMids", "bbo", "candle"):
                archive.write(message)


async def main() -> None:
    archive = Archive()
    try:
        while True:
            try:
                await session(archive)
            except (OSError, TimeoutError, ConnectionError, ConnectionClosed) as exc:
                print(f"public feed transport error={type(exc).__name__}; reconnecting", flush=True)
            finally:
                archive.close()
            await asyncio.sleep(RECONNECT_SECONDS)
    finally:
        archive.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"capture stopped: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
