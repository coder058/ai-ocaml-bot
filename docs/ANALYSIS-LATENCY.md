# Actual analysis timing and authority

Measured deployed scan: 5 October 2026, asOf 09:39:00 UTC, retrievedAt
09:39:21.249792Z, read at 09:39:36.105344Z. Safe private projection:
`.local/analysis-latency-20261005.json`. This is one observation, not an SLO,
isolated CPU benchmark, distribution or broker round-trip measurement.

91 instruments / 455 requested frame slots; no retrieval errors. Missing,
warming and closed-market slots count as requested work, not fully ready charts.

| Phase | Measured seconds |
| --- | ---: |
| Catalog and session | 4.117360 |
| Native history and cache | 8.782401 |
| Primary context, cached/not due | 0.000183 |
| Shared OCaml batch | 1.311571 |
| Python/C technical extension | 5.135046 |
| Quote requests | 0.618050 |
| Archived quotes | 0.110191 |
| Evidence and cache writes | 2.515320 |

`processingSeconds=22.590316254994832` now covers scan start through evidence
and cache writes, before final snapshot publication. The previous counter stopped
before evidence/cache writes. Old durations retain their original scope.
Publication, broker submission, acknowledgement and fill time are excluded.

Top-level `descriptiveAnalysisTiming` records measured per-instrument/per-frame
extension work, including validation/unavailable paths and Murphy panel creation.
It does not alter decision features, rules or first-feature journal projection.

| Instrument | Five frames and Murphy panels, measured milliseconds |
| --- | ---: |
| BTC/USD | 75.062 |
| ETH/USD | 43.096 |
| SOL/USD | 43.641 |
| DIA | 42.348 |
| QQQ | 55.399 |
| NVDA | 51.170 |
| xyz:EUR | 86.444 |
| xyz:XYZ100 | 88.650 |

Observed extension range: FXF 8.404 ms to COST 128.335 ms. Bar counts, contiguous
history, warmup and host scheduling differ; this is not a ranking of instrument
difficulty. Per-instrument OCaml cost and end-to-end broker latency remain
unmeasured. OCaml is measured as one batch, including process/serialization work.

## Current behavior

The scanner schedules on minute boundaries. Closed candles are validated for
timestamp alignment, closure, finite OHLCV and gaps; stock calendar adjacency
differs from continuous markets. Gaps reset warmup. Native frames are 1m, 5m,
30m, 1h and 4h; provider revisions do not overwrite first-observed evidence.
Separate feed collectors operate concurrently, but OCaml and Python market/frame
loops are sequential. Provider batching is not 91 parallel analyzers. Scheduling
does not guarantee a completed scan every minute or analysis every second.

OCaml computes EMA20/50, RSI14, MACD, bands, basic candle shapes and minimal
trend structure. Exploratory candidates require fresh warmed closed data, session
eligibility, trend and matching candle shape. The extension evaluates 61 installed
TA-Lib candle functions, a 113-function indicator catalog with explicit missing
inputs/warmup, and ten partial Murphy panels. This is not 61 validated strategies
or the complete Murphy book. Candidates have no calibrated win probability.

The BTC quote-cross owner was retired after verified flat handoff on October 5
12:50 UTC. BTC now shares the candle router; new entries remain disabled. The
Markov model is shadow-only: next-bar-direction frequency is not net-trade win
probability. Stocks remain OBSERVE/new entries disabled. Hyperliquid mainnet is
public-data only. Practice FX lacks credentials and verified execution transport.

## Next work, not completed

Exact native-input and calculation caches now reuse valid unchanged frames while
refreshing current age and Murphy context. Actual 13:39 scan computed 72/reused
288 native and extension slots. Its total was 21.666775942081586 seconds; an
opening-boundary scan took 55.08437746705022 seconds. These individual scans
are not a controlled speedup benchmark. Cache validation/copy/serialization has
its own cost; phase instrumentation now separates cache publication. The pipeline
still polls each minute rather than triggering from every WebSocket close.
See [rollout evidence and remaining scope](ALPACA-72-READINESS.md).

Integrate native receipt events while preserving provenance, calendar/freshness
gates and frozen research cohorts.
Measure closure-to-receipt, queue wait, analysis, durable write, submit-to-ack and
ack-to-fill separately. Bound provider concurrency; keep order ownership,
reconciliation and persistence before submission.

For AI decision authority: define targets/horizons, train on chronological
point-in-time data, compare simple baselines, evaluate calibration and executable
net outcomes, record attempts, then apply uncertainty and abstention gates. This
change establishes no probability threshold, edge or performance guarantee.

Alpaca paper uses real quotes and simulated fills, excluding market impact,
latency slippage and actual queue position. IEX is not a consolidated stock book.
Sources: [paper specification](https://docs.alpaca.markets/us/docs/paper-trading),
[stock streams](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data).
Paper results cannot establish live profitability; this system may lose money live.


## Measured cache publication bottleneck — 5 October 13:51–13:55 UTC

The 13:51 actual scan took 38.98685796605423s. Its separate calculation-cache
write was 5.892564660985954s and native-cache/evidence write 6.845539944944903s.
A read-only same-document encoding comparison on Dublin measured:

| Cache bytes | Python streamed JSON encode | Single JSON encode | Exact bytes equal |
|---|---|---|---|
| 16,123,437 | 3.3732169319409877s | 0.6661777819972485s | Yes |
| 13,828,699 | 3.748686637962237s | 0.7703925499226898s | Yes |

Atomic publication now encodes once before opening the temporary file, keeping
its fsync, permissions, NaN rejection and exact JSON bytes. This reduces that
measured encoding operation on those two documents; it does not establish a
controlled production scan speedup or broker lifecycle latency. The encoded
string temporarily occupies another roughly 14–16 MB for these actual files.
Dublin reported 826 MiB available during rollout; growing histories still need
memory/disk measurement. Eleven pipeline tests passed after the change.
