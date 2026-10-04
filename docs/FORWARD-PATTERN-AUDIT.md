# First-observed pattern audit

This audit measures subsequent price movements. It does **not** simulate broker fills, account P&L or a probability of winning a trade. It cannot authorize orders.

## Frozen first attempt — 2026-10-04

- Input: Dublin `market-frame-decisions.jsonl`, earliest actually observed feature record per venue/symbol/frame/candle. No feature recalculation from today's historical cache.
- Horizon: one wholly future native candle. **UNCALIBRATED GUESS:** this is a simple exploratory label, chosen before this audit is run; not an optimized holding period.
- Chronological split: `2026-10-04T21:00:00Z`. **UNCALIBRATED GUESS:** an operational boundary within the current work window, fixed before seeing that later sample. Earlier data is discovery; later data is validation. Labels whose outcome becomes known across the boundary are excluded.
- Catalog: every observed nonzero installed TA-Lib candlestick output, separately by signed code. No selection of winning patterns from the report.
- **UNCALIBRATED GUESS:** signed codes are mechanically treated as candidate direction. Some candles encode indecision or geometry; signed output does not mean a calibrated directional prediction.
- Baseline: all eligible observed candles of the same symbol, venue, timeframe and temporal fold, measured in the same direction and at the same horizon. This is an unconditional movement comparison, not a randomized controlled trial.

## Point-in-time rules

1. The signal candle must be fully closed before its feature record was observed.
2. Retain the earliest observation even when its feature values are unavailable. A later revision cannot replace it.
3. Begin the label at the open of the next whole candle starting strictly after observation. Never buy at the signal's close or at a candle already underway.
4. Require every future candle in the horizon, with later receipt timestamps. Reject gaps and missing future outcomes.
5. Distinguish discovery and validation by signal observation time. Purge labels crossing the split, including delayed receipt of their outcome.
6. Read a frozen byte prefix and report SHA-256, input size, skipped records and observation range. Ongoing appends are picked up by a later run.
7. Keep every comparison, ordered by identifiers rather than performance. Do not promote a policy from the largest number in this table.

## Reproduce on Dublin

```sh
cd /home/ubuntu/ocaml-paper-market-lab
.venv/bin/python research/forward_pattern_audit.py \
  --journal /home/ubuntu/jsbot-paper-state/market-frame-decisions.jsonl \
  --horizon-bars 1 --split-at 2026-10-04T21:00:00Z \
  --output /home/ubuntu/jsbot-paper-state/forward-pattern-audit.json
```

Six synthetic tests verify receipt ordering, rejection of missing/unfinished candles, split purging, unchanged earliest features and matched controls. Synthetic fixtures are not market results.

## Interpretation limits

The labels use actual later candles but assume their opening price as a reference, without a bid/ask execution model. Spread, fees, funding, borrow availability, slippage, queue position, latency and impact are absent. `netPnl` and `winProbability` therefore remain null. An empirical positive fraction is not a winning probability.

Adjacent horizons, cross-market returns and related patterns are dependent. Many comparisons create a selection bias; there is no multiplicity correction or statistical significance claim. Sparse/session gaps reject labels. The initial validation sample may be empty and will remain small during this short work window.

No observed paper result establishes live profitability. Even positive gross price labels can lose money after costs.
