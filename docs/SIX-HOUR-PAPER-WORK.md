# Six-hour paper trading development window

The user requested six hours of continued work toward a reliable and profitable
agent. Profitability and perfection cannot be promised or established by a
short paper sample. The Dublin VPS runs the paper service and collector between
Codex follow-ups. This file is the handoff for the scheduled follow-up loop.

## Starting evidence

- At 18:25:38 UTC on 27 September 2026, the complete signed broker snapshot
  showed 64 bot orders, 74 bot fills and zero open BTC. Executed sell notional
  minus buy notional was −$1.11455685460 before fee activities. The exact
  calculation is in `research/paper_fill_cash_flow.py`; `CFEE` and `FEE` both
  returned zero rows around 18:26 UTC. Net paper P&L is unverified.
- At 18:27 UTC, an IOC order targeting $100 was partially filled, then
  canceled. Its filled quantity was 0.000471840 BTC; the reconciled position
  was 0.000470659 BTC. No pending or open order remained at the check.
- Current order policy remains `quote_cross_30s_v1`, which uses no technical
  indicator or Markov probability. Closed-bar indicators and the 5m Markov
  audit are descriptive only. The previously examined July–September data are
  not a pristine test set.

## 18:54 UTC follow-up

- Dublin paper service, capture and timers were active. The broker reported
  zero BTC, no open order and no local pending journal. The complete signed
  snapshot at 18:54:40 UTC contained 68 bot orders and 83 bot fills; BTC was
  flat. Executed buy notional was $572.85303188063 and sell notional was
  $571.41097310016, leaving **−$1.44205878047** of filled cash difference
  before posted fee activities. This is not verified net P&L.
- The read-only [order-to-quote audit](../research/order_quote_audit.py)
  matched 43 WebSocket-initiated orders to the exact archived Alpaca US quote
  pair and broker status, with zero unmatched orders. The broker marked 26
  filled and 17 canceled; four cancellations had partial fills and 13 had no
  fill. The trigger quote crossing ranged from 0.04847 to 6.63402 basis points
  (median 2.35120). This is trigger magnitude, not expected forward return.
  The earlier REST orders are outside this trace audit.
- No replacement policy was deployed. The quote-cross rule has no measured
  net edge and cannot be called profitable from these observations.

## 19:24 UTC follow-up (work through 19:41 UTC)

- Dublin's paper order service, market capture, five-minute bar timer and new
  Markov shadow timer were active; the pending-order file was absent. No order
  policy or risk limit was changed.
- The public signed broker snapshot generated at 19:30:35 UTC contained 72 bot
  orders, 92 bot fills and an open BTC position of 0.001176752 BTC with broker
  market value $99.751367. Therefore the cumulative filled cash difference of
  −$101.76139933885 is **not a realized loss**: it includes the open inventory.
  It remains before fee activities. A fresh read-only paper Activities query
  returned zero `CFEE` and zero `FEE` rows at 19:32 UTC. Alpaca says crypto
  fees can post at end of day, so net paper P&L remains unverified.
- A quantity reconciliation found that bot buy fills minus bot sell fills
  exceeded the broker BTC position by 0.000016938 BTC at the 18:54 flat
  checkpoint (0.2504027% of bot buy-filled BTC), and by 0.000022836 BTC at
  19:30 (0.2503131%). This closely matches Alpaca's published tier-one
  0.25% taker fee on the BTC credited for buys. It is a consistency check,
  not proof of every fee entry: do not subtract another 0.25% buy fee from
  the observed flat cash difference without matching actual activities.
  The cash-flow auditor now reports the unexplained BTC quantity explicitly.
- The frozen descriptive candle/Markov model uses 52,070 adjacent labels and
  73 states with both bars strictly before 1 July 2026. The older audit's
  52,071 development labels included one transition into July; this frozen
  artifact excludes it. Its historical bars were fetched in September and
  may contain later revisions. The July–September analysis has already been
  inspected and cannot serve as an independent holdout.
- A read-only shadow evaluator is installed in Dublin. It writes predictions
  only for a bar observed before the following bar closes, then logs labels
  on later retrieval. Its initial manual execution succeeded but wrote no
  prediction because the snapshot was stale for that horizon. At 19:29:44,
  the latest retrieved bar started at 19:20; it left only about 16 seconds
  until the next five-minute close. The shadow now also runs immediately after
  each successful bar refresh and records actual lead time. Verify the
  subsequent label before scoring a forward evaluation sample. Even valid
  samples measure next midpoint close, not
  executable after-cost returns.
- At 19:34:46 the refresh automatically triggered the first real shadow
  prediction for the 19:25 bar, with a recorded lead of **13.562538 seconds**
  before the next bar's close. This is much too late to claim a five-minute
  forecast horizon. The label had not arrived at this checkpoint. The
  historical state frequency for this one observation was 0.5204565408252854
  from 5,695 training labels; this is not a calibrated chance of a profitable
  trade and did not authorize an order. At 19:39:53 the following bar was
  retrieved and labeled down, with a next-close midpoint move of −0.50480
  basis points. This is one outcome, not a performance estimate. The next
  recorded prediction had only 6.515208 seconds of lead time. The interval
  timer was drifting relative to the UTC five-minute closes; later samples
  near an exact close had almost five minutes of lead. Do not attribute the
  inconsistent lead times to unavoidable REST latency.
- The captured live one-minute bar stream delivered 653 closed bars over 690
  elapsed slots, with 37 missing minute slots; 108 of 138 five-minute groups
  had all five minute bars. Among 106 complete groups also present in the
  later REST snapshot, the median and 90th percentile absolute close-price
  difference were both zero, and the maximum was 0.09129 basis points. The
  stream bar reached the VPS around 60.05 seconds after its bar *start*,
  roughly at one-minute close. These observations support investigating a
  timely stream-based five-minute aggregator with strict gap handling. The
  37 missing slots prohibit assuming a continuous feed.
- Twelve Python tests passed, including a boundary check that excludes the
  July label and a point-in-time shadow prediction/label check. The old
  descriptive audit metrics did not change after the state refactor.

## 19:54 UTC follow-up (work through 20:01 UTC)

- Dublin's paper service, capture, telemetry, bar refresh and Markov shadow
  timers were active. The broker check reported no open orders, and there was
  no local pending-order journal. The 19:53 signed snapshot still had 72 bot
  orders, 92 bot fills and 0.001176752 BTC open. Recent journal samples were
  `candidate=false` under `quote_cross_30s_v1`; no new policy was deployed.
  The account Activities query still returned zero `CFEE` and `FEE` rows.
- The bar refresher used `OnUnitActiveSec=5min`, so execution time drifted
  through the five-minute boundary. The last two pre-change executions at
  19:50:00 and 19:55:00 already produced close-to-full-horizon predictions.
  The timer is now anchored to UTC five-minute closes at +5 seconds, with a
  +30-second retry if the API is late. This 5/30-second choice is an
  **uncalibrated scheduling guess**, based on the observed availability at
  about +1 second; collect more cycles before trusting the cadence.
- At 20:00:06 the aligned refresh retrieved the 19:55 bar, and shadow
  prediction had 293.374145 seconds before the next close. The 20:00:30
  retry returned the same bar; the shadow journal wrote no duplicate event.
  The order service remained active throughout. This verifies one aligned
  cycle, not long-run feed reliability.
- The chronological shadow scorer checks pairing, duplicate events and
  prediction-before-close. At 20:00 it had 6 predictions, 5 later labels and
  1 unlabeled prediction. The 5 scored examples had lead times from 3.525722
  to 299.494861 seconds, so they should not be pooled as equal-horizon
  evidence. The model Brier was 0.283329 versus 0.249920 for its frozen
  base-rate predictor on this tiny mixed sample. None had a positive
  next-midpoint move above the 50-basis-point first-tier taker fee-only
  round-trip hurdle. No after-cost edge follows from five examples.
- A pre-July state-mean audit found 1 of 73 states with a mean next-bar
  midpoint rise over that 50-basis-point fee-only hurdle. It had only 9
  training occurrences and zero occurrences in the already-inspected
  July–September interval. It does not support a probability size tier or
  order policy. The Brier score measures direction, not executable return.
- The exact baseline and rejected fee screen are recorded in
  [POLICY-ATTEMPTS.md](POLICY-ATTEMPTS.md), including their data limitations
  and the conditions required before reconsidering order authority.
- Fifteen Python tests passed, including the scorer's time-order and
  duplicate guards. No OCaml order logic changed.

## 22:47–22:57 UTC follow-up

- Dublin reported the paper order service, market capture, five-minute bar,
  Markov shadow and telemetry timers active at 22:56:37 UTC. The durable
  `NO_PENDING` marker was absent. The public signed snapshot at 22:55:54 UTC
  contained 95 broker orders, of which 94 carried the bot's BTC prefix, and
  121 broker fills, of which 118 carried that prefix. A broker BTC position of
  0.001184993 BTC had a reported market value of $99.700583. AAPL remained a
  separate protected position. This is a point-in-time service check, not a
  continuous uptime measurement.
- The preceding flat snapshot at 22:47:24 UTC had 93 bot orders, 117 bot fills,
  filled buys of $1062.80916274819 and filled sells of $1059.938718984512.
  Their cash difference was −$2.870443763678 while the broker reported no BTC
  position. Gross filled BTC quantity differed by 0.000031415 BTC, or
  0.2502534% of bought BTC. This is consistent with a buy-side asset fee, but
  the fee activities were not newly reconciled in this follow-up. No verified
  net P&L can be stated.
- A replacement dashboard was built locally with one row per broker order,
  partial-fill status, a selected-order trace, filterable entries and exits,
  the open BTC position, and an indicative bot-only cash-plus-mark figure.
  The indicator explicitly excludes AAPL, requires complete order/fill
  histories, and hides the figure if any non-bot BTC order or missing BTC mark
  prevents attribution. It does not label paper results as live profit.
  Closed-trade net P&L is shown as unverified until broker fee activities and
  position lots can be reconciled.
  A 22:55:54 UTC snapshot produced an indicative marked figure of
  −$3.1573682976477926 (buy fills $1162.7966702821598, sell fills
  $1059.938718984512, broker BTC mark $99.700583); this is not an executable
  liquidation price or verified net P&L.
- Seven web tests, TypeScript typecheck and Next.js production build passed
  before publishing. The order policy and VPS executable were not changed.

## 23:05–23:12 UTC monitor correction

- The user correctly identified a presentation failure: the large four-decimal
  negative USD figure could be read as thousands, while actual fills were
  below several large panels and canceled orders were mixed into the default
  list. No trading policy changed in this correction.
- The public signed snapshot at 23:06:01 UTC had 98 broker orders, 127 fills
  and an incomplete 4,000-row public journal. A local join of that retained
  journal found recorded decisions for 65 of 97 bot orders; older reasons were
  dropping from the public window even though the VPS still held the full
  append-only journal. This is a data-presentation defect, not evidence that
  those older orders lacked a decision.
- The monitor code now puts the latest Alpaca paper executions first, groups
  fills by broker order, displays execution amount, BTC quantity, average
  price, time and the actual recorded quote-cross rule, and defaults the full
  history to executed orders. Canceled attempts are a separate filter. The
  indicative USD amount is rounded to cents with an explicit USD unit, and
  net closed-trade P&L remains labeled unverified.
- The telemetry exporter now derives a compact per-order decision history from
  the complete owner-controlled journal, matched by the encoded quote time
  rather than a nearby timestamp. The test covers an old decision, its prior
  quote time and a neighboring unrelated event. Seven web tests, one exporter
  test, TypeScript typecheck and production build passed locally. Deployment
  and live verification remained to be done at this checkpoint.
- Vercel deployed the execution-first UI. The exporter candidate passed a
  read-only dry run on Dublin in `PAPER_ORDER` mode with 99 orders, 130 fills,
  73 matched decision records and an 804,823-byte signed payload. It replaced
  only the read-only telemetry exporter; the OCaml order executable and its
  policy were untouched. A signed public snapshot at 23:14:22 UTC contained
  74 compact decision records. Among its 73 executed bot orders, 52 had an
  exact recorded decision; the other 21 were earlier executions, all at or
  before 10:25 UTC, for which this decision trace is unavailable. The UI must
  say so for those rows and must not invent their individual triggers.
- The live page rendered 73 executed orders, 127 individual broker fills and
  a flat BTC position at 23:13:40 UTC. Its visible approximate cash difference
  was −$3.18 USD; this remains **unverified net P&L**. The latest displayed
  exit grouped three fills into $30.09 at an average $84,176.31/BTC and showed
  the recorded quote-cross condition. A concise explanation of the actual
  OCaml decision sequence was added from the implementation, without claiming
  that the rule predicts after-cost profits. Mobile navigation and wording
  were tightened; the public UI then showed two recent executions and the
  complete history link, and filtering exits plus selecting a trade updated
  the inspector in the browser. A sub-cent open P&L display was corrected so
  rounding cannot show a misleading negative zero. The final deployment check
  for that last formatting change remained outstanding at this checkpoint.
- At 23:23 UTC, a read-only paper asset inventory found 73 active tradable
  crypto pairs, 36 against USD. DIA, XLE and XOP were active/tradable US
  equity ETF proxies, not actual Dow or energy commodity feeds. This catalog
  count is not a measured simultaneous stream capacity.
- At 23:26 UTC, the Dublin collector was changed to archive ETH/USD and
  SOL/USD quotes and closed/revised minute bars alongside BTC/USD. The local
  OCaml socket still receives only BTC events; the order executable and its
  $100/$500 paper controls did not change. The Alpaca subscription authenticated
  and both new symbols produced real quotes and a closed minute bar. The
  collector had no restart or error immediately after rollout, and the OCaml
  service logged a new BTC feed baseline. Nineteen Python tests passed before
  deployment, including the BTC-only routing and gap/revision checks.
- An as-received, as-of UTC aggregator now audits 1m/5m/30m/1h/4h bars without
  fabricating missing minutes. At 23:27:57 UTC, BTC had 867 distinct closed
  1m bars, 140 complete 5m groups, 13 complete 30m groups, five complete 1h
  groups and zero complete 4h groups in that day's capture. ETH and SOL each
  had one closed minute after joining. No new symbol or timeframe has order
  authority; no stop distance or win probability is calibrated.
- At 23:30 UTC, the read-only Alpaca US historical 5m scan found 13 of the
  36 paper-tradable USD pairs with no missing slot between their first and
  last returned bar for the UTC day. ETH had 250 bars with 32 gaps and SOL
  had 280 with two gaps. This retrieval-later scan is only a data-coverage
  screen, not a point-in-time strategy test. The authenticated stream was
  expanded at 23:31 UTC to those 13 plus ETH and SOL, 15 symbols total,
  retaining BTC-only hot fanout and order authority. Ten symbols had actual
  events in the first 30 seconds; sustained throughput and all-symbol bar
  coverage remain unmeasured.
- At 23:36 UTC, a manual read-only shadow run processed the 15-symbol capture
  in 0.850 seconds and wrote private 1m/5m/30m/1h/4h bar coverage plus candle
  shapes and EMA trends. BTC's latest contiguous 5m tail contained only 20
  complete groups, so its 5m EMA trend stayed unavailable. The new systemd
  timer is enabled for one run per UTC minute. Its first scheduled run at
  23:37:05 UTC completed successfully in 0.939 seconds, and the next trigger
  was scheduled for 23:38 UTC. This research process has no broker imports,
  credentials, network calls or order authority.
- The telemetry exporter was extended to publish only the shadow's timestamp,
  symbol names, per-frame coverage and descriptive labels, omitting private
  capture file paths. A read-only VPS dry run at 23:40 UTC contained 102 broker
  orders, 132 fills and 76 matched decision traces; its signed body was
  817,768 bytes, below the existing 1 MiB ingest bound. The candidate replaced
  the exporter with a backup retained. A manual telemetry service run succeeded
  but skipped upload because the prior digest was unchanged and its heartbeat
  was not yet due. Public monitor visibility remains to be verified.

## 09:31–09:35 UTC follow-up (28 September)

- Dublin's paper service, Alpaca capture and Hyperliquid read-only capture were
  active at the checks. The paper service had zero systemd restarts at 09:11;
  the pending-order journal was absent and a complete broker query shortly
  before the planned restart found zero unresolved orders.
- The complete read-only snapshot at 09:31:38 UTC contained 252 bot orders,
  180 buy fills and 227 sell fills. Buy notional was $4,136.980382580415 and
  sell notional was $4,110.776598744178, a filled cash difference of
  −$26.203783836237 before fee activities. It is not a realized or net P&L:
  the broker held 0.000186743 BTC marked at $15.460531. `CFEE` and `FEE` each
  returned zero rows. The 0.000123549 BTC gross quantity difference is about
  0.250166% of bought quantity, consistent with an asset fee but not a matched
  fee attribution. Net paper P&L remains unverified.
- Broker order and fill histories were complete, but the public decision
  journal was capped at 4,000 events. Exact trace matching found 227 bot orders
  with a decision record and 25 without one. Do not invent triggers for those
  missing records.
- Hyperliquid health read five archived sessions with 784,955 BBO updates,
  82,035 candle updates and 6,824 allMids updates; it saw 126 distinct mid
  symbols including the 14 selected contracts, zero locally archived sequence
  gaps and zero malformed lines. The live hourly gzip member correctly appears
  under `incompleteGzipFiles` until it is rotated and closed; this is not proof
  of provider-side completeness.
- The first live health scan had aborted on that open gzip trailer. The scanner
  now retains its flushed prefix and reports the partial file. A synthetic
  regression test covers that case; 21 Python tests pass.
- New OCaml decision records now include both quote pairs, cross direction and
  trigger distance in basis points. The arithmetic is a pure tested helper for
  upward, downward and absent crosses. The remote Dune 3.24.2 build and all
  OCaml tests passed. The monitor has corresponding fields and the exporter
  allowlist preserves them; eight web tests, TypeScript typecheck and a Next.js
  production build passed. The read-only exporter passed a dry run with 254
  orders, 411 fills, 228 decision records and a 976,762-byte payload. It and
  the OCaml binary were installed after complete broker queries showed zero
  unresolved orders and the durable pending journal was absent. The service
  restarted in paper mode and loaded 194 contiguous BTC bars after the
  multi-symbol warmup fix. No strategy or risk limit changed.

## 09:53 UTC follow-up (28 September)

- The signed public monitor now serves commit `85f7881`. Its GitHub `monitor`
  job passed tests, TypeScript and production build. The OCaml Actions job
  also passed opam setup, Dune build and the full OCaml suite; both workflow
  jobs completed successfully at 09:48:21 UTC.
- The live page showed a 09:53:25 UTC broker snapshot, 193 executed orders and
  417 fills. The latest BTC position was 0.000119779 BTC, marked at $9.91.
  Its displayed cash-plus-mark amount was −$10.84 USD, explicitly indicative;
  closed-trade net P&L remains not verified.
- At 09:53:50 UTC, the read-only reconciliation found 255 bot orders, 185 buy
  fills and 232 sell fills. Buy notional was $4,206.982393537615 and sell
  notional $4,186.234458128558, cash difference −$20.747935409057 before fee
  activities. `CFEE`/`FEE` each still returned zero rows, and a quantity
  difference of 0.000125670 BTC remains unattributed. Orders/fills pagination
  was complete; the 4,000-event public journal was not complete. Net P&L is
  still unverified.
- The order/quote auditor originally read only the 28 September file, which
  made 78 prior-day orders look unmatched. It now accepts multiple daily files;
  across 27–28 September it matched 230/230 HOT_SAMPLE orders to their exact
  captured quote pair and broker status, with zero unmatched. There were 101
  filled and 129 canceled orders; crossing magnitudes ranged from 0.011831 to
  12.000184 bps, median 1.529065. These are trigger movements, not forward
  returns or evidence of an edge. Twenty-five other bot orders still have no
  matched HOT_SAMPLE decision record; their reason remains unavailable.
- The public inspector has now shown two real examples with exact quotes:
  the 09:39:27 buy crossed upward by 0.230050 bps and received five partial
  fills totaling $70 before cancellation of the remainder; the 09:52:03 sell
  crossed downward by 1.184709 bps and received four partial fills totaling
  $60 before cancellation of the remainder. These broker outcomes do not
  validate the strategy.

## 10:10 UTC follow-up (28 September)

- The OCaml paper service, Alpaca capture, Hyperliquid capture, one-minute
  multi-timeframe shadow timer and Markov shadow timer were active. The paper
  service had zero systemd restarts; the durable pending-order journal was
  absent. The multi-timeframe output was current through 10:10 UTC. It is a
  read-only candle summary, not a multi-asset trading model.
- The current Alpaca read-only snapshot had complete order and fill pagination
  and an incomplete 4,000-line public journal. The bot had 257 BTC orders and
  422 fills (187 buy, 235 sell). Buy notional was $4,246.982078 and sell
  notional $4,236.121736, a gross cash-flow difference of −$10.860342 before
  any fee reconciliation. No BTC position was open. The account separately
  held 10 protected AAPL shares marked at $3,404.40 with $1,457 unrealized
  gain; those shares are not attributable to this bot. Account equity was
  $101,434.50 and cash $98,030.10, so neither whole-account change can be
  presented as bot P&L. FEE and CFEE returned zero first-page rows; that does
  not establish that every economic execution cost is zero. Bot net P&L stays
  unverified.
- A follow-up snapshot at 10:21:36 UTC had 259 bot orders and 428 fills. Gross
  FILL activity buy qty summed to 0.051141176 BTC and sell qty to 0.051013235
  BTC, a difference of 0.000127941 BTC (0.250172% of buys); the position
  endpoint reported no BTC holding. This is consistent with Alpaca's
  documented tier-one 0.25% taker
  fee being charged in the credited crypto on buys, but no fee activity has
  posted to prove that attribution. Alpaca says crypto fee activities may post
  at end of day, so today's empty `CFEE`/`FEE` result is not a final fee ledger.
  The documented 0.25% fee on sell proceeds would be about $10.68 on the
  observed $4,271.02 sells if all filled IOC orders were tier-one takers; this
  is an estimate only. The −$10.95 fill cash difference therefore cannot be
  called net P&L, and the incomplete coin quantity must be reconciled before
  presenting a closed-trade result.
- The exact-quote audit now matches 232/232 `HOT_SAMPLE` order traces, with
  102 filled and 130 canceled; 25 earlier bot orders still have no such trace.
  Crossing magnitudes ranged from 0.011831 to 12.000184 bps, with a 1.510731
  bps median. This describes the trigger, not a return.
- A new descriptive fill-to-midpoint audit aligned the 389 fills belonging
  to matched hot orders into 174 order-level responses. Median signed response
  relative to fill price was +0.020714 bps at the nominal 1s horizon,
  +0.040841 bps at 5s and +0.136072 bps at 30s; positive-order shares were
  51.15%, 52.30% and 51.15%. But the first quote after each target arrived a
  median 2.600s, 3.028s and 3.015s late, with maxima of 84.964s, 80.964s and
  75.940s. These are not exact horizon markouts, omit activity fees and are
  not an edge or a profitability estimate. The figures are too small and
  delayed to justify a rule change.
- The frozen, read-only Markov shadow had 176 predictions, 175 scored and one
  not yet labeled. Its forward Brier score was 0.250335 versus 0.249947 for
  the frozen constant base-rate baseline; it did not improve that baseline
  on this serially dependent sample. The recorded next-midpoint moves had
  zero instances above the fee-only 50 bps round-trip hurdle. Prediction lead
  time had a 293.526s median and ranged from 3.526s to 299.495s. These labels
  still ignore executable bid/ask and costs; Markov has no order authority.
- Hyperliquid's current UTC-day health scan read 5 sessions, 831,795 BBO
  updates, 86,816 candle updates and 7,282 `allMids` updates across 126
  observed mid names. All 14 selected HIP-3 contracts appeared; there were
  zero locally recorded sequence gaps and corrupt lines, plus one expected
  still-open gzip file. The event-driven candle feed was sparse for
  `xyz:EUR` (152 updates) and `xyz:GBP` (26), so those counts do not establish
  complete one-minute bars or ten FX pairs. The collector remains read-only.
- Local Python research tests pass 24/24; the `e68e341` GitHub Actions run
  passed. The markout implementation preserves nine-digit Alpaca timestamps
  and now exposes quote delay so an observation arriving long after its target
  cannot be mistaken for an exact horizon. The changes were later committed
  as `c88e3c0` and passed GitHub Actions.

## 10:29 UTC follow-up (28 September)

- Commits `c88e3c0` (post-fill midpoint response audit) and `c147b25` (fee
  timing/quantity evidence) were pushed to `main`. GitHub Actions completed
  successfully for both. The 24 Python tests pass; the last commit only changed
  documentation.
- A fresh broker snapshot at 10:28:45 UTC had complete order/fill pages, no
  broker-open orders and no durable pending file. A just-submitted sell order
  at 10:28:03 for 0.000843881 BTC had filled 0.000187863 BTC across 2 fills
  ($15.55 at $82,763.21 average) and the remainder was canceled. The bot now
  holds 0.000656018 BTC marked at $54.30; this is a partial exit, not a flat
  position. The service remained active with zero restarts.
- The public signed snapshot at 10:28:50 UTC reflects the same partial exit:
  199 bot orders with fills, 435 bot fill rows, current BTC mark $54.30, and
  indicative bot cash-plus-mark −$11.10. Closed-trade net P&L remains
  unverified. The selected order inspector now visibly shows its earlier and
  current bid/ask ($82,793.25/$82,815.60 and $82,759.97/$82,778.30), 1.805 bps
  downward trigger, 8.971 ms receive-to-decision time, 2 broker fills and the
  partial-cancel outcome. This verifies the public monitor's latest order
  explanation; it does not validate expected returns.
- The telemetry exporter uploaded 262 account orders and 438 account fills;
  the public bot-only view shows fewer because it filters to BTC bot activity.
  The AAPL holding stays separated and protected. The paper policy, $100
  baseline, $500 BTC cap and hardcoded paper endpoint remain unchanged.

## Next verified steps

1. Commit/push the nanosecond-safe quote-response audit and this evidence log;
   wait for CI. Keep the public response fields explicitly labeled as delayed,
   fee-excluding diagnostics if they are ever added to the monitor.
2. Reconcile the bot's full BTC inventory and cash flow from its first order,
   Alpaca end-of-day activity pages and any asset-denominated fees; test the
   observed buy-quantity reduction against the fee rows rather than assigning
   it by appearance. Explain AAPL as a separate protected account holding.
   Do not infer P&L from account equity.
3. Measure decision-to-submit time, quote age, spread, partial-fill timing and
   quote delay around each response. Improve the markout only when the capture
   supports the exact sampling window; retain skipped/stale observations.
4. Keep the current Markov and candle policies in read-only shadow. The latest
   Markov sample is slightly worse than its constant baseline. Collect more
   as-received point-in-time labels and evaluate calibration, bid/ask outcomes,
   spread, fee records and missing/stale bars before proposing an alternative.
5. For HIP-3, validate contract metadata, event-driven candle gaps and
   per-symbol quote freshness/spread. Do not present capture volume as
   simultaneous tradability or HFT latency. Replay must be deterministic
   before any testnet execution adapter is considered.
6. Update the monitor only with complete broker-backed rows, explicit
   attribution and the policy/version behind each order. Do not promote a
   candidate or alter order sizing based on these inconclusive results.

Keep the hardcoded paper endpoint, AAPL protection, durable pending journal,
$100 baseline and $500 BTC exposure ceiling. Paper fills do not establish a
profitable live strategy; if evidence stays negative or inconclusive, report
that rather than forcing more trades.

## Monitor diagnosis and redesign — 29 September 2026

- At 10:58 UTC the Vercel page still showed a signed snapshot generated on
  28 September at 12:47:29 UTC. Dublin's paper executor and Alpaca capture
  were active; the telemetry timer was retrying a failed exporter. The exact
  exception was `telemetry exceeds the signed endpoint limit` (1 MiB), so the
  page had frozen while the OCaml service continued processing quotes.
- A read-only broker snapshot at 11:15 UTC showed `PAPER_ORDER`, live capture,
  148 bot orders submitted since 00:00 UTC, and 602 `HOT_SAMPLE` events that
  day: 149 had `candidate=true` and 453 had `candidate=false`. This is order
  activity under a quote-cross trigger, not Murphy/Markov probability trading.
  The latest observed BTC position was 0.001187307 BTC, marked at $99.72. The
  figure is point-in-time and is not a bot P&L result.
- The broker pagination response contained six repeated bot order rows across
  635 rows; 629 IDs were unique. Fill activity IDs were unique. The exporter
  now deduplicates orders/fills by broker ID, keeps the complete BTC order
  history and its retained decision reasons, and omits account-wide equity,
  non-BTC orders/fills, AAPL details and the unused candle table from public
  telemetry.
- The changed exporter passed a broker read-only dry run after 11:15 UTC with
  complete order and fill pagination: 630 BTC-relevant orders, 1,079 fills,
  605 decision traces (25 orders had no matching retained decision), and a
  636,901-byte signed payload. The retained source
  journal still reports incomplete because the exporter reads its latest
  4,000-line window; per-order traces remain available only where captured.
  No data was uploaded by this dry run.
- The UI changes remove the duplicated latest-trade cards, hourly activity
  chart, multi-pair candle table and repeated strategy prose. The first view
  now prioritizes the bot's indicative fill-cash-plus-mark, a prominent
  unreconciled-net-P&L status, BTC position, execution counts and an order
  history with one selected order's fill/quote/broker explanation. Unverified
  values stay labeled; no equity-wide P&L is shown.
- Python exporter tests, web tests, TypeScript and Next production build pass.
- Deployment was then completed: commit `1a12f3b` was pushed to `main`, the
  compact exporter was installed on Dublin after backing up the prior copy,
  and `ai-ocaml-telemetry.service` uploaded a signed snapshot successfully. The
  public API returned snapshot time `2026-09-29T11:30:48.873525Z` and API
  generation time `2026-09-29T11:30:58.907Z`; the web page showed `FEED LIVE`,
  630 unique BTC order rows, 1,079 unique fills, 192 retained journal events,
  and no account-wide equity, AAPL positions, or market research payload.
  The source journal is still marked incomplete. At that snapshot the page
  displayed indicative fill-cash-plus-open-mark of -$25.94, explicitly marked
  `NET P&L NOT RECONCILED`; it is not a realized or fee-adjusted result. The
  open BTC position was 0.000710987 BTC, broker unrealized P&L +$0.03, as of
  that snapshot only. The UI now presents a current monitor, not a profitability
  claim.

## Fee-aware result and simplified execution panel — 29 September 2026

- A fresh read-only export at `2026-09-29T12:05:58.149297Z` completed all
  Alpaca order, fill and fee pages. It found 642 BTC bot order rows, 1,093
  fills, 996 `CFEE` fee activities and no `FEE` rows. Fee attribution passed:
  the complete account crypto-order history contained no non-bot crypto order.
  The source journal remained a rolling, incomplete 4,000-line window.
- Posted fee activities totalled −$25.76 in USD and −0.000281995 BTC
  (about −$23.55 at the fee activity prices). The current BTC position was
  flat. Cumulative fill cash flow was −$26.056834544721153069, so the
  provisional result after posted USD fees was −$51.816834544721153069. The
  BTC-denominated fee is not subtracted a second time: its debit is reflected
  in fills versus available broker inventory. The broker quantity still
  differed from fills plus posted BTC fee activities by −0.000023918 BTC.
  Same-day fees can post later; this is a provisional paper cash result, not a
  certified closed-lot net P&L or evidence of live profitability.
- The monitor now shows the provisional result and its three components,
  separates USD fees from BTC fee units, exposes the quantity reconciliation
  in a collapsed calculation detail, and labels the metric as provisional.
  Its history count now says “orders with fills” because canceled orders can
  contain partial executions. The exporter includes complete CFEE/FEE page
  status and caches private fee activities for the existing five-minute
  refresh cadence to avoid repeating the full fee pagination each telemetry
  cycle. It keeps the Alpaca keys on Dublin; no fee activity rows or keys are
  sent to Vercel.
- The strategy, paper endpoint, order sizes, $500 BTC exposure limit and AAPL
  safeguards were not changed. The public monitor remains a BTC-only paper
  experiment using `quote_cross_30s_v1`; candles, Pattern Forge and Markov
  still have no order authority.
- Verification before deployment: Python suite 32/32, web suite 11/11,
  TypeScript typecheck and Next production build passed. The signed exporter
  dry run was 649,469 bytes, below the existing ingest limit, with complete
  broker pages and fee attribution. No OCaml source changed.

## Public verification and review — 29 September 2026, 12:31 UTC

- `6c0d5e1` was pushed to `main`; the fee-aware exporter was installed on
  Dublin after saving the previous script as
  `export_telemetry.py.bak-20260929-before-fee-pnl`. Local and VPS SHA-256
  matched. The read-only dry run at `12:23:30.573562Z` had complete order,
  fill and fee pages, bot fee attribution, and a 651,892-byte payload. The
  public signed API subsequently returned snapshot
  `2026-09-29T12:31:21.917073Z` with 645 bot orders, 1,095 fills and 996
  posted `CFEE` rows. Both `jsbot-paper.service` and `ai-ocaml-telemetry.timer`
  were active; timer logs show successful uploads and unchanged heartbeats.
- At that public snapshot, posted USD fees were −$25.76, posted BTC fees were
  −0.000281995 BTC, fill cash flow was −$26.100734051581153069, and BTC market
  value was $0. The resulting display value was −$51.860734051581153069
  (−$51.86). The broker BTC position was flat; fills plus posted BTC fees still
  differed from the position by −0.000024511 BTC. The journal window is
  incomplete. Keep this number labeled provisional; no closed-lot FIFO ledger
  or certified realized P&L is available.
- Public UI shows the provisional value, cash/mark/fee breakdown, active BTC
  position, order counts, and a per-order explanation with its quote inputs.
  It no longer shows account-wide equity, AAPL or the research tables. Its
  order count is explicitly “orders with fills”; this is not a count of
  matched round trips or profitable trades. Vercel builds `846c39a` and
  `165bdb1` tightened stale status to two existing five-minute heartbeats,
  improved mobile readability and fixed a wrapped logo. Visual and accessibility
  checks confirmed current data, order reasons and the corrected mark.
- Current live rule remains `quote_cross_30s_v1`, BTC/USD only. The public page
  check at 12:31 displayed 498 orders with fills, 1,095 broker fill rows, 228
  buy orders, 270 sell orders and 159 order submissions on the UTC date; the
  separate signed API snapshot at 12:31 contained 645 total bot order rows.
  These counts describe active order flow and are not matched round trips.
  This is already high enough activity for data collection; more order
  frequency is not a substitute for evidence after spread and fees. The
  current policy has no established edge. The selected order trigger was
  6.030 bps, while the public Alpaca first-tier schedule lists 15 bps maker or
  25 bps taker on each crypto transaction. Those are not a paired trade
  comparison, but they show why the trigger is not itself proof of a profitable
  round trip. Alpaca says crypto fees are charged in the credited asset and
  posted end-of-day, so same-day totals can be incomplete ([fee schedule](https://docs.alpaca.markets/us/docs/crypto-fees),
  [activities API](https://docs.alpaca.markets/us/docs/account-activities)).
- Review gaps: the monitor still lacks matched entry/exit round trips with
  per-trade realized P&L. Add these only after a chronological FIFO ledger
  correctly assigns USD and BTC fees, proves the starting inventory and closes
  the −0.000024511 BTC reconciliation gap. Do not widen symbols, size or rule
  authority before causal executable-price replay beats the baseline after
  spread, fees and latency. Candles/Murphy/Markov are descriptive or shadow
  only; this 30-second Alpaca paper loop is not HFT.
- Final verification after the last UI markup change: web tests 11/11, TypeScript
  typecheck and Next production build passed. Earlier in this turn, Python
  exporter suite passed 32/32. No order-authority code or order-size settings
  changed.

## 15:36–16:00 UTC follow-up — fixed EMA replay and capture audit

- Dublin's `jsbot-paper.service`, Alpaca/HIP capture, five-minute, Markov and
  telemetry timers were active at 15:31:56 UTC. The broker exporter read-only
  dry run at 15:36:43 UTC returned mode `PAPER_ORDER`, complete order/fill/fee
  pagination, 728 bot orders, 1,166 fills, 996 posted fee rows and attributed
  fees. The source journal is incomplete. Filled cash delta was
  −$129.223655561460153069; the BTC position mark was $99.913851; posted USD
  fees were −$25.76 and posted BTC fees were −0.000281995 BTC. The exporter’s
  provisional cash-plus-mark after posted USD fees was **−$55.069804561460153069**.
  BTC inventory still differs from fills plus posted BTC fee activity by
  −0.000055123 BTC. One BTC position remains open, so this figure is not
  realized, fully reconciled or final net P&L. No API keys were read or
  displayed; the first dry-run invocation used the wrong Python interpreter
  and failed before the correct read-only service interpreter was used.
- Added `research/executable_ema_replay.py`, a research-only replay for the
  fixed Pattern Forge EMA 20/50 display rule. It consumes first-seen bars as
  received, ignores later bar revisions, requires complete timeframe groups,
  executes at the first subsequent captured BTC quote, crosses ask/bid and
  charges the published 0.25% tier-one taker fee per side. This model still
  omits broker submission latency, queue, fill probability, partial fills and
  impact; it grants no order authority.
- Replay input contained 269,803 captured BTC quote events and 3,274 first-seen
  minute bars across 27–29 September; 35 updated bars were ignored. The 1m
  candidate returned −2.771% over 4 round trips on the partial 27 September
  session, −7.054% over 12 on 28 September, and −3.641% over 7 through the
  29 September checkpoint. Same-start buy-and-hold returned −0.889%, −1.708%
  and −0.770%. The 5m replay had two round trips on 28 September at −1.298%
  versus −0.727% buy-and-hold; it had no warmed 5m signal sample for 29
  September. The 30m/60m/4h bars did not yield 50 contiguous bars for the
  frozen EMA warm-up (maximum runs 30/14/3). No candidate showed an edge.
  Daily sessions are normalized independent unit-capital experiments, not
  account returns, and the short sample is not statistical validation.
- The initial replay exposed a timeframe-slot spacing error before these
  reported results; it was corrected, regression-tested and rerun. All 40
  Python tests pass. No order-policy, sizing or production VPS code changed.
- Fixed `research/stream_audit.py` after the existing parser rejected Alpaca
  timestamps with variable fractional precision. It now processes adjacent
  capture files as a continuous stream and resets reconstructed books at
  observed socket-session changes, not midnight file rotation. The combined
  audit found 616,825 BTC order-book updates, 1,976 trades, 271,883 quotes,
  3,286 minute bars and 35 bar revisions; among records with session metadata,
  seven socket sessions were observed, with nine full-book reset frames. It
  reported no crossed quotes/books, invalid quotes/bars, or sequence gaps in
  the records carrying sequence numbers. Some legacy records lack session IDs
  or sequence numbers, so whole-capture sequence continuity is not proven.
  The captured median top-quote spread was 3.034 bps; median reconstructed
  book spread was 2.784 bps. The roughly 45 ms event-to-receipt timestamp
  difference is not calibrated one-way network latency.
- Next: keep the current bounded paper rule unchanged while measuring its
  broker-backed results; develop a chronological, event-time order-book/trade
  flow candidate using the captured `o`/`t` data; test it on untouched later
  sessions with exact ask/bid and fees. Resolve the BTC quantity residual and
  FIFO fee attribution before presenting realized P&L. Do not promote a signal
  unless it survives a frozen out-of-sample test after costs and operational
  latency.

## Next verified steps

1. Build a chronological, fee-currency-aware BTC lot ledger. The 17:41 UTC
   snapshot's 0.000357864 BTC gross-fill-to-position difference is within
   0.000000280 BTC of the published expected buy-side fee on all bot buys, but
   actual fee activities stop at 06:51 UTC. Verify subsequent fee postings and
   starting inventory before displaying realized P&L per round trip.
2. Keep the quote-cross rule unchanged for the moment. Capture candidate,
   broker-accepted, fill and cancel counts separately; evaluate net executed
   outcomes with fees, spread and time-aligned quote data before changing its
   trigger or increasing order size.
3. Keep candles, Murphy context and Markov shadow read-only until a frozen
   point-in-time evaluation beats a baseline on executable after-cost outcomes.
   Keep non-BTC Alpaca and Hyperliquid instruments outside order authority.
4. Treat the payload limit as a scaling boundary. If the compact full-history
   snapshot approaches it again, split history into signed date pages rather
   than silently dropping older trades.

## 16:42–16:59 UTC follow-up — trade-flow screen and fresh health check

- Dublin's `jsbot-paper.service`, Alpaca market capture and Hyperliquid
  capture were active at 16:59 UTC. The 29 September Alpaca capture was still
  receiving events. The Markov shadow file also advanced; its latest public
  five-minute analysis still has no probability and explicitly has
  `orderAuthority: false`. The active order rule remains
  `quote_cross_30s_v1`; no policy, sizing, endpoint or risk limit was changed.
- The signed public monitor snapshot at `2026-09-29T16:59:18.180400Z` had 760
  bot order rows, 1,212 fills, 735 exact decision-history rows, complete
  broker order/fill/fee pages and an incomplete local journal. Broker statuses
  were 289 filled and 471 canceled, with no currently open order. Posted fees
  total −$25.76 USD and −0.000281995 BTC across 996 activities; the latest
  activity was 06:51 UTC. The current 0.000353877 BTC position was marked
  $29.373727. Bot fill cash delta was
  −$59.919081352150153069 before fee activities. Cash delta plus position
  mark minus posted USD fees is a **provisional −$56.305354352150153069**,
  not realized or fully reconciled P&L. Bot fill quantities minus sells and
  current inventory leave a 0.000350215 BTC difference; this exceeds the
  posted BTC fee quantity by 0.000068220 BTC. Do not subtract the BTC fee
  value again from marked inventory, and do not label the account P&L verified
  until the journal and quantity/fee reconciliation close.
- Added `research/trade_flow_screen.py` and synthetic tests. The source feed
  confirms `tks` is buyer/seller taker side. A read-only export from Dublin
  contained 276,190 BTC quote events and 2,001 trade events between
  27 September 07:28 and 29 September 16:42 UTC; the compressed local data
  digest is recorded in `POLICY-ATTEMPTS.md`. The test folds are 28 September
  and the partial 29 September session, after training on earlier dates.
- The frozen 90th-percentile positive buyer-flow threshold was 1.0 in both
  folds; because ties remain selected it retained 88.59% and 88.25% of
  training positives. It is not a selective top-decile rule in this sample.
  Thresholded long-only trades averaged −52.64 to −53.31 bps net over 1m/5m
  on the two test dates and had zero winning trades at those horizons. At
  30m the mean remained −50.65 to −52.96 bps and only one of 67 trades won.
  A separate long/short directional diagnostic also had zero net winners in
  all six fold/horizon cells, but its shorts are hypothetical and not
  authorized for this Alpaca paper account.
- The screen buys at captured ask and sells at captured bid, then applies the
  published tier-one 25 bps taker fee per leg. Its fills are still optimistic:
  it omits submission/acceptance, queue, impact and actual latency. Some
  1m-signal quote waits reached 114.6 seconds, so captured quotes are not a
  substitute for fill modeling. Reject this attempt; keep the live paper rule
  unchanged. The short reused sample cannot establish an edge or live
  profitability.
- The full Python suite passes 50/50, including the new trade-flow, compressed
  capture and Markov directional-fee tests. Before any later policy change,
  continue genuinely future captures and require a frozen signal to beat
  executable after-cost baselines with reconciled broker fills.
- Scored the live read-only Markov journal through 16:55 UTC against model
  hash `c5ba22a1...2e99c0`: 545 predictions, 544 labels, one pending label;
  median lead 293.57 seconds. Brier was 0.25127 versus 0.24999 for the frozen
  base rate. Model-sign directional midpoint return averaged +0.57 bps, was
  positive on 51.29% of labels, and cleared the 50 bps fee-only hurdle only
  twice. These are midpoint labels without spread or fill evidence; keep the
  model shadow-only. The scorer now reports directional return and the
  fee-only count explicitly; its regression test passes.
- Replayed the frozen EMA 20/50 rule over the full captured universe of 15
  USD crypto symbols: 1,181,731 quotes, 36,285 first-seen bars and 148 ignored
  bar revisions, through 17:03 UTC. Across the 30 1m symbol-day test sessions,
  median normalized return was −4.897%; only 7 sessions made money and no
  symbol both made money and beat the same-start baseline on both dates. The
  5m screen had only 14 round trips across 17 valid sessions; no symbol passed
  both dates. There were no 30m signals because no symbol had 50 contiguous
  30m bars. The isolated 5m ARB gain (+4.84% from one round trip on the partial
  29 September session) followed a −2.36% one-trade loss on the prior day.
  Freeze all 15 symbols and horizons for future shadow measurement; do not
  select ARB or any other winner from these already-inspected sessions.

## 17:17–17:21 UTC health refresh

- Dublin's bot, Alpaca capture and Hyperliquid capture services remain active;
  the capture and event journal were still advancing at 17:21 UTC. Latest
  signed monitor snapshot (`2026-09-29T17:20:20.121357Z`): 768 bot orders,
  1,223 fills, 743 decision-history rows, complete order/fill/fee pages,
  incomplete local journal, 291 filled / 477 canceled and no open order.
- The open BTC position was 0.000235512 BTC, marked $19.571134. Fill cash
  delta before fees was −$50.381176320610153069. With the posted −$25.76 USD
  fee activities, the provisional cash-plus-mark difference was
  **−$56.570042320610153069**. This is not realized or fully reconciled P&L.
  Gross bot fill quantity minus sells and current inventory left 0.000353052
  BTC unexplained; after the posted 0.000281995 BTC fee quantity, the
  unresolved difference was 0.000071057 BTC. Fee activities have not advanced
  past 06:51 UTC.
- Current monitor's five-minute summary says trend `falling`, probability
  `null`, `orderAuthority: false`; the last order still came from
  `quote_cross_30s_v1`. Its reported 6.744 ms receive-to-decision time is a
  local processing interval, not end-to-end exchange or broker latency.

## 17:28–17:34 UTC follow-up — actual fill markout refresh

- Dublin's bot and both market-capture services stayed active. The signed
  snapshot at `2026-09-29T17:33:15.125403Z` had 772 orders, 1,229 fills,
  747 decision traces, complete order/fill/fee pages, an incomplete journal,
  293 filled and 479 canceled orders, and no open order. Fees remained
  −$25.76 USD plus −0.000281995 BTC; no fee activity had posted since 06:51.
- The broker position was 0.000719715 BTC, marked $59.905392. Fill cash delta
  before USD fees was −$90.783862357990153069; adding the position mark and
  subtracting posted USD fee activities gives the **provisional
  −$56.638470357990153069** cash/mark change. It is not realized P&L: the
  journal is incomplete and the gross-fill/position difference is
  0.000356064 BTC. The posted BTC fee quantity accounts for 0.000281995 BTC;
  0.000074069 BTC remains unreconciled. Do not deduct the BTC fee value twice
  from actual marked inventory.
- Added UTC-date scoping to `research/public_order_markout.py` and gzip
  capture reading to the quote audit. On 421 fill rows dated 29 September,
  212 distinct filled orders had future quotes for all three horizons.
  Fee-aware hypothetical close/buyback markouts were −51.40/−51.52/−51.30 bps
  median at 1s/5s/30s; no order was positive after modeled fees. Median waits
  for the first quote after the horizon were 2.31–2.63 seconds; maxima were
  31.67–35.67 seconds. This is a quote-based hypothetical markout, not paired
  realized trade P&L or a true network-latency measurement.
- The Markov journal through 17:30 UTC had 552 predictions and 551 labels;
  its Brier score remained worse than base rate (0.25113 vs 0.24999). Mean
  model-direction midpoint return was +0.61 bps, and only 2 of 551 labels
  cleared the 50 bps fee-only hurdle. Keep it read-only.
- The bot remains on `quote_cross_30s_v1`, BTC/USD only, with no policy or
  risk-size changes. New quote, date-scope and snapshot immutability tests
  were added; the full Python suite passes 53/53. These research-tool changes
  are local and do not alter VPS order logic.

## 17:40–17:47 UTC follow-up — fee audit, longer markouts and book imbalance

- Dublin's `jsbot-paper.service`, Alpaca capture and Hyperliquid capture were
  active at 17:40 UTC; the paper mode was `PAPER_ORDER`. The signed snapshot
  generated at 17:41:04 UTC contained 774 bot orders, 1,234 fills, 749 exact
  decision traces, 294 filled and 480 canceled orders, no open order, and an
  incomplete public journal. The BTC position was 0.000718 BTC marked
  $59.662154. The most recent broker order was a canceled partial buy whose
  actual filled quantity was already reflected in the broker position.
- Fees were fully paginated but only posted through 06:51 UTC: −$25.76 USD and
  −0.000281995 BTC across 996 attributed activity rows. Fill notional cash
  delta before fee activities was −$90.791899171540153069. Combining it with
  the current mark and posted USD fees gives an **indicative −$56.889745**
  bot cash-plus-mark change before any fees posted after 06:51; it is not
  verified net P&L or a closed-trade result. The gross BTC fill difference is
  0.000357864 BTC. At the official 0.25% buy fee it predicts 0.0003575835625
  BTC of fee; the remaining quantity difference is 0.0000002804375 BTC.
  This is consistent with buy-side fees, but the fee activity cutoff and
  incomplete journal still block a complete reconciliation. The broker's
  current BTC position already reflects any asset-denominated fees: do not
  deduct them a second time.
- Extended the actual fill-to-quote markout to 1m, 5m and 30m (in addition to
  1s/5s/30s). Across 428 fill rows on 29 September, the fee-aware hypothetical
  markout medians at 1s/5s/30s/1m/5m/30m were −51.43/−51.52/−51.35/−51.62/
  −52.37/−53.68 bps. No one of 215 orders was positive after modeled fees at
  horizons through 5m; 10/206 were positive at 30m. Late 30m observations are
  censored (20 fills had no future quote). This hypothetical close/buyback
  model excludes submission latency, queue, impact and actual fee-tier
  confirmation; it is not realized trade P&L.
- Ran the read-only top-of-book imbalance screen on 638,416 order-book deltas
  and 281,568 quotes, with 27–28 September training and 29 September holdout.
  A frozen 90th-percentile positive-imbalance threshold selected 64 non-
  overlapping 1m and 12 non-overlapping 5m trades. Mean gross after spread was
  −3.35/−2.59 bps; mean after fee was −53.27/−52.51 bps, and none of the 76
  trades won after fees. No edge found; the chosen percentile and sample are
  exploratory, the dates have already been examined, and the replay omits
  order submission/queue/impact. Added gross-before-fee metrics and gzip
  capture reading to the research-only screen; four focused book-screen tests
  passed.
- Markov shadow through 17:40 UTC had 554 predictions, 553 labels and one
  pending label; Brier 0.251105 versus 0.249991 for base rate, mean
  directional midpoint +0.601 bps, 51.54% positive, and only 2 labels above
  the 50 bps fee-only hurdle. Keep read-only.
- No OCaml order logic, sizing, endpoint or policy changed. The current
  evidence rejects both the taker quote-cross and top-book-imbalance attempts
  for an executable net edge. Continue collecting a frozen prospective
  sample; do not tune against 27–29 September again. The full test suite passed
  54 tests before the final fee-output clarity fix; that fix and its regression
  test are included in the final 55-test verification. Research changes are
  committed locally after verification; no production deployment was made.

## 17:47–18:09 UTC follow-up — prospective cut and measured paper latency

- Dublin's paper orderer, Alpaca collector and Hyperliquid collector were
  active at 18:06:40 UTC. The signed snapshot at 18:06:33 UTC had 781 bot
  orders (296 filled, 485 canceled), 1,241 fills and 756 exact decision
  traces. Broker order/fill/fee pages were complete; the public journal was
  incomplete and there was no open order. The bot held 0.000240078 BTC marked
  $19.986768 in `PAPER_ORDER` mode.
- **Prospective candidate:** froze the historical top-book positive-imbalance
  90th-percentile threshold and set a strict holdout cutoff at 17:47 UTC. The
  archived book capture reached 18:08:05 UTC, yielding 22 later minute
  samples. Only one signal crossed the threshold, at 18:00 UTC; it qualified
  for both 1m and 5m. The zero-delay reference returned +19.70/+22.80 bps after
  spread but before fees, then −30.33/−27.25 bps after 25 bps taker fees per
  leg. It is a single event, not statistically useful evidence by itself.
- **Latency:** parsed 297 same-day service timing rows. Quote receipt to HTTP
  submit was median 1,347ms and p90 1,694ms; HTTP round trip was median 330ms
  and p90 366ms. Exact broker decision-to-first-fill timing across 565 traced
  filled orders was median 1,667.728ms, p90 2,062.462ms, p95 2,254.135ms and
  maximum 4,156.346ms. Of 756 traced orders, 191 had no fill (25.3%) under the
  deployed rule; this is context only and does not estimate candidate
  fillability. These are paper broker timestamps, not real-market latency.
- Replayed the one prospective signal after the measured median and p90 paper
  fill delays. The next captured ask arrived 3.111s after signal time in both
  scenarios. Gross returns after spread were +14.83/+16.91 bps at 1m/5m, then
  −35.18/−33.11 bps after modeled fees. The sample still assumes a fill at
  the first later quote; it does not include candidate-specific fill
  probability, queue or impact. The replay now retains per-trade decision,
  entry and exit timestamps, prices, delay and returns.
- Refreshed the signed monitor snapshot at 18:06:33 UTC. From the flat-BTC
  anchor at `2026-09-27T18:54:40.287202Z`, 1,158 later bot fills had a
  `−$49.780201` filled cash delta; current BTC mark added $19.986768 and posted
  USD fees were `−$25.76`, giving an indicative `−$55.553433` cash-plus-mark
  delta before fees after the activity cutoff. Fee pages covered 996
  attributed rows but the last activity remained 06:51:44 UTC. Sell fills
  after that cutoff totaled $2,581.222937; **I estimate** another $6.453057
  at the published 25 bps rate, so this marked delta would be about `−$62.01`
  if that fee estimate applies. It is not verified P&L: fees are stale, BTC
  remained open, and the public journal was incomplete. Gross BTC quantity
  difference was 0.000359069 BTC, within 0.000000281 BTC of the expected
  0.000358788 BTC buy fee; do not deduct that asset fee a second time from
  marked inventory.
- Markov shadow fetched through 18:00 UTC had 557 predictions and 556 labels,
  one pending label. Brier remained worse than the frozen base rate (0.251314
  vs 0.249989); mean model-direction midpoint move was +0.577 bps, 51.26%
  positive, with only 2 labels over the 50 bps fee-only hurdle. Keep it
  read-only.
- Added UTC holdout cutoff and measured entry-delay parameters to the
  research-only book screen, plus per-trade trace output. Tests enforce strict
  cutoff chronology, invalid-latency rejection, and the delayed-quote entry
  and exit horizon. The full test suite passes 59/59; `compileall` and
  `git diff --check` pass. No OCaml trading logic, risk limits, or production
  deployment changed; no candidate has an after-cost edge yet.

## 18:25–18:28 UTC follow-up — expanded prospective sample and flat inventory

- Rechecked Dublin at 18:27:49 UTC: paper orderer, Alpaca capture and
  Hyperliquid capture were all active. The signed snapshot at 18:27:26 UTC
  contained 788 bot orders (298 filled, 490 canceled), 1,247 fills and 763
  decision-history rows. Order/fill/fee pagination was complete; the public
  journal remained incomplete. BTC inventory was flat and there was no open
  order in the snapshot. Mode remained `PAPER_ORDER`.
- Replayed the frozen prospective imbalance policy from its unchanged
  17:47 UTC cutoff through captured book events at 18:08:05 UTC: 41 minute
  samples, three selected 1m trades and one selected 5m trade. All three 1m
  trades lost after modeled spread and two fees at the observed p50/p90
  paper-fill delays (mean −48.44 bps); the single 5m trade lost −33.11 bps.
  This small partial-day slice does not establish a general statistical
  rejection, but it confirms no after-cost edge to date. No threshold or
  cutoff was changed.
- Refreshed actual fills through the public snapshot at 18:27:57 UTC. Of 441
  fill rows dated 29 September, 223 orders had usable marks through 5m and 219
  at 30m; seven late fills lacked a 30m quote. Median hypothetical net
  close/buyback marks after modeled fees were −51.47/−51.52/−51.47/−51.54/
  −52.33/−53.83 bps at 1s/5s/30s/1m/5m/30m. No order was positive through
  5m; 10/219 were positive at 30m. These remain overlapping quote-based
  hypotheticals, not realized round trips.
- From the same flat-BTC anchor at 18:54:40 UTC on 27 September, 1,164 later
  bot fills generated a `−$29.913506` cash delta and ended flat. Posted fees
  were still `−$25.76 USD` plus `−0.000281995 BTC`, with last activity at
  06:51:44 UTC. Sells totaling $2,641.088836 after that cutoff imply an
  **estimated** additional $6.602722 at 25 bps; posted plus estimated fee
  adjustment gives about `−$62.28` for the anchored cash-flow interval. The
  estimate is not a broker posting, and the public journal is incomplete, so
  this is not verified P&L. Buy fills of 0.137230082 BTC less sells and zero
  current inventory leave 0.000343331 BTC; the published 25 bps buy fee
  predicts 0.000343075 BTC, a `0.000000256` BTC residual. The asset fee is
  already reflected in executed quantities and must not be deducted twice.
- Markov shadow through 18:25 UTC had 563 predictions and 562 labels. Brier
  remained worse than the frozen base rate (0.251212 vs 0.249990); mean
  directional midpoint move was +0.580 bps, with only two labels above the
  50 bps fee-only hurdle. Keep it read-only.
- No production code or paper order rule changed. Continue the frozen
  prospective evaluation on later captured sessions. No tested candidate has
  cleared spread, fees and the observed paper-path latency so far.
