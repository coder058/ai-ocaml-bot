# Prospective stock / ETF quote cohort

Read-only research, not an enabled strategy, broker execution model or claim of
profitability. It does not arm the stock scheduler.

## Frozen before the first session

Actual calendar response received **2026-10-05T06:03:16.73085Z**; manifest created
**06:03:16.751889Z**. Configuration: `research/cohorts/stock-20261005-06.json`.
Exact UTF-8/LF SHA-256:
`6dc7d3b44459f6bf1a236f6237c9ca22272631acfccfe650c1dc718d39a40b75`.

Actual broker calendar: October 5 and 6, 09:30–16:00 New York, **13:30–20:00 UTC**.
First date discovery; later date chronological comparison. **UNCALIBRATED GUESS:**
consecutive upcoming sessions are an exploratory design. Two sessions, related
frames and many patterns cannot establish independent validation, calibrated
winning probabilities or edge. The dates/rule were fixed before their results.

Sources: [US trading calendar API](https://docs.alpaca.markets/us/reference/legacycalendar),
[stock stream schema](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data).
IEX is one exchange, not a consolidated NBBO.

## Pipeline, step by step

1. Keep the existing 69 stock/ETF symbols and five native frames:
   1m/5m/30m/1h/4h, **345 correlated slots**. Separately record the actual 30 IEX
   WebSocket subscriptions. Other monitored products retain REST/history;
   monitoring does not imply a nonexistent stream subscription.
2. Hash the deployed OCaml analyzer before/after actual use. Replacement during
   invocation fails the scan. New first observations retain the fingerprint;
   old rows cannot acquire a reconstructed one. Actual deployed fingerprint:
   `e6b758316d3d5d0b84b26933772b23a194affa6f374e132614d6840fb620f6a9`.
   Source/library hashes are provenance, not signed deployment attestation or
   complete OCaml/TA-Lib parity.
3. Reuse original first features, including missing patterns/quotes. Reject
   AAPL, crypto, another policy or an unverified/different analyzer.
4. Entry is the original received IEX quote, inside the actual session and fresh
   at observation under the inherited five-second guard. No historical quote
   is repaired using today's data.
5. Horizon: one native frame after feature receipt; exit lag: 120 seconds.
   **UNCALIBRATED GUESS:** inherited exploratory choices, not calibrated holding
   periods/latency. Horizons reaching session close are excluded; absent 4h
   opportunities are not forced into the next day.
6. Stream processing retains the first fresh receipt at/after each fixed horizon,
   with prefix hashes. Retained quote memory follows observed horizons, not all
   daily events. Contradictory/decreasing clocks block that instrument. Missing
   daily archives remain absent.
7. Compare stream and REST exits on one common feature prefix/as-of clock. Keep
   both, never switch sources for the best result. Long subset uses originally
   recorded `trend_candle_confluence_v1`, not a winning-pattern search. Controls
   match instrument/frame/fold.
8. List every planned slot, observed/fingerprinted feature counts, references
   and rejections. No fills, short availability, managed-stop return, net costs
   or winning probabilities are inferred.
9. Retain exact dated report bytes through an atomic non-replacing archive;
   conflicting bytes under the same timestamp fail. Original attempts remain.
10. Localhost shows safe dated coverage inside the existing collapsed validation
    panel, separately from actual broker orders and gross closed-lot P&L.

## Automatic Dublin collection and actual checks

`ai-ocaml-stock-quote-audit.timer`: October 5–6 only, 13:00–20:55 UTC, every five
minutes. **UNCALIBRATED GUESS:** local research cadence, not execution speed/alpha.
`systemd-analyze calendar` verified the expression and next trigger at 13:00 UTC;
it does not repeat on later dates. No credential file or order adapter; private
network namespace. Reads existing captures and writes only
`/home/ubuntu/jsbot-paper-state/stock-quote-audit/`.

First direct attempt failed writing a root-owned report directory. Resolved with
a dedicated user-owned directory without changing earlier private artifacts.
Actual service **06:05:54.820386Z**: awaiting first session, 345 slots, zero
stream/REST labels. Dated artifact SHA-256
`96489c68d49986626df25050f93627d6b3bd661d6e00fed76785f7849c52bc03`.
After network isolation/retention, service **06:20:12.595208Z** likewise had zero
labels before the session; artifact SHA-256
`e4d32bb926e127f41a40d6bf611ec086d3e095e5c7a562e5903f8819122f8717`.
CPU times: 11.548s / 14.918s, individual observations, not a latency comparison.

Actual scanner at **06:12:19.734727Z**: 20 new first-frame decisions, matched
analyzer fingerprint, 18.787327102036215s. Bounded real tail: 25 matching
fingerprinted records. This verifies producer plumbing, not stock execution.

Checks: nine protocol tests locally/Dublin, nine pipeline tests on Dublin,
six first-feature and 14 quote-audit regressions; two real-file retention tests
locally/Dublin; 23 exporter tests locally/Dublin; 45 frontend tests, production
build/typecheck. Fixtures are not fills. Browser verified actual report/dates,
all 455 charts and no document/card overflow at 970/480 widths; normal viewport
restored. Proof `.local/stock-prospective-validation-proof.png`.

## Reproduce without broker requests

```sh
cd /home/ubuntu/ocaml-paper-market-lab
.venv/bin/python research/stock_quote_audit.py \
  --manifest research/cohorts/stock-20261005-06.json \
  --manifest-sha256 6dc7d3b44459f6bf1a236f6237c9ca22272631acfccfe650c1dc718d39a40b75 \
  --journal /home/ubuntu/jsbot-paper-state/market-frame-decisions.jsonl \
  --rest-quotes /home/ubuntu/jsbot-paper-state/market-quotes-reference.jsonl \
  --capture-root /home/ubuntu/jsbot-paper-state/market-capture/iex \
  --output /home/ubuntu/jsbot-paper-state/stock-quote-audit/report.json
python3 deploy/retain_stock_audit.py \
  --report /home/ubuntu/jsbot-paper-state/stock-quote-audit/report.json
```

Next: actual open-session source/quote coverage and all fixed comparisons, then
execution/stop/cost-aware evaluation before considering paper activation.
Positive reference moves alone can still lose money live.
