# Connection boundaries and operational checks

## Verified on 4 October 2026

| Provider | Market | Connection | Execution |
|---|---|---|---|
| Alpaca paper | BTC/ETH/SOL spot crypto | Authenticated data and broker | Existing BTC policy; other confluence entries paused |
| Alpaca paper | US stocks/ETF | Catalog, clock, IEX quotes, fractional router and closed-candle scheduler | Automatic policy in observation; new automatic orders disabled |
| Alpaca IEX | 30 stock/ETF symbols | WS authentication and subscription confirmed | Data only; Sunday check received no market ticks |
| Hyperliquid mainnet | 19 monitored HIP-3 contracts | Existing public market collector/scanner | Data only; no signer or real-money orders |
| OANDA practice | Conventional FX | Missing practice token/account | Data connector prepared; no FX execution adapter |

The scanner actually analyzed 91 instruments in 1m/5m/30m/1h/4h. The complete
Alpaca equity catalog contained 13,509 tradable entries; only 69 selected stocks/
ETF are scanned. Catalog membership is rechecked; available data, warmed frames,
valid candidates and execution authority are separate states. Dow/Nasdaq/energy
and currency ETFs are actual listed proxies, not cash indices, physical energy
or spot FX. Free IEX is a single-exchange feed, not full NBBO.

Nine bot-owned excluded crypto positions were sold at Alpaca paper and all nine
orders reported `filled`. BTC and SOL were the remaining broker crypto positions
at 14:53 UTC. AAPL and unrelated inventory were excluded from order authority.
BONK/PEPE pending IDs were recovered only after complete history, two authenticated
404 lookups, no open order and owned-balance checks. Recovery evidence and a ledger
backup remain private on Dublin. Broker decimal quantity text is now retained and
floored to the actual asset grid rather than rounded above available inventory.

## Stock paper router

`stock_paper_main.exe --check` refreshes public connection health and reconciles
durable pending IDs. An explicit buy uses dollar notional; a sell uses exact share
quantity. Orders are market DAY during the broker's open regular session. The
adapter validates active tradable fractionable stocks and caps buys at the user's
$500 tier. It blocks AAPL, unowned inventory, conflicting orders, duplicated ledger
IDs and malformed broker responses. It writes the pending request before POST;
uncertain outcomes retain their ID and are never blindly resubmitted.

No stock strategy is currently armed. API access was checked on Sunday, when the
broker clock reported closed and next regular open 5 October 09:30 New York.
Synthetic execution tests passed; no live-market stock fill is claimed.

The minute service now runs the [closed-candle scheduler](STOCK-AUTOMATION.md)
in OBSERVE. It connects available stock frame readings to tested owned entry/exit
handling and records current abstentions. Its new-order route remains disabled;
this is an engineering path tested with synthetic broker responses, not a claim
of successful automatic stock execution at the real paper broker.

## Conventional FX setup

Create an eligible OANDA **v20 practice** account and obtain its API token directly
from the provider. Do not paste the token into chat. On Dublin, run interactively:

```sh
sudo python3 /home/ubuntu/ocaml-paper-market-lab/deploy/install_fx_practice_credentials.py
sudo systemctl start ai-ocaml-fx-connection.service
sudo /home/ubuntu/ocaml-paper-market-lab/.venv/bin/python /home/ubuntu/ocaml-paper-market-lab/research/oanda_practice.py --candles
```

The installer makes one read-only practice request before saving an owner-only
file. The connector discovers actual account CURRENCY instruments and requests
the ten preferred pairs only when available. Only complete provider candles enter
the five-frame cache. FX tick volume is price-update count and midpoint OHLC is
not executable bid/ask pricing. The current adapter collects data; an owned,
reconciled FX execution adapter still has to be implemented and tested.

A [pure OCaml FX request planner](FX-REQUEST-PLANNING.md) now prepares exact
base-unit allocation from account-specific prices/home conversions, actual
precision, explicit price bounds and caller-supplied stops. Its synthetic checks
do not connect a practice account. HTTP submission, durable FX ownership and
uncertain-response reconciliation remain incomplete; order authority stays off.

Hyperliquid testnet catalog inspection found `xyz:EUR` and `xyz:JPY`; a funded
testnet wallet and tested signing/risk adapter would still be required for its
orders. These contracts cannot replace ten conventional currency pairs.

## Evidence and limits

OCaml build/unit checks and Linux synthetic OMS tests verify routing boundaries,
partial fills, lost responses, persistence, rejection and restart behavior. Public
monitor telemetry strips credentials, account IDs and unrelated holdings. The
Alpaca order-update stream was authenticated/subscribed; it does not replace full
REST reconciliation and does not prove a lossless provider sequence.

Paper execution does not establish live fill quality or profitability. The current
technical policies have no calibrated winning probability or validated edge.

Sources: [Alpaca crypto order support](https://docs.alpaca.markets/us/docs/crypto-trading),
[fractional stock trading](https://docs.alpaca.markets/us/docs/fractional-trading),
[free market-data limits](https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api),
[paper order updates](https://docs.alpaca.markets/us/docs/websocket-streaming),
[OANDA practice API](https://developer.oanda.com/rest-live-v20/development-guide/).

## Installation name mapping

The read-only exporter defaults to `ai-ocaml-market-capture.service`. An existing
installation can set `AI_OCAML_CAPTURE_SERVICE` in its private broker environment
file to its actual collector unit. This selects the health check only; it does
not rename, restart or duplicate a data collector, and the private unit name is
not exported to the public monitor. Invalid unit syntax stops the projection.
