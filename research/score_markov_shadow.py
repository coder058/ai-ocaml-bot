"""Audit chronological shadow labels without granting trading authority.

Predictions were written before their outcome's close. A small paper sample
cannot establish profitability, and native bar-close labels ignore executable
costs. Alpaca crypto bars can include quote midpoints as well as trades:
https://docs.alpaca.markets/us/docs/historical-crypto-data-1 .
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path

from pattern_event_study import STEP, parse_time


def score(model: dict, model_id: str, events: list[dict], *, as_of=None) -> dict:
    if model.get("kind") != "read_only_markov_candle_shadow_v1":
        raise ValueError("unexpected model kind")
    def counts(up, total):
        if any(isinstance(n, bool) or not isinstance(n, int) for n in (up,total)) or not 0 <= up <= total or total <= 0:
            raise ValueError("invalid frozen training counts")
        return up / total
    base = counts(model["trainingUp"], model["trainingLabels"])
    states = model["states"]
    if not isinstance(states, dict):
        raise ValueError("frozen state mapping missing")
    for state in states.values():
        counts(state["up"],state["total"])
    if sum(s["total"] for s in states.values()) != model["trainingLabels"] or sum(s["up"] for s in states.values()) != model["trainingUp"]:
        raise ValueError("state totals conflict with frozen base rate")
    if as_of is not None and as_of.tzinfo is None:
        raise ValueError("score cutoff has no timezone")
    def stamp(value):
        at = parse_time(value)
        if at.tzinfo is None or as_of is not None and at > as_of:
            raise ValueError("shadow event is naive or beyond score cutoff")
        return at
    predictions: dict[str, dict] = {}
    labels: dict[str, dict] = {}
    previous_at = None
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
        observed = stamp(event["observedAt"])
        if previous_at is not None and observed < previous_at:
            raise ValueError("shadow journal receipt order decreases")
        previous_at = observed
        if kind == "label" and key not in predictions:
            raise ValueError("label appears before its prior prediction in journal")
        target[key] = event
    if labels.keys() - predictions.keys():
        raise ValueError("label without prior prediction")
    for key, prediction in predictions.items():
        start, observed = stamp(key), stamp(prediction["observedAt"])
        retrieved = stamp(prediction["snapshotRetrievedAt"])
        if start.timestamp() % STEP.total_seconds() or not start + STEP <= retrieved <= observed < start + STEP + STEP:
            raise ValueError("prediction was outside next-bar observation window")
        probability = prediction["upProbability"]
        if isinstance(probability,bool) or not isinstance(probability,(float,int)) or not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("invalid probability")
        state = states.get(prediction["state"])
        up, total = (state["up"],state["total"]) if state else (model["trainingUp"],model["trainingLabels"])
        if probability != up / total or prediction["trainingCount"] != total or isinstance(prediction["trainingCount"],bool) or prediction["fallback"] is not (state is None):
            raise ValueError("prediction conflicts with exact frozen model")
        lead = (start + STEP + STEP - observed).total_seconds()
        # GUESS: # UNCALIBRATED GUESS — inherited microsecond tolerance for
        # serialized lead duration, not a calibrated order-latency threshold.
        if not math.isfinite(float(prediction["secondsBeforeNextClose"])) or abs(lead - float(prediction["secondsBeforeNextClose"])) > 0.000001:
            raise ValueError("recorded lead time conflicts with timestamps")
        close = prediction["close"]
        if isinstance(close,bool) or not math.isfinite(float(close)) or float(close) <= 0:
            raise ValueError("invalid original prediction close")
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
        if stamp(label["observedAt"]) < next_close_at or not next_close_at <= stamp(label["snapshotRetrievedAt"]) <= stamp(label["observedAt"]):
            raise ValueError("label was observed before its close")
        lead = (next_close_at - observed).total_seconds()
        probability = float(prediction["upProbability"])
        if not isinstance(label["up"], bool):
            raise ValueError("invalid direction label")
        outcome = int(label["up"])
        squared.append((probability - outcome) ** 2)
        baseline_squared.append((base - outcome) ** 2)
        leads.append(lead)
        move = float(label["forwardMidpointBps"])
        next_close = label["nextClose"]
        if (isinstance(next_close,bool) or not math.isfinite(float(next_close)) or float(next_close)<=0
                or not math.isfinite(move) or isinstance(label["forwardMidpointBps"],bool)):
            raise ValueError("invalid label close or movement")
        # SOURCE: exactly the producer's retained-close formula. Python JSON
        # round trips preserve its float; do not fit a tolerance to bad labels.
        if move != (float(next_close)/float(prediction["close"])-1)*10_000 or label["up"] != (float(next_close)>float(prediction["close"])):
            raise ValueError("label direction/movement conflicts with original close")
        moves.append(move)
        # SOURCE: 0.5 is the neutral binary split, not proof of calibration.
        if probability > 0.5:
            directional_moves.append(move)
        elif probability < 0.5:
            directional_moves.append(-move)
        else:
            directional_moves.append(0.0)
    # SOURCE: linearized sum of two published tier-one 25 bps taker fees.
    # This hurdle excludes received-asset compounding, spread and the unverified
    # actual account tier; it is not a net trading result.
    fee_only_roundtrip_bps = 2 * 0.0025 * 10_000
    return {
        "schema":"frozen_markov_shadow_score_v2", "orderAuthority":False,
        "winProbability":None, "brokerPnl":None, "asOf":as_of.isoformat() if as_of else None,
        "feeOnlyHurdleBps":fee_only_roundtrip_bps,
        "feeScenario":"published T1 linearized two-leg hurdle; actual account tier unverified",
        "modelId": model_id,
        "predictions": len(predictions),
        "scored": len(labels),
        "unlabeled": len(predictions) - len(labels),
        "leadSeconds": {"min": min(leads) if leads else None,
                        "median": statistics.median(leads) if leads else None,
                        "max": max(leads) if leads else None},
        "markovBrier": sum(squared) / len(squared) if squared else None,
        "frozenBaseRateBrier": sum(baseline_squared) / len(baseline_squared) if baseline_squared else None,
        "meanDirectionalBarCloseBps": sum(directional_moves) / len(directional_moves)
            if directional_moves else None,
        "positiveDirectionalBarCloseShare": sum(move > 0 for move in directional_moves)
            / len(directional_moves) if directional_moves else None,
        "directionalBarCloseMovesAboveFeeOnly": sum(
            move > fee_only_roundtrip_bps for move in directional_moves
        ),
        # SOURCE: this is a raw up-move count, not a predicted-direction trade result.
        "positiveBarCloseMovesAboveFeeOnly": sum(
            move > fee_only_roundtrip_bps for move in moves
        ),
        "legacyLabelField":"forwardMidpointBps retains provider bar-close movement, not a verified pure midpoint",
        "limitation": "Serially dependent shadow sample. Prediction lead times vary; labels use later retrieved native bar closes, potentially trades and quote midpoints, not bid/ask execution. Brier scores and a fee-only hurdle do not establish calibration or after-cost profitability.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("journal", type=Path)
    parser.add_argument("--output",type=Path,help="Save the frozen aggregate report, not raw events")
    args = parser.parse_args()
    content = args.model.read_bytes()
    model = json.loads(content)
    with args.journal.open("rb") as source:
        size = os.fstat(source.fileno()).st_size
        raw = source.read(size)  # SOURCE: freeze actual prefix before ongoing appends.
        if len(raw) != size:
            raise ValueError("journal prefix changed during read")
    events = [json.loads(line) for line in raw.splitlines(keepends=True) if line.endswith(b"\n")]
    result = score(model, hashlib.sha256(content).hexdigest(), events, as_of=datetime.now(timezone.utc))
    result.update({"journalInputBytes":size,"journalSha256":hashlib.sha256(raw).hexdigest(),
                   "partialFinalLineIgnored":bool(raw and not raw.endswith(b"\n")),
                   "scorerSha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "canonicalModelSha256":hashlib.sha256(json.dumps(model,sort_keys=True,separators=(",",":")).encode()).hexdigest()})
    if args.output:
        temporary=args.output.with_suffix(".tmp")
        with temporary.open("w",encoding="utf-8") as target:
            json.dump(result,target,separators=(",",":"),allow_nan=False)
            target.flush();os.fsync(target.fileno())
        os.chmod(temporary,0o640)  # SOURCE: existing private report permissions.
        os.replace(temporary,args.output)
    print(json.dumps(result, indent=2,allow_nan=False))
