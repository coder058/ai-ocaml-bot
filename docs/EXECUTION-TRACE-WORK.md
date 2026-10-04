# Eight-hour execution and trace work

## Current instruction and window

User requested at least eight more hours on 2026-10-04 at 19:36:49 UTC, and asked to continue until the bot is ready. Minimum follow-up window reaches 2026-10-05T03:36:49Z. Scheduled runs are opportunities for work, not eight hours of continuous completed development. Work inline, no subagents; preserve unrelated dirty files and Fly Brain.

Readiness means a tested and understandable engineering system, not profitability: every monitored frame has a truthful data/policy/routing state; enabled paper routes reconcile durable orders and owned positions, handle exits and failures, and show real pre-order evidence. Unsupported or uncredentialed products remain explicitly blocked. Do not promise every chart can place an order or guarantee an edge.

## Diagnosed first — actual 19:39 UTC snapshots

- 91 symbols x five frames = 455 analyses, not 455 separate broker products.
- 69 Alpaca equities/ETF: 345 frames; 340 regular-session closed, five no-data frames. Broker connected, account ready, next open 2026-10-05 09:30 New York; automaticStrategy=false and executionGateArmed=false. Existing stock router supports explicit requests and reconciliation, not an automatic candle strategy.
- 19 Hyperliquid HIP-3 instruments: 95 frames, public data only. No paper broker execution adapter or live wallet use.
- BTC/ETH/SOL: 15 frames. BTC uses its separate quote_cross_30s_v1 orderer, not the chart confluence rule. ETH/SOL confluence newEntriesEnabled=false. Owned exits/pending reconciliation remain active.
- Full frame states: warming 3, ready 88, stale 14, candidate 5, market_closed 340, no_data 5. Candidates were ETH 30m long, xyz:TSLA 30m long, xyz:AMZN 1h long, xyz:META 4h short and xyz:SILVER 4h short. These are frozen-rule descriptive candidates, not five available orders.
- OANDA practice connection status: connected=false, practice_credentials_missing. No credentials should be sent in chat. Pending optional account question remains; continue other work.
- OCaml Multi_paper enforces one active ticket per crypto symbol and ten tickets maximum; these are documented operational choices, not fitted portfolio rules. More timeframes do not automatically make independent positions. A current position count also excludes closed trades; old history was deliberately reset from the UI.
- Previously tested EMA short-frame crypto candidate failed modeled fees; see existing docs/POLICY-ATTEMPTS.md. Do not reactivate that failed configuration merely to inflate order counts.

## Step-by-step work queue

1. Build the current coverage audit for every symbol/frame: actual closed bar and reception, indicator/pattern availability, the exact frozen policy condition, current routing/gate state and explicit unknown or unperformed checks.
2. Show the audit in localhost: stage counts, filters, all 455 rows and chart detail. Trace factual evidence/rule outcomes and risk decisions; do not invent private thoughts or explanations after a trade.
3. Start a clearly dated new decision/order cohort. Preserve old broker audit files and current open inventory, while keeping old history hidden. Join new orders to their exact durable IDs and recorded quote/candle evidence; unknown evidence stays unknown.
4. Improve pre-submit trace completeness in the actual orderers, including reconciled ownership, quote time, size, stop/exit rule, pending state and broker acknowledgement. Persist evidence before POST; synthetic failures must prove recovery and no duplicate orders.
5. Design and test automatic stock/ETF scheduling against closed frames, calendar, $100 baseline, one owned instrument position, pending reconciliation and managed exits. AAPL remains protected. Existing data can prepare the route on Sunday; a closed session cannot be represented as live execution.
6. Evaluate frozen candidate policies chronologically, including actual executable quotes/costs and controls. Current forward-pattern audit supplies gross price labels only. Do not convert signed pattern detections into calibrated probabilities or $500 confidence bets.
7. Examine all five frames for all markets programmatically; treat missing/stale/warming data separately. Indicators run on closes; polling every second does not create a new 4h bar. Do not fabricate flat candles to force readiness.
8. Keep Hyperliquid mainnet public-only and spot FX blocked without a practice connection. Broker/testnet expansion requires an actual supported adapter and account; simulation must be identified as simulation.
9. Test, scoped commit, deploy Dublin, verify runtime and browser for each finished change. Keep localhost and Vercel-off state. Record results below each run. At the minimum window review remaining readiness work; continue feasible unfinished work without declaring ready from elapsed time.

## Next required verification

The monitor has 455 chart previews and full TA-Lib/Murphy detail, but no visible per-frame execution trace yet. Next milestone is truthful coverage and a new decision cohort, then a tested stock automation path. Broker history reset must remain preserved.

## 2026-10-04: execution trace milestone

- Added `/api/execution`, a whitelisted current-state projection of all 91 x five frame cells, and a localhost analysis/execution desk with route totals, candidate filter, instrument search and per-cell decision path. Unknown broker preflight remains unknown. It does not claim all candlestick/indicator functions drive entries.
- Preserved the positions-only API and old history reset. New orders are a separate cohort starting at the actual work-start clock, 2026-10-04T19:36:49Z. Fills join exact order IDs and matching symbol/side; no neighboring chart is used to explain a historical order.
- Exporter now retains actual journal timestamps for BTC and multiframe decisions. Whole-second journal stamps are represented as bounded one-second intervals, not invented subsecond precision. Retrospective, future or undated evidence is withheld.
- Verified in the browser: 455 matrix cells, ten paused ETH/SOL frame routes, 345 stock routes without automation and 95 public-only HIP-3 routes. Actual 20:03:08 UTC BTC buy showed broker filled quantity 0.001170294 and $99.99 captured fill notional, along with the earlier recorded quote cross. These are paper broker observations, not live profitability evidence. An earlier partial BTC entry appeared as partial/rest canceled.
- Verification: 34 frontend tests passed, TypeScript and production build passed; 16 exporter tests passed locally and on Dublin's system Python. The TA-Lib virtual environment lacks cryptography and failed the exporter import; the existing system-Python export runtime passed. No credential/package change was needed.
- Deployed only the scoped exporter change to Dublin and restarted localhost using the verified Next PID. Checked the actual legacy-named multi-paper timer; it is enabled and its service completed successfully. The absent newer unit alias is not evidence that the actual service stopped.
- Work remains: complete and adversarially test stock automation/owned exits, add actual pre-submit risk evidence, and evaluate execution-aware candidate policies before enabling new entries. Spot FX practice credentials and a Hyperliquid paper adapter remain unavailable.

## Stock scheduler milestone — 20:24 UTC

- Added a pure OCaml Stock_policy, checking all five frame boundaries and actual fresh source/receipt timestamps, selected frozen trend/shape, valid invalidation and source scope. Installed a scheduler that delegates to the existing serialized router rather than implementing a second POST path.
- New managed orders preserve exact deterministic identities, $100 baseline, one owned position per stock instrument and the existing uncalibrated ten-position operational limit. Owned exits precede entries; manual positions are not adopted, including after an earlier automatic position has closed. Exit triggers and fresh IEX quotes are rechecked at the router boundary.
- The router saves actual account/session/ownership/open-order/quote preflight evidence alongside its pending intent and DECISION event before POST. Acknowledgements and partial quantities use existing exact ownership checks. The exporter whitelists these facts and never publishes account IDs or secrets.
- Verification on Dublin: OCaml build and dune tests passed; all five stock frame boundaries checked; 18 real-binary synthetic tests passed (eight scheduler + ten existing router); 17 exporter tests passed locally and on system Python. Frontend 35 tests and final production build/typecheck passed after correcting an optional-status TypeScript guard.
- Actual deployment: backed up the known stock unit and replaced its check-only entry point with the scheduler in OBSERVE, supplying no --execute. Service succeeded at 20:24:54 UTC, minute timer active, session closed, new entries false, zero candidates/router invocations and no owned stock positions. This is not a live-market stock fill verification.
- Previous monitor commit d6f6e02 passed both public CI jobs in run 37231097355. Next: browser verification of the scheduler route projection, scoped commit/CI, and execution-aware prospective research. Automatic stock entries remain unarmed; their local stops cannot protect overnight gaps. No missing FX credentials or Hyperliquid signer was invented.
