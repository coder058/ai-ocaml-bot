# Conventional FX request planning

## Verified scope

`fx/fx_order_plan.ml` is a pure OCaml request planner in a separate library.
It makes **no HTTP calls**,
reads no credentials and grants no order authority. It prepares the body for a
future OANDA practice adapter; it is not that adapter, an automatic strategy or a
claim of connected FX execution. The localhost connection remains blocked when
the practice account/token is absent.

Inputs must be original practice account/catalog/pricing responses and an actual
HTTP receipt, not midpoint candles or invented exchange rates. Initial account
scope is USD home currency without MT4 association. Non-USD accounts fail rather
than silently treating home currency as dollars. Other home currencies need an
additional measured conversion design and tests.

## Preparation steps

1. Validate unique JSON fields, conventional pair syntax and the account's actual
   `CURRENCY` instrument. A currency ETF or HIP-3 contract cannot enter this path.
2. Read provider `displayPrecision`, `tradeUnitsPrecision`, minimum trade size
   and maximum order units. Reject unsupported precision/overflow. Unlike the
   existing conservative balance parser, a conversion divisor cannot lose any
   nonzero decimal digits.
3. Require a tradeable noncrossed bid/ask, original UTC source time, pricing poll
   time and actual receipt. Exact nanoseconds reject even a one-nanosecond future
   quote. The caller supplies its operational maximum age; no new latency
   threshold is fitted or assumed in this planner. The common UTC parser requires
   the existing `TZ=UTC` runtime convention.
4. Request full pricing **without `since`**, using
   `includeHomeConversions=true`. The base currency's `positionValue` converts
   base units into account-home USD. Provider pricing `time` is a poll/since clock,
   not an independently supplied publication time for each conversion factor.
5. Convert a user-requested $50/$100/$500 allocation to base-currency units, then
   floor to the actual order grid. $100 in EUR/USD is not 100 EUR; $100 in USD/JPY
   is not $100 divided by its JPY quote. These tiers are not winning probabilities
   or maximum-loss limits. For USD-quoted instruments use the larger of the
   provider valuation and the buy price bound (or observed ask for a short).
   Cross-pair valuation uses the recorded USD factor, which can move before
   execution: this snapshot bound is **not a guaranteed executed-dollar cap**.
6. Check the floored units against actual catalog size limits and the selected
   first price bucket's liquidity. This conservatively withholds larger requests
   rather than assuming deeper liquidity; provider liquidity is not a fill
   guarantee.
7. Require an explicit caller-supplied worst price and protective stop on the
   correct side of the current spread. No ATR multiplier, stop distance or
   probability is invented. Attach ordinary `stopLossOnFill` with GTC; it is not a
   guaranteed stop or a guarantee against gaps.
8. Prepare signed units, MARKET/FOK, OPEN_ONLY, matching owned order/trade client
   IDs and the attached stop. Identity is for reconciliation, not authentication.

The planner assumes its caller supplies authentic account-specific inputs. It
does not establish which account produced an arbitrary JSON document. The later
practice adapter must enforce a hardcoded practice origin and join the exact
account/catalog/quote request context privately.

## Checks and remaining work

On 5 October, the actual Dublin OCaml build and test executable passed 82
synthetic checks, including USD/JPY and a cross pair, short sign, every supported
unit grid, size/liquidity failures, future/stale clocks, duplicate identities,
wrong account currency, MT4, false currency products and conversion precision
loss. Inputs are fictional fixtures; no practice account was queried and no
orders or fills were produced by these tests. The existing OCaml suite passed
separately.

An initial placement inside `paper_market` changed the linked analyzer's SHA256,
although no candidate-policy source was edited. Moved this preparation into the
separate `fx_planning` library and rebuilt; the actual analyzer recovered the
frozen SHA256 `e6b758316d3d5d0b84b26933772b23a194affa6f374e132614d6840fb620f6a9`.
Actual journal audit retained 91 crypto/HIP-3 records with the transient build
fingerprint from 09:04:22.681008 to 09:07:21.576486 UTC. They were not overwritten
or relabeled. No stock session record was emitted during that pre-open interval;
the first-session journal was still empty. The 09:08 scan matched the frozen
analyzer, with no retrieval errors. Module separation preserves the frozen
candidate artifact rather than changing the prospective protocol to accept a
new fingerprint.

Before calling FX execution implemented, complete and test:

- Hardcoded practice HTTP/authentication, owner-only credential access and
  sanitized provider errors; actual eligible account/catalog/pricing checks.
- Margin, regional guaranteed-stop requirements, foreign inventory/order
  protection, aggregate risk and exact original policy/evidence joins.
- Fsync intent before submission, exact client/trade/transaction identity,
  uncertain-response reconciliation without automatic resubmission, restart
  recovery and closes of owned trades only.
- Actual practice acknowledgement/fill/dependent-stop checks and continued
  reconciliation, followed by prospective execution-aware policy evaluation.
- FX closed-candle feed integration, monitor coverage and observable factual
  decisions. Prepared code does not add any FX products to the existing 91/455
  live scanner count.

Sources: [order definitions](https://developer.oanda.com/rest-live-v20/order-df/),
[pricing requests](https://developer.oanda.com/rest-live-v20/pricing-ep/),
[home conversions](https://developer.oanda.com/rest-live-v20/pricing-df/).
Paper/practice results do not establish live profitability. The project has no
validated profitable edge and may lose money live.
