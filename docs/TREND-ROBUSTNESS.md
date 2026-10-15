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

## Results — run 15 October 2026, after the pre-registration commit `39e5df5`

The report is `research/reports/trend-robustness-20261015.json`. To reproduce:
`cd research && python trend_robustness.py`.

### Test 1: PASS (3 of 3 datasets meet A and B; worst net CAGR +5.1%)

| Dataset | Rule net CAGR | Sharpe | Max DD | Buy-and-hold CAGR | Sharpe | Max DD | A | B | C |
|---|---|---|---|---|---|---|---|---|---|
| MSFT 1986–2017 | +17.1% | 0.59 | −68% | +24.8% | 0.70 | −72% | ✓ | ✓ | ✗ |
| GOOG 2004–2013 | +11.8% | 0.53 | −31% | +27.7% | 0.83 | −65% | ✓ | ✓ | ✗ |
| WTI spot 1986–2019 | +5.1% | 0.21 | −62% | +1.9% | 0.17 | −82% | ✓ | ✓ | ✓ |

### Test 2: PASS (median lag cost 0.45 pp/yr ≤ 1.0)

| Dataset | Same-close CAGR | Next-session CAGR | Cost of lag |
|---|---|---|---|
| SPX | +7.80% | +7.32% | 0.48 pp |
| NASDAQ | +7.17% | +6.76% | 0.41 pp |
| MSFT | +17.10% | +17.57% | −0.47 pp |
| GOOG | +11.82% | +10.18% | 1.64 pp |

### What this changes

- The rule made money on all three unseen datasets and cut drawdowns every
  time. It is a crash-avoidance rule, not a return booster.
- On single stocks in long bull runs it trails buy-and-hold by a lot
  (C failed on MSFT and GOOG). Keep `TREND_SYMBOLS` to broad index ETFs
  (SPY, QQQ), where it matched or beat buy-and-hold in the holdout. Do not use
  it for stock picking.
- The live one-session delay costs about half a point a year. That is already
  priced in when judging paper results.

## Correction — same day, after code review

The first run measured buy-and-hold from bar 1, but measured the rule only from
the end of its 200-bar warm-up, so the two covered different periods. GOOG's
first ~200 sessions after its IPO were a large rally that the rule could not
yet trade. That inflated buy-and-hold. `trend_robustness.py` now measures both
from the rule's first held bar. The rule itself and the pass criteria are
unchanged. The corrected report is
`research/reports/trend-robustness-20261015-aligned.json`, and the original is
kept for the record.

| Dataset | Rule CAGR / Sharpe / DD | Buy-and-hold, same period | A | B | C |
|---|---|---|---|---|---|
| MSFT | +17.1% / 0.59 / −68% | +23.5% / 0.69 / −72% | ✓ | ✓ | ✓ |
| GOOG | +11.8% / 0.53 / −31% | +14.1% / 0.51 / −65% | ✓ | ✓ | ✓ |
| WTI | +5.1% / 0.21 / −62% | +3.6% / 0.20 / −82% | ✓ | ✓ | ✓ |

Execution lag, aligned: median cost 0.46 points per year (pass).

**The earlier conclusion was overstated.** With matched periods, the rule's
Sharpe was within 0.10 of buy-and-hold or better on all three datasets. It
earned less raw return on MSFT and GOOG, but with less risk on GOOG. The
guidance to keep it on index ETFs stands: that is where the selection and
holdout evidence lives.

The same warm-up mismatch affected only the **develop** fold of
`cost_aware_backtest.py`. Validate and holdout begin long after every rule is
warm, so the selection (which compared rules with cash) and the holdout
tables are unaffected.
