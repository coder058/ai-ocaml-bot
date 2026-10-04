# Project review — 4 October 2026

## Verdict

This is a working OCaml paper execution and market analysis lab with meaningful engineering components. It is not yet a demonstrated HFT system, a validated AI trading agent, or evidence of a profitable strategy. The current signals are basic technical rules; the reliability and research evidence need work before a strong public presentation.

This review read the current implementation, documentation, research records, broker history, Dublin services and localhost monitor. It reran the checks listed below. It did not deploy a strategy, clear pending orders, or submit manual orders. Historical research results were inspected, not rerun. Snapshot counts and marks can change after this review.

## Current measured state

Source: read-only Dublin telemetry synchronized to `.local/telemetry.json`, analysis as of 2026-10-04T13:04:00Z, retrieved at 13:04:20.635272Z.

- Scanner: 67 instruments, five requested frames, no provider errors in this snapshot.
- Universe: 36 Alpaca crypto/USD, 12 equity/ETF instruments and 19 Hyperliquid HIP-3 instruments. These are different products and execution capabilities.
- New multi-frame experiment: 370 broker orders across 31 crypto symbols; 150 filled, 220 canceled. 151 orders have positive executed quantity because one canceled order was partially filled. These counts are not closed round trips or independent strategy observations.
- New experiment: 10 open tickets; two have unresolved pending exits.
- Stocks/ETF and HIP-3 rows are analysis only. The FX-like instruments verified are EUR, GBP and JPY perpetual contracts, not ten spot FX pairs. Legacy BTC execution remains a separate quote-cross policy.
- Localhost was down at review start. The existing launcher restored it and read-only SSH synchronization. The displayed snapshot at 13:03:58Z showed 1,660 lab orders with fills and 3,416 broker fill rows, including the legacy BTC rule.
- The same displayed snapshot showed an approximately -$205.04 provisional marked lab result, including posted USD fees. This is neither closed-trade realized P&L nor a strategy-separated performance report.
- Dublin services for paper execution, capture, scanner and multi-frame timer were active. The Vercel telemetry timer was inactive. A service exit marked successful does not mean every order succeeded.
- Dublin observed memory: 1,910 MiB total, 401 MiB used, 1,300 MiB available; disk 22% used. This observation does not justify buying more RAM. It is not a load benchmark.

### Data readiness

Source: frame status counts from the same 13:04 analysis snapshot. Ready below includes candidate readings. Market-closed rows are separate from missing data; the 12 listed instruments were outside their regular session.

| Frame | Ready/candidate | Warming | Stale | No data | Market closed |
|---|---:|---:|---:|---:|---:|
| 1m | 15 | 18 | 21 | 1 | 12 |
| 5m | 23 | 23 | 8 | 1 | 12 |
| 30m | 49 | 1 | 5 | 0 | 12 |
| 1h | 50 | 2 | 3 | 0 | 12 |
| 4h | 51 | 2 | 2 | 0 | 12 |

Requesting all five frames does not mean all instruments have usable data on all five. Short-frame adjacency/warmup and sparse venue candles remain material problems. No provider error is not equivalent to complete candle coverage.

## What is actually built

- Shared OCaml calculations: EMA20/50, Wilder RSI14, MACD12/26/9 and Bollinger20/2; doji, hammer, shooting-star and bullish/bearish engulfing shapes; limited two-bar trend structure. This is a simplified technical feature set, not a comprehensive Murphy implementation. Full parity with the original Pattern Forge implementation is not established.
- Native historical warmup, incremental caches, completed-bar checks and equity-session adjacency handling. Prospective first-observed readings are retained; historical data retrieved today is not misrepresented as historical point-in-time observations.
- OCaml multi-frame paper experiment: long-only non-BTC crypto entries combining EMA trend and bullish candle shape; exit on a candle-derived invalidation level or falling trend in the originating frame. The rule is uncalibrated and does not provide a measured probability of winning.
- Durable pending IDs written before submission, broker reconciliation, partial-fill handling, external-inventory protection and IOC limit orders. BTC has its own legacy rule. Alpaca execution origin is hardcoded to paper; protected AAPL inventory is not traded by this system.
- Public Hyperliquid data collection and HIP-3 analysis. There is no demonstrated Hyperliquid paper execution adapter.
- Local monitor with orders, grouped fills, decision reasons, open positions and frame inspection. Aggregate accounting is explicitly provisional.
- Chronological research screens, recorded rejected policies and a frozen Markov forward experiment.

## Critical findings

### 1. Unresolved exits and quantity precision

Sources: durable ledger, read-only broker positions and client-order lookup, `bin/multi_paper_main.ml`, `lib/multi_paper.ml` and the quantity serialization path.

| Asset | Pending since UTC | Broker quantity text | Submitted quantity text | Excess |
|---|---|---|---|---|
| BONK | 2026-10-02 18:32:24 | 26529255.31914894 | 26529255.319148943 | 0.000000003 BONK |
| PEPE | 2026-10-02 12:03:47 | 22466216.216216221 | 22466216.216216225 | 0.000000004 PEPE |

Both client-order lookups returned HTTP 404 / code 40410000, order not found. Binary float plus decimal formatting generated quantities exceeding the observed available balance. This is a confirmed quantity defect. It is a plausible cause of rejection, but the actual POST response was not retained; the exact broker rejection cannot be reconstructed from the generic `UNCERTAIN` event.

Only HTTP 422 is treated as a definitive rejection. Other responses retain pending authority; a subsequent 404 leaves the ticket blocked without a bounded resolution/escalation path. Avoiding duplicate orders is useful, but indefinite blocked exits are unsafe. Stops are local checks, not resting protective broker orders, and pending state can prevent an exit.

Acceptance: exact decimal/integer-grid order quantities, tests reproducing these actual values, classified and persisted broker error responses, and restart-safe recovery/escalation for rejected versus uncertain submissions. Do not blindly clear a pending ID and resubmit when acceptance remains uncertain.

### 2. Trading constraints are not visible enough

The experiment has a ten-ticket operational cap, one position per symbol, quote freshness checks, long-only entries and a technical confluence requirement. The cap is an explicitly uncalibrated choice. Two blocked tickets consume capacity. Quote age can block exits in sparse markets. Increasing order counts does not solve those defects or create statistical edge.

Acceptance: show the current binding blocker per symbol and exit, distinguish data readiness from risk authority, and audit stale quote handling against actual venue update cadence without silently treating old quotes as executable.

### 3. Accounting and strategy attribution are incomplete

The aggregate combines legacy BTC and the new experiment. It uses fill cash flows, marked crypto inventory and posted fees, with fee timing/inventory residual limitations. The history groups fills by order; it does not deliver a complete realized net closed-lot ledger.

Acceptance: replay every fill, allocate quantity-denominated and USD fees, reconcile initial inventory and broker balances, and show realized/unrealized/fees per strategy and closed position. Any unresolved residual must remain explicit. Add a strategy equity curve and drawdown only after the underlying ledger reconciles.

### 4. Neither HFT nor a validated AI advantage is established

REST polling and subprocess-based broker requests remain on the execution path. A roughly 19-second universe scan and occasional local receive-to-decision timings are not an end-to-end HFT benchmark. There are no reviewed reproducible p50/p95/p99 latency, sustained throughput, GC or recovery benchmark results.

Historical source: `docs/POLICY-ATTEMPTS.md`. The recorded frozen Markov forward experiment had Brier score 0.25127 versus 0.24999 for its frozen base-rate baseline; lower is better. It did not demonstrate improved calibration. Recorded fee-aware technical and flow/imbalance screens did not establish a deployable edge. These are inspected historical results, not fresh reruns.

Acceptance: deterministic replay using the same production signal/risk/order state machine, published hardware and dataset provenance, latency distributions including feed-to-decision and submission/acknowledgment separately, and chronological out-of-sample model comparisons against simple baselines. Account for executable bid/ask prices, fees, funding where applicable and the number of attempted hypotheses. Winning probabilities require measured calibration and uncertainty, not conversion of a signal score into a percentage.

### 5. Public delivery is behind the local system

Local HEAD was `982eefd`; verified public main was `ceb63c47ffc3e105c24093e8398098906cd7f331`. There were eight local commits ahead of public main. Dublin receives individual files rather than a verified versioned release. Local uncommitted and untracked work exists; a passing check does not prove that exact tree is deployed or published.

README and market-pipeline documentation still describe BTC-only execution and an older synchronization cadence. The current local sync sleeps 60 seconds after a fetch, so the total cycle includes fetch time; UI display refresh is a different interval. The old eight-hour work log lacks a final audit. Elapsed time does not demonstrate eight hours of continuous work.

Acceptance: a release manifest containing commit/build/config hashes, a reproducible install/replay command, accurate scope documentation, sanitized example telemetry and an externally accessible demo or recorded walkthrough. Localhost is not accessible to an external recruiter.

## Checks rerun during this review

- Local Python unittest discovery: 83 discovered, 78 passed, five runtime tests skipped on Windows.
- Web: 15 tests passed; TypeScript typecheck passed.
- Dublin: `TZ=UTC opam exec -- dune runtest --force` passed six OCaml test executables, including 17 pure multi-paper checks.
- Dublin: five executable multi-paper runtime tests passed with the synthetic broker harness.
- CI configuration exists for OCaml build/tests and web tests/typecheck/build. It does not currently run the Python discovery/runtime suite. No claim is made that GitHub CI ran successfully for the eight unpublished commits.
- Web production build was not rerun during this read-only review; the existing build was used to restore the monitor.

The green tests did not cover the real high-token-count precision failure. They validate selected behavior, not strategy profitability or fault-free production operation.

## Recommended order of work

1. Repair exact quantities and the pending/rejection lifecycle. Reproduce both failed exits in tests; verify broker/ledger agreement and observable recovery before strategy expansion.
2. Build a reconciled, strategy-separated fill/lot/fee ledger. Make the monitor primarily show closed/open trades, realized and unrealized results, fees, blockers and the reasoning for the selected trade.
3. Finish measurable short-frame data quality: per-venue candle completeness, timestamp semantics and replayable prospective data. Document which instruments truly have executable data.
4. Add a production-equivalent replay and performance benchmark, including fault injection and restart recovery. This is the strongest route to a credible systems engineering demonstration.
5. Evaluate one frozen model hypothesis against technical and base-rate baselines with chronological holdouts. Preserve unsuccessful attempts. Expand broker execution only after its adapter and lifecycle are independently verified.
6. Publish an accurate, versioned release with architecture, benchmark/research report and a simple accessible demonstration. Keep the project independent; do not imply affiliation with an employer.

There is useful engineering work here, but the current execution defect, unproven model edge and incomplete public delivery prevent presenting it as a reliable HFT/AI trading system. Paper fills and paper P&L do not establish live execution quality or profitability; this strategy could lose money live.
