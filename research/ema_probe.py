"""Point-in-time exploratory EMA probe on Alpaca US BTC daily midpoint bars.

This is a deliberately frozen single-rule benchmark, not a validated strategy.
Bars include quote midpoints, so next-open execution is only a proxy.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

# GUESS: # UNCALIBRATED GUESS — Pattern Forge displays EMA 20 and 50. Using
# their crossover to authorize a trade has no measured edge yet.
FAST = 20
SLOW = 50
# SOURCE: https://docs.alpaca.markets/us/docs/crypto-fees — tier-one taker fee.
TAKER_FEE = 0.0025
# GUESS: # UNCALIBRATED GUESS — 4.208061 bps is the observed p90 quote spread
# in a 42-quote stream sample, far too small to establish historical spread.
SPREAD_BPS_PROXY = 4.208061
# SOURCE: one basis point is 1/10,000 by definition.
BPS = 10_000


def ema(previous: float | None, value: float, span: int) -> float:
    # SOURCE: standard exponential moving average recurrence.
    alpha = 2 / (span + 1)
    return value if previous is None else alpha * value + (1 - alpha) * previous


def max_drawdown(equity: list[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1)
    return worst


def probe(bars: list[dict], holdout_start: date, fee: float, spread_bps: float) -> dict:
    cash = 1.0  # SOURCE: normalized starting capital for a relative benchmark.
    shares = 0.0
    baseline_shares = 0.0
    fast = slow = None
    previous_signal = None
    observations: list[tuple[date, float, float]] = []
    trades: list[tuple[date, str]] = []
    for index, bar in enumerate(bars):
        day = date.fromisoformat(bar["t"][:10])
        opening, closing = float(bar["o"]), float(bar["c"])
        if not (0 < opening and 0 < closing):
            raise ValueError(f"invalid daily bar price at {day}")
        if index >= SLOW:
            if baseline_shares == 0:
                baseline_shares = 1.0 / (opening * (1 + spread_bps / (2 * BPS))) * (1 - fee)
            if previous_signal and shares == 0:
                shares = cash / (opening * (1 + spread_bps / (2 * BPS))) * (1 - fee)
                cash = 0.0
                trades.append((day, "buy"))
            elif not previous_signal and shares > 0:
                cash = shares * opening * (1 - spread_bps / (2 * BPS)) * (1 - fee)
                shares = 0.0
                trades.append((day, "sell"))
            # GUESS: # UNCALIBRATED GUESS — terminal mark assumes crossing the
            # measured short-sample spread proxy and paying the cited taker fee.
            liquidation = closing * (1 - spread_bps / (2 * BPS)) * (1 - fee)
            observations.append((day, cash + shares * liquidation,
                                 baseline_shares * liquidation))
        fast = ema(fast, closing, FAST)
        slow = ema(slow, closing, SLOW)
        previous_signal = fast > slow
    if not observations:
        raise ValueError("not enough bars for the frozen EMA rule")
    holdout = [row for row in observations if row[0] >= holdout_start]
    prior = next((row for row in reversed(observations) if row[0] < holdout_start), None)
    if not holdout or prior is None:
        raise ValueError("holdout must have bars on both sides")
    def window(rows: list[tuple[date, float, float]], start_rule: float, start_baseline: float) -> dict:
        return {
            "first": rows[0][0].isoformat(),
            "last": rows[-1][0].isoformat(),
            "sessions": len(rows),
            "rule_return_pct": (rows[-1][1] / start_rule - 1) * 100,
            "buy_hold_return_pct": (rows[-1][2] / start_baseline - 1) * 100,
            "rule_max_drawdown_pct": max_drawdown([row[1] for row in rows]) * 100,
            "rule_trades": sum(rows[0][0] <= trade_day <= rows[-1][0]
                               for trade_day, _ in trades),
        }
    gaps = [str(date.fromisoformat(bars[i]["t"][:10])) for i in range(1, len(bars))
            if date.fromisoformat(bars[i]["t"][:10]) - date.fromisoformat(bars[i-1]["t"][:10]) != timedelta(days=1)]
    annual = {}
    for year in sorted({row[0].year for row in observations}):
        year_rows = [row for row in observations if row[0].year == year]
        prior_year = next((row for row in reversed(observations) if row[0] < year_rows[0][0]), None)
        annual[str(year)] = window(year_rows, prior_year[1] if prior_year else 1.0,
                                   prior_year[2] if prior_year else 1.0)
    return {
        "bars": len(bars),
        "daily_gaps": gaps,
        "rule": "long BTC when prior close EMA20 > EMA50; otherwise flat; next daily midpoint open proxy",
        "fee_each_side": fee,
        "spread_bps_roundtrip_proxy": spread_bps,
        "full": window(observations, 1.0, 1.0),
        "holdout": window(holdout, prior[1], prior[2]),
        "calendar_years": annual,
        "all_trades": len(trades),
        "trade_log": [{"date": day.isoformat(), "side": side} for day, side in trades],
        "scope": "Exploratory full-capital normalized midpoint-bar probe with an uncalibrated feature and cost proxy. It does not implement the paper bot's $30 order cap. No real fill, latency, fee-tier, funding or live profitability inference.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bars", type=Path)
    parser.add_argument("--holdout-start", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    bars = json.loads(args.bars.read_text(encoding="utf-8"))["bars"]
    print(json.dumps(probe(bars, args.holdout_start, TAKER_FEE, SPREAD_BPS_PROXY), indent=2))


if __name__ == "__main__":
    main()
