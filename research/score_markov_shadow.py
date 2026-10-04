"""Audit chronological shadow labels without granting trading authority.

Predictions were written before their outcome's close. A small paper sample
cannot establish profitability, and midpoint labels ignore executable costs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

from pattern_event_study import STEP, parse_time


def score(model: dict, model_id: str, events: list[dict]) -> dict:
    if model.get("kind") != "read_only_markov_candle_shadow_v1":
        raise ValueError("unexpected model kind")
    predictions: dict[str, dict] = {}
    labels: dict[str, dict] = {}
    for event in events:
        if event.get("modelId") != model_id:
            continue
        kind = event.get("type")
        key = event.get("barStart")
        if kind not in ("prediction", "label") or not isinstance(key, str):
            raise ValueError("unexpected shadow event")
        target = predictions if kind == "prediction" else labels
        if key in target:
            raise ValueError("duplicate shadow event")
        target[key] = event
    if labels.keys() - predictions.keys():
        raise ValueError("label without prior prediction")
    base = model["trainingUp"] / model["trainingLabels"]
    squared = []
    baseline_squared = []
    leads = []
    moves = []
    directional_moves = []
    for key, label in labels.items():
        prediction = predictions[key]
        start = parse_time(key)
        if parse_time(label["nextBarStart"]) != start + STEP:
            raise ValueError("label is not from adjacent bar")
        observed = parse_time(prediction["observedAt"])
        next_close_at = start + STEP + STEP
        if not start + STEP <= observed < next_close_at:
            raise ValueError("prediction was outside next-bar observation window")
        if parse_time(label["observedAt"]) < next_close_at:
            raise ValueError("label was observed before its close")
        lead = (next_close_at - observed).total_seconds()
        # GUESS: # UNCALIBRATED GUESS — microsecond tolerance for a serialized
        # float timestamp; exact equality is fragile across JSON round trips.
        if abs(lead - float(prediction["secondsBeforeNextClose"])) > 0.000001:
            raise ValueError("recorded lead time conflicts with timestamps")
        probability = float(prediction["upProbability"])
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("invalid probability")
        if not isinstance(label["up"], bool):
            raise ValueError("invalid direction label")
        outcome = int(label["up"])
        squared.append((probability - outcome) ** 2)
        baseline_squared.append((base - outcome) ** 2)
        leads.append(lead)
        move = float(label["forwardMidpointBps"])
        moves.append(move)
        # SOURCE: 0.5 is the neutral split of a calibrated probability on [0, 1].
        if probability > 0.5:
            directional_moves.append(move)
        elif probability < 0.5:
            directional_moves.append(-move)
        else:
            directional_moves.append(0.0)
    # SOURCE: two tier-one 25 bps taker fees from the published Alpaca schedule.
    fee_only_roundtrip_bps = 2 * 0.0025 * 10_000
    return {
        "modelId": model_id,
        "predictions": len(predictions),
        "scored": len(labels),
        "unlabeled": len(predictions) - len(labels),
        "leadSeconds": {"min": min(leads) if leads else None,
                        "median": statistics.median(leads) if leads else None,
                        "max": max(leads) if leads else None},
        "markovBrier": sum(squared) / len(squared) if squared else None,
        "frozenBaseRateBrier": sum(baseline_squared) / len(baseline_squared) if baseline_squared else None,
        "meanDirectionalMidpointBps": sum(directional_moves) / len(directional_moves)
            if directional_moves else None,
        "positiveDirectionalMidpointShare": sum(move > 0 for move in directional_moves)
            / len(directional_moves) if directional_moves else None,
        "directionalMidpointMovesAboveFeeOnly": sum(
            move > fee_only_roundtrip_bps for move in directional_moves
        ),
        # SOURCE: this is a raw up-move count, not a predicted-direction trade result.
        "positiveMidpointMovesAboveFeeOnly": sum(
            move > fee_only_roundtrip_bps for move in moves
        ),
        "limitation": "Small, serially dependent paper shadow sample. Prediction lead times vary; labels use later retrieved midpoint closes, not bid/ask execution. Brier scores do not measure after-cost profitability.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("journal", type=Path)
    args = parser.parse_args()
    content = args.model.read_bytes()
    model = json.loads(content)
    events = [json.loads(line) for line in args.journal.read_text(encoding="utf-8").splitlines()]
    print(json.dumps(score(model, hashlib.sha256(content).hexdigest(), events), indent=2))
