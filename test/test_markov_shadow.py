"""Point-in-time checks for read-only predictions and later labels."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from freeze_markov_model import freeze  # noqa: E402
from markov_shadow import events_for_snapshot  # noqa: E402


def bar(stamp: str, close: float) -> dict:
    # SOURCE: synthetic prices test timing and labels, not a trading threshold.
    return {"t": stamp, "o": close, "h": close, "l": close, "c": close}


def snapshot(bars: list[dict], retrieved: str) -> dict:
    return {"symbol": "BTC/USD", "timeframe": "5Min", "bars": bars,
            "retrievedAt": retrieved}


MODEL = {"kind": "read_only_markov_candle_shadow_v1", "trainingUp": 1,
         "trainingLabels": 2, "states": {}}
MODEL_ID = "synthetic-model"


class MarkovShadowTests(unittest.TestCase):
    def test_prediction_precedes_successor_and_later_label(self) -> None:
        # SOURCE: synthetic timestamps exercise the five-minute bar contract.
        first = snapshot([bar("2026-09-27T00:00:00Z", 100),
                          bar("2026-09-27T00:05:00Z", 101),
                          bar("2026-09-27T00:10:00Z", 102)], "2026-09-27T00:16:00Z")
        prediction_time = datetime(2026, 9, 27, 0, 16, tzinfo=timezone.utc)
        prediction = events_for_snapshot(first, MODEL, [], prediction_time, MODEL_ID)
        self.assertEqual([event["type"] for event in prediction], ["prediction"])
        self.assertEqual(prediction[0]["upProbability"], 0.5)
        self.assertEqual(prediction[0]["secondsBeforeNextClose"], 240)
        self.assertTrue(prediction[0]["fallback"])
        self.assertEqual(events_for_snapshot(first, MODEL, prediction, prediction_time, MODEL_ID), [])
        later = snapshot(first["bars"] + [bar("2026-09-27T00:15:00Z", 103)],
                         "2026-09-27T00:21:00Z")
        events = events_for_snapshot(later, MODEL, prediction,
                                     datetime(2026, 9, 27, 0, 22, tzinfo=timezone.utc), MODEL_ID)
        self.assertEqual([event["type"] for event in events], ["label", "prediction"])
        self.assertEqual(events[0]["nextClose"], 103)
        self.assertTrue(events[0]["up"])

    def test_stale_snapshot_cannot_backfill_prediction(self) -> None:
        document = snapshot([bar("2026-09-27T00:00:00Z", 100),
                             bar("2026-09-27T00:05:00Z", 101)], "2026-09-27T00:20:00Z")
        self.assertEqual(events_for_snapshot(document, MODEL, [],
                         datetime(2026, 9, 27, 0, 21, tzinfo=timezone.utc), MODEL_ID), [])

    def test_training_excludes_boundary_successor(self) -> None:
        document = snapshot([bar("2026-06-30T23:45:00Z", 100),
                             bar("2026-06-30T23:50:00Z", 101),
                             bar("2026-06-30T23:55:00Z", 102),
                             bar("2026-07-01T00:00:00Z", 200)], "2026-09-27T00:00:00Z")
        model = freeze(document)
        self.assertEqual(model["trainingLabels"], 1)


if __name__ == "__main__":
    unittest.main()
