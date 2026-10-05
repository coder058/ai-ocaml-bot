# Separate first-session opportunity cohort

## Actual gap, not a retrospective signal repair

At 08:09 UTC on 5 October, DIA, QQQ and NVDA's current 4h source candle
started **2 October 16:00 UTC**. Its original first observation was
**2 October 20:01:37.772159 UTC**, with `market_closed`, no candidate and no
analyzer fingerprint then. Re-evaluating that held candle during Monday's open
session does not make it a new first-ever source candle. The original journal
and [original stock quote protocol](STOCK-QUOTE-PROTOCOL.md) retain those facts.

This companion records a distinct actual opportunity: the first regular-session
evaluation per **session date / instrument / frame / source candle**. It captures
all statuses and absent candidates/quotes. It cannot select a later favorable
reading, invent the earlier quote or change the original first-candle cohort.
The same held bar across different days remains correlated, not independent
evidence. The choice of first session reading is an **UNCALIBRATED GUESS**, not
optimized signal timing or an execution recommendation.

## Frozen scope and causality

- Companion created **2026-10-05T08:14:37.718943Z**, before the first session.
  Exact UTF-8/LF bytes in
  `research/cohorts/stock-session-opportunities-20261005-06.json`:
  SHA-256 `6d1300c7fc54d5ab3f19e78d97cd446b45bd189b9a271e13edd505227d2fa033`.
- Inherits the unchanged original manifest's actual calendar, 69 listed stocks/
  ETF, five native frames, 30 actual IEX stream subscriptions, compiled OCaml
  candidate fingerprint, long policy and discovery October 5 / comparison
  October 6. Base SHA-256
  `6dc7d3b44459f6bf1a236f6237c9ca22272631acfccfe650c1dc718d39a40b75`.
  AAPL, crypto, HIP-3 and dates outside that cohort are excluded.
- Actual broker clock must say open and its timestamp must precede the actual
  new observation inside the pinned regular session. The actual matching source
  candle must be closed at the analyzer boundary. Future clocks, changed binary,
  duplicate analyzer slots, missing/mismatched candles fail this capture.
- Already recorded date/instrument/frame/source bars cannot gain later changes.
  New record contains the actual newly computed reading, its earlier known quote,
  broker clock, analyzer hash and response clock. It does not claim that newly
  retrieved historical features were known when that old candle first closed.
- Append is flushed/fsynced before cache checkpoint. A crash between journal and
  checkpoint can produce duplicate identity; identical copies deduplicate and
  conflicting copies are withheld. No arbitrary latest-version selection.
- Same existing one-frame observation-relative horizon / 120-second exit lag:
  **UNCALIBRATED GUESS**, not a calibrated holding period or measured execution
  latency. Horizons crossing close are rejected, never repaired next session.
  First fresh IEX archive exit and same-prefix REST comparison retain the existing
  guards. Entry remains the new original session quote, not last candle close.
- `forward_features.py` only copies already-computed fields. It has no TA library,
  indicator calculation or policy change; `murphy_analysis` re-exports the same
  serialization. This allows the read-only research module to run without TA-Lib.

## Verified deployment, not session results

Nine new session tests passed locally and on Dublin. Nine pipeline, nine Murphy,
nine original-stock-protocol and six first-candle regressions passed on Dublin.
The initial local import failed because TA-Lib was absent; the pure serialization
extraction resolved it. An initial Dublin module-style test invocation collided
with the Python `test` package; explicit discovery ran the actual repository
tests. These failed attempts were not market-data or broker failures.

Actual **08:23** automatic scan: no retrieval errors, 18.36213477794081 seconds,
zero session readings / zero tracked slots and an actual empty new journal.
This is the expected before-open result, not proof of a regular-session capture.
No old rows were copied to it.

`ai-ocaml-stock-session-audit.service` has **PrivateNetwork=yes**, no credential
file or order flag; it reads existing files and writes only the dedicated private
`stock-session-audit/` directory. Its timer uses the original October 5–6
13:00–20:55 UTC five-minute exploratory cadence. Calendar parser verified next
13:00 UTC; first session open remains **13:30 UTC**.

Actual first report **08:25:10.850554Z**: 345 planned slots, zero observations /
references, journal zero bytes, `awaiting_first_session`, exit status zero.
Immutable artifact `report-20261005T082510850554Z.json`, 51,268 bytes, SHA-256
`2ae395b151db40743c13abf0040f71fafc7625b75b4675f25e1fb68852ed8aa4`.
Individual CPU time 0.235485s is a before-open read-only observation, not trading
latency or HFT performance.

Twenty-four exporter tests locally/Dublin and 45 frontend tests passed;
production build/typecheck passed. Public projection validates both pinned
manifests and safe aggregate counts, without raw labels, private rows, returns,
broker P&L or fee estimates. Per-frame counts are checked against their totals.
The localhost validation section presents this separately from the original
first-ever-candle cohort and from actual broker execution.

## Reproduce without network or orders

```sh
cd /home/ubuntu/ocaml-paper-market-lab
.venv/bin/python research/stock_session_opportunities.py \
  --journal /home/ubuntu/jsbot-paper-state/stock-session-opportunities.jsonl \
  --rest-quotes /home/ubuntu/jsbot-paper-state/market-quotes-reference.jsonl \
  --capture-root /home/ubuntu/jsbot-paper-state/market-capture/iex \
  --output /home/ubuntu/jsbot-paper-state/stock-session-audit/report.json
python3 deploy/retain_stock_audit.py \
  --report /home/ubuntu/jsbot-paper-state/stock-session-audit/report.json
```

Actual open-session readings, missing quote/source counts, later frozen outcomes
and execution/stop/cost evaluation remain pending. No policy is promoted by this
plumbing; reference/paper results do not establish live profitability. This may
lose money live.
