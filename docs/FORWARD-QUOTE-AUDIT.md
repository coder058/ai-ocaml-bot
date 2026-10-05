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

## Separate frozen stream-exit attempt — before its first run

The existing Alpaca crypto capture has immutable provider quotes and actual
nanosecond reception clocks for BTC/ETH/SOL. Use those **only for subsequent
exit references**, keeping the same first-observed feature row and entry quote.
No earlier missing entry is repaired. No new connection or credential is needed.

All horizon, split, five-second freshness, 120-second lag and conditional T1
scenario choices above remain unchanged. Keep this attempt separate from the
REST-exit report: denser sampling changes which first future quote is observed.
It is not an optimized execution rule, actual broker fill or a promoted policy.
Both daily archive prefixes are hashed separately and incomplete appends skipped.

Before reporting this extension, freeze an explicit subset of **originally
recorded** `trend_candle_confluence_v1` **long** candidates. Do not recompute
the signal or infer membership from signed TA-Lib codes. Keep the unconditional
same-market/frame/fold controls, counts and no-order-authority boundary. This
subset remains a quote reference, not a stop-managed executed strategy backtest;
absent stock labels cannot be evidence to arm the stock scheduler.

For a controlled source comparison, load the feature prefix once and use one
common as-of time for both exit sources, with every other frozen choice above
unchanged. Publish both reports, including absent labels and failures. Do not
attribute differences from the earlier 92-label run solely to exit sampling,
because subsequent feature records also arrived.

```sh
.venv/bin/python research/forward_quote_audit.py \
  --journal /home/ubuntu/jsbot-paper-state/market-frame-decisions.jsonl \
  --quotes /home/ubuntu/jsbot-paper-state/market-capture/us/2026-10-04.jsonl \
           /home/ubuntu/jsbot-paper-state/market-capture/us/2026-10-05.jsonl \
  --quote-source crypto_stream --horizon-bars 1 --max-exit-lag-seconds 120 \
  --rest-exit-baseline /home/ubuntu/jsbot-paper-state/market-quotes-reference.jsonl \
  --split-at 2026-10-04T21:00:00Z --crypto-taker-bps 25 \
  --output /home/ubuntu/jsbot-paper-state/forward-stream-quote-audit.json
```

### Controlled stream/REST result — 2026-10-05

On one common feature prefix and as-of clock, stream exits supplied 133 labels
versus 103 REST exits; all 103 REST label identities were also present in the
stream result. Both had zero discovery observations and 8,071 missing fresh
first entry references. Stream timely-exit rejections: five; REST: 35. This
measures sampling coverage, not better trading performance.

The originally recorded frozen **long** confluence subset had ten stream labels,
only BTC 1m/5m. Its mean ask-to-bid reference movement was -5.2014212485856905 bps;
conditional T1 after-fee scenario -55.112946651224355 bps. REST had eight such
labels, means -5.49294064657785 / -55.403010274222844 bps. Neither subset supports
policy promotion; there were no stock labels, verified fill outcomes or calibrated
probabilities. The stream unconditional set had 133 references and 87 exploratory
pattern comparisons, mean -3.9787533968174844 / scenario -53.89638449704103 bps.

Feature prefix 339,490,971 bytes, SHA-256
`18977e3c4be89e6fe5c74aea3d505d2b96614b9068c3d13edfc4bd9772569cd7`.
REST quote prefix 230,988 bytes, SHA-256
`bbb0c9a08f62b66ccb7ef662c75e4b725ec851d19fc4a7bc5a834641d76e52d5`.
Stream day October 4: 44,033,079 bytes, SHA-256
`541c755dbff5ef5b9f8cb34f12a42ef8bd8c8ca38af4dbe3a185e78258498339`;
October 5: 2,149,397 bytes, SHA-256
`bd04a7ff2df11bff74de0544ca77856907be2fc321c2d4cc0aaac408a3a96b58`.
47,268 stream references passed source/receipt/freshness/price/size checks;
43,918 were unusable; 98,723 non-quote events were excluded. All prefixes and
full comparison rows remain in the private reproducible report.

## Prospective entry-source extension — 5 October

From the 01:15 UTC production scan, newly observed features can retain actual
recent receipts from the existing bounded WebSocket capture tail. Earlier
feature rows cannot gain later quotes. The entry reference must retain its
original captured reception plus `referenceCheckedAt`; the audit rejects checks
later than feature observation or earlier than captured receipt. It reports
`entryTransportCounts`, including `not_recorded` for older rows, rather than
inferring historical transport. This changes acquisition for new observations,
not the frozen horizon, temporal split, fee scenario, long membership or order
policy. It is not evidence of improved returns or execution.

## Unchanged prospective audit — 2026-10-05 01:29:54 UTC

Same original feature prefix/as-of across stream/REST exits, unchanged one-frame
horizon, 120-second lag, 21:00 split and published T1 scenario. Stream 191 labels
versus REST 155, all 155 common; no discovery labels. Original entry transports:
178 not recorded / 11 REST batch / two actually archived WebSocket. Those two
new source records were not retroactively attached to old observations. This
small count is not a general coverage or performance improvement claim.

Frozen long confluence: 14 stream references, mean -4.847230918918556 bps /
conditional fee scenario -54.76052505951608 bps. REST subset 12, likewise
negative. No policy promotion, calibrated probability, fills or broker P&L.

Feature prefix 352,173,472 bytes, SHA-256
`7989886bbaae849332ffe5e10e9ee9e24233fad1bc86edbaf275a1c50112b12b`.
Stream 4 October 44,033,079 bytes, SHA-256
`541c755dbff5ef5b9f8cb34f12a42ef8bd8c8ca38af4dbe3a185e78258498339`;
5 October 7,527,518 bytes, SHA-256
`4f80589ea14482f7a33c8a7c175f94054f4e3f1e125ac363f8166df5bb9415bc`.
REST 314,171 bytes, SHA-256
`fec08b5e0868fef2dc23f360c4a4c4b0ec9e0e8f6b9b2a858197a74abcfa7f75`.
