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

- Release `ff76c40` was pushed; public CI run 37214877640 passed both OCaml/routing checks and monitor tests/typecheck/build at 15:58:46 UTC. Frontend source/docs were synchronized to Dublin; the frontend itself remains localhost-only.
- Final browser checks found one usability issue: changing history filters retained an unrelated selected order. This was corrected so deliberate filter changes reset selection, while periodic snapshot updates keep it fixed. Market ready counts now respect the selected timeframe; connection cards show their own timestamp and stale health.

## Completed monitor hour and release verification

- UTC clock confirmed the one-hour monitor window at 16:12:14, after the first connection hour (14:12:09–15:12:14). Work included accounting/FIFO implementation, actual snapshot storage, desk views, filtered HTTP exports, desktop/narrow QA and release verification; elapsed time alone is not the evidence.
- Final frontend release `e76b07e` passed public CI run 37215319748 at 16:05:03 UTC. Local and Dublin frontend source hashes match after normalizing Windows line endings. Listener is loopback only, 127.0.0.1:3000; no web server was exposed on Dublin.
- The browser actually downloaded `ai-ocaml-orders.csv`: 1,513 filtered BTC execution orders, each with a reason column, no AAPL, snapshot 16:03:51 UTC. Changing the filter to SOL selects SOL's actual order; a selected older BTC order stayed unchanged across the next broker snapshot at 16:05:24 UTC.
- Mobile 390px layout used position/history cards, with document scroll width equal to client width (375px excluding the scrollbar). QQQ/4h detail showed the actual closed-session blocker, candle start 2 October 16:00 UTC and 54 contiguous bars; no new stock execution was invented.
- The final connection audit found a rebrand/configuration defect: exporter checked a public default unit name while the existing collector retained its private installation name. The collector itself was active with zero restarts and current captures. Added an explicit private `AI_OCAML_CAPTURE_SERVICE` setting and validated unit syntax; public telemetry exposes only the resulting active boolean. Authenticated exporter check then reported captureActive true, without restarting or duplicating the collector.

## Next actual steps

1. Supply an eligible OANDA v20 practice account/token through the secure VPS installer (no secret in chat). Verify the real FX catalog/pricing/candles and complete the FX order/ownership/reconciliation adapter before claiming FX execution.
2. During the next regular stock session, verify real stock quote/bar events and the explicit paper route with broker outcomes. Connected Sunday transport and synthetic execution tests do not prove a stock fill.
3. Strategy development follows this task: chronological point-in-time evaluation, explicit recorded candidate policies, calibrated risk/probability decisions only when supported. The current BTC rule remains uncalibrated and new ETH/SOL confluence entries remain paused.

- The overview now always shows the latest global matched closures; history filters remain scoped to their history views. This prevents an earlier SOL-only history filter from silently hiding all overview closures.
- Sixteen exporter tests passed on Dublin after the collector-name mapping fix. Actual collector health was true; the service remained active throughout.
