# Native daily, weekly and monthly context

The minute scanner now also retrieves native `1Day`, `1Week` and `1Month` bars for the
actually monitored Alpaca stocks/ETF and BTC/ETH/SOL. It attaches the same
instrument's primary context to each of its five intraday Murphy panels.
These are additional time scales, not additional broker products or orders.
Hyperliquid daily/weekly history uses its separate public adapter, with native
`1M` **30-day epoch blocks** added separately from Alpaca calendar months.
Calendar-month HIP-3 history remains unavailable. Murphy law 1 remains **partial**: context
availability alone does not complete trend confirmation or book methodology.

## Data and causality

- Native provider endpoints: [stock bars](https://docs.alpaca.markets/us/reference/stockbars)
  and [crypto bars](https://docs.alpaca.markets/us/reference/cryptobars-1).
  Pagination follows every returned token and rejects repeated tokens or
  unexpected instruments. The 10,000 limit applies to the total page.
- Equities use IEX, with existing raw daily/weekly adjustment retained. Monthly
  prices/volume use the documented `split` adjustment, explicitly known only
  at this retrieval. This is not a point-in-time corporate-action history,
  a dividend-adjusted total return or consolidated volume. Every frame shows
  its own adjustment and receipt; raw and adjusted histories are not silently
  compared as one scale. Crypto uses the US feed.
- Stock periods begin at New York midnight; crypto periods at UTC midnight.
  Calendar-date arithmetic handles New York DST. Missing stock days are
  compared against the actual broker calendar; missing periods reset warmup.
  No flat candles are inserted.
- Only closed periods are used. Daily closure waits until the next native
  midnight rather than regular-session 16:00, because a daily aggregation can
  include other prints. Weekly closure conservatively waits until the next
  Monday midnight. On Sunday, the latest week can therefore still be withheld.
  The UI displays actual last-bar and closure timestamps.
- Monthly periods start on the first calendar day at native midnight and
  close at the following month's native midnight. New York DST, leap years,
  year rollover and varying month lengths use calendar arithmetic, never a
  fixed 30-day duration. A month can begin on a holiday/weekend while containing
  actual broker sessions; missing whole months reset indicator warmup.
- History is **as retrieved**, with actual retrieval time. It is not a
  point-in-time backtest. Subsequent forward journal records retain the context
  actually observed then; no earlier record is retroactively enriched.

## Descriptive calculation and cadence

EMA20/EMA50 reuse the existing Pattern Forge windows and conventional initial
SMA / exponential recursion. Trend is descriptive ordering of the actual
close and those averages, not a probability or a learned entry rule. Warmup
needs the actual 50 consecutive periods. The seed spans EMA50 plus a preceding
observation and a leading-period allowance; every returned bar is validated.

The hourly refresh is an **UNCALIBRATED GUESS** for limiting read-only REST
work. It runs inside the serialized existing scanner and caches summaries,
without adding an order process. The Alpaca collector does not spend Hyperliquid
REST budget; the separate HIP-3 collector reserves its actual native requests
through the shared public-data budget. A cache
cannot be reused with a future retrieval time or a changed instrument scope.
Errors, missing/warming/stale periods and original reception timestamps remain
visible. All primary context carries `orderAuthority=false` and
`winProbability=null`.

## Verification on 2026-10-04

Six synthetic tests passed locally and on Dublin: midnight/DST, open weekly
period exclusion, missing latest period, holiday adjacency, invalid/duplicate
rows, complete pagination, scope guards and cache causality. Nine Murphy,
six pipeline and six forward-audit tests passed on Dublin. These fixtures are
not strategy results.

Actual initial retrieval at 21:02:09 UTC supplied 72 instrument contexts and
144 daily/weekly summaries, all then descriptive. QQQ had 255 daily and 52
weekly consecutive bars; BTC had 370 daily and 52 weekly. The subsequent
21:03 scanner completed in 28.86 seconds with no retrieval errors. These are
individual observations, not guaranteed throughput or HFT latency.

No execution policy was enabled by this context. It supplies no validated
edge, calibrated winning probability or evidence of live profitability.

## Monthly verification — 5 October 05:23 UTC

Read-only native `1Month` probes for QQQ/NVDA and BTC returned 53 periods,
including the open October period, at 02:46:58–59 UTC. The production collector
withholds that open month and obtains actual 52-month history for EMA50 rather
than inventing monthly candles from intraday data. Nine calendar/native tests
passed locally and on Dublin, seven HIP-3 adapter regressions, eight pipeline
and nine Murphy tests on Dublin; 40 frontend tests and production build passed.

Actual cached retrieval 04:52:13–23 UTC: 72 monthly summaries, 71 descriptive
and SOL warming. QQQ/NVDA/BTC had 52 consecutive closed periods. QQQ's last
monthly start/closure were 2026-09-01T04:00:00Z / 2026-10-01T04:00:00Z; October
was withheld. Browser QQQ 1h showed actual EMA20/50, receipt and split adjustment
beside separately identified raw daily/weekly context. This is descriptive
as-retrieved information, not validation of a trading policy.

## Hyperliquid native `1M` verification — 5 October 08:03 UTC

Two actual public `candleSnapshot` probes at 07:46:27 UTC for `xyz:EUR` and
`xyz:XYZ100` returned 11 and 13 rows including the current open block. Their
native boundaries were August 5, September 4, October 4 and November 3 UTC:
exact 30-day Unix epoch blocks, not calendar-month starts. Official interval
support: [Hyperliquid info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint).
The adapter validates every instrument, interval, grid and inclusive end;
open periods are withheld and gaps reset warmup. The separate `Native1M` key
prevents accidental comparison with Alpaca `1Month` semantics.

The existing serialized collector seeds one instrument per scan, now with
three budgeted native requests. This cadence remains an explicitly uncalibrated
operational choice, not a throughput guarantee. Older two-interval caches are
eligible for an actual new attempt; failures retain old receipts and the normal
retry cadence. The 52-block range reuses the existing EMA50 plus preceding and
leading-period allowance, not a measured strategy parameter.

Actual cache at 08:03: 11 of 19 monitored instruments had received `Native1M`;
all were warming. EUR had ten consecutive closed blocks and XYZ100 twelve,
last starting September 4 and closing October 4. EMA50 was unavailable. These
are actual short listing histories, not an implementation failure to synthesize
missing years. Calendar-month HIP-3 context and full Murphy confirmation remain
incomplete. No broker execution or policy activation was added.

Ten adapter tests passed locally and on Dublin, nine pipeline and nine Murphy
regressions on Dublin; 45 frontend tests and production build/typecheck passed.
Browser EUR 1h verified the actual native dates, individual receipt, unavailable
EMA20/50 and explicit 30-day label. Proof `.local/hip3-native-30day-proof.png`.
The stock protocol's compiled analyzer and frozen candidate rule are unchanged;
its Python source fingerprints record initial provenance, not an attestation
that every later auxiliary transport change has the same source bytes.
