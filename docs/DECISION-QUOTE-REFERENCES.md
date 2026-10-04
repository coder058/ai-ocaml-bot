# Actual bid/ask references for prospective research

The serialized minute scanner reads two market-data GET batches: the monitored
Alpaca crypto symbols and monitored IEX stocks/ETF. It records provider bid/ask,
raw sizes, original quote timestamp and actual response-reception timestamp.
It performs no order POST and cannot authorize a trade.

Provider references: [crypto quotes](https://docs.alpaca.markets/us/reference/cryptolatestquotes-1)
and [stock quotes](https://docs.alpaca.markets/us/reference/stocklatestquotes-1).
IEX is one exchange rather than consolidated NBBO. Raw provider size units are
not converted into executable stock quantity or depth. Displayed spread is
computed from the actual bid/ask divided by their midpoint, in basis points.

## Boundary checks

- Exact requested scopes only; AAPL and excluded crypto cannot be queried by
  this collector. Unsupported Hyperliquid routes stay `unconnected`.
- Nonfinite, empty, crossed and malformed quotes fail validation. Freshness at
  reception uses the inherited five-second operational router guard, not a
  calibrated latency or profitability parameter.
- Nanosecond provider timestamps are retained as original strings. Decimal
  comparison to the measured microsecond reception clock rejects even a quote
  one nanosecond after that reception. Python 3.10 cannot parse the original
  fraction directly through datetime; the parser now handles this explicitly.
- Stale closed-session prices are preserved as **stale**, never current
  executable prices. Missing or failed requests never become candle-derived
  bid/ask values. Quote authority is false; win probability is null.
- Current references appear in each frame's decision path as **context**.
  They do not pass risk checks or explain an earlier broker order. The actual
  order router still fetches its own fresh quote before submission.

## Forward evidence

New, distinct provider quote observations append to private
`market-quotes-reference.jsonl`. Subsequent first-observed frame records retain
the quote actually known at that scan. Existing records are not rewritten or
backfilled with a later price. There is no quote history before capture began,
and a first frame with unavailable/invalid quote evidence stays unavailable.

This is sampling at scan reception, not a complete order book or HFT capture.
No queue/impact/slippage/fill model, fee allocation, prospective bid/ask label
audit or net performance has been implemented by this collector. Earlier gross
candle labels must not be described as cost-adjusted returns.

## Verification

Five synthetic tests passed locally and on Dublin: precision/authority,
stale/future (including sub-microsecond future), invalid/crossed/empty quotes,
partial batches, scope/GET-only guards and failed retrievals. The first Dublin
test caught Python 3.10's fractional timestamp incompatibility. It was corrected
without discarding or rewriting the first-observed audit files.

Actual 21:20 UTC scan had 1 fresh, 57 stale, 14 invalid and 19 unconnected
instrument references. BTC received bid 85,911.78 / ask 85,935.20 at
21:20:40.198132 UTC for provider quote 21:20:39.556206312 UTC; computed spread
2.72568 bps. QQQ's actual quote was from Friday October 2 and marked stale.
These samples are not executed prices or a profitability result.
