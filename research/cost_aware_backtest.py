"""Offline cost-aware strategy screen with a frozen develop/validate/holdout split.

Why this exists: every policy in docs/POLICY-ATTEMPTS.md traded 1s-5m horizons
whose gross moves (about 0.1-5 bps) cannot clear Alpaca's published 25 bps
per-side crypto taker fee. This screen asks the missing question first: at
which horizon and venue does a simple rule's gross move exceed its round-trip
cost? It needs no network, credentials or broker and has no order authority.

Data come from datasets bundled inside two PyPI packages so the run is
reproducible in a sandbox: `arch` (S&P 500 / NASDAQ daily 1999-2018, Ken
French monthly US market and risk-free 1926-2018) and `backtesting`
(BTC/USD monthly 2012-2024, EUR/USD hourly 2017-2018, GOOG daily 2004-2013).
Install with `pip install arch backtesting pandas`. Historical index data are
adjusted closes as retrieved by those packages, not point-in-time records.

Causality: a position decided from the close of bar t earns bar t+1's return.
Costs are charged on every change in position weight. Cash earns the Ken French
risk-free rate where available and zero otherwise (conservative for the rules).

Results are simulated and pre-tax. They do not establish live profitability.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

# SOURCE: per-side cost assumptions. Crypto: published Alpaca tier-1 taker fee
# (https://docs.alpaca.markets/us/docs/crypto-fees) plus a 2 bps half-spread
# (repo audits measured a ~2.6 bps median full BTC spread). Equity ETF: Alpaca
# lists $0 commission; 2 bps covers half-spread plus slippage on SPY/QQQ-class
# ETFs (UNCALIBRATED GUESS, deliberately pessimistic for liquid ETFs). FX: 1 bp
# per side is an UNCALIBRATED GUESS for a retail EUR/USD spread.
COST_BPS_PER_SIDE = {"alpaca_crypto_taker": 27.0, "equity_etf": 2.0, "fx_retail": 1.0}

# Frozen before any validation/holdout result was viewed. Changing these after
# seeing results invalidates the holdout; record a new attempt instead.
SPLITS = {
    "daily": (("1999-01-01", "2008-12-31"), ("2009-01-01", "2013-12-31"), ("2014-01-01", "2018-12-31")),
    "us_market_monthly": (("1927-01-01", "1969-12-31"), ("1970-01-01", "1999-12-31"), ("2000-01-01", "2018-12-31")),
    "btc_monthly": (("2012-01-01", "2017-12-31"), ("2018-01-01", "2020-12-31"), ("2021-01-01", "2024-12-31")),
    "fx_hourly": (("2017-04-01", "2017-09-30"), ("2017-10-01", "2017-12-31"), ("2018-01-01", "2018-03-01")),
}
FOLDS = ("develop", "validate", "holdout")


@dataclass(frozen=True)
class Dataset:
    name: str
    bars: pd.DataFrame  # Open/High/Low/Close indexed by timestamp
    rf: pd.Series  # per-bar cash return aligned to bars
    periods_per_year: float
    venue: str
    split: str


def _french() -> pd.DataFrame:
    from arch.data import frenchdata

    raw = frenchdata.load()
    # The packaged index stores YYYYMM as an integer nanosecond offset.
    stamps = [str(int(ts.value)) for ts in raw.index]
    index = pd.to_datetime(stamps, format="%Y%m") + pd.offsets.MonthEnd(0)
    return pd.DataFrame(raw.values / 100.0, index=index, columns=raw.columns)


def _daily_rf(index: pd.DatetimeIndex) -> pd.Series:
    monthly = _french()["RF"]
    by_month = monthly.copy()
    by_month.index = by_month.index.to_period("M")
    periods = index.to_period("M")
    rate = pd.Series(periods.map(lambda p: by_month.get(p, 0.0)), index=index, dtype=float)
    # Spread each month's rate evenly over that month's trading bars.
    counts = pd.Series(1, index=index).groupby(periods).transform("count")
    return rate / counts


def load_datasets() -> list[Dataset]:
    from arch.data import nasdaq, sp500
    import backtesting.test as bt

    out: list[Dataset] = []
    for name, module in (("SPX_daily", sp500), ("NASDAQ_daily", nasdaq)):
        frame = module.load()
        ratio = frame["Adj Close"] / frame["Close"]
        bars = pd.DataFrame({c: frame[c] * ratio for c in ("Open", "High", "Low", "Close")})
        out.append(Dataset(name, bars, _daily_rf(bars.index), 252.0, "equity_etf", "daily"))
    french = _french()
    total = (french["Mkt-RF"] + french["RF"]).loc["1926-07-01":]
    close = (1 + total).cumprod()
    # Monthly data has no intrabar OHLC; candle rules are skipped for it.
    bars = pd.DataFrame({"Open": close.shift(1), "High": np.nan, "Low": np.nan, "Close": close})
    out.append(Dataset("US_market_monthly", bars, french["RF"].reindex(bars.index).fillna(0.0), 12.0, "equity_etf", "us_market_monthly"))
    btc = bt.BTCUSD[["Open", "High", "Low", "Close"]].copy()
    out.append(Dataset("BTC_monthly", btc, pd.Series(0.0, index=btc.index), 12.0, "alpaca_crypto_taker", "btc_monthly"))
    fx = bt.EURUSD[["Open", "High", "Low", "Close"]].copy()
    out.append(Dataset("EURUSD_hourly", fx, pd.Series(0.0, index=fx.index), 24 * 260.0, "fx_retail", "fx_hourly"))
    return out


# ---- signals: each returns target weight in [0, 1] decided at bar close ----

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def bot_confluence(bars: pd.DataFrame, _: float) -> pd.Series:
    """Port of trend_candle_confluence_v1: enter long on a rising EMA20/50
    trend plus a bullish engulfing or hammer candle; exit when the close falls
    below the entry candle low or the trend turns falling."""
    o, h, l, c = (bars[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    if np.isnan(h).all():
        return pd.Series(np.nan, index=bars.index)
    fast, slow = ema(bars["Close"], 20).to_numpy(), ema(bars["Close"], 50).to_numpy()
    body = np.abs(c - o)
    rng = np.maximum(h - l, 1e-12)
    lower = np.minimum(o, c) - l
    upper = h - np.maximum(o, c)
    hammer = (lower >= 2 * body) & (upper <= body) & (body / rng >= 0.05)
    prev_o, prev_c = np.roll(o, 1), np.roll(c, 1)
    engulf = (prev_c < prev_o) & (c > o) & (o <= prev_c) & (c >= prev_o)
    engulf[0] = False
    weight = np.zeros(len(c))
    holding, stop = False, 0.0
    for i in range(len(c)):
        if np.isnan(slow[i]):
            continue
        rising = fast[i] > slow[i]
        if holding and (c[i] < stop or not rising):
            holding = False
        elif not holding and rising and (engulf[i] or hammer[i]):
            holding, stop = True, l[i]
        weight[i] = 1.0 if holding else 0.0
    return pd.Series(weight, index=bars.index)


def sma_trend(bars: pd.DataFrame, periods_per_year: float) -> pd.Series:
    """Hold when close is above its 200-bar average (10 bars on monthly data,
    the same ~10-month window). Fixed from published practice, not fitted."""
    n = 10 if periods_per_year <= 12 else 200
    avg = bars["Close"].rolling(n, min_periods=n).mean()
    return (bars["Close"] > avg).astype(float).where(avg.notna())


def tsmom_12m(bars: pd.DataFrame, periods_per_year: float) -> pd.Series:
    """Hold when the trailing ~12-month return is positive."""
    n = int(round(periods_per_year))
    past = bars["Close"].pct_change(n)
    return (past > 0).astype(float).where(past.notna())


def vol_target_trend(bars: pd.DataFrame, periods_per_year: float) -> pd.Series:
    """sma_trend scaled to a 15% annualised volatility target, capped at 1x
    (no leverage). Weight changes below 10 percentage points are not traded."""
    trend = sma_trend(bars, periods_per_year)
    window = 3 if periods_per_year <= 12 else 20
    realised = bars["Close"].pct_change().rolling(window).std() * math.sqrt(periods_per_year)
    raw = (trend * (0.15 / realised).clip(upper=1.0)).where(trend.notna() & realised.notna())
    out, last = [], np.nan
    for value in raw.to_numpy():
        if np.isnan(value):
            out.append(np.nan)
            continue
        if np.isnan(last) or abs(value - last) >= 0.10 or value == 0.0:
            last = value
        out.append(last)
    return pd.Series(out, index=bars.index)


def _month_end_only(signal: pd.Series, bars: pd.DataFrame, periods_per_year: float) -> pd.Series:
    """Attempt 2: on intramonth data, act only on the last bar of each calendar
    month and hold that decision until the next month end. Reduces whipsaw
    seen in develop attempt 1 (about nine daily round trips per year)."""
    if periods_per_year <= 12:
        return signal
    months = bars.index.to_period("M")
    last = pd.Series(months, index=bars.index) != pd.Series(months, index=bars.index).shift(-1)
    return signal.where(last).ffill().where(signal.notna())


def sma_trend_monthly(bars: pd.DataFrame, periods_per_year: float) -> pd.Series:
    return _month_end_only(sma_trend(bars, periods_per_year), bars, periods_per_year)


def trend_ensemble_monthly(bars: pd.DataFrame, periods_per_year: float) -> pd.Series:
    """Attempt 2: equal-weight average of sma_trend and tsmom_12m (0, 0.5 or 1),
    decided at month end. Diversifies the single-lookback choice; no fitting."""
    both = (sma_trend(bars, periods_per_year) + tsmom_12m(bars, periods_per_year)) / 2
    return _month_end_only(both, bars, periods_per_year)


def buy_and_hold(bars: pd.DataFrame, _: float) -> pd.Series:
    return pd.Series(1.0, index=bars.index)


STRATEGIES: dict[str, Callable[[pd.DataFrame, float], pd.Series]] = {
    "buy_and_hold": buy_and_hold,
    "bot_confluence": bot_confluence,
    "sma_trend": sma_trend,
    "tsmom_12m": tsmom_12m,
    "vol_target_trend": vol_target_trend,
    # Attempt 2 additions, registered after develop-only attempt 1.
    "sma_trend_monthly": sma_trend_monthly,
    "trend_ensemble_monthly": trend_ensemble_monthly,
}


def evaluate(ds: Dataset, weights: pd.Series, start: str, end: str, cost_bps: float) -> dict | None:
    ret = ds.bars["Close"].pct_change()
    held = weights.shift(1)  # decided at previous close, earns this bar
    window = (ret.index >= start) & (ret.index <= end) & held.notna() & ret.notna()
    if window.sum() < 3:
        return None
    w, r, rf = held[window].to_numpy(), ret[window].to_numpy(), ds.rf[window].to_numpy()
    # Entering the window from cash pays the entry cost once.
    turnover = np.abs(np.diff(np.concatenate(([0.0], w))))
    cost = turnover * cost_bps / 10_000.0
    gross = w * r + (1 - w) * rf
    net = gross - cost
    years = len(net) / ds.periods_per_year
    equity = np.cumprod(1 + net)
    peak = np.maximum.accumulate(np.concatenate(([1.0], equity)))[1:]
    excess = net - rf
    sd = excess.std(ddof=1)
    cash_cagr = float(np.prod(1 + rf) ** (1 / years) - 1)
    cagr = float(equity[-1] ** (1 / years) - 1)
    return {
        "bars": int(len(net)),
        "years": round(years, 2),
        "net_cagr": cagr,
        "gross_cagr": float(np.prod(1 + gross) ** (1 / years) - 1),
        "cash_cagr": cash_cagr,
        "excess_cagr_vs_cash": cagr - cash_cagr,
        "sharpe": float(excess.mean() / sd * math.sqrt(ds.periods_per_year)) if sd > 0 else 0.0,
        "max_drawdown": float((equity / peak - 1).min()),
        "turnover_per_year": float(turnover.sum() / years),
        "cost_drag_per_year": float(cost.sum() / years),
        "time_invested": float(w.mean()),
    }


def run(folds: tuple[str, ...]) -> list[dict]:
    rows = []
    for ds in load_datasets():
        cost = COST_BPS_PER_SIDE[ds.venue]
        for name, fn in STRATEGIES.items():
            weights = fn(ds.bars, ds.periods_per_year)
            for fold, (start, end) in zip(FOLDS, SPLITS[ds.split]):
                if fold not in folds:
                    continue
                result = evaluate(ds, weights, start, end, cost)
                if result is not None:
                    rows.append({"dataset": ds.name, "venue": ds.venue, "cost_bps_per_side": cost,
                                 "strategy": name, "fold": fold, **result})
    return rows


def horizon_hurdle(rows: list[dict]) -> list[dict]:
    """Typical absolute bar move versus round-trip cost per dataset."""
    out = []
    for ds in load_datasets():
        move = ds.bars["Close"].pct_change().abs().median() * 10_000
        cost = 2 * COST_BPS_PER_SIDE[ds.venue]
        out.append({"dataset": ds.name, "median_abs_bar_move_bps": round(float(move), 2),
                    "round_trip_cost_bps": cost, "move_to_cost": round(float(move / cost), 2)})
    return out


def crypto_cost_sensitivity(folds: tuple[str, ...]) -> list[dict]:
    """Apply the bot's own Alpaca crypto taker cost to every dataset, so the
    horizon effect is visible independently of the instrument."""
    rows = []
    cost = COST_BPS_PER_SIDE["alpaca_crypto_taker"]
    for ds in load_datasets():
        for name in ("bot_confluence", "sma_trend_monthly"):
            weights = STRATEGIES[name](ds.bars, ds.periods_per_year)
            for fold, (start, end) in zip(FOLDS, SPLITS[ds.split]):
                if fold in folds:
                    result = evaluate(ds, weights, start, end, cost)
                    if result is not None:
                        rows.append({"dataset": ds.name, "strategy": name, "fold": fold, "cost_bps_per_side": cost, **result})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folds", default="develop,validate",
                        help="comma list from develop,validate,holdout; open holdout only once")
    parser.add_argument("--output")
    args = parser.parse_args()
    folds = tuple(f for f in args.folds.split(",") if f)
    if not set(folds) <= set(FOLDS):
        parser.error(f"folds must be within {FOLDS}")
    report = {"costBpsPerSide": COST_BPS_PER_SIDE, "splits": SPLITS, "folds": folds,
              "hurdle": horizon_hurdle([]), "results": run(folds),
              "cryptoCostSensitivity": crypto_cost_sensitivity(folds),
              "limits": "Simulated, pre-tax, adjusted index data; no live or paper fills. Not evidence of live profitability."}
    text = json.dumps(report, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    frame = pd.DataFrame(report["results"])
    pd.set_option("display.width", 200)
    print(pd.DataFrame(report["hurdle"]).to_string(index=False))
    cols = ["dataset", "strategy", "fold", "net_cagr", "cash_cagr", "sharpe", "max_drawdown", "turnover_per_year", "cost_drag_per_year", "time_invested"]
    print(frame[cols].round(4).to_string(index=False))
    print("\nSame rules at the bot's Alpaca crypto taker cost:")
    print(pd.DataFrame(report["cryptoCostSensitivity"])[cols].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
