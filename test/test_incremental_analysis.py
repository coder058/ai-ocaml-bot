"""Actual OCaml/full parity with synthetic inputs; no broker or market results."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from incremental_analysis import analyze, signature, reusable, save

ENGINE = Path(__file__).resolve().parents[1] / "_build/default/bin/analyze_frames_main.exe"
# SOURCE: actual user's five frames; deterministic synthetic prices/time only.
FRAMES = {"1m": 1, "5m": 5, "30m": 30, "1h": 60, "4h": 240}
NOW = datetime(2026, 10, 1, 12, 1, tzinfo=timezone.utc)
stamp = lambda dt: dt.isoformat().replace("+00:00", "Z")


def fixture():
    market = {"venue": "Alpaca crypto", "symbol": "BTC/USD", "frames": {}}
    for frame, minutes in FRAMES.items():
        boundary = int(NOW.timestamp()) // (minutes * 60) * minutes * 60
        rows = []
        # SOURCE: 100 synthetic bars exceed the existing EMA50 warmup.
        for index in range(100):
            close = 100 + index / 10
            rows.append({"t": stamp(datetime.fromtimestamp(boundary - (100-index)*minutes*60, timezone.utc)),
                         "o": close + .02, "h": close + .04, "l": close-1, "c": close, "v": 100})
        market["frames"][frame] = rows
    return {"asOf": stamp(NOW), "markets": [market]}


def full(payload, engine):
    before = hashlib.sha256(engine.read_bytes()).hexdigest()
    process = subprocess.run([str(engine)], input=json.dumps(payload).encode(),
                             capture_output=True, check=True)
    after = hashlib.sha256(engine.read_bytes()).hexdigest()
    if before != after:
        raise RuntimeError("engine replaced")
    return json.loads(process.stdout), before


class SignatureChecks(unittest.TestCase):
    def test_exact_revision_calendar_clock_identity_and_session_invalidate(self):
        p = fixture(); market = p["markets"][0]
        key = signature(market, "5m", 5, p["asOf"], "engine")
        self.assertEqual(key, signature(market, "5m", 5, stamp(NOW+timedelta(minutes=1)), "engine"))
        for modify in (lambda m: m["frames"]["5m"][0].update(c=101),
                       lambda m: m.update(sessionOpen=False),
                       lambda m: m.update(expectedStarts={"5m": [1]})):
            revised = copy.deepcopy(market); modify(revised)
            self.assertNotEqual(key, signature(revised, "5m", 5, p["asOf"], "engine"))
        self.assertNotEqual(key, signature(market, "5m", 5, stamp(NOW+timedelta(minutes=4)), "engine"))
        self.assertNotEqual(key, signature(market, "5m", 5, p["asOf"], "different engine"))

    def test_cache_is_disposable_and_cannot_reuse_future_or_corrupt_values(self):
        entry = save({"status": "ready"}, "key", stamp(NOW))
        self.assertTrue(reusable(entry, "key", stamp(NOW)))
        self.assertFalse(reusable(entry, "key", stamp(NOW-timedelta(minutes=1))))
        entry["value"]["status"] = "candidate"
        self.assertFalse(reusable(entry, "key", stamp(NOW)))


@unittest.skipUnless(ENGINE.exists() and os.name == "posix", "requires real Linux OCaml analyzer")
class NativeParity(unittest.TestCase):
    def cycle(self, payload, cache):
        expected, _ = full(payload, ENGINE)
        actual, _, cache, counts = analyze(payload, ENGINE, cache, full, FRAMES)
        self.assertEqual(actual, expected)
        return cache, counts

    def test_repeated_scan_restart_and_minute_age_match_full_with_four_reused_frames(self):
        p = fixture(); cache, counts = self.cycle(p, {})
        self.assertEqual(counts["computedFrames"], len(FRAMES))
        cache, counts = self.cycle(p, json.loads(json.dumps(cache)))
        self.assertEqual(counts["computedFrames"], 0)
        p["asOf"] = stamp(NOW+timedelta(minutes=1))
        _, counts = self.cycle(p, cache)
        self.assertEqual(counts["computedFrames"], 1)
        self.assertEqual(counts["reusedFrames"], len(FRAMES)-1)

    def test_missing_close_and_historical_revision_recompute_exact_affected_slot(self):
        p = fixture(); cache, _ = self.cycle(p, {})
        p["markets"][0]["frames"]["4h"][0]["v"] = 200
        cache, counts = self.cycle(p, cache)
        self.assertEqual(counts["computedFrames"], 1)
        p["asOf"] = stamp(NOW+timedelta(minutes=4))
        cache, counts = self.cycle(p, cache)
        self.assertEqual(counts["computedFrames"], 2)
        result, _, _, _ = analyze(p, ENGINE, cache, full, FRAMES)
        self.assertEqual(result["markets"][0]["frames"]["5m"]["status"], "stale")
        self.assertIsNone(result["markets"][0]["frames"]["5m"]["candidate"])

    def test_session_open_close_calendar_revision_and_clock_rollback_match_full(self):
        p = fixture(); m = p["markets"][0]; m["venue"] = "Alpaca equities"; m["symbol"] = "QQQ"
        m["sessionOpen"] = False
        m["expectedStarts"] = {f: [int(datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp())//60
                                    for r in rows] for f, rows in m["frames"].items()}
        cache, _ = self.cycle(p, {})
        m["sessionOpen"] = True
        cache, counts = self.cycle(p, cache)
        self.assertEqual(counts["computedFrames"], len(FRAMES))
        m["expectedStarts"]["4h"].pop(1)
        cache, counts = self.cycle(p, cache)
        self.assertEqual(counts["computedFrames"], 1)
        p["asOf"] = stamp(NOW-timedelta(minutes=1))
        self.cycle(p, cache)

    def test_corrupt_cache_and_future_candle_recovery_do_not_publish_cached_candidates(self):
        p = fixture(); cache, _ = self.cycle(p, {})
        key = "Alpaca crypto|BTC/USD|5m"
        cache["frames"][key]["value"]["candidate"] = "invented"
        cache, counts = self.cycle(p, cache)
        self.assertEqual(counts["computedFrames"], 1)
        p["markets"][0]["frames"]["1m"].append({**p["markets"][0]["frames"]["1m"][-1], "t": stamp(NOW)})
        cache, _ = self.cycle(p, cache)
        p["asOf"] = stamp(NOW+timedelta(minutes=1))
        self.cycle(p, cache)


if __name__ == "__main__":
    unittest.main()
