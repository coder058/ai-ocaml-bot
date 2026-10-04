# Connections and monitor work — 4 October 2026

## User request

Work inline. Spend at least one hour on connections/paper execution and then at least one hour on the monitor. New crypto trading is restricted to BTC, ETH and SOL. Connect a broad supported set of stocks, index/energy instruments and FX practice products. Strategies are a subsequent task. Public project name is AI OCaml Bot.

## Timing and evidence

- Start verified with UTC clock: 2026-10-04T14:12:09Z (16:12 Madrid).
- Connection phase must continue at least until 15:12:09Z.
- Actual monitor phase start: 2026-10-04T15:12:14Z; continue through at least 16:12:14Z.
- Do not equate elapsed time with engineering work. Record finished changes, checks, blockers and deployments below.

## Decisions

- Alpaca's hardcoded paper origin is the execution provider for stocks/ETF and the three allowed cryptocurrencies. AAPL inventory remains protected. More analysis products do not automatically receive order authority.
- Hyperliquid mainnet remains public data only. Live perp orders and real-money Polymarket orders are outside this paper task.
- Read-only Hyperliquid testnet catalog check: 268 DEX entries, xyz present; active xyz catalog 37 assets, FX-like entries xyz:EUR and xyz:JPY. Native active catalog had 158 entries and no FX matches. This does not verify wallet funding or order acceptance.
- A user question is pending for OANDA v20 demo credentials or a funded Hyperliquid testnet wallet. Secrets must not be sent to chat. Prepare the practice-only connection while this is pending; do not invent connected broker execution.
- Existing owned altcoin exposure needs a controlled wind-down. Resolve uncertain order IDs from broker evidence and exact quantities, preserve history and never sell unrelated inventory.

## Connection phase checklist

1. Enforce BTC/ETH/SOL entry allowlist at signal and order boundaries.
2. Replace imprecise quantity serialization, preserve actual broker error outcomes, and recover the two blocked exits using broker evidence.
3. Connect a separate stocks/ETF adapter with session, asset, ownership and fractional-order checks. Verify API access without forcing strategy trades.
4. Broaden and verify the non-crypto catalog and data coverage; preserve provider/product/feed labels and timestamps.
5. Prepare FX practice/testnet adapter and status reporting. Record any actual missing user account/funding requirement.
6. Verify runtime behavior, commit scoped changes, deploy to Dublin and check telemetry.

## Monitor phase checklist

1. Study public trading terminal examples and provider documentation.
2. Present one clear account/lab overview with realized, unrealized, fees and reconciliation status.
3. Separate open positions, closed round trips, executions, pending/rejected orders and connection health.
4. Instrument and strategy filters; readable trade detail, decision evidence and explicit unavailable fields.
5. Mark simulator, broker paper, testnet and analysis-only products distinctly.
6. Verify desktop and narrow layouts, remove disruptive refresh behavior, keep localhost available and uploads disabled.

## Completed evidence

- OCaml exact decimal quantities, entry allowlist and excluded-asset market wind-down compiled and deployed. Eight synthetic multi-OMS runtime tests passed. BONK/PEPE recovery required complete history, two 404 lookups and no open order; evidence and backup remain private.
- Nine excluded positions were sold through Alpaca paper; authenticated order lookups reported all nine `filled`. At 14:53 UTC only BTC and SOL remained as broker crypto positions. Unrelated inventory and AAPL were protected.
- The stock/ETF router compiled and passed ten Linux synthetic runtime checks, including partial fills, lost responses, restart, duplicate ledger IDs, wrong identity and unowned inventory. Real API clock/quotes/account checks succeeded. Sunday stock session is closed; no stock fill is claimed and no automatic stock strategy is armed.
- Catalog: 13,509 active tradable stocks/ETF, 69 requested stocks/ETF present. Scanner ran 91 instruments at five frames, 40.3866 seconds in the first expanded run, no reported provider errors. This is not a load/latency benchmark or proof all frames are ready.
- IEX stock WebSocket authenticated and confirmed 30 subscriptions. The free Basic limit is 30; quote/bar counts were zero at Sunday verification. Separate process heartbeat distinguishes connection liveness from market freshness.
- Alpaca paper `trade_updates` authenticated and subscription was confirmed. Private lab-only order journal plus sanitized connection telemetry added; full REST history remains authoritative.
- OANDA practice-only data connector, account-specific FX catalog and closed-candle transport prepared. Four synthetic tests passed. Actual state: `practice_credentials_missing`. It has no FX execution adapter. Interactive secure installer is available on Dublin; a practice account/token is still required from the user.
- Full OCaml build/unit checks passed; six candle pipeline checks, two crypto stream checks, two IEX subscription checks, two paper order projection checks, fifteen exporter checks and six local transport checks passed in the stated environments.
- Connection telemetry is now carried to the localhost snapshot. Vercel uploads remain disabled. Monitor phase started at 15:12:14 UTC after the connection hour and public CI verification.
- Connection commit `4360ee9` was pushed to the public AI OCaml Bot repo; GitHub CI completed successfully at 15:09:26 UTC, including OCaml build/unit checks, synthetic routing/connection tests and existing web tests/typecheck/build.
- At 15:07 UTC all 69 monitored stocks were confirmed fractionable. A subsequent scanner run took 25.6714 seconds and reported no provider errors, but some short frames were warming, stale or missing. The monitor must expose these states instead of implying all 455 frames are ready.

## Remaining risk

Paper results do not establish live fill quality or profitability. Strategy work is deferred. Missing practice credentials or testnet funding can prevent broker FX execution even when public data is accessible.

## Monitor evidence in progress

- Studied public eJournal/OpenTerminal feature documentation; wrote original desk components, without copying terminal source.
- Replaced the single crowded view with Overview, Closed trades, Orders & fills, Markets and Connections. Desktop tables and narrow position/history cards expose P&L, quantities, fills and reason controls.
- Actual complete broker history matched 1,647 FIFO partial closures with no unmatched sells in the 15:34 snapshot. These are gross matched fill closures, not 1,647 profitable/settled trades. Fees cannot be assigned precisely per closure.
- Added real snapshot P&L collection, serialized duplicate protection, restart persistence and recovery after truncated append tails. Collection runs while the localhost API is polled; no pre-existing equity curve was invented.
- Read-only HTTP CSV export returned 200 and 1,511 BTC matched closure rows at the 15:50 check. Instrument, policy, UTC date, side and no-fill filters were tested; unrelated AAPL is excluded.
- Independent Decimal audit at 15:50:07 UTC: cash flow -210.705471231843439442 USD, broker marks 101.189262 USD, posted USD fees -93.56 USD; net marked -203.076209231843439442 USD. This reconciles the displayed rounded value for that snapshot only and remains provisional.
- Twenty-four web tests passed, including FIFO partial quantities, invalid/oversold history, duplicate fills, external activity, fee attribution, CSV filtering and persisted real observations. Typecheck/build verification is recorded with the final release below.
- Dublin service checks at 15:52 UTC: paper executor, crypto/Hyperliquid collectors, multi-market scanner, stock/order streams and stock/FX connection timers active. Public uploads disabled. No FX practice credentials have been supplied and no stock strategy was armed.

## Remaining connection blocker

Conventional FX is not connected to a broker. The practice-only data connector and secure installer are reviewable on Dublin, but require an eligible OANDA v20 demo account/token. Its FX order adapter is still future work. Hyperliquid mainnet remains public data; testnet's observed two FX-like products do not provide ten conventional FX pairs. Do not claim all market execution paths are complete.
