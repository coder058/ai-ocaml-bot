# Live paper engineering run

`paper_crypto_main` is an OCaml diagnostic trading loop for **Alpaca paper**.
The Dublin service currently runs `--paper --hot-stream`, receives BTC/USD
quotes and closed-minute bars from an Alpaca WebSocket collector over a local
Unix socket, and has `PAPER_ORDERS=1` in a root-owned environment file. Trading
still requires both `--paper` and that environment gate. The older REST quote
poll remains available as a diagnostic fallback.
The only trading origin is `https://paper-api.alpaca.markets`.

The decision is deliberately simple: compare a live quote with a reference
quote sampled at the earlier REST loop's 30-second cadence; buy when the new
bid rises above the reference ask, or sell the bot-owned position when the new
ask falls below the reference bid. Every WebSocket quote is still received,
validated and archived. This cross-spread rule has **not** been calibrated or shown to
have an edge. The user changed the paper sizing on 27 September: the active
experimental baseline is $100 per buy and the BTC exposure ceiling is $500.
The requested $50 lower and $500 higher probability tiers await a calibrated
probability model; the live quote-cross rule does not label them. The bot uses IOC limit
orders, one pending order at a time, a durable pre-submission journal, open
order/account/position checks, a paper-only host, and an ownership marker. It
refuses an existing BTC position it cannot attribute to itself. It does not
place live orders.

## Broker cash-flow checkpoint, 27 September 2026

At **18:25:38 UTC**, the signed monitor snapshot had complete broker order and
fill pagination and no open BTC position. The read-only
[fill cash-flow audit](../research/paper_fill_cash_flow.py) identified 64 bot
orders and 74 bot fills (39 buy fills, 35 sell fills). It summed
**$452.89327845983** of executed buy notional and **$451.77872160523** of
executed sell notional: **−$1.11455685460** of filled cash difference before
separately posted fee activities. AAPL was excluded. Alpaca returned zero
`CFEE` and `FEE` activities when queried at about 18:26 UTC, and documents
that crypto fees can post at the end of the day. Thus **net P&L is not yet
verified**, and the paper result does not predict live profitability.

At 18:27 UTC, after that flat checkpoint, the new $100-target policy submitted
a buy for 0.001180659 BTC. Alpaca filled only 0.000471840 BTC and canceled the
remainder; the reconciled BTC position was 0.000470659 BTC, with no open or
pending order. This was a partial paper fill, **not a $100 completed buy**.

Alpaca may partially fill an IOC order and cancel its remainder. The first
observed order on 27 September 2026 filled 0.000000020 BTC, leaving a net
0.000000019 BTC position. The bot keeps ownership of that residual, suppresses
sub-$10 sells, and permits a later buy only when the total BTC position would
remain within the current $500 position cap. Such a tiny fill is not evidence of
strategy quality.

Selected Pattern Forge indicator and shape formulas are computed from Alpaca
closed bars in OCaml, with a separate retrieval-timestamped Alpaca 5m snapshot
for context. They are descriptive and have no order authority or calibrated
probability. Pattern Forge also reads Hyperliquid candles and Energy Monitor reads public
electricity/gas feeds. Neither provides a calibrated signal for Alpaca BTC
execution. Their current OCaml probes are not part of this order path. A later
research run can compare Pattern Forge's closed BTC candles with Alpaca fills,
and Energy Monitor can be evaluated against an energy-linked asset if that
market and aligned timestamps become available. Connecting either to order
authorization now would invent a trading relationship.

## Checks on Dublin

```sh
cd /home/ubuntu/ocaml-paper-market-lab
opam exec -- dune runtest --force
opam exec -- dune exec bin/paper_crypto_main.exe -- --once
sudo bash -c 'set -a; . /etc/jsbot-paper.env; set +a; /home/ubuntu/ocaml-paper-market-lab/_build/default/bin/paper_crypto_main.exe --check-positions'
sudo systemctl status jsbot-paper --no-pager
sudo journalctl -u jsbot-paper -n 30 --no-pager
```

The current paper service is armed. It enters MONITOR mode if `--paper` is
omitted or `/etc/jsbot-paper.env` does not contain:

```text
APCA_API_KEY_ID=<paper key id>
APCA_API_SECRET_KEY=<paper secret>
PAPER_ORDERS=1
```

The file must be owned by root with mode 0600. Do not paste secrets into a
shell command, terminal history, issue, log or chat. Install them with a local
interactive editor on the VPS, then restart the service. `journalctl` should
show `PAPER_ORDER`, quote observations, decision holds, any `SEND`, broker
`ACK`, and later `reconcile`. Verify orders and positions against the Alpaca
paper dashboard. A `pending` journal that cannot be reconciled stops further
submissions and needs operator review.

The older REST service sent 20 paper orders from 08:36–10:26 UTC on 27
September; each had a broker acknowledgement and terminal reconciliation.
Its buy attempts reached $299.999246395 of the then-active $300 daily budget.
That daily limit was removed after the user's clarification. The earlier $30 BTC
position/order cap was replaced on 27 September by the $100 baseline/$500
exposure ceiling. Pending-order reconciliation and the paper-only endpoint remain. The
WebSocket path began at 13:00 UTC. Its original adjacent-quote rule produced
no candidate among 1,348 quote pairs audited from 13:16:05–13:38:43 UTC;
the earlier 30-second cadence found six descriptive crosses among 34 samples.
The WebSocket policy was changed to that cadence at 13:40 UTC. The OCaml consumer has shown live
quotes, closed bars and a 5m context loaded from 352 contiguous Alpaca bars.

At 13:45:43 UTC the collector was restarted for a recovery check. It
authenticated again, and the OCaml process logged a new feed session and
reset its quote baseline at 13:45:44 UTC. A 13:46:17 UTC sampled cross led to a
paper BTC/USD buy with client order ID
`jsbotbtcbuy20260927T134617065211486Z`. Alpaca acknowledged it and returned
a completed fill; OCaml reconciled the order at 13:46:21 UTC. A broker read
showed no open orders, a BTC position of 0.000235149, and the protected 10
AAPL shares. The signed public snapshot at 13:46:30 UTC showed 27 account
orders and 37 fill activities, including the new buy. The filled order size
was 0.000235739 BTC; the broker position was smaller. This runbook does not
attribute that difference without a fee-activity reconciliation.

For this single cycle, the service logged 7.409 ms from local receipt to
decision, 1,302.796 ms from receipt to the start of the HTTP order request,
and a 316.036 ms HTTP round trip. The timing excludes neither broker checks
nor journal writes from the middle interval. It does not establish a latency
distribution or an HFT execution capability.

Paper fills are simulated from quotes. They do not establish live fill quality
or profitability. The cross-spread rule may lose money after spread, fees,
slippage, and adverse selection.
