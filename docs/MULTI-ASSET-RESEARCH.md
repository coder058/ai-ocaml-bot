# Multi-asset paper research boundary

## What is running

On 27 September 2026 at 23:26 UTC, Dublin's authenticated Alpaca US crypto
stream began archiving quotes and closed-minute bars for BTC/USD, ETH/USD and
SOL/USD. A read-only same-day historical 5m scan of the 36 tradable USD pairs
then found 13 with no gap between their first and last returned bars. At
23:31 UTC the collector expanded to those 13 plus ETH and SOL: 15 subscribed
pairs in total. The first 30 seconds of the new session contained actual
events for 10 of them; this short observation is not a sustained capacity
measurement. BTC alone also gets trades and order books and is the only symbol
forwarded to the OCaml paper-order process. The other 14 have **no order
authority**. The read-only inventory script found 73 active tradable crypto
pairs, including 36 `/USD` pairs, in this paper account at 23:23 UTC.
This is an asset catalog count, **not** a simultaneous-feed capacity test.

The same account reports DIA, XLE and XOP as active, tradable US equities.
DIA is a Dow ETF proxy; XLE and XOP are energy-sector ETF proxies. None is the
cash Dow index, an oil futures contract or a live European energy feed. Energy
Monitor's daily/public energy tables cannot justify intraday entry orders.
Equity sessions and feeds must be treated separately from 24/7 crypto.

A separate read-only systemd timer now runs once per UTC minute on Dublin.
`research/multi_timeframe_shadow.py` reads only the archived crypto events and
writes a private snapshot with per-symbol/per-frame closed-bar coverage,
consecutive-bar count, Pattern Forge candle shapes and EMA20/EMA50 trend when
enough contiguous bars exist. The manual run at 23:36 UTC processed 15 symbols
in 0.850 seconds. BTC had a 1m rising EMA trend but no 5m trend because the
latest contiguous 5m tail had only 20 bars; ETH and SOL lacked any complete
captured 5m group. These are descriptive readings with no order authority or
calibrated probability. The one-run time is not a sustained performance test.

## Timeframes and evidence

`research/multi_timeframe_bars.py` builds UTC 1m, 5m, 30m, 1h and 4h candles
only when every constituent as-received minute bar exists. It never fills a
missing minute with a fabricated bar. A later Alpaca bar revision enters only
analyses made after its recorded receipt time. Alpaca's historical crypto bars
API also documents minute and hour frames, but later historical bars can
contain revisions and are not past point-in-time knowledge.

At 23:27:57 UTC, the captured BTC day contained 867 distinct closed 1m bars,
140 complete 5m groups, 13 complete 30m groups, five complete 1h groups and
**zero complete 4h groups**. ETH and SOL each had one closed 1m bar after their
subscription and no complete longer group yet. These counts describe
coverage, not trading signals. In the same-day later historical scan, ETH
had 250 returned 5m bars and 32 missing slots between its first and last;
SOL had 280 and two missing slots. The REST values are retrieved-later data,
not an as-received history. Feed latency, dropped messages and resource load
must be measured again as the watchlist grows; 15 authenticated subscriptions
do not establish that all 36 pairs can be handled reliably.

## Promotion path for a new paper policy

1. Measure per-symbol received quotes, consecutive closed bars, missing
   intervals, revisions, spread, volume and feed age on Dublin. Explicitly
   record periods with no data. Only compare signals to an outcome that had
   not yet occurred when the decision was recorded.
2. Specify candidate states from Pattern Forge's candle shapes and Murphy
   trend indicators at each chosen horizon. Markov transitions are a model
   of observed states, not a prediction guarantee. Freeze the model and then
   score new, chronological shadow decisions against an unmodified baseline.
3. Calculate executable entry at the ask and exit at the bid, using the
   applicable broker fee tier, observed spread, actual order outcome and
   latency. Count no-fill and partial-fill cases. An estimated direction-win
   rate alone cannot establish positive net expected value. Alpaca documents
   a tier-one 0.25% crypto taker fee per side; that is a 0.50% round-trip fee
   hurdle before spread or adverse movement.
4. Derive a stop and size **together** from a measured loss budget and a
   falsifiable trade-invalidating price level (for example, a tested ATR or
   swing-low candidate). For a long position, `quantity <= permitted_loss /
   (entry_price - stop_price + expected_per-unit execution costs)`, subject
   to asset increments and the $500 BTC exposure ceiling. No permitted-loss,
   ATR multiplier or minimum sample count has been calibrated yet. Alpaca
   supports crypto stop-limit orders, but a limit may fail to execute through
   a fast move; it does not guarantee maximum loss.
5. Keep the user's $50, $100 and $500 sizes as **requested tiers**, not as
   probability labels. A threshold for each tier requires out-of-sample
   calibration of after-cost results and a portfolio-wide exposure budget.
   The currently deployed $100 BTC baseline is a user-requested paper
   experiment, not a learned optimal size. A candidate that fails the
   after-cost evidence gate abstains rather than generating more trades.

There is no calibrated probability of winning for any symbol, timeframe or
Pattern Forge state today. The existing 5m Markov screen failed its optimistic
fee hurdle and has no order authority. All paper fills are simulated; even a
later favorable paper result could lose money live.

References: [Alpaca crypto bars](https://docs.alpaca.markets/us/reference/cryptobars-1),
[crypto fees](https://docs.alpaca.markets/us/docs/crypto-fees),
[crypto order types](https://docs.alpaca.markets/us/docs/crypto-orders).
