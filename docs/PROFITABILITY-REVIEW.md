# Profitability review and fix — 8 October 2026

**Question:** why does the bot lose money, what is disconnected, missing or extra,
and can it be made profitable?

**Short answer:** it lost money because every strategy traded horizons where the
typical price move is far smaller than the cost of a round trip. The fix is to
change the horizon and the venue, not to tune more candle rules. A month-end
trend rule on liquid ETFs passed a frozen develop/validate/holdout test after
costs. It is now implemented in OCaml behind the existing paper router. It runs
in observe-only mode until the owner arms it.

Everything below is simulated or paper. Nothing here proves live profitability.

## 1. Why it was not profitable

The cause is arithmetic, not a software bug. Alpaca's published tier-1 crypto
taker fee is 25 bps per side, so a round trip costs 50 bps plus the spread.
The bot's own audits (see [POLICY-ATTEMPTS](POLICY-ATTEMPTS.md),
[FORWARD-QUOTE-AUDIT](FORWARD-QUOTE-AUDIT.md) and [MARKOV-SHADOW-SCORE](MARKOV-SHADOW-SCORE.md))
measured these gross moves for its signals:

| Strategy (horizon) | Measured gross move | Round-trip cost | Result |
|---|---|---|---|
| `quote_cross_30s_v1` (1s–30m) | median −2.0 to +0.5 bps | ≈50 bps | median −51 to −54 bps per order; none positive at 1s–5m |
| Markov 5m shadow | +0.42 bps mean, Brier ≈ base rate | ≈50 bps | no edge |
| EMA20/50 1m replay | −2.8% to −7.1% per day | ≈50 bps | lost more than buy-and-hold |
| Taker-flow 1m/5m/30m | ≈ −52 bps net mean | ≈50 bps | 0 winning trades |
| Book imbalance 1m/5m | −3 bps gross | ≈50 bps | 0 net-positive trades |
| Candle confluence (forward audit) | −2.7 to −5.2 bps | ≈50 bps | −52 to −55 bps after fees |

The signals needed edges about 100 times larger than anything measured. More
symbols, more frames, faster execution or better audit trails cannot fix that.
The 4 October snapshot showed about −$205 of provisional marked loss on
1,660 lab orders.

Contributing causes:

- **Wrong venue for short horizons.** The bot traded crypto, which charges 25 bps
  per side, while the stock path is commission-free. Stocks had no armed
  strategy; the stock scheduler stayed in observation.
- **Taker-only execution.** Every order was an IOC limit or market order that
  crossed the spread. There was no maker posting, so the bot always paid the
  spread plus the full taker fee.
- **No cost gate anywhere in the decision path.** Nothing compared an expected
  move with the cost before an order was sent (`grep fee lib/ bin/` finds none).
- **Signals with no demonstrated edge.** These were textbook candle shapes and
  EMA crosses. The Markov model's Brier score equalled the base rate. Probability
  tiers were defined but never calibrated.
- **Latency.** Quote-to-submit was about 1.3 s, using curl subprocesses. Even a
  real micro-edge at the 1-second horizon would be gone before the order arrived.
- **Effort went to provenance instead of edge.** About 59,000 words of docs
  against about 3,500 lines of OCaml. Each new policy got heavy audit machinery
  before anyone checked the basic move-versus-cost question.

## 2. What is disconnected

| Component | State |
|---|---|
| `fx/` OANDA request planning | No credentials, no order adapter. It plans requests but cannot execute. |
| Hyperliquid HIP-3 capture and context | Data only. No wallet or execution path. |
| Markov shadow, TA-Lib/Murphy analysis, forward audits | Descriptive only, with no order authority. |
| Stock scheduler (`stock_auto_main`) | Built and tested but never armed, and its candle policy has no edge. |
| `web/` Vercel ingest route | Disabled. Only the localhost monitor works. |
| Research scripts nothing references | `hot_stream_fixture`, `live_paper_reconcile`, `market_universe_audit`, `multi_symbol_capture_health`, `stream_bar_coverage`, `usd_crypto_coverage_scan` |
| All VPS services and timers | Stopped on 5 October ([SHUTDOWN](history/SHUTDOWN.md)). Development moved to Event Desk. |

## 3. What is missing

1. A cost or horizon check before choosing a strategy. **Added:**
   `research/cost_aware_backtest.py` reports median bar move versus round-trip
   cost for each dataset.
2. A long, multi-regime historical test with a frozen holdout. Earlier screens
   used 2–3 days of reused data. **Added:** 1999–2018 equity indexes,
   1927–2018 US market, 2012–2024 BTC.
3. A strategy whose horizon fits the venue's costs. **Added:** `monthly_trend_v1`.
4. Strategy-separated, reconciled net P&L. This is still missing; see the
   [4 October review](PROJECT-REVIEW-2026-10-04.md) finding 3.
5. Resting broker-side stops. Exits are still local checks only.

## 4. What is extra

These parts add maintenance cost without moving toward profit:

- Five intraday frames across 72 instruments and 360 analysis slots, when
  intraday horizons cannot clear costs.
- The legacy BTC `quote_cross_30s_v1` executor. It is measured as negative after
  fees and should not be restarted.
- Parallel FX, HIP-3 and Markov tracks that cannot trade.
- Very detailed per-run hash and provenance prose in the docs.

These are left in place, because removing them is the owner's decision. They are
listed here so they are not mistaken for paths to profitability.

## 5. The iteration loop, run with safeguards

Repeating until something looks profitable on the same data guarantees a false
positive. To prevent that, the loop was run under a protocol fixed before any
result was seen:

- **Splits:** frozen in `SPLITS` (develop / validate / holdout). Daily equities:
  1999–2008 / 2009–13 / 2014–18. US market monthly: 1927–69 / 1970–99 /
  2000–18. BTC monthly: 2012–17 / 2018–20 / 2021–24.
- **Costs:** 27 bps per side for crypto (taker fee plus half-spread), 2 bps per
  side for ETFs (half-spread plus slippage; commission is $0), 1 bp for FX.
- **Iteration happens only on develop.** Validate is opened once for the chosen
  candidate, and holdout is opened once at the end.

**Attempt 1 (develop):** five rules — buy-and-hold, a port of the bot's candle
confluence rule, the daily 200-day SMA, 12-month time-series momentum, and a
volatility-targeted trend. None beat cash on all three equity datasets. The
analysis showed that the daily SMA whipsawed about 9 round trips a year. On
hourly data, the bot's rule turned over 166 times a year, which costs about
45% a year at crypto fees.

**Attempt 2 (develop):** two variants based only on that analysis. One makes the
decision only at month end (`sma_trend_monthly`). The other is an equal-weight
SMA plus momentum ensemble. `sma_trend_monthly` was the only rule with a
positive Sharpe on every equity dataset and on BTC, so it was selected before
validation.

**Validate (opened once):** the rule was net-profitable on every dataset,
12–21% a year, with smaller drawdowns than buy-and-hold. In this bull-market
window it earned less raw return than buy-and-hold.

**Holdout (opened once):**

| Dataset | `sma_trend_monthly` net | Buy-and-hold | Rule max DD | B&H max DD |
|---|---|---|---|---|
| S&P 500, 2014–18 | **+6.7%/yr**, Sharpe 0.58 | +6.3%/yr, Sharpe 0.49 | −12% | −20% |
| NASDAQ, 2014–18 | +8.7%/yr, Sharpe 0.63 | +9.7%/yr, Sharpe 0.63 | −24% | −24% |
| US market, 2000–18 | **+8.3%/yr**, Sharpe 0.73 | +5.8%/yr, Sharpe 0.34 | −17% | −50% |
| BTC, 2021–24, 27 bps/side | **+59%/yr**, Sharpe 1.14 | +34%/yr, Sharpe 0.77 | −41% | −73% |

At the bot's own crypto cost, the original candle rule lost 55% a year on hourly
data. The month-end rule still made 6–8% a year on equities at that same cost,
because it trades about once a year.

The full reports are in `research/reports/cost-aware-20261008-*.json`. To
reproduce them:

```sh
pip install -r research/requirements-backtest.txt
python research/cost_aware_backtest.py --folds develop,validate
python research/cost_aware_backtest.py --folds holdout   # already opened; do not re-select on it
```

### Limits of this result

- The index data are adjusted closes from the `arch` package. ^GSPC and ^IXIC
  exclude dividends, which understates buy-and-hold by about 2% a year and
  slightly flatters the rule. The Ken French US-market series includes
  dividends, and the rule still won on it.
- The 10-month and 200-day rule was published in 2007, so the US-market
  2000–18 holdout overlaps the publication sample. The 2014–18 daily and
  2021–24 BTC holdouts come after publication.
- Two attempts and seven rules were tried, which is low multiplicity. Even so,
  one holdout per dataset is not statistical proof. BTC has only 48 holdout months.
- The tests are pre-tax. Monthly switching creates short-term gains in a taxable
  account.
- The edge is mostly risk reduction: smaller drawdowns, and avoiding most of
  2001–02 and 2008. In steady bull markets it lags buy-and-hold.
- These are simulated fills at the close. Real fills come from the live paper
  router at a market price the next session.

## 6. What was changed in code

- `lib/monthly_trend.ml`: a pure `monthly_trend_v1` decision. It holds when the
  last completed month's final close is above its 200-session average, and
  uses completed months only. It fails closed on stale months, a missing month
  end, gaps, short history, unordered bars or invalid closes. The client ID is
  bound to the symbol, decision month and side, so the rule makes at most one
  entry and one exit per symbol per month.
- `bin/monthly_trend_main.ml`: reads Alpaca daily bars and routes every order
  through the existing serialized `stock_paper_main.exe`. It requires
  `--execute`, `PAPER_ORDERS=1`, `STOCK_PAPER_ORDERS=1` and
  `TREND_AUTO_ORDERS=1`; otherwise it only observes. It never touches positions
  owned by another policy or entered manually. AAPL stays protected through the
  router's symbol check.
- `bin/stock_paper_main.ml`: the router accepts `monthly_trend_v1` intents. It
  recomputes the decision from the intent's own retained closes. It also
  re-checks the gate, the $100 baseline, entry ownership for exits, and quote
  freshness right before submitting.
- `bin/stock_auto_main.ml`: the candle scheduler no longer handles exits for
  trend-owned ETFs.
- Tests:
  - `test/test_monthly_trend.ml`: parity with the Python backtest on 24 real
    S&P 500 month ends, plus fail-closed cases.
  - `test/test_monthly_trend_runtime.py`: the real executables against a fake
    broker. Covers entry, hold, exit, monthly de-duplication, observe mode, the
    gate, and a forged intent being refused.
  - `test/test_cost_aware_backtest.py`: causality and cost accounting.
- CI runs the new tests and the develop/validate screen.
- `deploy/ai-ocaml-monthly-trend.{service,timer}`: weekdays at 15:05 UTC, in
  **observe mode**. The `-paper.conf` drop-in arms it.

## 7. Turning it on (owner decision)

The VPS services were deliberately stopped on 5 October, and this change does
not restart anything. To run the new rule on Alpaca paper:

1. Deploy a build of this commit to the VPS and run `dune runtest`.
2. Install `deploy/ai-ocaml-monthly-trend.service` and `.timer`. Run in observe
   mode for at least one session and check `monthly-trend.json`.
3. Install the `-paper.conf` drop-in to arm it.
4. Keep `jsbot-paper.service` (`quote_cross_30s_v1`) and the crypto multi-paper
   entries **off**. They are measured negative after fees.
5. Judge it on reconciled paper fills over months, not days. One trade a year
   per symbol means a reliable verdict takes years. The historical test is the
   main evidence until then.

Not done, and possible next steps: BTC through the crypto adapter (validated in
the screen, but it needs the crypto ownership path); position sizing beyond the
$100 baseline; and the reconciled per-strategy P&L ledger.
