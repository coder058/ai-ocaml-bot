# Paper policy and candidate log

This file records each tested rule before any paper order authority changes.
Historical BTC/USD bars retrieved on 27 September 2026 can contain revisions.
July–September was examined before this log and is not an untouched holdout.
Paper execution is simulated and cannot demonstrate live profitability.

## `quote_cross_30s_v1` — deployed paper baseline

- **Authority:** OCaml paper orders only, subject to the hardcoded Alpaca paper
  endpoint, AAPL exclusion, pending-order reconciliation, $100 target buy and
  $500 BTC exposure ceiling.
- **Inputs:** as-received Alpaca US BTC/USD quotes. A buy requires current bid
  above the preceding sampled ask while flat; a sell requires current ask
  below the preceding sampled bid while holding bot BTC.
- **Evidence through 27 September 2026, 20:00 UTC:** 72 bot orders and 92 bot
  fills in the latest complete signed snapshot at 19:53. The 18:54 flat
  checkpoint had −$1.44205878047 in cumulative filled cash difference, with
  an unexplained BTC quantity difference consistent with a 0.25% buy-side
  fee haircut. `CFEE`/`FEE` activity rows were not yet posted. The rule has
  no measured after-cost edge. Trigger quote crossings of the traced WebSocket
  orders had median 2.35120 basis points, which is not forward return.
- **Decision:** keep only as bounded paper data collection; do not represent
  it as a profitable strategy or extend authority to live trading.

## `markov-candle-fee-screen-v1` — rejected for order authority

- **Declared features:** Pattern Forge candle shapes, close direction and
  Murphy-style EMA trend from adjacent, closed Alpaca US BTC/USD 5Min bars.
- **Training:** 52,070 next-adjacent-bar labels with both bar starts before
  1 July 2026. This cutoff excludes the boundary label into July. The model
  has 73 observed states.
- **Optimistic screen:** require the state's *training mean* next-close
  midpoint return to exceed 50 basis points, the [published first-tier Alpaca
  taker fee](https://docs.alpaca.markets/us/docs/crypto-fees) for a buy and
  a sell combined. This ignores spread, latency,
  slippage, bar revisions and any uncertainty penalty; it is not a backtest
  of executable orders.
- **Result:** one state passed: `falling|up|Doji,Shooting-star shape,Bullish
  engulfing`, mean +54.185149693050974 basis points from only **9** training
  labels. It occurred **zero** times in the already-inspected July–September
  interval. No independent after-cost evaluation exists. An up probability
  above one half would not, by itself, pass the fee hurdle.
- **Decision:** no paper orders and no $50/$500 probability sizing from this
  screen. The frozen state-frequency model runs in read-only forward shadow
  mode solely to collect point-in-time evidence.

### Forward shadow status at 29 September 2026, 16:55 UTC

- Frozen model ID `c5ba22a1be9a455f283e9dd32ab8867d202421438f4c60c9d54b9df9292e99c0`
  produced 545 predictions, of which 544 had later adjacent-bar labels; one
  prediction remains unlabeled. Lead time median was 293.57 seconds (range
  3.53–299.49 seconds).
- Brier score was **0.25127**, slightly worse than the frozen base-rate Brier
  **0.24999**. Choosing direction from whether the model probability is above
  or below 50% yielded mean directional *midpoint* move of +0.57 bps, 51.29%
  positive, and only 2 of 544 moves above the 50 bps fee-only hurdle. This
  ignores spread and actual fills; one observation has only a few seconds of
  lead.
- **Decision:** keep the Markov model read-only. The shadow is serially
  dependent, small and based on midpoint labels; it provides no evidence of an
  executable after-cost edge.

## Forward shadow evaluation protocol

- Record the model hash, state, probability, bar close, snapshot retrieval
  time, actual observation time and seconds remaining to the next close.
- Record the next adjacent close only on a later retrieval; reject duplicate
  predictions, duplicate labels, non-adjacent bars and labels observed before
  the outcome's close.
- Score direction against the frozen pre-July base rate. Keep lead times and
  outcomes visible; short-lead and near-full-horizon predictions are not
  comparable. Midpoint moves cannot establish executable after-cost return.
- Require a new chronological sample with as-of bid/ask execution and fee
  reconciliation before reconsidering order authority. No sample count or
  statistical threshold has yet been calibrated for promotion.

## `ema20-50-as-received-replay-v1` — rejected for order authority

- **Rule:** long BTC when the Pattern Forge display EMA 20 exceeds EMA 50;
  otherwise flat. Parameters were fixed before this replay from the existing
  chart display and were not optimized against its three-day capture.
- **Data and timing:** first-seen Alpaca BTC/USD minute bars received on 27–29
  September 2026, with later `updatedBars` deliberately ignored. Five-minute
  and higher bars require complete UTC groups and reset indicators at gaps.
  Each signal executes at the first subsequently received captured quote.
- **Costs:** exact observed ask for buys and bid for sells, plus the official
  tier-one 0.25% taker fee on each side. Alpaca's fee is deducted in the
  credited asset and is posted at end of day ([official fee schedule](https://docs.alpaca.markets/us/docs/crypto-fees)).
- **Execution limitation:** this optimistic replay omits order submission
  latency, acceptance, queueing, partial fills and market impact. Each UTC day
  starts at normalized unit cash and the replay forces day-end liquidation;
  results are not account returns.
- **Observed results:** on 1m, the 27 September partial session returned
  −2.771% after modeled spread and fees across 4 round trips versus −0.889%
  for same-start buy-and-hold; 28 September returned −7.054% across 12 versus
  −1.708%; 29 September through the capture checkpoint returned −3.641%
  across 7 versus −0.770%. On 5m, 28 September's 2 round trips returned
  −1.298% versus −0.727%; there was no warmed 5m sample for 29 September.
  The 30m, 60m and 4h captures did not provide 50 contiguous bars for the
  frozen EMA warm-up (maximum runs were 30, 14 and 3 bars respectively).
- **Decision:** this fixed EMA rule showed no after-cost edge in the tested
  sample. Do not grant it paper-order authority. The sample is only a few
  sessions and overlapping market regimes; it is not independent statistical
  validation. Even a positive paper replay would not establish live
  profitability.

## `taker-flow-minute-screen-v1` — rejected for order authority

- **Rule:** aggregate Alpaca BTC/USD trade notional by *receipt-time* UTC
  minute. Alpaca defines `tks=B/S` as buyer/seller taker side. At each complete
  minute, test long entries on positive signed notional imbalance using a
  threshold fit only to prior dates; also run a direction diagnostic that
  hypothetically shorts negative-flow minutes. The signed-flow short leg is
  diagnostic only; short-sale support, borrow and funding were not verified.
- **Data:** 276,190 valid quotes and 2,001 trade events, from
  2026-09-27 07:28:07 UTC through 2026-09-29 16:42:50 UTC. The data are from
  three captured sessions, with 28 September and 29 September used as
  chronological test folds. The latter is a partial session and the capture
  has already informed other exploratory screens. The local filtered input is
  `../btc-quotes-trades-20260927-29.jsonl.gz` (SHA-256
  `c287a1c1b1bae0bac075c9640d0116c7d37586022f4661ba9260febfd4b8545e`).
- **Frozen screen:** train on all earlier positive-flow minute samples; use
  their empirical 90th percentile as the long threshold. The 90% selection
  share is an explicitly uncalibrated exploratory guess. Both training folds
  produced a threshold of `1.0`; retaining ties selected 88.59% and 88.25% of
  positive-flow training samples. Thus this threshold did not isolate a small
  top decile in these data. No threshold was refit on either test day.
- **Execution/costs:** enter at the first captured ask strictly after the
  minute close; exit at the first captured bid at or after 1m, 5m or 30m;
  charge the [published tier-one taker fee](https://docs.alpaca.markets/us/docs/crypto-fees)
  of 25 bps per leg. Alpaca describes `tks` in its
  [real-time crypto stream schema](https://docs.alpaca.markets/us/docs/real-time-crypto-pricing-data).
  This is still optimistic: no broker acceptance, queue, submission latency,
  partial fill or impact model. Receipt times do not establish when a real
  order could fill.
- **Test results, thresholded long-only:** on 28 September, 241/144/39
  non-overlapping completed round trips at 1m/5m/30m had mean net returns of
  −52.78/−52.64/−52.96 bps; winning shares were 0/0/2.56%. On 29 September,
  171/103/28 round trips returned −52.85/−53.31/−50.65 bps on average, with
  zero winning trades at all three horizons. Normalized all-in returns ranged
  from −72.07% to −18.72% for the first fold and −59.59% to −13.26% for the
  partial second fold; these are simulated unit-capital sequences, not account
  returns.
- **Signed direction diagnostic:** allowing long positive flow and
  *hypothetical* short negative flow produced zero net winners in all six
  fold/horizon combinations. Mean per-round-trip net returns ranged from
  −52.65 to −55.40 bps. This cannot establish a deployable short strategy.
- **Decision:** reject the candidate. The threshold is tied and weakly
  selective, both taker directions lose after observed spread plus modeled
  fees, and the sample is short and reused. Keep the existing bounded paper
  rule unchanged; this attempt grants no additional paper-order authority and
  is not evidence about live profitability.

## `ema20-50-multi-asset-screen-v1` — frozen for future shadow, not orders

- **Rule/universe:** apply the same pre-existing EMA 20/50 long/flat display
  rule, without per-symbol tuning, to BTC/USD plus the 14 already captured
  research symbols: AAVE, ADA, ARB, AVAX, DOT, ETH, FIL, GRT, LDO, ONDO,
  RENDER, SOL, SUSHI and WIF, all quoted in USD. Evaluate 1m, 5m and 30m.
  The fast/slow periods were fixed from Pattern Forge before this screen.
- **Data:** first-seen bars and received-time quotes from
  2026-09-27 07:28:07 through 2026-09-29 17:03:39 UTC: 1,181,731 quotes,
  36,285 first-seen minute bars, and 148 later bar updates ignored. Data were
  captured for 15 symbols and were already used by earlier screens; 28
  September is a full test day and 29 September is partial. Filtered source
  `../ema-research-quotes-bars-20260927-29.jsonl.gz` has SHA-256
  `7fb37fecc8030ccd40d1d08e8dec687df71f6162c1c01286780cccf8e898e12e`.
- **Execution/costs:** first later captured ask for buys and bid for sells;
  official first-tier 25 bps taker fee per leg; unit-cash daily samples with
  forced day-end liquidation. It remains optimistic because broker/network
  latency, acceptance, queue, partial fills and impact are not modeled.
- **1m screen:** across the 30 symbol-day sessions for 28–29 September, 172
  round trips had median daily normalized return −4.897%; 7 sessions were
  profitable, 9 beat same-start buy-and-hold, and **no symbol was both
  profitable and ahead of baseline on both test dates**.
- **5m screen:** only 17 of 30 symbol-day sessions produced a result, with 14
  round trips total. Four sessions were profitable, but median daily strategy
  return was 0% (cash); no symbol was profitable and ahead of baseline on both
  test dates. ARB/USD's single 5m round trip was −2.36% on 28 September and
  +4.84% on partial 29 September; one gain after one loss is not repeatable
  evidence.
- **30m screen:** no symbol produced a warmed signal; the longest contiguous
  30m bar run was 34, below the fixed 50-bar slow EMA warm-up. This capture
  also cannot evaluate 1h or 4h.
- **Decision:** no edge established. The screen includes 15 assets and
  multiple horizons, increasing false-discovery risk; the sample is only two
  test dates, one partial. Keep the whole universe frozen for later
  genuinely-future shadow evaluation, with no new order authority. A positive
  paper replay alone would not establish live profitability.

## `quote_cross_30s_v1` — 29 September live-paper fill markout

- **Scope:** read-only public signed snapshot at `2026-09-29T17:32:23.621003Z`,
  filtered to 421 broker fill rows dated 29 September. The audit joined those
  fills to 746 exact hot-order quote traces across the retained history; 25
  orders had no retained decision trace and zero joined IDs were unmatched.
  Within the dated fill set, 212 unique filled orders had usable future quotes
  at every markout horizon.
- **Forward markout:** directional midpoint response medians were +0.135,
  −0.071 and +0.488 bps at nominal 1s/5s/30s; positive-order shares were
  51.42%, 49.06% and 54.72%. The first quote after each target arrived a
  median 2.31–2.63 seconds later, with maxima 31.67–35.67 seconds. Those are
  observation delays, not network latency or guaranteed fill times.
- **Fee-aware hypothetical close/buyback:** using the actual fill price, a
  later executable bid for buys / ask for sells, and the official 25 bps
  tier-one taker fee on each leg, the median order markout was −51.40, −51.52
  and −51.30 bps at 1s/5s/30s. No marked order was positive at any horizon.
  This is not matched realized round-trip P&L; it omits the live order's
  submission delay, queue and impact.
- The trigger's median quote crossing was 1.811 bps (range 0.0024–23.1451);
  that one-sided trigger size is not an estimate of net round-trip return.
- **Decision:** the currently deployed paper rule still has no measured
  after-cost edge. Keep it paper-only and bounded; do not increase its size or
  grant technical/Markov or multi-symbol order authority on this evidence.

## `quote_cross_30s_v1` — extended 29 September markouts

- **Snapshot:** signed public paper snapshot at `2026-09-29T17:41:04.061241Z`;
  428 broker fill rows dated 29 September, 749 retained exact decision traces,
  and 25 bot orders without a retained trace. There were no unmatched order
  IDs. The point-in-time status was `PAPER_ORDER`, with order service and
  capture active; 774 bot orders, 1,234 fills, 294 filled orders and 480
  canceled orders. No open order was present in the snapshot.
- **Markout sample:** 215 filled orders had a future quote at 1s/5s/30s,
  214 at 1m/5m and 206 at 30m. Median directional midpoint responses were
  +0.135/−0.060/+0.471/+0.020/−0.920/−2.042 bps at 1s/5s/30s/1m/5m/30m;
  these are midpoint marks before costs. At the corresponding first observed
  executable quote, after modeling a 25 bps fee on each leg, median
  close/buyback markouts were −51.43/−51.52/−51.35/−51.62/−52.37/−53.68 bps.
  Positive net-order shares were 0/0/0/0/0/4.85% (10 of 206 at 30m).
- **Observation delay and missing data:** the first captured quote after the
  target arrived a median 2.28–3.00 seconds later, with maxima of 31.67–96.53
  seconds depending on horizon. Two fills lacked a future quote at 1m/5m and
  20 lacked one at 30m because the late-session marks were not yet observable.
  Quote-arrival delay is not network latency or a guaranteed fill time.
- **Fee and position reconciliation:** posted activities were complete through
  06:51 UTC only, totaling −$25.76 USD and −0.000281995 BTC. Bot buys were
  0.143033425 BTC, sells 0.141957561 BTC, and the broker position was 0.000718
  BTC. The 0.000357864 BTC gross-fill/position difference is within
  0.000000280 BTC of the expected 0.000357584 BTC buy-side fee at the published
  0.25% tier-one rate. This is a strong quantity consistency check, not proof
  of each fee posting or complete net P&L: fees had not updated since 06:51,
  the journal was incomplete, and the position was open. Do not deduct the
  BTC fee a second time from the broker's marked quantity.
- **Decision:** no executable after-cost edge is visible in this markout.
  These are overlapping, paper-fill-based hypothetical closes, not matched
  realized round trips; the model excludes submission delay, queue, impact and
  actual fee-tier confirmation. Keep the deployed rule unchanged and do not
  promote it as profitable.

## `top-book-imbalance-90p-v1` — rejected for order authority

- **Rule:** at each completed UTC minute, use the last received top-of-book
  size imbalance. Select positive imbalances above their 90th percentile from
  earlier captured days, then enter long at the first later ask and exit at
  the first later bid at 1m or 5m. The 90% tail share is an
  **uncalibrated exploratory choice**, not a discovered optimum. No short
  trades were tested.
- **Data and timing:** chronological, receipt-time reconstruction from
  638,416 BTC order-book deltas and 281,568 quote events, 27–29 September
  2026. The 29 September holdout contained 1,061 UTC-minute samples through
  17:41 UTC. Training used 1,162 positive-imbalance samples from 27–28
  September; the frozen threshold was 0.0070120471. The threshold selected
  67/1,061 holdout minutes at 1m and 13/214 eligible minutes at 5m; overlapping
  signals skipped were 3 and 1. The source included seven observed socket
  sessions and nine full-book resets; 4,760 records lacked a session ID.
- **Execution/costs:** first captured ask then bid includes observed spread;
  the reported gross series is after spread but before fees. The net series
  applies the published tier-one 25 bps crypto taker fee per leg
  ([official schedule](https://docs.alpaca.markets/us/docs/crypto-fees)). This
  replay omits broker submission latency, queue, fill probability and impact.
- **Results:** 64 non-overlapping 1m trades had mean gross −3.35 bps after
  spread, 21.9% positive before fees, and mean net −53.27 bps; none was
  positive net. Twelve non-overlapping 5m trades had mean gross −2.59 bps,
  50% positive before fees, and mean net −52.51 bps; none was positive net.
  Normalized unit-capital sequences returned −28.95% and −6.12%; these are
  simulated path returns over this partial day, not account returns. A
  no-trade cash baseline is 0% over the same interval, so this candidate did
  not beat it.
- **Decision:** reject for now. Both short chronological sample and latest
  date have already informed other screens; record reuse and 90th-percentile
  choice raise false-discovery risk. No deployment, symbol expansion, sizing
  change or order-authority change follows. Require genuinely future sessions
  under frozen features and controls; paper results still cannot establish
  live profitability.

## `top-book-imbalance-90p-v1` — prospective latency-aware start

- **Frozen cutoff:** `2026-09-29T17:47:00Z`. The screen uses only minute
  decisions strictly after that time for holdout scoring; its threshold
  remains fit only on positive-imbalance samples from 27–28 September. The
  captured book stream reached `2026-09-29T18:08:05Z` and supplied 22
  post-cutoff minute samples. This is an early, low-power prospective slice.
- **Signals and zero-delay reference:** one selected signal occurred at
  `18:00:00Z` and was eligible at both 1m and 5m. At the first captured ask
  (received 658ms after the minute boundary), the hypothetical 1m and 5m
  gross returns after spread were +19.70 and +22.80 bps. After the published
  25 bps fee per leg, both were negative: −30.33 and −27.25 bps. This is one
  signal shared across horizons, not two independent trades.
- **Observed paper-path latency:** 297 `ORDER_TIMING` rows on 29 September
  reported a median 1,347ms from quote receipt to HTTP submit, p90 1,694ms;
  HTTP round trip was median 330ms, p90 366ms. In the signed broker snapshot
  at `18:06:33Z`, 565 of 756 exact-traced orders had a fill. From decision
  quote to first paper fill, median was 1,667.728ms, p90 2,062.462ms, p95
  2,254.135ms and maximum 4,156.346ms. These are observed timings for the
  deployed rule and simulated broker, not live exchange latency. The 191
  no-fill traced orders are not used to infer this candidate's fill chance.
- **Latency sensitivity:** replaying the same single signal after the observed
  median/p90 decision-to-fill delay moved entry to the next captured ask at
  18:00:03.111Z. Gross after-spread returns fell to +14.83 bps at 1m and
  +16.91 bps at 5m; after modeled fees they were −35.18 and −33.11 bps.
  This replay begins holding the named horizon from that delayed entry quote.
  It assumes a fill at the first later ask/bid and still omits candidate
  fill probability, order queue and market impact. The per-trade timestamps,
  prices and returns are retained by `research/orderbook_imbalance_screen.py`.
- **Decision:** no edge. The initial future slice produced one signal, and it
  failed the fee hurdle both before and after the measured paper-path delay.
  Do not tune the threshold using this result. Keep the candidate frozen and
  collect future sessions; its present sample cannot support an edge claim.

### Continuation through 18:27 UTC

- The original `17:47Z` cutoff and 27–28 September training threshold were
  unchanged. The capture now reached `18:08:05Z`, with 41 post-cutoff 1m
  samples. Three 1m signals were selected at 18:00, 18:16 and 18:26 UTC; only
  the 18:00 signal also met the 5m slot rule. No parameters were refit.
- At zero added delay, all three 1m net markouts were negative after fees;
  mean −46.66 bps, median −51.51 bps. At the frozen paper-fill median and p90
  delays, all three were again negative; mean −48.44 bps and median −52.16
  bps. Only one of three was positive before fees after spread, and its gain
  did not cover the two modeled taker fees. The 5m result is still one trade,
  with −33.11 bps after the p50/p90 latency scenario.
- This remains a single partial day and only three non-overlapping 1m events;
  the 5m result shares the 18:00 event. Treat it as an interim failure to clear
  costs, not a statistical rejection of every future version. Keep this
  configuration frozen while the prospective sample grows; do not search the
  already viewed data for a better cutoff or percentile.
