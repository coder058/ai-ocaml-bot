import assert from "node:assert/strict";
import test from "node:test";
import { tradeLedger, csv } from "../lib/trade-ledger.ts";
// SOURCE: synthetic broker fixtures test FIFO and attribution, not market performance.
const order = (id, side, symbol = "QQQ") => ({
  id,
  clientOrderId: "aibotstk" + id,
  symbol,
  side,
  status: "filled",
  filledQty: "1",
});
const fill = (id, orderId, side, qty, price, at) => ({
  id,
  orderId,
  side,
  symbol: "QQQ",
  qty,
  price,
  transactionTime: "2026-10-01T12:00:" + at + "Z",
});
const snapshot = () => ({
  ordersComplete: true,
  fillsComplete: true,
  journal: [],
  orders: [order("b", "buy"), order("s", "sell")],
  fills: [
    fill("b1", "b", "buy", "1", "100", "00"),
    fill("s1", "s", "sell", "0.4", "110", "01"),
  ],
  positions: [
    {
      symbol: "QQQ",
      qty: "0.6",
      marketValue: "66",
      unrealizedPl: "6",
      protected: false,
    },
    { symbol: "AAPL", qty: "10", marketValue: "1000", protected: true },
  ],
  cryptoFees: {
    pagesComplete: true,
    attributedToBot: true,
    activityRows: 0,
    usdFeeRows: 0,
    btcFeeRows: 0,
    unclassifiedRows: 0,
    usdNetAmount: "0",
    btcFeeQty: "0",
    btcFeeValueAtActivityPriceUsd: "0",
    fetchedAt: "2026-10-01T12:01:00Z",
  },
});

test("partial exit matches only sold quantity and preserves portfolio decomposition", () => {
  const r = tradeLedger(snapshot());
  assert.equal(r.available, true);
  assert.equal(r.closed.length, 1);
  assert.equal(r.closed[0].quantity, 0.4);
  assert.equal(r.closed[0].grossPnl, 4);
  assert.equal(r.unrealized, 6);
  assert.equal(r.realizedWithPostedCosts, 4);
});
test("FIFO scale-in and scale-out uses chronological fills and deduplicates broker rows", () => {
  const d = snapshot();
  d.orders.push(order("b2", "buy"));
  d.fills.push(
    fill("b2", "b2", "buy", "1", "120", "00.500"),
    fill("s2", "s", "sell", "1", "130", "02"),
    d.fills[0],
  );
  const r = tradeLedger(d);
  assert.equal(r.available, true);
  assert.equal(r.closed.length, 2);
  assert.equal(Number(r.grossRealized.toFixed(9)), 26);
});
test("integer quantity matching does not create tiny phantom lots", () => {
  const d = snapshot();
  d.fills = [
    fill("b", "b", "buy", "22466216.216216221", "0.000004", "00"),
    fill("s", "s", "sell", "22466216.216216221", "0.000005", "01"),
  ];
  d.positions = [];
  const r = tradeLedger(d);
  assert.equal(r.available, true);
  assert.equal(r.closed.length, 1);
  assert.equal(Number(r.closed[0].grossPnl.toFixed(6)), 22.466216);
});
test("incomplete, external, oversold or invalid fill histories hide realized results", () => {
  for (const alter of [
    (d) => (d.fillsComplete = false),
    (d) =>
      d.orders.push({ ...order("external", "buy"), clientOrderId: "manual" }),
    (d) => (d.fills[1].qty = "2"),
    (d) => (d.fills[0].transactionTime = null),
    (d) => (d.fills[0].side = "sell"),
  ]) {
    const d = snapshot();
    alter(d);
    assert.equal(tradeLedger(d).available, false);
  }
});
test("CSV preserves quoted reasons and neutralizes spreadsheet formulas", () => {
  assert.equal(
    csv([{ reason: "=SUM(A1)", value: 4 }], ["reason", "value"]),
    '"reason","value"\r\n"\'=SUM(A1)","4"',
  );
  assert.match(csv([{ reason: 'a,"b"\nline' }], ["reason"]), /a,""b""\nline/);
});

test("conflicting duplicate immutable fill IDs block accounting instead of silently selecting a row", () => {
  const d = snapshot();
  d.fills.push({ ...d.fills[0], price: "999" });
  const result = tradeLedger(d);
  assert.equal(result.available, false);
  assert.match(result.reason, /Conflicting duplicate/);
});
