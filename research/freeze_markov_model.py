"""Freeze a descriptive next-bar model from pre-July historical bars only.

Historical Alpaca bars were retrieved in September and can have revisions.
This artifact is for forward shadow scoring, never order authorization.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from markov_candle_audit import observations
from pattern_event_study import HOLDOUT_START, parse_time


def freeze(document: dict) -> dict:
    counts: dict[str, Counter[bool]] = defaultdict(Counter)
    bars = document["bars"]
    # SOURCE: the existing audit declared 1 July as the chronological cutoff.
    cutoff = HOLDOUT_START
    # observations() has no timestamps in its rows. Build the training-only
    # document first so even the cross-boundary label cannot enter the model.
    training_document = dict(document, bars=[bar for bar in bars
                                             if parse_time(bar["t"]) < cutoff])
    rows = observations(training_document)
    if not rows:
        raise ValueError("no adjacent pre-cutoff labels")
    for key, up, _, _ in rows:
        counts[key][up] += 1
    total_up = sum(up for _, up, _, _ in rows)
    return {
        "kind": "read_only_markov_candle_shadow_v1",
        "source": document.get("source"),
        "historicalRetrievedAt": document.get("retrievedAt"),
        "trainingCutoffExclusive": cutoff.isoformat(),
        "trainingLabels": len(rows),
        "trainingUp": total_up,
        "states": {key: {"up": value[True], "total": sum(value.values())}
                   for key, value in sorted(counts.items())},
        "limitation": "Historical bars were retrieved after the period and may be revised; probabilities are descriptive next-midpoint-close rates, without executable costs or calibration.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bar_file", type=Path)
    parser.add_argument("model_file", type=Path)
    args = parser.parse_args()
    model = freeze(json.loads(args.bar_file.read_text(encoding="utf-8")))
    args.model_file.parent.mkdir(parents=True, exist_ok=True)
    args.model_file.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"trainingLabels": model["trainingLabels"],
                      "states": len(model["states"]), "output": str(args.model_file)}))
