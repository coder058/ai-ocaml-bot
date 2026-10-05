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
                      "trainingUp": 1, "trainingLabels": 2,
                      "states":{"known":{"up":1,"total":2}}}
        self.prediction = {"type": "prediction", "modelId": "fixture",
                           "barStart": "2026-09-27T00:00:00Z",
                           "observedAt": "2026-09-27T00:05:10Z",
                           "secondsBeforeNextClose": 290,
                           "snapshotRetrievedAt":"2026-09-27T00:05:09Z",
                           "upProbability": 0.5, "trainingCount":2,
                           "fallback":True, "state":"unseen", "close":100}
        self.label = {"type": "label", "modelId": "fixture",
                      "barStart": "2026-09-27T00:00:00Z",
                      "nextBarStart": "2026-09-27T00:05:00Z",
                      "observedAt": "2026-09-27T00:10:01Z",
                      "snapshotRetrievedAt":"2026-09-27T00:10:00Z",
                      "up": True, "nextClose":101, "forwardMidpointBps": (101/100-1)*10_000}

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
        model={**self.model,"trainingUp":4,"trainingLabels":5,"states":{"known":{"up":4,"total":5}}}
        prediction["trainingCount"]=5
        label = {**self.label, "up": True, "nextClose":100.6,"forwardMidpointBps":(100.6/100-1)*10_000}
        result = score(model, "fixture", [prediction, label])
        self.assertAlmostEqual(result["meanDirectionalBarCloseBps"], 60)
        self.assertEqual(result["directionalBarCloseMovesAboveFeeOnly"], 1)

    def test_unlabeled_predictions_also_require_original_model_and_receipt_evidence(self):
        for change in ({"upProbability":0.9},{"fallback":False},{"trainingCount":True},
                       {"snapshotRetrievedAt":"2026-09-27T00:05:11Z"},
                       {"observedAt":"2026-09-27T00:10:00Z"},{"close":float("nan")}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                score(self.model,"fixture",[{**self.prediction,**change}])

    def test_label_must_agree_with_original_closes_and_arrive_after_prediction(self):
        for change in ({"up":False},{"forwardMidpointBps":float("nan")},
                       {"forwardMidpointBps":200},{"nextClose":True},
                       {"snapshotRetrievedAt":"2026-09-27T00:09:59Z"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                score(self.model,"fixture",[self.prediction,{**self.label,**change}])
        with self.assertRaises(ValueError):
            score(self.model,"fixture",[self.label,self.prediction])

    def test_cutoff_naive_clock_and_invalid_training_counts_fail_closed(self):
        from datetime import datetime,timezone
        with self.assertRaises(ValueError):
            score(self.model,"fixture",[self.prediction],as_of=datetime(2026,9,27,tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            score(self.model,"fixture",[{**self.prediction,"observedAt":"2026-09-27T00:05:10"}])
        for change in ({"trainingLabels":True},{"trainingUp":3},{"states":{}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                score({**self.model,**change},"fixture",[])


if __name__ == "__main__":
    unittest.main()
