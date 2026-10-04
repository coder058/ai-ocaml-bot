# Paper engineering evidence and strategy limits — 27 September 2026

This is an independent paper-trading engineering project. No agent can ensure
that every trade will be good. The diagnostic cross-spread rule is **active in
Alpaca paper only** (`PAPER_ORDERS=1` on Dublin as of 13:00 UTC). Pattern Forge
shapes and energy observations remain descriptive. Do not present a green
build, a filled paper order or a chart pattern as evidence of predictive edge.
The earlier measurements below were recorded before this bounded paper run;
the historical 2026 holdout was already examined.

From 08:36 to 10:26 UTC, the earlier REST polling service sent, received
acknowledgements for, and reconciled **20 additional paper orders**. Its
durable journal shows $299.999246395 in buy attempts against a then-active $300
daily cap, removed after the user's clarification. The broker later showed no BTC position, no open order, and the
pre-existing 10 AAPL shares. At 13:00 UTC the paper service switched to the
Alpaca WebSocket quote feed. After restoring the prior 30-second decision
cadence, a 13:46:17 UTC candidate led to a paper buy, broker acknowledgement,
fill and 13:46:21 UTC reconciliation. The 13:46:30 UTC signed public snapshot
showed the order and fill. Neither period demonstrates profitability.

## What was measured today

An early paper-broker snapshot returned a complete list of the account's orders at that time. Five orders
had this bot's `jsbotbtc` client-ID prefix: three buys (one IOC canceled after
a tiny partial fill) and two filled sells. Summing `filled_qty ×
filled_avg_price` gives **$39.9887759676 bought** and **$39.8978419145 sold**.
The difference is **−$0.0909340531** in gross cash flows *before separately
posted sell fees*. Broker positions then showed **zero BTC** and the pre-existing
**10-share AAPL long**. This is an observed, very small paper sample, not a
backtest or estimate of future performance. Alpaca says crypto fees may be
posted at the end of the day, so the account activity ledger must be reconciled
before reporting a final net P&L. The calculation script is retained outside
the published repository in the task workspace.

A reproducible [quote-quality audit](../research/quote_audit.py) of the signed
07:19 UTC snapshot parsed **685 quote log rows**, but only **421 distinct quote
timestamps**; **264 rows** repeated an earlier market quote. Approximate quote
age at logging had a **21.226989-second median**, **88.452922-second p90** and
**278.630044-second maximum**. The logged spread had a **2.6128-basis-point
median** and **3.7743-basis-point p90**. These figures are computed from one
short session, and repeated log rows are not independent market observations.
Journal timestamps are rounded to whole seconds, which produced a minimum
calculated age of −0.663541 seconds; this is a timestamp-resolution artifact,
not evidence of a quote from the future. This audit motivated replacing the
polling input with the WebSocket feed; it does not measure a profitable edge.

The new private Alpaca US stream was audited with
[stream_audit.py](../research/stream_audit.py) after 151 events: 42 quotes, two
trades and 107 book messages, including one full book reset. The observed
event-to-VPS receipt timestamp difference for quotes was **0.044005 seconds
median** and **0.045184 seconds p90**; book updates had **0.045578 seconds
median** and **0.126375 seconds p90**. The initial full book snapshot was
**110.736494 seconds** older than its receipt and dominates the book maximum.
The short sample had zero invalid quotes, zero crossed reconstructed books and
zero updates before the reset. The VPS reports NTP synchronization, but the
exchange/VPS clock offset was not independently calibrated, so these deltas
must not be called one-way network latency. No fill behavior or predictive
performance follows from this short capture.

The collector now also archives Alpaca US one-minute bars and late revisions.
Its first audited continuation contained two delivered closed-minute bars,
approximately 60.048 seconds after each bar's start timestamp. The bar
timestamp is the *start* of the minute, so this number is not network latency.
For historical feature work, a read-only 5-minute pull from 20 September
through midnight 27 September returned 2,016 bars. The
[continuity audit](../research/bar_gap_audit.py) found one missing interval:
26 September at 07:30 UTC, between bars at 07:25 and 07:35. No invalid OHLC
rows were found. Indicators must treat that interval as a gap; bars from a
later historical download are not a point-in-time record of when revisions
became available.

A broader Alpaca US 5-minute download from 1 January through midnight 27
September 2026 returned **77,404 bars**, with **48 gaps / 69 missing intervals**
and no invalid OHLC rows. A frozen exploratory
[Pattern Forge feature audit](../research/pattern_event_study.py) resets its
EMA state at each gap and only labels adjacent bars. For the declared
July–September holdout, the next-bar midpoint close rose after **49.45%** of
all eligible bars (25,272 cases), **45.45%** of bullish engulfing shapes
(1,329), **52.16%** of bearish engulfing shapes (1,321) and **53.19%** of
shooting-star shapes (1,519). The shooting-star mean next-bar midpoint return
was only **0.151 basis points**; the first-tier Alpaca taker fee alone is
**25 basis points per side**. These are descriptive, overlapping feature
groups with no statistical correction, live execution model or demonstrated
predictive edge. The shapes are a subset reimplemented from Pattern Forge;
cross-language parity is not yet proven.

### Closed-candle Markov transition audit

The read-only [Markov candle audit](../research/markov_candle_audit.py) builds
states from the current bar's close direction, Pattern Forge candle shapes and
EMA20/50 trend. It counts the next *adjacent* five-minute bar's direction using
only previous bars for each state. Gap boundaries are excluded. The January–June
development interval supplied **52,071** adjacent labels; the July–September
interval supplied **25,238**. July–September was already inspected in the
earlier shape study, so it is **reused evaluation data**, not a fresh holdout.

On that reused interval, the frozen state-frequency forecast had a Brier score
of **0.249536** versus **0.249996** for the constant development up-rate.
The next-bar midpoint rose in **49.45%** of cases and averaged **+0.1494 basis
points**. Only **59 of 25,238** next-bar midpoint rises exceeded **50 basis
points**, the first-tier Alpaca taker *fee-only* hurdle for buying and selling.
The hurdle excludes spread and execution slippage; the midpoint close is not a
fillable exit. There were 73 observed development states, so rare combinations
can have unstable rates. Historical bar revisions, dependence and earlier
inspection further weaken this evidence. **No Markov state currently authorizes
an order or selects the requested $50/$500 paper tiers.** The current OCaml
paper execution rule is still the uncalibrated quote-cross experiment.

### One frozen daily-rule probe, not an execution claim

The read-only [daily-bar downloader](../research/fetch_daily_bars.py) saved
**1,730 closed Alpaca US BTC/USD daily bars** from 1 January 2022 through 26
September 2026; the audit found no missing calendar days. Before calculating
returns, I chose the 2026 calendar boundary as an **UNCALIBRATED GUESS** for a
holdout. [ema_probe.py](../research/ema_probe.py) tests one uncalibrated rule:
long BTC when the prior daily close's EMA20 exceeds EMA50, otherwise flat, with
the trade modeled at the next day's midpoint open. EMA20/50 was taken from the
Pattern Forge display; its use as a trade rule is a guess. The model charges
Alpaca's documented first-tier 0.25% taker fee on both sides and a **4.208061
basis-point round-trip spread proxy** based on only 42 observed stream quotes.
Daily bars can contain quote midpoints, so these modeled fills are not
executable evidence. Returns use normalized full-capital exposure, which does
not implement the actual bot's $30 order cap.

| Period | Rule return | Buy/hold return | Rule maximum drawdown | Rule trades |
| --- | ---: | ---: | ---: | ---: |
| 20 Feb 2022–26 Sep 2026 (1,680 sessions) | +68.28% | +109.30% | −44.05% | 29 |
| 2026 holdout to 26 Sep (269 sessions) | +3.88% | −3.52% | −10.73% | 5 |

The single partial-year holdout is weak evidence; the full period trails a
simple buy/hold benchmark by about 41.02 percentage points under this proxy.
The 2022 and 2025 calendar returns of the rule were negative (−40.01% and
−1.48%). This is not a calibrated strategy, and no causal contribution from
Pattern Forge or Energy Monitor has been established. The current paper
orders are an engineering experiment, not a strategy approval.

## Inputs and their limits

| Input | Available evidence | Trading limit |
| --- | --- | --- |
| Alpaca crypto quotes / order books | The Dublin collector archives Alpaca US WebSocket quotes, trades, books and minute bars with receipt timestamps. OCaml receives quotes and bars over a local socket; a separate 5m historical snapshot is labeled with retrieval time. In one capture, 262 closed-minute bars appeared in 285 elapsed minute slots; 23 were missing and were not filled synthetically. From 13:16:05–13:38:43 UTC on 27 September, 1,349 captured quotes yielded zero adjacent-quote crosses and six crosses across 34 non-overlapping samples at the earlier REST service's 30-second cadence. | The cadence comparison is descriptive and informed a paper engineering policy change, not a calibrated edge. A stale quote, lost socket event or different venue must not authorize an order. The historical snapshot may include later bar revisions and is descriptive context, not point-in-time backtest evidence. |
| Pattern Forge | Its public API supplies validated closed Hyperliquid candles for BTC, ETH and SOL. The monitor derives descriptive 5m, 1h and 1d shapes/indicators from them. | Hyperliquid is not Alpaca's execution venue. Its candle patterns and geometric thresholds are uncalibrated; no order is authorized by them. |
| Alpaca US stocks / ETFs | The Basic market-data plan gives live IEX coverage, not consolidated SIP, and excludes the most recent 15 minutes of historical SIP queries. | Do not treat IEX alone as a full-market execution reference for energy ETFs or AAPL. AAPL is explicitly protected from this bot. |
| Energy Monitor | Public European electricity/gas observations and a candidate EIA WTI/Brent daily historical source. | These have different units, publication times and underlying markets from any Alpaca ETF. No direct tradable mapping or predictive lag has been validated. |
| Alpaca paper | The order API, positions and activities can validate software behavior. Alpaca simulates fills and may randomly partially fill marketable orders. | Paper fills omit several live-market frictions and cannot establish live profitability. |

The Alpaca Market Data documentation lists stocks, crypto, options and news
history, but does not itself establish access to complete company financial
statements. **Inference:** fundamental equity research would need separately
licensed, point-in-time statements/corporate-event data. Crypto has no company
earnings statement analogous to an equity, and energy physical data needs its
own publication-time audit.

## Gate before any live order or predictive claim

1. **Declare the hypothesis and horizon.** Specify the traded Alpaca symbol,
   the venue of each input, the intended holding period, benchmark and decision
   timestamp. A descriptive candle shape is a feature, not a hypothesis of net
   profit.
2. **Prove point-in-time data.** Retain raw event timestamps, receipt times,
   exchange/source IDs, gaps and revisions. Use only observations that were
   available before the simulated decision. A source outage or stale input
   blocks the order.
3. **Measure costs on the intended order path.** At Alpaca's documented first
   crypto tier, a taker order has a 0.25% fee. A taker buy followed by a taker
   sell therefore faces about **0.50% in quoted fees alone**, before the
   bid-ask spread, slippage and latency. This is a fee-schedule calculation, not
   a measured total cost for this account. Check actual tier and activity
   postings. A strategy must show an out-of-sample net edge after these costs.
4. **Evaluate without selection leakage.** Freeze candidate definitions,
   compare with simple baselines, split data by time, walk forward, count every
   configuration tried, include bad regimes, and report uncertainty and drawdown.
   The published research on backtest overfitting shows why choosing the best
   of many rules on the same history is unreliable.
5. **Forward-test and reconcile.** Run in shadow mode first, then a bounded
   paper test. Reconcile fills, cancellations, fees, holdings, order IDs,
   data-feed failures and restarts. Paper results remain separate from any
   claim about live returns.
6. **Enforce independent risk controls.** Keep the exact paper origin,
   minimum order rules, one pending order, the current $500 BTC exposure ceiling
   and AAPL protection. The user replaced the earlier $300-per-bot/$2–$30
   guidance on 27 September with a $100 experimental baseline and requested
   $50/$500 probability tiers that still require calibration. Repeated paper
   round trips have no daily turnover cap. A new loss
   limit or signal threshold needs real calibration; it must not be guessed
   silently. A breach or unknown broker state halts execution.

### How much analysis and time?

There is **no source-backed universal number of minutes or candles** an AI
agent should inspect before a trade. The time required is determined by the
declared horizon and measured data/cost uncertainty. For this project:

- **Scalping:** the WebSocket path is active for paper quotes, but only the
  local receipt-to-decision interval has been sampled. Broker response, fill
  timing, spread and fees still need a complete, timestamped execution study
  before calling it a low-latency scalping strategy.
- **Day trading:** use closed intraday observations, a point-in-time event and
  cost model, multiple out-of-sample days/regimes, and a live shadow run.
  Calendar duration and sample size must be justified by a precision/power
  calculation on the actual event rate, not declared in advance as proof.
- **Swing trading:** use closed daily bars, multi-regime history, corporate
  actions/fundamentals where relevant, and publication lags for energy data.
  The current Energy Monitor observations have no validated Alpaca mapping.

For an unattended VPS process, direct Alpaca APIs and an OCaml deterministic
risk gate are more appropriate than placing orders through an LLM/MCP session.
The official Alpaca MCP server is useful for interactive account/data
exploration, but it does not replace point-in-time testing, cost accounting or
broker reconciliation. The current direct paper adapter also avoids giving a
remote MCP service broader standing execution authority.

## Primary sources

- [Alpaca paper trading specifications](https://docs.alpaca.markets/us/docs/paper-trading)
- [Alpaca crypto fees](https://docs.alpaca.markets/us/docs/crypto-fees)
- [Alpaca real-time crypto data](https://docs.alpaca.markets/us/docs/real-time-crypto-pricing-data)
- [Alpaca market-data subscriptions](https://docs.alpaca.markets/us/docs/about-market-data-api)
- [Alpaca market-data FAQ on IEX and SIP](https://docs.alpaca.markets/us/docs/market-data-faq)
- [Alpaca historical data](https://docs.alpaca.markets/us/docs/historical-api)
- [Alpaca paper order listing](https://docs.alpaca.markets/us/reference/getallorders-1)
- [Bailey et al., backtest overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659)
- [Pattern Forge reading rules](https://github.com/coder058/pattern-forge/blob/main/docs/reading-rules.md)
- Energy Monitor's local EIA source audit (`docs/eia-crude-benchmark-audit-2026-09-26.md` in that separate project) remains unpublished here; its availability and point-in-time suitability still need verification.

The immediate honest risk: the observed earlier paper sample lost money before
all fees were reconciled. The now-active paper rule can continue to lose paper
money within its budget and says little about live execution quality or
profitability.
