import test from "node:test";
import assert from "node:assert/strict";
import { historyExport } from "../lib/history-export.ts";
// SOURCE: synthetic stock/crypto executions test scope and filters, not returns.
const t = () => ({
  generatedAt: "2026-10-04T12:00:00Z",
  ordersComplete: true,
  fillsComplete: true,
  journal: [],
  positions: [],
  orders: [
    {
      id: "b",
      clientOrderId: "aibotstkb",
      symbol: "QQQ",
      side: "buy",
      submittedAt: "2026-10-03T12:00:00Z",
      status: "filled",
      filledQty: "1",
    },
    {
      id: "s",
      clientOrderId: "aibotstks",
      symbol: "QQQ",
      side: "sell",
      submittedAt: "2026-10-04T12:00:00Z",
      status: "filled",
      filledQty: "1",
    },
    {
      id: "a",
      clientOrderId: "aibotstka",
      symbol: "QQQ",
      side: "buy",
      submittedAt: "2026-10-04T12:00:00Z",
      status: "canceled",
      filledQty: "0",
    },
    {
      id: "private",
      clientOrderId: "manual",
      symbol: "AAPL",
      side: "buy",
      submittedAt: "2026-10-04T12:00:00Z",
      status: "filled",
      filledQty: "10",
    },
  ],
  fills: [
    {
      id: "bf",
      orderId: "b",
      symbol: "QQQ",
      side: "buy",
      qty: "1",
      price: "100",
      transactionTime: "2026-10-03T12:00:00Z",
    },
    {
      id: "sf",
      orderId: "s",
      symbol: "QQQ",
      side: "sell",
      qty: "1",
      price: "110",
      transactionTime: "2026-10-04T12:00:00Z",
    },
  ],
  decisionHistory: {
    s: { policy: "manual_check", reason: "Explicit paper route check" },
  },
});
test("CSV export keeps date/instrument/side/policy filters and actual reasons, excluding private positions", () => {
  const d = t();
  const csv = historyExport(
    d,
    new URLSearchParams({
      kind: "orders",
      symbol: "QQQ",
      side: "Sell",
      from: "2026-10-04",
      policy: "manual_check",
    }),
  );
  assert.equal(csv.split("\r\n").length, 2);
  assert.match(csv, /Explicit paper route check/);
  assert.doesNotMatch(csv, /AAPL/);
  const attempts = historyExport(
    d,
    new URLSearchParams({ kind: "orders", side: "Unfilled attempts" }),
  );
  assert.match(attempts, /canceled/);
  assert.doesNotMatch(attempts, /"filled"/);
  const closed = historyExport(
    d,
    new URLSearchParams({ kind: "closed", from: "2026-10-04" }),
  );
  assert.match(closed, /FIFO matched fills before fees/);
  assert.equal(closed.split("\r\n").length, 2);
  assert.equal(
    historyExport(
      d,
      new URLSearchParams({ kind: "closed", symbol: "BTC/USD" }),
    ).split("\r\n").length,
    1,
  );
});
test("export fails closed on incomplete history or invalid request instead of downloading misleading data", () => {
  assert.throws(
    () =>
      historyExport(
        { ...t(), fillsComplete: false },
        new URLSearchParams({ kind: "orders" }),
      ),
    /Complete/,
  );
  assert.throws(
    () =>
      historyExport(
        t(),
        new URLSearchParams({
          kind: "closed",
          from: "2026-10-05",
          to: "2026-10-04",
        }),
      ),
    /date range/,
  );
  assert.throws(
    () => historyExport(t(), new URLSearchParams({ kind: "anything" })),
    /kind/,
  );
});
