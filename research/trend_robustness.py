"""Pre-registered robustness tests for the selected monthly_trend_v1 rule.

The plan and pass criteria are in docs/TREND-ROBUSTNESS.md and were committed
before this script first ran. The rule is imported unchanged from
cost_aware_backtest.sma_trend_monthly; nothing here selects or tunes a rule.

Data: MSFT daily from `pmdarima`, GOOG daily from `backtesting`, WTI spot daily
from `arch` (install research/requirements-backtest.txt plus pmdarima).
Results are simulated and pre-tax; they are not live profitability.
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

import cost_aware_backtest as cab

# SOURCE: docs/TREND-ROBUSTNESS.md. WTI's 5 bps is an UNCALIBRATED proxy for a
# futures/ETF implementation; spot crude itself is not directly tradable.
FRESH_COST_BPS = {"MSFT_daily": 2.0, "GOOG_daily": 2.0, "WTI_spot_daily": 5.0}


def _ohlc(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[["Open", "High", "Low", "Close"]].astype(float)


def fresh_datasets() -> list[cab.Dataset]:
    from arch.data import wti
    from pmdarima.datasets import load_msft
    import backtesting.test as bt

    msft = load_msft()
    msft = _ohlc(msft.set_index(pd.to_datetime(msft["Date"])))
    goog = _ohlc(bt.GOOG)
    oil = wti.load()["DCOILWTICO"].dropna()
    oil = pd.DataFrame({"Open": oil, "High": oil, "Low": oil, "Close": oil})
    return [cab.Dataset(name, bars, cab._daily_rf(bars.index), 252.0, "equity_etf", "daily")
            for name, bars in (("MSFT_daily", msft), ("GOOG_daily", goog), ("WTI_spot_daily", oil))]


def lag_datasets() -> list[cab.Dataset]:
    daily = [ds for ds in cab.load_datasets() if ds.name in ("SPX_daily", "NASDAQ_daily")]
    return daily + [ds for ds in fresh_datasets() if ds.name in ("MSFT_daily", "GOOG_daily")]


def whole(ds: cab.Dataset, weights: pd.Series, cost: float, start=None) -> dict:
    begin = start if start is not None else ds.bars.index[0]
    return cab.evaluate(ds, weights, str(begin.date()), str(ds.bars.index[-1].date()), cost)


def first_held(weights: pd.Series) -> pd.Timestamp:
    """First bar on which the rule earns a return (after its warm-up)."""
    return weights.shift(1).first_valid_index()


def test_fresh() -> dict:
    rows = []
    for ds in fresh_datasets():
        cost = FRESH_COST_BPS[ds.name]
        weights = cab.sma_trend_monthly(ds.bars, ds.periods_per_year)
        start = first_held(weights)
        rule = whole(ds, weights, cost, start)
        # Bug fix (15 Oct, after the first run): buy-and-hold is now measured
        # over the same period as the rule, excluding the rule's warm-up.
        hold = whole(ds, cab.buy_and_hold(ds.bars, ds.periods_per_year), cost, start)
        a = rule["net_cagr"] > 0
        b = rule["max_drawdown"] > hold["max_drawdown"]
        c = rule["sharpe"] >= hold["sharpe"] - 0.10
        rows.append({"dataset": ds.name, "cost_bps_per_side": cost, "rule": rule, "buy_and_hold": hold,
                     "A_positive": a, "B_smaller_drawdown": b, "C_sharpe_within_0.10": c})
    passing = sum(r["A_positive"] and r["B_smaller_drawdown"] for r in rows)
    worst = min(r["rule"]["net_cagr"] for r in rows)
    return {"rows": rows, "datasets_meeting_A_and_B": passing, "worst_net_cagr": worst,
            "pass": passing >= 2 and worst >= -0.02}


def test_lag() -> dict:
    rows = []
    for ds in lag_datasets():
        weights = cab.sma_trend_monthly(ds.bars, ds.periods_per_year)
        # Both variants are measured from the delayed rule's first held bar.
        start = first_held(weights.shift(1))
        same = whole(ds, weights, 2.0, start)
        # One extra session: decided at the month-end close, held from the next close.
        late = whole(ds, weights.shift(1), 2.0, start)
        rows.append({"dataset": ds.name, "same_close_cagr": same["net_cagr"], "next_session_cagr": late["net_cagr"],
                     "reduction": same["net_cagr"] - late["net_cagr"]})
    median = float(pd.Series([r["reduction"] for r in rows]).median())
    return {"rows": rows, "median_reduction": median, "pass": median <= 0.01}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output")
    args = parser.parse_args()
    report = {"preRegistration": "docs/TREND-ROBUSTNESS.md", "fresh": test_fresh(), "lag": test_lag(),
              "limits": "Simulated, pre-tax; WTI spot is not directly tradable. Not live profitability."}
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, default=str)
            handle.write("\n")
    for r in report["fresh"]["rows"]:
        x, h = r["rule"], r["buy_and_hold"]
        print(f"{r['dataset']:15} rule {x['net_cagr']:+.2%} sh {x['sharpe']:.2f} dd {x['max_drawdown']:.0%} | "
              f"hold {h['net_cagr']:+.2%} sh {h['sharpe']:.2f} dd {h['max_drawdown']:.0%} | "
              f"A {r['A_positive']} B {r['B_smaller_drawdown']} C {r['C_sharpe_within_0.10']}")
    print("fresh pass:", report["fresh"]["pass"])
    for r in report["lag"]["rows"]:
        print(f"{r['dataset']:15} same {r['same_close_cagr']:+.2%} next {r['next_session_cagr']:+.2%} cost {r['reduction']:+.2%}")
    print("lag median reduction:", f"{report['lag']['median_reduction']:+.2%}", "pass:", report["lag"]["pass"])


if __name__ == "__main__":
    main()
