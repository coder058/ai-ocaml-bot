"""Copy actual already-computed forward features; no TA library or calculation."""


def forward_reading(reading):
    """Keep actual observed features, without copying entire chart histories."""
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
        "divergences": suite.get("divergences", []),
        # SOURCE: existing Murphy law numbering, unchanged serialization.
        "primaryContext": next((law.get("evidence", {}).get("primaryContext") for law in suite.get("murphy", []) if law.get("law") == 1), None),
        "currentDerivativeContext": next((law.get("evidence", {}).get("currentDerivativeContext") for law in suite.get("murphy", []) if law.get("law") == 10), None),
        "orderAuthority": False, "winProbability": None,
    }
    return compact
