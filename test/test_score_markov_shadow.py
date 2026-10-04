"""Audit the shadow scorer's chronological and duplicate guards."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from score_markov_shadow import score  # noqa: E402


class ShadowScoreTests(unittest.TestCase):
    def setUp(self) -> None:
        # SOURCE: synthetic values test pairing only; not observed performance.
        self.model = {"kind": "read_only_markov_candle_shadow_v1",
                      "trainingUp": 1, "trainingLabels": 2}
        self.prediction = {"type": "prediction", "modelId": "fixture",
                           "barStart": "2026-09-27T00:00:00Z",
                           "observedAt": "2026-09-27T00:05:10Z",
                           "secondsBeforeNextClose": 290,
                           "upProbability": 0.5}
        self.label = {"type": "label", "modelId": "fixture",
                      "barStart": "2026-09-27T00:00:00Z",
                      "nextBarStart": "2026-09-27T00:05:00Z",
                      "observedAt": "2026-09-27T00:10:01Z",
                      "up": True, "forwardMidpointBps": 1}

    def test_pairs_only_after_close(self) -> None:
        result = score(self.model, "fixture", [self.prediction, self.label])
        self.assertEqual(result["scored"], 1)
        self.assertEqual(result["leadSeconds"]["min"], 290)
        self.assertEqual(result["markovBrier"], 0.25)

    def test_duplicate_prediction_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            score(self.model, "fixture", [self.prediction, self.prediction])

    def test_label_before_close_is_rejected(self) -> None:
        self.label["observedAt"] = "2026-09-27T00:09:59Z"
        with self.assertRaisesRegex(ValueError, "before its close"):
            score(self.model, "fixture", [self.prediction, self.label])

    def test_directional_move_uses_prediction_and_two_sided_fee_hurdle(self) -> None:
        # SOURCE: synthetic 60 bps move checks fee hurdle arithmetic only.
        prediction = {**self.prediction, "upProbability": 0.8}
        label = {**self.label, "up": True, "forwardMidpointBps": 60}
        result = score(self.model, "fixture", [prediction, label])
        self.assertEqual(result["meanDirectionalMidpointBps"], 60)
        self.assertEqual(result["directionalMidpointMovesAboveFeeOnly"], 1)


if __name__ == "__main__":
    unittest.main()
