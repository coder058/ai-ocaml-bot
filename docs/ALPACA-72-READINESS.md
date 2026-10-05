# Alpaca execution readiness and repeated audit

## Scope and completion criteria

The user requested broker paper execution for the existing 69 stocks/ETFs and
BTC/ETH/SOL, each analyzed at 1m/5m/30m/1h/4h. That is 72 instruments and 360
correlated analysis slots. The previous research watchlist also contained 19
Hyperliquid perpetuals: its 455 slots are not 455 executable broker products.
The deployed scanner now selects Alpaca only; the public Hyperliquid capture
and its older research evidence are retained separately. No internal execution
simulator is being introduced.

Readiness requires actual data, current analysis, an explicitly enabled and
tested paper route, durable intent, broker acknowledgement, reconciliation and
owned exit handling. A synthetic passing candidate for every slot tests routing;
it does not demonstrate actual signals or fills on all instruments. Independent
frames do not each receive a separate position in the same underlying.

The expanded objective also requires AI decisions and calibration, full stated
pattern coverage, portfolio risk, measured lifecycle latency, net accounting,
professional monitoring, reproducible evaluation and a verified FX practice
connection. Finishing a smaller paper lifecycle does not finish that objective.

## Framework decision — 5 October 2026

- [hftbacktest](https://hftbacktest.readthedocs.io/en/latest/): supports L2/L3
  reconstruction, queue/fill and latency research. Its documented live prototype
  venues are Binance Futures and Bybit, Rust only. It does not provide our current
  Alpaca integration or missing stock L2/L3 data.
- [NautilusTrader integrations](https://nautilustrader.io/docs/latest/integrations/):
  useful event/reconciliation architecture and Rust/Python research/live engine;
  Alpaca is absent from the current published supported-adapter list. A migration
  would require broker/OCaml integration work, not automatically solve it.
- [QuantConnect Alpaca](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/alpaca):
  supports an Alpaca paper environment. Its hosted deployment needs a live node;
  the current [free-plan table](https://www.quantconnect.com/pricing) does not
  include hosted brokerage deployments. Self-hosted LEAN is a separate integration
  option, with C#/Python strategy APIs and its own setup/data requirements.
- [HFTS](https://hfts.app/): research replay; published free tier has one day per
  test, limited runs and no network access. Vendor timing precision is not our
  measured broker latency. Its page describes L1 data and L2/L3 as future work.
- Paperinvest: direct home/pricing/docs requests failed during this check.
  Search-cached pricing described five daily free trades and no free WebSocket
  data, but current terms could not be verified. Do not promise unlimited free
  execution or a verified connection.

Decision: retain the existing OCaml/Alpaca broker paper route for this milestone.
Use other engines only for a measured, separate research benefit or a verified
adapter improvement. No accounts, subscriptions or mainnet wallets were added.

## Verified changes and attempts — 12:30–13:00 UTC

- Actual broker account was ACTIVE, trading unblocked, crypto ACTIVE; observed
  non-marginable buying power 99,355.08 USD. This is a dated account reading,
  not a strategy capital allocation or P&L result.
- Existing stock entries and ETH/SOL confluence entries were disabled; legacy BTC
  continued with quote_cross_30s_v1. An initial flat handoff failed because an
  actual BTC entry/pending intent appeared. The legacy owner was restored; no
  position was silently adopted or liquidated.
- Added a legacy entry-drain gate, retaining pending reconciliation and owned
  exits. At 12:50:13.057033Z broker BTC position/open orders and local owned/pending
  files were clear. Disabled the predecessor, persisted a flat handoff marker
  with directory fsync, and enabled BTC inclusion in the multiframe observer.
  Its new-entry gate remains disabled at this checkpoint. The new unit conflicts
  with the predecessor; the predecessor also refuses startup after handoff.
- The 12:46 scan verified 72 markets, five frames, no reported transport errors,
  and 14.985687003936619 seconds through evidence/cache writes. This single scan
  excludes order submission and fills; it is not a latency distribution or HFT.
- Preserved the actual frozen descriptive analyzer with SHA-256
  e6b758316d3d5d0b84b26933772b23a194affa6f374e132614d6840fb620f6a9
  in a separate private executable before modifying linked OMS modules. The
  scanner's explicit --engine pin retains the previous prospective analysis
  identity. No prior feature/label rows were repaired or relabeled.
- Replaced the guessed ten-stock capacity with 69 stock positions, one per
  requested ticker, while retaining the user's $100 automatic baseline and router
  buying-power/ownership checks. Batched owned-exit quotes. The eleven-position
  synthetic regression actually reaches the serialized router; this is not a
  statement that eleven real positions exist.
- Corrected a verified code gap: stock/multiframe durable writes could outlive
  preflight quote freshness. Both routers now recheck immediately before POST,
  retain the attempted identity, write NOT_SENT and send nothing when it expires.
  Real OCaml tests injected six-second fsync stalls beyond the inherited five-
  second guard; both showed durable DECISION/NOT_SENT, zero HTTP orders and no
  same-bar retry. These are synthetic engineering failures, not market latency.
- Corrected the exporter health model so retiring a legacy process cannot hide
  a healthy, currently reporting paper timer. Stale/future/missing reports remain
  unverified. Private unit aliases are not published.
- Observed live crypto latest-quote ages at 13:00:29: BTC approximately 0.92s,
  ETH 6.32s, SOL 9.01s. Thus the inherited, explicitly uncalibrated five-second
  source-age guard can block legitimate latest-quote responses. Do not quietly
  loosen it or misreport old source timestamps as fresh; measure this separately.
- Free IEX latest quotes were accessible. Live consolidated SIP returned HTTP
  403; delayed SIP was accessible and its samples were fifteen minutes old.
  Delayed quotes are not eligible replacements for a fresh execution reference.

## Evidence checks completed so far

- Dublin full OCaml build and dune unit checks passed after initial handoff work.
- Revised real-binary tests: stock scheduler 10, multiframe router 10, exporter
  25 passed, including uncertain broker outcomes, identity/ownership conflicts,
  partial fills and deliberately delayed durable writes.
- Earlier stock router lifecycle tests: 10 passed. Pipeline regression tests:
  nine passed. Re-run changed components after subsequent edits.
- Frontend 46 tests and production build/typecheck passed, including all 360
  displayed routes under synthetic enabled-runtime conditions, while risk remains
  unknown and no broker orders are invented. Actual browser deployment must still
  be checked after the localhost restart.
- Full-symbol pure-policy coverage actually passed on Dublin: all 72 requested
  products and 360 frame routes, no broker calls. Full dune/build gate passed.

## Incremental calculation and input provenance — 13:18–13:39 UTC

- Implemented exact per-frame native-input/calculation fingerprints. Returned
  revisions, native closure buckets, broker calendar/session changes and actual
  analyzer changes invalidate reuse. Corrupt or future cache entries recalculate.
  Current ages refresh without retaining an old freshness claim. The frozen
  executable is unchanged; non-dirty placeholder arrays are discarded internally.
- Full/optimized parity passed against the real OCaml executable for synthetic
  unchanged/revised inputs, missing closes, future candles, session transitions,
  calendar changes, rollback and persisted/corrupt caches. Extension parity also
  passed with refreshed cross-frame/primary contexts. Every Murphy panel refreshes;
  this does not add new Murphy strategies or change the frozen candidate rule.
- A private rollout initially omitted the Alpaca-only environment and compared
  the old 91-product scope (two passes, no differences). Corrected the environment
  explicitly; the 13:26 snapshot verified exact full/incremental parity for all
  72 products/360 slots. Diagnostic double calculation is excluded from normal
  deployment. The scanner timer was temporarily stopped during this rollout and
  restored after the successful check; order/owned-exit timers were not stopped.
- Actual normal 13:32 scan computed 72 native and 72 extension frames, reusing
  288 of each. Total scan was 23.431893571047112 seconds. Opening-boundary scan
  13:30 took 55.08437746705022 seconds. Later 13:39 scan was
  21.666775942081586 seconds with the same 72/288 counts and zero reported errors.
  These varying individual scans do not demonstrate a controlled latency gain,
  p95, tick responsiveness or end-to-end broker timing. Original per-phase
  extension timing included calculation-cache publication; subsequent code
  separates `analysis_cache_write` without reinterpreting earlier timings.
- Separated cold/thin-history requests from warm instruments by actual retained
  start date and seed state. Otherwise one missing history forced every symbol
  in its batch to request the longest range repeatedly. Actual 13:37 1m equities
  batches contained 27 warm and 42 seed instruments, returning 78 and 2,808
  closed bars respectively. No absent candle was invented or gap ignored.
- Every new slot has an input digest and actual native fetch/analysis clocks.
  Candidate inputs are retained privately with file and directory fsync; prior
  revisions cannot overwrite the content-addressed archive. Future durable
  intents retain this reading; exact joined broker evidence projects only actual
  hashes. Older orders receive no reconstructed native-input proof.
- Actual BTC/USD 5m candidate replay at 13:37 verified its retained input SHA
  `4703588ef8bc471ef7167e514d34b54c38497bc124fa86c3835a10791b060dbe`, original
  executable SHA and all native output fields against the current recorded
  reading. Ubuntu could read the retained archive. This candidate was not an order.
- Current 13:39 coverage: 262 ready, 17 candidate, 53 warming, 23 stale, five
  no-data. Those five were FXB 1m/5m, FXC 1m and FXA 1m/5m on IEX. All 360 slots
  are represented, but only ready/candidate data states are warmed/current;
  they do not imply passed execution risk gates or calibrated probabilities.
- Six incremental, three archive, 12 Murphy, ten transport and 26 exporter tests
  passed on Dublin; 47 frontend tests and production build/typecheck passed.
  The exporter test initially used a venv without cryptography; reran successfully
  with the installed system Python dependency rather than hiding the failed run.
- Latest observed stock scheduler was OBSERVE/new entries false, zero router
  invocations; multiframe was PAPER_EXPERIMENT/new entries false, exclusive BTC
  owner active. New-entry arming profiles are prepared but not installed. Execution
  validation, portfolio risk and actual broker stop/exit proof remain required.

## Open audit register

This register contains unresolved requirements, not a claim that these are the
only possible defects. No zero-error or perfection claim is permitted.

| ID | Requirement / verified gap | Next proof required |
|---|---|---|
| U1 | BTC candle routing exists after handoff; new entries still disabled | Actual candle-derived order, prior evidence, broker ack and reconciled ownership |
| D1 | Incomplete/stale/warming slots, including absent IEX histories | Every requested symbol/frame listed with actual seed, last close, source and cause |
| D2 | Revision-aware calculation reuse deployed; minute polling and cache/transport cost remain | Profile separated phases and integrate event-driven receipt without changing causal eligibility |
| E1 | Stocks remain observation; fractional paper lifecycle unverified in regular session | Executable quote/cost/risk review, exact order/fill evidence and owned exits |
| F1 | Actual spot FX execution unavailable | Supported practice catalog, authorized account, adapter and broker acknowledgement |
| A1 | Markov is descriptive shadow; actual related data inventory exists, intended digest identity/model remain incomplete | Data provenance, defined executable target, chronological baseline/calibration comparison |
| A2 | $50/$500 confidence tiers lack calibration | Out-of-sample calibrated probability and an explicit sizing rule; retain $100 baseline meanwhile |
| R1 | Portfolio loss/correlation/disconnection controls incomplete | Tested aggregate reservations and actual owned risk; validate fractional broker stops and their expiry |
| L1 | Lifecycle latency incomplete; individual scan times vary substantially | Measured candle/receipt/decision/persist/send/ack/fill timestamps per route |
| P1 | Exact cohort crypto fees not attributable from current broker activity fields | Preserve gross/net distinction; recover exact links or state unavailable without guessed allocation |
| M1 | Monitor needs actual deployed verification and clearer operational hierarchy | Browser/API inventory, connection, new orders and factual evidence; previous history reset retained |
| V1 | Full Murphy and predictive edge not established | Explicit finite strategy catalog, reproducible tests and honest public limitations |

Review this register against code, tests, live services and actual broker records
after each completed change. Remove a gap only when its stated proof exists.
Paper execution quality and paper results do not establish live profitability.


## Original native replay and data inventory — 14:17 UTC

Automatic entry routers now require the retained native archive and original
executable to reproduce every native output field. New entries remain paused.
Managed exits retain their original ownership handling; older orders are not
retrospectively certified. Real SPY 1m replay, hostile input/corrupt archive
checks and real router fake-HTTP lifecycle tests passed; exact evidence and
initial fixture failures are in EXECUTION-TRACE-WORK.md.

Actual related recordings/news metadata are inventoried in
RELATED-DATA-INVENTORY.md. September news receipts cannot be used for decisions
in May–August recordings. This resolves part of data discovery, not A1/A2 AI
training/calibration or strategy deployment. CI for incremental commit 03160b1
passed both jobs in run 37320658710. No completion, edge or profit claim.


## Shared account cycle and actual owned exit — 14:38 UTC

Stock and crypto routers now serialize account cycles through the same POSIX
lock before HTTP or durable ledger work. Real cross-router kernel exclusion and
existing pending/partial-fill/exit regressions passed. This resolves concurrent
cycles on the current VPS, not R1 aggregate loss/correlation/reservation limits.

The existing owned SOL position closed by its local invalidation exit; a direct
broker read verified filled sell 0.831943285 at 119.39 and no remaining SOL
position. Exact pre-order/broker timestamps are retained in EXECUTION-TRACE-WORK.
New entries remain disabled. Paper execution is not live profitability evidence.


## Unresolved counterpart orders and current buying power — 14:46 UTC

New buys now fail closed when either owned cohort has unresolved durable orders
or unreadable counterpart state. Existing owned exits continue. Crypto rechecks
broker buying power before each possible entry instead of reusing the initial
balance after other actions. Six shared-account and twelve crypto runtime tests
passed; stock router/scheduler pending-gate regressions passed. This is a partial
R1 improvement, not an aggregate loss/correlation allocation or readiness claim.

The actual SOL exit is present in the localhost execution API with broker fill
and exact recorded reason. New entries remain disabled. Inspect final stock
session-read/freshness timing, broker stops and actual automatic stock lifecycle
before enabling a paper-entry profile. Broader AI/FX/evaluation scope is unchanged.
