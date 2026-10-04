# AI OCaml Bot

An auditable live market monitor and **Alpaca paper-only** execution experiment,
written in OCaml. This is an independent portfolio project, not affiliated with
Alpaca. It does not claim a profitable strategy.

**Local monitor:** [127.0.0.1:3000](http://127.0.0.1:3000/).
The Vercel deployment is paused; the local mode is the verified current setup.

The Dublin VPS runs an OCaml paper order service and an Alpaca US market-data
collector. The local monitor reads a sanitized broker and journal snapshot
through SSH; no Alpaca secret is sent to the website. The dashboard
shows current lab-owned positions, per-frame execution states and a separately
dated cohort of new orders with retained decision evidence. Earlier trade history
remains hidden after the requested reset. Protected AAPL
and unrelated account holdings stay private. The retained accounting code subtracts posted USD crypto
fees and use broker marks; they stay provisional until daily fee posting,
quantities and closed-lot reconciliation are complete.

A second, read-only collector records public Hyperliquid HIP-3 prices, BBOs and
1m candle updates for selected FX-like, index, energy and equity contracts.
It cannot access a wallet or submit orders. Its capture and restart behavior
are documented in [the Hyperliquid feed runbook](docs/HYPERLIQUID-CAPTURE.md).
This is market-data collection, not a claim that the OCaml executor is HFT.

## Current behavior

A shared OCaml batch analyzer now supplies the localhost market radar across
the five requested frames. The 4 October connection check analyzed 91 markets:
BTC/ETH/SOL, 69 listed stocks/ETF and 19 HIP-3 contracts. The Alpaca catalog
contained 13,509 active tradable stocks/ETF; catalog availability does not mean
all are continuously monitored. A separate authenticated free IEX WebSocket
captures 30 selected stock/ETF symbols. It uses native
historical warmup, an incremental cache and the actual equity-session calendar.
New confluence crypto entries remain paused. A tested OCaml stocks/ETF scheduler
now connects closed candidates to the durable paper router in **observation**;
no new automatic stock strategy is armed. Conventional
FX requires an OANDA v20 practice account; its data connector currently reports
missing credentials and has no FX order adapter. Currency ETFs and Hyperliquid
FX-like perps are labeled as such. See [connections and operations](docs/CONNECTIONS.md),
[the market pipeline](docs/MARKET-PIPELINE.md) and
[the ongoing refinement log](docs/EIGHT-HOUR-REFINEMENT.md).

### Read the execution path

**Closed candles → OCaml evidence → frozen candidate → route/gates → ownership
and executable quote preflight → durable request → paper acknowledgement/fills.**

Localhost exposes a filterable 91 x five matrix with factual data/policy/routing
states and explicit unknown checks. A candidate is not an order; five frames
describe the same underlying instrument. The frozen rule uses selected OCaml
shapes/EMA trend; full TA-Lib supplies separate descriptive Python analysis. No
calibrated winning probability is displayed. See [execution work evidence](docs/EXECUTION-TRACE-WORK.md)
and the [stock scheduler/owned-exit runbook](docs/STOCK-AUTOMATION.md).

- The Dublin collector archives Alpaca US BTC/USD WebSocket quotes, trades,
  order books, closed-minute bars and later bar revisions with receipt times.
  It also archives ETH and SOL quotes and minute bars. New crypto entries are
  restricted to BTC, ETH and SOL at the signal and adapter boundaries. Prior
  bot-owned altcoin positions were wound down in nine broker-filled paper sales
  on 4 October. Historical captures and executions remain available.
  Only BTC quotes and bars reach the legacy OCaml receiver over its Unix socket.
  ETH/SOL use the separate multiframe OMS, with new entries paused and owned
  exits/pending reconciliation separate. The [multi-asset research boundary](docs/MULTI-ASSET-RESEARCH.md)
  records the measured market catalog and five requested timeframes. Session IDs and
  a per-consumer sequence expose reconnects and lost datagrams.
- A separate read-only timer derives closed 1m/5m/30m/1h/4h candle coverage,
  selected Pattern Forge shapes and EMA trends once per minute for the research
  watchlist. It has no broker credentials or order path; gaps prevent a frame
  from being manufactured or a trend from being calculated prematurely.
- The OCaml service was verified in `PAPER_ORDER` mode with `PAPER_ORDERS=1`
  on Dublin on 28 September 2026. The monitor is the freshest operational
  snapshot; any service check is only a point-in-time observation. It receives
  each quote and evaluates the cross-spread rule against a reference quote
  sampled at the earlier REST service's 30-second cadence. It records each
  sample and starts a separate worker for broker I/O on candidates so the feed
  receiver can continue. A deliberately simple, **uncalibrated** cross-spread
  price-move rule submits IOC limits only to the Alpaca **paper** origin.
- OCaml describes Alpaca closed-minute bars with selected Pattern Forge style
  EMA, RSI, MACD, Bollinger and candle-shape rules. A separate five-minute
  Alpaca historical snapshot supplies a more continuous, retrieval-timestamped
  context. Missing intervals reset indicators. These readings have no order
  authority and no calibrated probability; full cross-language parity with
  Pattern Forge remains unverified.
- Before every submission it checks paper account status and buying power,
  all open orders, the BTC position, and the BTC asset's price increment.
- An order journal is written before the API call. An ambiguous response
  blocks the next order until the previous client order ID is reconciled.
- A persistent ownership marker prevents the bot from selling a BTC position
  that predates its own buy. The current paper baseline is $100 per buy with a
  $500 BTC exposure ceiling. The requested $50 and $500 probability tiers are
  defined but cannot be selected until probabilities are calibrated. Repeated
  completed round trips have no daily turnover cap. These amounts supersede
  the earlier $2–$30 order and $300-per-bot guidance.
- Credentials are sent to `curl` through standard input rather than argv;
  credential variables are stripped from the child process environment.
- An append-only local journal records quotes, decisions and broker responses.
  New quote-cross decision events retain both bid/ask pairs and the exact
  trigger direction/margin; older orders without those fields are not
  reconstructed or presented as if their prices had been retained.
- `--research-once` reads closed BTC, ETH and SOL candles from Pattern Forge
  for descriptive 5m, 1h and 1d context. This path cannot authorize orders.
- Raw captures stay on Dublin; the public monitor receives signed summaries,
  lab-scoped crypto/stock orders, fills and selected per-order decision events. Account-wide balances
  and unrelated holdings stay out of the public projection.
- `web/` contains the localhost-first paper monitor; its earlier Vercel upload is disabled. Dublin exports broker snapshots
  and the journal with Ed25519 signatures; Vercel never receives Alpaca keys.

The quote-cross strategy rule remains **uncalibrated**. The user specified the
new $100 baseline paper size on 27 September; neither its risk nor edge has
been calibrated. The requested Murphy/candlestick/Markov probability strategy
has no order authority yet. A [read-only Markov candle audit](research/markov_candle_audit.py)
measures next-bar transitions on Alpaca US BTC five-minute history and reports
its limits in [the evidence note](docs/pretrade-evidence.md). Between 08:36 and 10:26
UTC on 27 September, the earlier 30-second REST version sent 20 paper orders,
received 20 broker acknowledgements and reconciled all 20. It used
$299.999246395 of a then-active $300 daily buy-attempt budget; the broker later showed
zero BTC, no open order and the pre-existing 10 AAPL shares. The WebSocket
order path started at 13:00 UTC. An audit of 1,349 captured quotes from
13:16:05–13:38:43 UTC found zero crosses among adjacent quotes and six crosses
among 34 non-overlapping 30-second samples. This motivated restoring the
earlier diagnostic cadence on the WebSocket at 13:40 UTC; it is not an edge
estimate. A collector restart at 13:45:43 UTC produced a new session and a
fresh OCaml baseline. The next qualifying sample at 13:46:17 UTC led to an
Alpaca paper BTC/USD buy: the broker acknowledged it, reported a fill and no
open order, and OCaml reconciled it at 13:46:21 UTC. The public monitor showed
the same new order and fill in its 13:46:30 UTC snapshot. In this one cycle,
local receipt-to-decision was 7.409 ms, receipt-to-HTTP 1,302.796 ms, and the
HTTP round trip 316.036 ms. These are distinct measurements, not a latency
distribution or live-trading result. Pattern Forge and Energy Monitor remain descriptive context in
their own domains. See [the live-paper runbook](docs/LIVE-PAPER.md),
[the evidence and strategy limits](docs/pretrade-evidence.md), and the
[public HFT-lab plan](docs/PUBLIC-HFT-LAB-PLAN.md). The plan marks future work
and acceptance gates; it does not claim unbuilt steps are implemented.

## Trading desk

The current desk shows **Open positions**, **Analysis & execution**, **New paper
orders** and **Market charts**. Earlier closed-trade history, the old curve and
CSV export remain hidden after the reset. The new order cohort starts at
2026-10-04T19:36:49Z and distinguishes fills from pending/canceled attempts,
showing exact pre-submit evidence when retained. It does not infer net trade P&L
or explain a historical order using today's indicators.

Net marked P&L is fill cash flow + broker inventory marks + posted USD fees.
The displayed realized/posted-cost component is that provisional total minus
broker open-position unrealized P&L, not settled per-trade net P&L. Asset fees
and delayed posting prevent a claim of fully reconciled closed returns.

The retained accounting implementation uses actual snapshots, not a backtest;
its older curve is not exposed by the current positions-only API. Dublin data
capture and the deployed paper service continue independently. See the
[monitor guide](docs/TRADING-DESK.md).

## Build and test

### Local paper monitor (Windows)

Run `deploy/start_local_monitor.ps1` from PowerShell. It builds the web app,
fetches the public broker projection through the existing Dublin SSH connection,
and starts the monitor at **http://127.0.0.1:3000**. The SSH refresh worker runs
after each broker fetch plus a 60-second pause while this computer is on. A separate compressed SSH worker reads file-backed analysis/OMS status after a 15-second pause without broker calls. Analysis and broker reception timestamps stay distinct. Alpaca credentials stay on Dublin;
the web app reads `.local/telemetry.json` and disables its Blob ingestion route.
No Vercel plan or Blob storage is required for this local mode.

The Dublin Vercel upload timer is disabled for this setup; the paper trading
service stays active. See [local monitor operations](docs/LOCAL-MONITOR.md).

Runtime PID files and logs are in the Git-ignored `.local/` directory. A failed
refresh retains the previous snapshot, whose timestamp stays visible in the UI;
the UI warns when snapshots are older than two minutes (an uncalibrated operational threshold). The local file carries
the full fetched history and its completeness flags, without the Vercel 1 MiB
upload guard. Posted fees may still lag; the displayed paper result remains
indicative until broker accounting is reconciled.

```sh
opam install . --deps-only
opam exec -- dune build @all
opam exec -- dune runtest --force
opam exec -- dune exec bin/paper_crypto_main.exe -- --once
```

The `--once` mode reads one public quote and never places an order. On 27
September 2026, Alpaca accepted a BTC/USD IOC buy that was canceled after a
partial fill of 0.000000020 BTC; the net position was 0.000000019 BTC. Later
paper buys and sells were filled and reconciled. These are execution plumbing
checks, not performance results. The bot handles sub-$10 dust. The account's
existing 10-share AAPL position is outside its BTC/USD order path. The service
continues under the paper-only and per-position controls.

Paper fills are simulated and can differ from live execution. Even a working
paper order loop may lose money live after fees, spread, slippage, and adverse
selection.
