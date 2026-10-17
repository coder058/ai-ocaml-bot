# Trade audit — 17 October 2026

**Scope:** every Alpaca paper trade this bot made, from the first order on
27 September 2026 to the service freeze on 5 October 2026.

**Method and its limit:** this audit was assembled from the measurements the
bot's own docs recorded at the time. The raw broker history (orders, fills,
fee rows) lives only in the Alpaca paper account and on the Dublin VPS, and
neither was reachable from the environment that wrote this. To audit every
individual trade from the broker, run `research/trade_audit.py` (below). Its
output supersedes the recorded figures here wherever they differ.

All results are Alpaca **paper** fills. They are simulated and are not live
profitability.

## 1. Which strategies traded

| Client-ID prefix | Strategy | Traded | What it did |
|---|---|---|---|
| `jsbotbtc` | `quote_cross_30s_v1`, legacy BTC | 27 Sep – 5 Oct (retired at 12:50 UTC) | BTC/USD IOC orders whenever the current quote crossed one sampled 30 s earlier. **Most of the volume.** |
| `jsbotmtf` | `trend_candle_confluence_v1`, crypto multi-frame | 2 Oct – 5 Oct | Long-only crypto entries on EMA trend plus a bullish candle; exits on candle-low or trend flip. Up to 31 symbols, cut back to BTC/ETH/SOL on 4 Oct. |
| `aibotstk` | Stock router | **Never placed an order.** | The stock scheduler ran in observe mode only; every recorded snapshot shows zero router invocations. |
| `aibottrc` | `crypto_monthly_trend_v1` | **Never placed an order.** | Built 15 Oct, after the freeze; observe-only. |
| — | Manual | — | 10 AAPL shares that predate the bot, protected. No bot order touched them. |

## 2. Timeline of recorded trading

| When (UTC) | Recorded evidence | Source |
|---|---|---|
| 27 Sep 08:36–10:26 | First REST version: 20 orders, all acknowledged and reconciled. Used $299.999 of a $300 buy budget; ended flat. | `pretrade-evidence.md` |
| 27 Sep, first 5 orders | Bought $39.99, sold $39.90: **−$0.09** gross cash flow, before fees. One IOC buy was canceled after a tiny partial fill. | `pretrade-evidence.md` |
| 27 Sep 13:00 | Switched to the WebSocket feed. The first traced order: 7.4 ms receive-to-decision, 1.30 s receive-to-HTTP. | `README.md` |
| 27 Sep 18:54 (flat) | **−$1.44** cumulative fill cash flow; 72 orders and 92 fills by 19:53. | `POLICY-ATTEMPTS.md` |
| 28 Sep 09:53 | 255 orders, 422 fills. Buys $4,246.98 vs sells $4,236.12: **−$10.86** before fees. | `SIX-HOUR-PAPER-WORK.md` |
| 29 Sep 06:51 | Posted fees so far: −$25.76 USD and −0.000282 BTC. The BTC quantity gap matched the 0.25% buy fee to within 0.00000028 BTC. | `POLICY-ATTEMPTS.md` |
| 29 Sep 17:41 | 788 bot orders (298 filled, 490 canceled), 1,247 fills. | `SIX-HOUR-PAPER-WORK.md` |
| 29 Sep markout | Of 215 filled quote-cross orders, **none** was positive after fees from 1 s to 5 m. Median −51 to −54 bps per order. | `POLICY-ATTEMPTS.md` |
| 1 Oct 21:24 | 1,537 orders and 2,451 fill rows; order and fill history complete. | `LOCAL-MONITOR.md` |
| 2 Oct | Two multi-frame exits (BONK, PEPE) got stuck pending; see §4. | `PROJECT-REVIEW-2026-10-04.md` |
| 4 Oct 13:04 | Multi-frame: 370 orders across 31 symbols (150 filled, 220 canceled), 10 open tickets. All strategies: 1,660 lab orders with fills, 3,416 fill rows, **≈ −$205.04** provisional net marked. | `PROJECT-REVIEW-2026-10-04.md` |
| 4 Oct 15:50 | **Decimal audit:** fill cash flow −$210.71, open marks +$101.19, posted USD fees −$93.56: **net marked −$203.08**. 1,647 FIFO partial closures matched, none unmatched. | `CONNECTIONS-AND-MONITOR-WORK.md` |
| 4 Oct | Bot-owned altcoins wound down in nine filled sales. | `README.md` |
| 4 Oct 19:36:49 | A new, dated order cohort starts. | `EXECUTION-TRACE-WORK.md` |
| 5 Oct 05:22–05:31 | New cohort: 145 orders (107 with a fill), 101 matched exits. Gross **+$0.65 before costs**; net unavailable. | `EXECUTION-TRACE-WORK.md` |
| 5 Oct 05:44 | 3,248 posted CFEE fee rows. None carries an order ID or transaction time, so fees can't be joined to trades. | `EXECUTION-TRACE-WORK.md` |
| 5 Oct 12:50 | BTC verified flat; the quote-cross bot retired; multi-frame entries disabled. | `EXECUTION-TRACE-WORK.md` |
| 5 Oct 14:33 | **Last recorded trade:** SOL/USD exit, 0.831943285 at $119.39, triggered by its candle-low stop (119.48). | `EXECUTION-TRACE-WORK.md` |
| 5 Oct (freeze) | No open orders; only the protected AAPL position. Services stopped. | `history/SHUTDOWN.md` |

## 3. Profit and loss

- **Last full reconciliation (4 Oct 15:50): −$203.08 net marked**, all
  strategies combined. That is fill cash flow plus open marks plus posted USD
  fees. It excludes sell fees posted later and anything traded after 15:50 on
  4 October.
- **Cause:** fees, not bad fills. Gross results were close to zero; for
  example, the 4–5 October cohort made +$0.65 gross on 101 exits. But every
  order paid about 0.25% taker fee per side, about 50 bps per round trip.
  Posted USD fees alone were −$93.56 by 4 October. The bot's buy fees,
  charged in BTC and other assets, cost more on top of that.
- **Split by strategy:** never reconciled. Quote-cross made most of the
  volume, so it carries most of the loss. The audit tool below splits it per
  strategy and per round trip.

## 4. Problems found in the trades

1. **Stuck exits from a quantity bug.** BONK and PEPE sells sent from 2 Oct
   asked for slightly more than the account held (26529255.319148943 vs
   26529255.31914894, and 22466216.216216225 vs 22466216.216216221). The
   cause was converting binary floats to decimal text. The broker later
   returned "order not found", and the exits stayed blocked. Exact-decimal
   quantities fixed it, and on 15 Oct a bounded 10-minute release was added
   for requests that never reach the broker.
2. **Taker-only execution.** Every bot order crossed the spread (an IOC limit
   or a market order). There were no maker orders, so each trade paid the
   full fee schedule.
3. **No cost check before trading.** Nothing compared expected move with cost
   before sending an order; see `PROFITABILITY-REVIEW.md`.
4. **25 early quote-cross orders have no retained decision trace.** Their
   reasons can't be reconstructed, and they were not back-filled.
5. **Fees can't be joined to trades.** Alpaca's fee rows carry no order ID,
   so per-trade net P&L can only be estimated.
6. **AAPL protection held.** No recorded snapshot shows a bot order on AAPL.

## 5. What could not be verified here

- Each individual order and fill, the exact final net (trades after 4 Oct
  15:50, including the last SOL exit), and fees posted after 5 Oct.
- A per-strategy P&L split.
- Whether the broker account matches the local ledgers today.

## 6. Run the complete audit

`research/trade_audit.py` is read-only and uses only GET requests to the
paper origin. It pulls the **complete** order, fill and fee history (no page
cap, and it fails closed if pagination stops advancing) and positions. It then
writes:

- `trades.csv`: every order, with its strategy, status, quantities, prices and
  fill count.
- `round-trips.csv`: every FIFO closed lot, with gross P&L, an estimated fee
  at the published 25 bps rate, and holding time.
- `TRADE-AUDIT.md`: a per-strategy summary, the account-level net (same
  formula as the monitor), and an inventory check that BTC fees explain
  quantity gaps.
- An anomaly list: overfills, fill and order mismatches, duplicate client
  IDs, sells beyond owned buys, orders above $500, AAPL touched, stale open
  orders, broker rejections, altcoin entries, and ledger/broker disagreements
  (pending locally but terminal at the broker, or missing from either side).

On the VPS:

```sh
cd /home/ubuntu/ocaml-paper-market-lab
sudo python3 research/trade_audit.py --env /etc/jsbot-paper.env \
  --state-dir /home/ubuntu/jsbot-paper-state --output-dir /home/ubuntu/trade-audit
```

`sudo` is only needed to read the root-owned credentials file. The raw
snapshot is saved as `raw/broker-snapshot.json`, mode 600. It is private
account data: do not commit it. Re-run the analysis offline with
`--snapshot /home/ubuntu/trade-audit/raw`.

## 7. Size, turnover and fees (estimated from recorded totals)

Derived on 17 Oct from the recorded figures above, not from raw broker rows.
`research/trade_audit.py` gives exact values.

- **Bet size:** buys targeted $100 each, and BTC exposure was capped at
  $500. IOC orders often filled only partly, so actual fills were small. On
  28 Sep, 422 fills totalled $8,483 of buys and sells, about **$20 per fill**.
- **Most capital at risk at once:** about $1,500 by design ($500 BTC plus ten
  $100 multi-frame tickets). Open positions on 4 Oct were marked at $101.19.
- **Turnover:** USD fees are charged on sells at 25 bps. Posted USD fees of
  $93.56 imply about **$37,000 of sells**, and so roughly **$75,000 of total
  buys plus sells**. That is about $22 per fill row and $45 per filled order,
  consistent with the 28 Sep sample.
- **Fees vs. loss:** buy fees are charged in the received coin and on
  29 Sep matched the USD sell fees ($25.76 vs. ≈$24 of BTC). Total fees by
  4 Oct were therefore about **$185–190 of the $203 loss (≈ 92%)**. Spread
  and slippage account for roughly the remaining $15–20.
- **Loss path:** −$1.44 (27 Sep, flat) → −$10.86 gross (28 Sep) → −$51.86
  provisional (29 Sep 12:31) → −$203.08 (4 Oct 15:50).
- **Return:** about −0.27% of turnover, about −0.12 dollars per filled order,
  or about −13.5% of the most capital at risk at once.
