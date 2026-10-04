# Frozen multi-frame crypto paper experiment

## Engineering decision

This is an uncalibrated prospective **paper experiment**, not a profitable
policy promotion. The user requested broader paper execution and the five
frames. Before arming, the shared analysis passed closed-bar causality tests,
the pure OMS passed ownership/reconciliation tests, and the actual OCaml
executable passed five synthetic broker lifecycle tests. A Dublin observe run
at `2026-10-01T23:29:58Z` found seven fresh long signals; it posted no orders.
Most quote preflights abstained under the five-second freshness guard.

No after-cost edge, win probability, optimal stop or $500 conviction tier has
been measured. Earlier EMA-only and book policies did not demonstrate an edge.
This trend/candle experiment must be evaluated separately and every later
policy change recorded. More orders can increase losses.

## Simple pipeline

1. Native closed candles at 1m, 5m, 30m, 1h and 4h; preserve retrieval time.
2. Shared OCaml Pattern Forge indicator formulas and selected candle shapes.
3. A fresh rising EMA20/EMA50 trend plus bullish engulfing/hammer geometry may
   produce a long candidate. Alpaca crypto does not permit this bot to short.
4. One portfolio router selects the shortest eligible frame while flat. It
   records the origin frame and bar and prohibits competing positions in the
   same instrument. A signal bar is attempted once, even if IOC gets no fill.
5. Check paper account, USD crypto asset class, real broker increments,
   ownership, open orders, current quote and buying power before the IOC limit.
6. Persist a deterministic pending client order ID and its full reason before
   sending. Reconcile actual final quantities; canceled orders can have fills.
7. Show broker orders/fills and their explicit decision IDs in the monitor.

Entry target is the user's **$100 baseline**. The maximum of **ten experimental
tickets** is an **UNCALIBRATED GUESS** for bounded operational experimentation,
not an optimal portfolio weight. No new leverage or margin is requested.
BTC remains exclusively with its legacy rule and the user's $500 ceiling.
AAPL and other unrelated holdings are excluded from the public projection.

## Exit and failure behavior

- Exit when a fresh latest bid reaches the actual entry candle low, or a fresh
  reading has falling EMA trend on the origin frame. This exit definition is
  uncalibrated; no optimized target, duration or return has been inferred.
- Invalidation is a **local monitored exit**, not a resting broker stop. An
  outage or stale quote can delay it. IOC orders can fill partly or not at all.
- Sell at most the experiment's owned quantity and the actual broker position.
  Received-asset fee debits can reduce inventory. Dust below the broker's asset
  minimum stays owned and blocks reentry rather than being fabricated as flat.
- A timeout/unknown POST outcome retains its pending ID. Read-only order lookup
  must resolve it before another submission; a missing order is not blindly
  resubmitted. Corrupt or duplicate-symbol ledgers halt rather than reset.
- HTTP 422 is an explicit broker rejection; the same entry bar is not retried.
- A serialized systemd unit plus file lock prevents overlapping OMS instances.

## Scope and observability

The radar analyzes 36 Alpaca crypto/USD instruments, twelve listed US equity/
ETF proxies and nineteen verified xyz HIP-3 perps. This router grants order
authority only to eligible **non-BTC Alpaca crypto**. The other venues remain
analysis only. xyz EUR/GBP/JPY are derivatives, not ten spot FX pairs.

Broker marks and fill cash flows are summed in USD. Inventory residuals and
received-asset fees are kept separately for each asset. Crypto debits already
reflected in inventory are not subtracted twice. USD fees cannot be allocated
to individual trades when broker activity does not identify them; the combined
lab result remains provisional, not fully reconciled realized P&L.

Current checks use a five-second quote guard, a two-minute analysis guard and
a fifteen-second OMS timer. These are **UNCALIBRATED GUESS** operational choices,
not exchange latency guarantees or evidence of HFT. REST candle analysis with
IOC paper orders is not an HFT strategy, and paper fills cannot establish live
execution quality or live profitability.

## Operations

Units: `ai-ocaml-multi-paper.service` / `ai-ocaml-multi-paper.timer`. Default
`MULTI_PAPER_ORDERS=0` keeps observe mode; explicit local systemd configuration
must arm it alongside the existing `PAPER_ORDERS=1` paper gate.

Private state in `/home/ubuntu/jsbot-paper-state/`:

- `multi-paper-ledger.json`: durable ownership/pending order/seen signal bars.
- `multi-paper-events.jsonl`: append-only per-order signal and broker outcomes.
- `multi-paper.json`: small monitor snapshot, with reasons for abstaining.

To pause entries and exits while preserving the ledger, stop the timer and the
running service. Do not delete the ledger, change credentials or sell unrelated
positions to "reset" the experiment. Resolve any retained pending ID at the
paper broker before changing ownership. Pausing the service also stops local
invalidation exits; this limitation must remain visible to the operator.
