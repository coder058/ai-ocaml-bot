# `monthly_trend_v1` robustness — pre-registration (written before running)

This plan was committed before any result below existed. The rule is the one
selected in [the profitability review](PROFITABILITY-REVIEW.md) and is **not
changed** here. These tests can only confirm or weaken that selection; they
cannot be used to pick a different rule.

## Test 1 — data the rule has never seen

| Dataset | Source (bundled in a PyPI package) | Period | Cost per side |
|---|---|---|---|
| MSFT daily | `pmdarima` `load_msft` (adjusted OHLC) | 1986-03 to 2017-11 | 2 bps |
| GOOG daily | `backtesting.test.GOOG` | 2004-08 to 2013-03 | 2 bps |
| WTI spot daily | `arch.data.wti` (FRED DCOILWTICO) | 1986-01 to 2019-01 | 5 bps (UNCALIBRATED proxy) |

- WTI spot cannot be bought directly. Futures roll and ETF contango are not
  modelled, so WTI tests the signal, not a tradable product.
- The Ken French/`arch` crude monthly series is excluded. It is a mid-month
  **average**, and averaging creates artificial trend persistence.
- Each dataset is tested over its whole sample, because the rule is fixed.

**Per-dataset criteria:**

- **A:** net CAGR > 0.
- **B:** max drawdown is smaller than buy-and-hold's.
- **C:** Sharpe ≥ buy-and-hold Sharpe − 0.10.

**Overall pass:** at least 2 of 3 datasets meet both A and B, and no dataset
has a net CAGR below −2%/yr.

## Test 2 — execution lag

The live scheduler decides from the month-end close but trades in the next
session, at about 15:05 UTC. The backtest earned the next bar's return from the
decision close itself. Re-run with the position change delayed by one session
on SPX, NASDAQ, MSFT and GOOG daily, over their full samples.

**Criterion:** the median CAGR reduction from the lag is ≤ 1.0 percentage
point per year.

## What a failure means

If either test fails, the rule stays in observe mode and the failure is
reported. The rule is not tuned on these datasets.
