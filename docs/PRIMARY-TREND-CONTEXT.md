# Native daily and weekly context

The minute scanner now also retrieves native `1Day` and `1Week` bars for the
actually monitored Alpaca stocks/ETF and BTC/ETH/SOL. It attaches the same
instrument's primary context to each of its five intraday Murphy panels.
These are additional time scales, not additional broker products or orders.
Hyperliquid primary history is not connected by this module. Monthly history
is still missing, so Murphy law 1 remains **partial**.

## Data and causality

- Native provider endpoints: [stock bars](https://docs.alpaca.markets/us/reference/stockbars)
  and [crypto bars](https://docs.alpaca.markets/us/reference/cryptobars-1).
  Pagination follows every returned token and rejects repeated tokens or
  unexpected instruments. The 10,000 limit applies to the total page.
- Equities use the IEX feed and raw adjustment; these are not consolidated
  volumes or prices adjusted for corporate actions. Crypto uses the US feed.
- Stock periods begin at New York midnight; crypto periods at UTC midnight.
  Calendar-date arithmetic handles New York DST. Missing stock days are
  compared against the actual broker calendar; missing periods reset warmup.
  No flat candles are inserted.
- Only closed periods are used. Daily closure waits until the next native
  midnight rather than regular-session 16:00, because a daily aggregation can
  include other prints. Weekly closure conservatively waits until the next
  Monday midnight. On Sunday, the latest week can therefore still be withheld.
  The UI displays actual last-bar and closure timestamps.
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
without adding an order process or spending Hyperliquid REST budget. A cache
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
