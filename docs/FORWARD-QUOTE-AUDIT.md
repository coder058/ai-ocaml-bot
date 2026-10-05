# First-observed quote reference audit

This method compares recorded ask and later bid references. It does not simulate
fills, broker P&L, execution latency or winning probabilities, and has no order
authority. Collection is sampled, with raw sizes and no depth/impact model.

## Frozen attempt before first report — 2026-10-05

- Horizon: one native frame duration after actual feature receipt. **UNCALIBRATED
  GUESS:** inherited one-bar exploratory design, not an optimized holding period.
  This differs from the gross-candle method's next wholly future candle.
- Exit lag limit: 120 seconds after the horizon. **UNCALIBRATED GUESS:** reuse of
  an existing operational freshness interval, not a fitted execution parameter.
  Missing or later exits are rejected, rather than forward-filled.
- Split: unchanged `2026-10-04T21:00:00Z` from the gross audit. Actual quote
  collection began at 21:18 UTC, so this attempt has no quote-aware discovery
  sample. Subsequent observations cannot be called independent validation of a
  previously selected quote policy.
- Crypto scenario: 25 basis points per taker leg, from the published T1 tier in
  [Alpaca crypto fees](https://docs.alpaca.markets/us/docs/crypto-fees). The user's
  actual volume tier and allocated posted fees have not been verified. This is
  a conditional scenario, not their actual costs. Buy fees reduce the asset
  received; sell fees reduce cash. Equity total costs remain unknown/null.
- Every nonzero pattern code is compared as a **long** reference to the same
  symbol/venue/frame/fold unconditional reference set. Negative codes do not
  establish short availability; no pattern ranking selects a trading policy.

## Causal rules

Use the original first feature row's quote only. Later quotes cannot repair an
earlier missing, stale or invalid entry. Verify provenance, source feed, allowed
instrument, receipt before feature observation and the existing five-second
quote age guard at both receipt and observation, retaining nanosecond source
timestamps. Outcomes use the first later received fresh quote whose source time
is at or beyond the fixed horizon, never the best future price. Reject late
receipts, future observations, missing quotes and split-crossing outcomes. Hash
both frozen input prefixes. All related timeframes/patterns remain dependent.

## Reproduce on Dublin

```sh
cd /home/ubuntu/ocaml-paper-market-lab
.venv/bin/python research/forward_quote_audit.py \
  --journal /home/ubuntu/jsbot-paper-state/market-frame-decisions.jsonl \
  --quotes /home/ubuntu/jsbot-paper-state/market-quotes-reference.jsonl \
  --horizon-bars 1 --max-exit-lag-seconds 120 \
  --split-at 2026-10-04T21:00:00Z --crypto-taker-bps 25 \
  --output /home/ubuntu/jsbot-paper-state/forward-quote-audit.json
```

Positive reference fractions are empirical sample statistics, not calibrated
winning probabilities. Even a positive fee scenario lacks latency, queue,
partial fills, impact and actual account fee allocation. Paper/reference results
do not establish live profitability. Do not promote a policy from this audit.

## First actual run — 2026-10-05T00:08:18Z

- 92 long quote references, all in the later fold; zero quote-aware discovery
  observations. Composition: BTC 1m 72, 5m 13, 30m three, 1h one; SOL 30m and
  1h one each; ETH 30m one. These are overlapping/correlated reference labels,
  not 92 independent trades or executed pattern policies.
- Mean ask-to-bid movement: -2.8149645280571876 bps. Under the explicitly
  conditional T1 scenario: -52.73840729894407 bps. No after-scenario reference
  was positive in this sample. These aggregate means do not test a selected
  candidate policy, establish actual account fees or measure broker P&L.
- 73 exploratory pattern comparisons retained. Rejected: 818 not-ready signals,
  7,716 missing/invalid/stale first entry references, 31 missing timely exits.
  Missing earlier quotes were not backfilled.
- Feature prefix: 335,990,621 bytes, SHA-256
  `396732abc9ddab1f405f82c328ce696d684890c811dabc46b3f8f872af84c21b`.
  Quote prefix: 209,253 bytes, SHA-256
  `81cb181f4a80719fd6484295e73c9bd5f5d6eb642450dfaaed11c36f900146ae`.
  Quote source had 440 lines, 144 usable and 296 rejected references.
- Ten causal synthetic audit tests passed locally and on Dublin Python 3.10,
  plus five quote-capture and six gross-audit regression tests in both places.

No policy was promoted. The sample is crypto-only and contains no validated
stock/ETF execution opportunity. No conclusion about spot FX was possible.
