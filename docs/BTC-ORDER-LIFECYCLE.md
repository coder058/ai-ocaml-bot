# BTC paper order lifecycle and evidence

This is the existing `quote_cross_30s_v1` systems demonstration, not the
Murphy/Markov candidate policy or evidence of an edge. The $100 baseline and
$500 BTC exposure ceiling remain unchanged. Only the hardcoded Alpaca paper
origin is used; AAPL and unsupported crypto entries remain protected.

## Durable reconciliation

`lib/btc_order_state.ml` validates the lookup against the retained client ID,
BTC symbol, side, documented lifecycle and exact decimal quantities before
changing ownership or removing a pending file. New intents retain the actual
nine-decimal submitted quantity alongside side and ID. Legacy two-field
intents remain readable and are bounded by the matching broker order's quantity.
Missing fills never become invented zeros; nonzero excess precision, overfills,
wrong identity, inconsistent full fills and unknown lifecycles remain unresolved.

Terminal buy orders with actual partial fills retain ownership; partial canceled
exits retain the marker. Validated full exits clear it. A timeout/nonterminal
response keeps the same intent and prevents a new order. Reconciliation events
are persisted before local mutation. Repeated terminal reconciliation is
idempotent after interruption. No lookup response is selected by proximity.

The ownership marker records the most recent bot buy identity, not a complete
per-lot ownership ledger. Agreement between marker presence and broker position
presence is explicitly named **ownership marker consistency**, not independent
proof of every share's origin. Manual BTC balance changes remain a limitation.

## Actual pre-submit evidence

`lib/btc_quote_clock.ml` parses actual provider UTC source timestamps without
discarding nanoseconds, rejects invalid calendars/precision, and checks source
and receipt against the inherited five-second guard. A source timestamp after
actual capture receipt is rejected. The guard is rechecked after durable intent
and journal writes, immediately before POST; an expired quote produces NOT_SENT
and no HTTP request. This is a freshness bound, not a measured HFT guarantee.

The BTC journal now records its measured gettimeofday clock at microsecond
resolution. Nanosecond ages use that measured local clock and exact provider
source/collector clocks; expressing an age in nanoseconds does not establish
nanosecond accuracy of the local gettimeofday measurement.

BTC_PREFLIGHT records the actual account gate, no unresolved durable intent,
no open broker orders, marker/position agreement, buying-power/exposure check
or risk-reducing exit, exact requested quantity, limit and quote clocks. Its
event is durable before POST. These are observed checks, not private thoughts,
winning probabilities or new evaluations of past charts.

The exporter joins only the exact client ID/side and original decision quote,
verifies actual preflight receipt before broker submission, and whitelists public
facts. Conflicting retained events, future/retrospective receipts, malformed facts
or another instrument cannot supply a preflight. The localhost order detail shows
readable retained checks separately from the original quote trigger. Old orders
without these facts remain unavailable; no retrospective explanation is created.

## Reproduce verification

```sh
TZ=UTC opam exec -- dune build @all
TZ=UTC opam exec -- dune runtest --force
python3 -m unittest discover -s test -p test_export_telemetry.py -v
cd web
npm test
npm run build
```

The real reconciliation module's tests use temporary files and injected lookup
responses: identity/quantity failures, uncertain requests, event-write failure,
nonterminal/partial/full lifecycle and unchanged durable intent. Quote-clock tests
check nanosecond guard boundaries, invalid dates, source/receipt futures and
stale sources even without a REST receipt. Synthetic values are not market data.
Exporter tests also reject a preflight one nanosecond after broker submission;
frontend projection excludes unknown/private risk fields and unverified clocks.

At 02:15:03 UTC on 5 October, the deployed hardened reconciliation processed an
actual terminal BTC paper sell with broker filled quantity `0.001150443` after
its earlier pending acknowledgement; the pending file was absent on inspection.
The later quote-clock/preflight deployment restarted at 02:16:03 UTC. At the
02:17 inspection its high-resolution quote journal was active but no new
BTC_PREFLIGHT event had occurred: do not call that a verified new risk-evidence
broker trade. Subsequent real observations must be recorded separately.

At 02:20:04.841189552Z, Alpaca received a natural paper buy with actual original
requested quantity `0.001154981` at limit `86581.44`: quantity × limit equals
`99.99991815264` USD. One captured fill was `0.0001155` at `86581.44`, or
`10.000156320` USD; the remainder was canceled. The original quote decision was
recorded at 02:20:02.494338Z and exact matching preflight at 02:20:04.528095Z,
both before submission. At 02:20:37.964400Z, validated reconciliation preserved
that partial and cleared pending. This was observed without forcing an order.

Browser verified this exact partial with readable controls and later the
separate **$100 requested / $10 filled** values sourced from original broker
quantity/limit fields. A market order without original notional is not valued
using a guessed limit or current quote. Old history remains hidden. Responsive
970/480 CSS-pixel checks matched document and evidence scroll widths. Proofs:
ignored local `.local/btc-preflight-proof.png` and `.local/btc-request-fill-proof.png`.
Final verification: full OCaml build/dune checks, exporter 20 tests locally/on
Dublin system Python, frontend 40 tests and production build/typecheck.

Source: [Alpaca order identity and lifecycle](https://docs.alpaca.markets/us/docs/orders-at-alpaca).
Paper execution still differs from live liquidity, fees and fill behavior.
