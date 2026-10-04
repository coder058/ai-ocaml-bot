"""Record forward, read-only Markov predictions from as-retrieved 5m bars.

One prediction is logged for the latest closed bar only, before its successor
closes. Labels are logged on later invocations; neither event can send orders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from markov_candle_audit import states_for_bars
from pattern_event_study import STEP, parse_time


def events_for_snapshot(document: dict, model: dict, journal: list[dict],
                        observed_at: datetime, model_id: str) -> list[dict]:
    if model.get("kind") != "read_only_markov_candle_shadow_v1":
        raise ValueError("unexpected model kind")
    if observed_at.tzinfo is None:
        raise ValueError("observation time has no timezone")
    retrieved_at = parse_time(document["retrievedAt"])
    if retrieved_at.tzinfo is None or retrieved_at > observed_at:
        raise ValueError("invalid snapshot retrieval time")
    bars = document["bars"]
    states = states_for_bars(document)
    if not bars:
        raise ValueError("empty bar snapshot")
    predictions = {event["barStart"]: event for event in journal
                   if event.get("type") == "prediction" and event.get("modelId") == model_id}
    labeled = {event["barStart"] for event in journal
               if event.get("type") == "label" and event.get("modelId") == model_id}
    events = []
    for start, prediction in predictions.items():
        if start in labeled:
            continue
        successor = parse_time(start) + STEP
        next_bar = next((bar for bar in bars if parse_time(bar["t"]) == successor), None)
        if next_bar is None or successor + STEP > retrieved_at:
            continue
        # The prediction must predate the successor close. This also keeps a
        # stale snapshot from generating retroactive apparent forecasts.
        prediction_at = parse_time(prediction["observedAt"])
        if prediction_at >= successor + STEP:
            continue
        next_close = float(next_bar["c"])
        prior_close = float(prediction["close"])
        if not math.isfinite(next_close) or not math.isfinite(prior_close) or next_close <= 0 or prior_close <= 0:
            raise ValueError("non-positive prediction or label close")
        events.append({"type": "label", "modelId": model_id,
                       "barStart": start, "nextBarStart": next_bar["t"],
                       "observedAt": observed_at.isoformat(),
                       "snapshotRetrievedAt": document["retrievedAt"],
                       "nextClose": next_close, "up": next_close > prior_close,
                       "forwardMidpointBps": (next_close / prior_close - 1) * 10_000})  # SOURCE: bps definition.
    latest = bars[-1]
    start = latest["t"]
    bar_end = parse_time(start) + STEP
    if (states[-1] is not None and start not in predictions
            and bar_end <= retrieved_at and observed_at < bar_end + STEP):
        key = states[-1]
        counts = model["states"].get(key)
        up, total = (counts["up"], counts["total"]) if counts else (
            model["trainingUp"], model["trainingLabels"])
        if not 0 <= up <= total or total <= 0:
            raise ValueError("invalid frozen model counts")
        close = float(latest["c"])
        if not math.isfinite(close) or close <= 0:
            raise ValueError("invalid current close")
        events.append({"type": "prediction", "modelId": model_id,
                       "barStart": start, "barEnd": bar_end.isoformat(),
                       "observedAt": observed_at.isoformat(),
                       "snapshotRetrievedAt": document["retrievedAt"],
                       "secondsBeforeNextClose": (bar_end + STEP - observed_at).total_seconds(),
                       "secondsAfterCurrentClose": (observed_at - bar_end).total_seconds(),
                       "state": key, "close": close,
                       "upProbability": up / total, "trainingCount": total,
                       "fallback": counts is None})
    return events


def run(snapshot_path: Path, model_path: Path, journal_path: Path) -> list[dict]:
    model_bytes = model_path.read_bytes()
    model_id = hashlib.sha256(model_bytes).hexdigest()
    model = json.loads(model_bytes)
    document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    journal = ([json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
               if journal_path.exists() else [])
    observed_at = datetime.now(timezone.utc)
    events = events_for_snapshot(document, model, journal, observed_at, model_id)
    if events:
        with journal_path.open("a", encoding="utf-8") as output:
            for event in events:
                output.write(json.dumps(event, separators=(",", ":")) + "\n")
            output.flush()
            os.fsync(output.fileno())
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("journal", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.snapshot, args.model, args.journal)))
