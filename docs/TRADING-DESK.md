# Trading desk

The verified deployment is **http://127.0.0.1:3000**. The localhost frontend is
read-only. Dublin runs data collection and the currently deployed paper rule
independently of the browser. Vercel uploads are disabled.

## Views

- **Overview:** net marked paper P&L, broker unrealized P&L, the provisional
  realized/posted-cost decomposition, open exposure, actual open positions,
  recorded P&L curve and recent closing executions.
- **Closed trades:** FIFO matched closing quantities, entry/exit times and
  average prices, gross P&L and links to the actual entry/exit reasons.
- **Orders & fills:** grouped broker executions, canceled unfilled attempts,
  partial fills, individual fill rows and retained decision/quote evidence.
- **Markets:** provider/product labels, five requested closed-candle frames,
  coverage states and concrete abstention reasons. Timeframe selection keeps
  individual frames readable on narrow screens.
- **Connections:** broker transport, IEX stock stream, broker order stream,
  crypto capture, Hyperliquid analysis and the FX practice credential blocker.

History filters use instrument, recorded policy and UTC calendar dates. Orders
can be filtered to buys, sells, executions or unfilled attempts. CSV export
includes the entire matching history, rather than only the current page.
Order selection stays fixed during background API polling. Narrow layouts use
cards for positions and histories so P&L and reason controls remain visible.

## Accounting limits

Net marked result = sell fills − buy fills + broker inventory marks + posted
USD crypto fees. Asset-denominated fees are already reflected in inventory and
must not be charged against that mark twice. Broker fee posting can lag.

The realized/posted-cost metric is this provisional result minus broker
unrealized P&L. It is an arithmetic decomposition, not a verified tax/accounting
realized return. FIFO closure rows match actual traded quantities with integer
nine-decimal precision. They report **gross P&L before fees**: aggregate fee
activities do not supply a reliable per-order assignment. Partial closures can
create multiple rows, and remaining fee-related lots are not declared settled.

Incomplete histories, external activity in a lab-traded asset or invalid fill
identity hide attributable results. Historical excluded altcoin executions
remain in the audit trail; new crypto entry authority is BTC/ETH/SOL only.

## Curve and freshness

The curve records actual successful broker snapshots while the localhost API
is polled, in Git-ignored `.local/performance.jsonl`. It does not synthesize
earlier points or collect local observations while the monitor is closed.
The collector waits 60 seconds after each completed broker fetch; API polling
every 15 seconds does not make the broker history instantaneous. A two-minute
staleness warning is an **uncalibrated operational choice**.

## Public examples consulted

The information layout was informed by the public feature descriptions of
[eJournal](https://github.com/earlisreal/eJournal) (trade log and FIFO matching)
and [OpenTerminal](https://github.com/marketcalls/OpenTerminal) (positions,
orders, portfolio and watchlists). The desk implementation is original; no
terminal source or proprietary trading strategy was copied.

Paper execution does not establish live profitability. The project does not
yet demonstrate HFT performance, a calibrated winning probability or an AI
trading edge.
