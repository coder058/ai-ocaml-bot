"""Descriptive Murphy checklist + the complete installed TA-Lib candle catalog.

OCaml remains the existing signal engine. This read-only extension uses TA-Lib's
C implementation through Python; it is not an OCaml port or an order policy.
Sources: https://ta-lib.org/functions/ and
https://stockcharts.com/ten-laws/murphys-ten-laws.pdf
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import talib
from talib import abstract

# SOURCE: these are TA-Lib's published descriptive indicator groups, excluding
# arithmetic transforms and functions that require a second independent asset.
GROUPS = ("Momentum Indicators", "Overlap Studies", "Volatility Indicators",
          "Volume Indicators", "Cycle Indicators", "Statistic Functions", "Price Transform")
FUNCTIONS = {name: abstract.Function(name) for group in GROUPS
             for name in talib.get_function_groups()[group]}
CANDLES = {name: abstract.Function(name) for name in
           talib.get_function_groups()["Pattern Recognition"]}
# GUESS: # UNCALIBRATED GUESS — retain 120 actual candles per chart for readable
# previews and expansion. The analytics use the full contiguous cache, not this slice.
DISPLAY_BARS = 120
# GUESS: # UNCALIBRATED GUESS — two right/left bars confirm a swing. Chart-shape
# geometry below is exploratory, not a validated Murphy trading strategy.
PIVOT_RADIUS = 2
# GUESS: # UNCALIBRATED GUESS — five percent of the observed chart range defines
# near-equal swing levels; calibrate with labeled formations before trading.
LEVEL_TOLERANCE = 0.05
# SOURCE: conventional Fibonacci retracement ratios plus the half-retracement
# used in Murphy's discussion. Levels are geometry, not predicted reversal prices.
RETRACEMENTS = (0.382, 0.5, 0.618)
# SOURCE: existing shared OCaml Pattern Forge EMA display windows.
EMA_WINDOWS = (20, 50)
LAW_NAMES = ("Map the trends", "Spot the trend", "Support and resistance",
             "Retracements", "Trendlines", "Moving averages", "Oscillators",
             "MACD warnings", "ADX trend strength", "Volume confirmation")


def scalar(value):
    n = float(value)
    return n if math.isfinite(n) else None


def catalog():
    return [{"code": name, "name": function.info["display_name"],
             "lookback": function.lookback, "parameters": dict(function.parameters)}
            for name, function in CANDLES.items()]


def required_seed_bars():
    # SOURCE: enough observations for the largest installed default TA-Lib
    # lookback, including candlestick averaging. No invented warmup count.
    return max(f.lookback for f in (*FUNCTIONS.values(), *CANDLES.values())) + 1


def timestamp(row):
    value = datetime.fromisoformat(row["t"].replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Candle timestamp has no timezone")
    return int(value.timestamp())


def contiguous(rows, minutes, as_of, expected_starts=()):
    """Reject invalid/open rows; restart after missing bars, respecting sessions."""
    boundary = int(datetime.fromisoformat(as_of.replace("Z", "+00:00")).timestamp())
    # SOURCE: expected equity starts come from the actual broker session calendar.
    successors = dict(zip(expected_starts, expected_starts[1:]))
    tail = []
    previous = None
    for row in rows:
        current = timestamp(row)
        values = [float(row[k]) for k in ("o", "h", "l", "c", "v")]
        op, hi, lo, close, volume = values
        # SOURCE: seconds per minute; OHLC invariants and closed-candle boundary.
        if (current % (minutes * 60) or current + minutes * 60 > boundary or
                not all(math.isfinite(v) for v in values) or
                not 0 < lo <= min(op, close) <= max(op, close) <= hi or volume < 0):
            raise ValueError("Invalid, unaligned or unfinished candle")
        if previous is not None:
            if current <= previous:
                raise ValueError("Candle timestamps are not increasing")
            if current != previous + minutes * 60 and successors.get(previous // 60) != current // 60:
                tail = []
        tail.append({"t": row["t"], **dict(zip(("o", "h", "l", "c", "v"), values))})
        previous = current
    return tail


def pivots(rows):
    result = []
    for i in range(PIVOT_RADIUS, len(rows) - PIVOT_RADIUS):
        neighbors = rows[i-PIVOT_RADIUS:i] + rows[i+1:i+PIVOT_RADIUS+1]
        for kind, key, compare in (("high", "h", max), ("low", "l", min)):
            level = rows[i][key]
            if (level > compare(r[key] for r in neighbors) if kind == "high" else
                    level < compare(r[key] for r in neighbors)):
                result.append({"kind": kind, "index": i, "time": rows[i]["t"],
                               "confirmedAt": rows[i+PIVOT_RADIUS]["t"], "price": level})
    return result


def geometry(rows):
    points = pivots(rows)
    close = rows[-1]["c"]
    highs = [p for p in points if p["kind"] == "high"]
    lows = [p for p in points if p["kind"] == "low"]
    support = max((p["price"] for p in lows if p["price"] <= close), default=None)
    resistance = min((p["price"] for p in highs if p["price"] >= close), default=None)
    lines = []
    for name, side in (("support", lows), ("resistance", highs)):
        if len(side) >= 2:
            a, b = side[-2:]
            slope = (b["price"] - a["price"]) / (b["index"] - a["index"])
            projected = b["price"] + slope * (len(rows) - 1 - b["index"])
            lines.append({"name": name, "from": a["time"], "fromPrice": a["price"],
                          "to": rows[-1]["t"], "toPrice": projected,
                          "anchors": [a, b], "slopePerBar": slope})
    alternate = []
    for point in points:
        if alternate and alternate[-1]["kind"] == point["kind"]:
            prior = alternate[-1]
            if (point["price"] > prior["price"] if point["kind"] == "high" else
                    point["price"] < prior["price"]):
                alternate[-1] = point
        else:
            alternate.append(point)
    retracements = []
    if len(alternate) >= 2:
        a, b = alternate[-2:]
        retracements = [{"ratio": ratio, "price": b["price"] - ratio * (b["price"] - a["price"]),
                         "from": a["time"], "to": b["time"]} for ratio in RETRACEMENTS]
    tolerance = (max(r["h"] for r in rows) - min(r["l"] for r in rows)) * LEVEL_TOLERANCE
    shapes = []
    # SOURCE: formations require confirmed swings and a closing neckline break.
    # GUESS: # UNCALIBRATED GUESS — matching geometry is the heuristic above;
    # it does not infer a winning probability, price target or order authority.
    if len(alternate) >= 3:
        a, b, c = alternate[-3:]
        if abs(a["price"] - c["price"]) <= tolerance:
            if a["kind"] == c["kind"] == "high" and close < b["price"]:
                shapes.append("double_top_neckline_break")
            if a["kind"] == c["kind"] == "low" and close > b["price"]:
                shapes.append("double_bottom_neckline_break")
    if len(alternate) >= 5:
        a, b, c, d, e = alternate[-5:]
        if abs(a["price"] - e["price"]) <= tolerance:
            if a["kind"] == c["kind"] == e["kind"] == "high" and c["price"] > max(a["price"], e["price"]) and close < min(b["price"], d["price"]):
                shapes.append("head_shoulders_neckline_break")
            if a["kind"] == c["kind"] == e["kind"] == "low" and c["price"] < min(a["price"], e["price"]) and close > max(b["price"], d["price"]):
                shapes.append("inverse_head_shoulders_neckline_break")
    if len(lines) == 2:
        lower, upper = lines
        if lower["toPrice"] < upper["toPrice"]:
            down, up = lower["slopePerBar"], upper["slopePerBar"]
            if down > 0 and up < 0:
                shapes.append("converging_triangle_geometry")
            if down > up > 0:
                shapes.append("rising_wedge_geometry")
            if up < down < 0:
                shapes.append("falling_wedge_geometry")
    return {"support": support, "resistance": resistance, "pivots": points,
            "trendlines": lines, "retracements": retracements, "chartShapes": shapes,
            "calibrated": False, "pivotRadius": PIVOT_RADIUS, "levelTolerance": LEVEL_TOLERANCE}


def analyze_frame(rows, minutes, as_of, expected_starts=()):
    tail = contiguous(rows, minutes, as_of, expected_starts)
    if not tail:
        return {"status": "no_data", "reason": "No actual closed candles", "bars": [],
                "patterns": {}, "indicators": {}, "patternEvents": [], "orderAuthority": False}
    inputs = {name: np.asarray([r[key] for r in tail], dtype=np.float64)
              for name, key in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"), ("volume", "v"))}
    patterns, events, indicators = {}, [], {}
    # SOURCE: contiguous() validates every historical row. Keep actual chart
    # history across gaps, but never bridge those gaps for indicator warmup.
    displayed = [{"t": row["t"], **{k: float(row[k]) for k in ("o", "h", "l", "c", "v")}}
                 for row in rows[-DISPLAY_BARS:]]
    chart_start = max(0, len(tail) - DISPLAY_BARS)
    for name, function in CANDLES.items():
        needed = function.lookback + 1
        if len(tail) < needed:
            patterns[name] = {"status": "warming", "value": None, "requiredBars": needed}
            continue
        values = function(inputs)
        patterns[name] = {"status": "ready", "value": int(values[-1]), "requiredBars": needed}
        for i in range(max(chart_start, function.lookback), len(tail)):
            if values[i]:
                events.append({"time": tail[i]["t"], "code": name,
                               "name": function.info["display_name"], "value": int(values[i])})
    for name, function in FUNCTIONS.items():
        needed = function.lookback + 1
        if len(tail) < needed:
            indicators[name] = {"status": "warming", "requiredBars": needed, "values": {}}
            continue
        required = [v for values in function.input_names.values()
                    for v in (values if isinstance(values, list) else [values])]
        if any(value not in inputs for value in required):
            indicators[name] = {"status": "unavailable", "reason": "Requires an independent input series", "values": {}}
            continue
        values = function(inputs)
        arrays = values if isinstance(values, (list, tuple)) else [values]
        latest = {output: scalar(array[-1]) for output, array in zip(function.output_names, arrays, strict=True)}
        indicators[name] = {"status": "ready" if all(v is not None for v in latest.values()) else "unavailable",
                            "values": latest, "parameters": dict(function.parameters)}
    overlays = {}
    for period in EMA_WINDOWS:
        values = talib.EMA(inputs["close"], timeperiod=period)
        by_time = {row["t"]: scalar(value) for row, value in zip(tail, values, strict=True)}
        overlays[f"EMA{period}"] = [by_time.get(row["t"]) for row in displayed]
    return {"status": "ready", "bars": displayed, "contiguousBars": len(tail),
            "patterns": patterns, "patternEvents": events, "indicators": indicators,
            "geometry": geometry(tail), "overlays": overlays,
            "patternCount": len(CANDLES), "indicatorCount": len(FUNCTIONS),
            "source": f"TA-Lib {talib.__version__} C via Python", "orderAuthority": False,
            "winProbability": None}


def enrich(result, requested, frame_minutes):
    for market, original in zip(result["markets"], requested, strict=True):
        for frame, minutes in frame_minutes.items():
            reading = market["frames"][frame]
            try:
                extension = analyze_frame(original["frames"][frame], minutes, result["asOf"],
                    original.get("expectedStarts", {}).get(frame, ()))
            except (ValueError, KeyError, TypeError) as error:
                extension = {"status": "invalid", "reason": str(error), "bars": [],
                             "patterns": {}, "indicators": {}, "patternEvents": [], "orderAuthority": False}
            reading["technicalSuite"] = extension
        for frame, reading in market["frames"].items():
            suite = reading["technicalSuite"]
            geometry_values = suite.get("geometry", {})
            indicators = suite.get("indicators", {})
            def values(name):
                return indicators.get(name, {}).get("values", {})
            def law(index, status, evidence):
                return {"law": index, "name": LAW_NAMES[index-1], "status": status, "evidence": evidence}
            aligned = {key: {"trend": r.get("trend"), "status": r.get("status"), "bar": r.get("lastBarStart")}
                       for key, r in market["frames"].items()}
            available = "descriptive" if suite.get("status") == "ready" else "unavailable"
            suite["murphy"] = [
                law(1, "partial", {"frames": aligned, "missing": "Monthly/weekly primary trend history"}),
                law(2, available, {"trend": reading.get("trend"), "structure": reading.get("structure")}),
                law(3, available, {"support": geometry_values.get("support"), "resistance": geometry_values.get("resistance")}),
                law(4, available, {"retracements": geometry_values.get("retracements", [])}),
                law(5, "heuristic" if available == "descriptive" else available, {"trendlines": geometry_values.get("trendlines", [])}),
                law(6, available, {"ema20": reading.get("ema20"), "ema50": reading.get("ema50")}),
                law(7, available, {"RSI": values("RSI"), "STOCH": values("STOCH"), "WILLR": values("WILLR"), "CCI": values("CCI")}),
                law(8, available, {"MACD": values("MACD"), "divergence": "Not a verified swing-divergence detector"}),
                law(9, available, {"ADX": values("ADX"), "PLUS_DI": values("PLUS_DI"), "MINUS_DI": values("MINUS_DI")}),
                law(10, "partial" if available == "descriptive" else available,
                    {"OBV": values("OBV"), "AD": values("AD"), "MFI": values("MFI"),
                     "volumeScope": market["venue"], "openInterest": None,
                     "missing": "Consolidated volume / open-interest confirmation"}),
            ]
    result["technicalCoverage"] = {
        "patternCatalog": catalog(), "patternCount": len(CANDLES),
        "indicatorCount": len(FUNCTIONS), "indicatorCatalog": [
            {"code": name, "name": f.info["display_name"], "group": f.info["group"],
             "lookback": f.lookback, "parameters": dict(f.parameters)} for name, f in FUNCTIONS.items()],
        "murphyLaws": list(LAW_NAMES), "source": f"TA-Lib {talib.__version__} C via Python + shared OCaml",
        "displayBars": DISPLAY_BARS, "seedBars": required_seed_bars(), "orderAuthority": False,
        "completeMurphyBook": False,
        "remaining": ["Weekly/monthly primary trends", "Verified momentum divergences",
            "Full reversal/continuation formation library", "Elliott wave, time-cycle interpretation",
            "Point-and-figure analysis", "Market breadth / intermarket confirmation",
            "Consolidated volume and open interest", "Strategy validation and probabilities"],
        "sources": ["https://ta-lib.org/functions/", "https://stockcharts.com/ten-laws/murphys-ten-laws.pdf"]}
    return result


def forward_reading(reading):
    """Keep actual first-observed features, without copying entire chart histories."""
    compact = {key: value for key, value in reading.items() if key != "technicalSuite"}
    suite = reading.get("technicalSuite", {})
    geometry_values = suite.get("geometry", {})
    compact["technicalEvidence"] = {
        "source": suite.get("source"), "status": suite.get("status"),
        "lastCandle": (suite.get("bars") or [None])[-1],
        "contiguousBars": suite.get("contiguousBars"),
        "patternValues": {name: row.get("value") for name, row in suite.get("patterns", {}).items()},
        "indicatorValues": {name: row.get("values") if row.get("status") == "ready" else None
                            for name, row in suite.get("indicators", {}).items()},
        "geometry": {key: geometry_values.get(key) for key in
                     ("support", "resistance", "retracements", "trendlines", "chartShapes")},
        "orderAuthority": False, "winProbability": None,
    }
    return compact
