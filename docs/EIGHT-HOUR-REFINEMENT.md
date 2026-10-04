# Eight-hour paper bot refinement

Window requested by the user: 2026-10-01 21:54:16 UTC through
2026-10-02 05:54:16 UTC. Work inline. Record actual changes and measured
observations; elapsed time is not a measure of completed engineering work.

## Pipeline and delivery order

1. Verify broker activity, service health, market catalog and current barriers.
2. Use one shared OCaml technical engine for all instruments and the requested
   1m, 5m, 30m, 1h and 4h frames. Seed closed historical candles as of retrieval;
   never treat later retrieval as information known during a historical replay.
3. Keep a bounded incremental candle cache rather than rereading raw captures
   for each analysis. Validate timestamps, gaps, revisions and final candle close.
4. Emit readable trend, indicator, candle-pattern and invalidation-level context
   with concrete per-frame eligibility/abstention reasons. No invented win rate.
5. Evaluate frozen candidates chronologically; record every attempted policy.
6. Connect new paper order authority only with tested venue/symbol, ownership,
   pending-order reconciliation, account/risk and evidence checks. Individual
   frames generate candidates; one portfolio router prevents conflicting orders
   for the same asset. No arbitrary requirement to trade on every candle.
7. Show the short pipeline and a market/timeframe radar in the localhost monitor
   alongside broker fills, reasons and provisional accounting. Keep internal
   simulations distinct from executed broker paper orders.
8. Test, commit, deploy to Dublin, verify live behavior, and collect forward
   observations during the remaining window. Leave Frankfurt/Fly Brain alone.

## Constraints

- Hardcoded Alpaca paper trading origin, protected AAPL holdings, durable
  pending-order journal, $100 ordinary paper size and $500 BTC exposure cap.
- The user authorized more markets and more paper opportunities. The user did
  not authorize real-money Hyperliquid orders. Its current collector is public
  mainnet data only. A verified testnet adapter/account is needed for venue
  testnet orders; an internal simulator must be labeled as such.
- Alpaca supports listed US equities and selected crypto, not conventional spot
  FX orders. Hyperliquid FX-like, equity and index perps are derivatives; do not
  relabel them as spot currencies, cash indices or owned shares.
- No parameter is described as calibrated unless actual evidence supports it.
  Paper results cannot establish live profitability. More orders can lose more.

## Initial evidence

- Local broker snapshot `2026-10-01T22:02:01.998514Z`: 1,545 bot orders and
  2,461 fill activity rows. Over the preceding 24 hours: 386 submitted orders,
  271 with a positive filled quantity; 204 buys, 182 sells; final statuses were
  118 filled and 268 canceled. A canceled IOC can still have partial fills.
- Dublin orderer, Alpaca capture, Hyperliquid capture and multi-timeframe timer
  were active. Available memory was 1,483 MiB; disk used 12/58 GiB at the check.
- Only BTC reaches the OCaml order path. Its order policy is
  `quote_cross_30s_v1`; candlestick/Murphy/Markov readings have no order authority.
- `multi_timeframe_shadow.py` reads only two UTC days and needs 50 contiguous
  candles for EMA50. This places a structural ceiling below warmup at 1h/4h;
  waiting longer cannot fix that rolling-window design. Other frames also lose
  warmup after missing constituent minutes. The current snapshot exposed these
  gaps rather than fabricating continuous candles.
- The currently verified localhost monitor is at http://127.0.0.1:3000 and
  refreshes broker data through SSH. Vercel uploads are disabled.

## Completed changes

- Shared `Frame_analysis` and JSON batch CLI reuse `Technical` in OCaml for all
  five frames and every market. The existing BTC parser remains the default;
  other symbols are accepted only through the explicit descriptive path.
- Native historical warmup plus incremental cache now supplies long frames
  independently of dropped minute-stream messages. Its retrieval time is
  retained; it is not a reconstructed past point-in-time backtest.
- Equity adjacency uses the actual Alpaca calendar and New York timezone,
  including overnight closures and early sessions. Missing scheduled bars
  still reset indicators. Closed sessions cannot emit trading candidates.
- Dublin's first real scan at `2026-10-01T22:24:00Z` analyzed 67 instruments:
  36 Alpaca crypto/USD pairs, 12 listed equities/ETF proxies and 19 HIP-3 perps.
  It had zero API errors and 12 descriptive confluence candidates. The initial
  bootstrap took 154.805 seconds, dominated by paced public history calls;
  it consumed 2.935 CPU seconds according to systemd. Subsequent scans were
  measured around 29 seconds before the REST budget refinement.
- BTC's 5m/30m/1h/4h readings each had 51 consecutive native bars. EUR's
  requested frames had 52 historical bars; the first snapshot classified its
  30m/1h bearish confluence as candidates. Neither observation establishes edge.
- Fixed a frozen-request timestamp that made all 1m rows stale after the slow
  bootstrap. Added a persisted sliding REST budget using Hyperliquid's official
  weight limits, replacing a fixed sleep after every request. This refinement
  is deployed. A real scan at `22:40:00Z` took 25.0833 seconds with no provider
  errors; seventeen 1m rows were ready and one had a candidate. At `23:28:00Z`,
  the incremental scan took 10.998 seconds, again with zero API errors.
- The minute systemd timer is active. The original BTC paper orderer stayed
  active; no trading policy, credentials or broker order authority changed.
- Local sync now carries the market-only scanner output. The monitor shows
  category/search filters, all five frame readings, indicator values, candle
  shapes and explicit analysis-only scope. The EUR 1h inspector and filters
  were verified in the actual browser. Broker history remains visible above it.
- All five OCaml test executables passed. Six Python scanner tests and four
  local transport tests passed; the twelve web tests, TypeScript check and
  production build passed. The listener remains `127.0.0.1:3000`.

The eight-hour heartbeat ends at the stated deadline. It does not itself
demonstrate eight hours of completed work. The new scanner is read-only;
  The next paper router stage is described below; the window remains active.

## Multi-market order and monitor stage (23:30 UTC checkpoint)

- Added an explicit paper-only crypto adapter and a small OCaml OMS. It keeps
  one owned ticket per instrument, origin frame, actual candle-low invalidation,
  durable pending ID, partial-fill quantities and one attempt per signal bar.
- All seventeen pure OMS checks passed. Five real-executable synthetic broker
  tests passed, including fees/partial exits, restarts, unknown accepted/missing
  responses, HTTP 422, external inventory, disarmed gates and open-order blocks.
  A rounding mismatch found by these tests was fixed so the ledger quantity
  equals the nine-decimal quantity actually submitted.
- Broker positions, open orders and latest quotes are batched once per run;
  metadata is queried for possible orders rather than every unchanged holding.
- The real observe run at `23:29:58Z` found seven long signals and sent no
  orders. Quote ages measured at `23:31:39Z` ranged from about 0.24 seconds for
  ETH to 72.69 seconds for XTZ across eight requested symbols. The five-second
  guard remains uncalibrated and can reduce eligible orders; it was not relaxed
  to manufacture more trades.
- Extended the sanitized broker projection, exact-ID explanations, inventory
  units and combined USD marked accounting to the new lab crypto namespace.
  AAPL stays excluded. Fourteen exporter tests, five local sync tests, fifteen
  web tests, TypeScript and a production build passed.
- The localhost monitor was rebuilt and restarted; its real browser now shows
  combined lab accounting and an open-position list. Local broker sync is now
  once per minute, an explicit operational guess. No new paper orders have yet
  been claimed at this checkpoint. The frozen exploratory policy, limits and
  paper/live gap are recorded in `MULTI-PAPER-EXPERIMENT.md`.

## Next check

1. Confirm the REST-budget revision improves 1m availability and handles failed
   provider reads without blocking healthy venues. Measure actual scan duration.
2. Preserve first-observed frame decisions for prospective outcome measurement;
   do not overwrite prior signals after history revisions.
3. Build a small, tested multi-market paper router with shared risk and durable
   ownership/reconciliation. Keep new broker executions distinguishable and
   attributable in the monitor. Do not silently add another independent bot
   competing for the same BTC inventory.
4. Test a complete experimental paper lifecycle before enabling any new symbol.
   Treat uncalibrated trend/candle policies as experiments, not discovered edge.
5. The verified HIP-3 xyz catalog has only EUR/GBP/JPY FX-like contracts among
   requested currencies; it is not a connection for ten spot FX pairs. Discover
   other actual available instruments, but do not fabricate their existence or
   submit mainnet orders to obtain more trades.
