# Closed-candle stock/ETF scheduler

## Implemented boundary, verified 4 October 2026

`stock_auto_main.exe` connects the shared OCaml readings to the existing durable
stock router. The deployed service runs **OBSERVE**, without `--execute`: no new
automatic stock order is armed. Broker access is actual Alpaca paper access;
execution/failure checks used synthetic responses. A Sunday observation is not
an open-session stock execution test.

```mermaid
flowchart LR
  A[Closed stock/ETF frames] --> B[Frozen OCaml long candidate]
  B --> C[Scheduler: ownership and gates]
  C --> D[Serialized durable stock router]
  D --> E[Persist pending request and preflight]
  E --> F[Hardcoded Alpaca paper origin]
  F --> G[Validate cumulative fills and reconcile]
  G --> C
```

## Decision and lifecycle

1. Reconcile the ledger before selecting requests. Corrupt identities, duplicate
   IDs and decreasing cumulative fills halt the scan. Unknown responses retain
   the original client ID.
2. Accept the frozen `trend_candle_confluence_v1`, fresh analysis/receipt times,
   read-only source, valid closed frame, long candidate, rising trend and bullish
   engulfing/hammer shape. AAPL, crypto and HIP-3 cannot use this route. All five
   requested frames are checked; every TA-Lib detection is not an entry rule.
3. Inspect managed owned exits before new entries. Manual positions are not
   adopted. A newer manual buy cannot inherit an earlier automatic entry's stop.
4. Entries use the user's $100 baseline and a deterministic symbol/frame/bar/
   policy identity. One position per instrument prevents other frames scaling in.
   Previously attempted identities are not blindly retried.
5. At the router boundary, recheck account, regular session, exact own quantity,
   external inventory conflicts, open/pending orders and asset eligibility. Fetch
   a fresh IEX quote and reject an already-invalidated entry. IEX is not full NBBO.
6. Save request and factual preflight/candle evidence before POST. Validate broker
   identity and cumulative fills. Partial entries own only actual filled shares.
7. A local exit triggers at the entry candle low or falling EMA trend on its
   origin frame. Recheck the trigger with a fresh router quote and sell only the
   remaining exact owned quantity during the regular session.

This is **not a resting broker stop** and cannot protect overnight gaps or work
while the service/session is unavailable. The EMA reversal is an **UNCALIBRATED
GUESS**, not a fitted exit. Snapshot/quote guards and the ten-position operational
cap inherit explicitly uncalibrated choices from the existing experiment; these
are not confidence estimates or optimal sizing.

## Gates and deployment

- Scheduler submission requires `--execute`, `PAPER_ORDERS=1`,
  `STOCK_PAPER_ORDERS=1` and `STOCK_AUTO_ORDERS=1`.
- New entries also require `STOCK_AUTO_NEW_ENTRIES=1`. Owned exits and pending
  reconciliation are separate from the new-entry gate.
- The router independently checks the automatic gates, immutable intent and
  fresh quote. An earlier scheduler quote cannot substitute for its quote.
- Installed `ai-ocaml-stock-paper.service` deliberately supplies no `--execute`.
  The existing minute timer reconciles and records `stock-auto.json`; credentials
  remain private. Localhost labels this **Stock policy in observation**.

At 20:24:54 UTC the actual service completed successfully, its timer was active,
the broker session was closed, mode was OBSERVE, newEntriesEnabled was false,
eligibleLongSignals/routerInvocations were zero, and ownedPositions was empty.
No stock fill is claimed from this deployment.

## Verification and remaining activation gates

Pure OCaml tests cover all five boundaries, source/policy restrictions, future/
old bars, selected shape/trend, invalidation and stale quotes. Eight new real-
binary synthetic scheduler tests cover owned entry/exit, exact-bar deduplication,
disabled gates, closed sessions, stale/invalidated quotes, POST timeout before/
after acceptance, partial quantity, manual/external inventory, protected products
and corrupted ledgers. The ten existing router runtime tests also pass. Synthetic
curl requires both ledger and DECISION event before POST and the exact paper URL.
These are engineering checks, not backtests.

### Measured event timestamps — 5 October 02:44 UTC

New stock-router decision/acknowledgement events, durable `sentAt` fields and
stock/multiframe operational receipts preserve the measured microseconds from
`gettimeofday`. Native candle starts keep their original whole-second format.
Earlier journals are not rewritten; their one-second uncertainty remains.
Microsecond representation is not a claim of clock accuracy, synchronization
or HFT latency.

The full OCaml build/unit checks and 26 real-binary synthetic lifecycle tests
(ten stock router, eight scheduler, eight multiframe) passed on Dublin. At the
synthetic HTTP boundary, tests inspect the actual durable files and require
intent time <= decision time <= receipt of POST. These checks do not imply an
actual open-session stock fill. Production `stock-auto.json` at
02:44:05.661216Z was OBSERVE, session closed, zero router invocations and no
owned stock positions; `stock-connection.json` and `multi-paper.json` also
retained their new fractional operational clocks.

Before activation: collect open-session first-observed candidates and executable
quotes, evaluate chronological costs/controls, inspect the frozen policy's
evidence and verify the actual enabled lifecycle at paper. Current gross candle
labels do not supply execution costs or calibrated winning probabilities. This
system can still lose money live.
