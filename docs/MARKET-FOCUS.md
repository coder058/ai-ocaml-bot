# Research focus: equities, indices, FX and energy

Source: the user's revised scope on 4 October 2026. This supersedes the crypto-centered confluence experiment as the primary research target; it does not establish that technical analysis has an edge in other asset classes.

## Operational change

New multi-frame crypto confluence entries require both the existing paper gates and `MULTI_PAPER_NEW_ENTRIES=1`. The deployed entry gate is disabled. Owned crypto positions still receive exit checks and pending-order reconciliation; they are not liquidated merely to change the research universe. The independently owned legacy BTC quote rule remains enabled according to the user's earlier request to keep BTC alongside other markets. There is no newly connected equities or FX execution path in this change.

## Verified intended markets

Source: read-only authenticated Alpaca paper `/v2/assets/{symbol}` responses on 4 October 2026, approximately 13:53 UTC. All instruments below returned `us_equity`, `active`, `tradable=true`, `fractionable=true`. This verifies asset metadata, not strategy edge or account-specific fractional order acceptance.

- Index ETF proxies: DIA (Dow), QQQ (Nasdaq-100), SPY (S&P 500). Orders would be in ETF shares, not the cash index.
- Popular stocks: TSLA, NVDA, MSFT, AMZN, GOOGL, META, AMD. AAPL inventory remains protected.
- Energy ETF proxies: XLE, XOP. These are not physical oil/gas or energy futures.
- Current Hyperliquid public-data catalog includes xyz:EUR, xyz:GBP, xyz:JPY, index/equity and energy perpetual contracts. These are perpetuals, not spot FX pairs; availability must continue to be checked from metadata. Mainnet remains market-data only.

Source: paper `/v2/clock` returned `is_open=false`, next regular session `2026-10-05T09:30:00-04:00` (15:30 Madrid). Sunday analysis cannot be treated as an open regular equity session.

## Execution work still required

1. Implement a separate equities paper adapter with the exact paper origin, protected inventory, stock quote/feed semantics, equity calendar, fractional order restrictions and durable order reconciliation. The crypto IOC adapter must not simply receive stock symbols.
2. Reconcile stock fills and fees separately from the existing crypto ledger and expose order/position ownership in the monitor.
3. Evaluate technical features as candidate inputs on each actual instrument and frame, with chronological holdouts and simple baselines. Do not assign a winning probability from candle shape alone. Existing parameters are not calibrated by changing the market.
4. For FX, verify actual testnet/practice products and authentication before writing an order adapter. If no broker practice product is available, an internal execution simulator may be used for research but must be labeled simulator, not broker paper trading. Do not sign mainnet orders.
5. Preserve exact timestamps, executable quotes, session gaps, bid/ask costs and funding where relevant. Report tested hypotheses and negative results; more products do not establish statistical edge.

Paper results do not establish live fill quality or profitability. Technical rules may lose money in equities and FX as well as crypto.
