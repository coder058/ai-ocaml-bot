# Existing market/news data inventory

Actual read-only inspection: 5 October 2026, 14:17:28.139150 UTC.
Source code: `research/inspect_related_data.py`. No broker calls, body/notes
exports, model fitting, fills simulation or order authority were added.

## Pattern Forge recordings

Validated the existing public catalog against each actual JSON file: matching
metadata/counts, unique chronological UTC hourly bars, finite/valid OHLCV,
closed-time boundaries and no candle closing after its recorded as-of. The
private inspection artifact retains actual JSON bytes/hashes separately from
the catalog's original parquet source hashes.

| Recorded contract | Actual hourly candles | Gap intervals | Missing hours |
|---|---|---|---|
| GOLD-USD | 2,461 | 67 | 120 |
| SILVER-USD | 2,334 | 125 | 223 |
| WTIOIL-USD | 2,482 | 42 | 76 |
| SP500-USD | 2,469 | 77 | 119 |
| NAS100-USD | 2,327 | 143 | 207 |
| BTC-USD | 2,025 | 3 | 6 |
| ETH-USD | 1,952 | 2 | 5 |
| SOL-USD | 1,920 | 26 | 36 |
| HYPE-USD | 1,048 | 12 | 15 |
| SPCX-USD | 1,549 | 59 | 74 |

Total: **20,567 actual hourly candles**. The catalog labels their venue
**Polymarket Perps**, source owner recordings from Google Cloud Storage. The
inspection does not independently authenticate those original contracts or
equate them with Alpaca ETF/stocks or Hyperliquid perpetuals. First starts vary
from May to July; final closes are August 21–22 UTC. No finer timeframe exists
in these files. Do not interpolate 1m/5m/30m candles or invent bid/ask executions.
HYPE/SPCX inventory does not authorize trading those products.

These can support a separately identified historical feature/baseline study;
they lack original receipt-time histories and executable quotes. A close-to-close
forecast on them cannot establish net trading probabilities for our Alpaca route.

## Info Desk news evidence

Read the existing `desk.sqlite3` with SQLite `mode=ro`. Selected only source,
receipt/version counts; drafts, notes, document bodies and the separate
verification database were excluded.

- 27 documents / 27 versions: EIA 15, Federal Register 11, OFAC 1.
- Actual first receipt: September 9, 2026, 14:04:32.016988 UTC.
- Actual latest retained receipt: September 10, 2026, 15:37:52.002924 UTC.
- No trading outcome labels or a currently running fresh news feed verified.

**None of those first news receipts overlaps the historical recordings' time
window.** Joining these September news captures to May–August candle decisions
would introduce future information. A causal news feature must use a version
received before the intended decision, preserve its exact source/version and
record later revisions separately. It must not replace risk gates or manufacture
a trade explanation after submission.

The user has been asked whether Info Desk is the intended former “AI Digest”.
Identification is still pending; this inspection is not a news-to-strategy
integration or a trained AI decision model.

## Reproduce

```sh
python research/inspect_related_data.py \
  --pattern-forge-public /path/to/pattern-forge/public \
  --info-desk-database /path/to/info-desk/data/desk.sqlite3 \
  --output /private/output/related-data-inventory.json
```

The reader stops on catalog/closed-candle inconsistencies. Hashes and missing
hours are measured from the actual supplied files. No probabilities, confidence
tiers, predictive edge or live profitability have been demonstrated.
