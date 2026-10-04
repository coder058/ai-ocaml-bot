import test from "node:test";
import assert from "node:assert/strict";
import { positionsView } from "../lib/positions-view.ts";

test("positions-only reset preserves inventory and never exposes past history", () => {
  const btc = { symbol: "BTCUSD", qty: "0.001", side: "long", avgEntryPrice: "80000", currentPrice: "81000", marketValue: "81", unrealizedPl: "1", protected: false };
  const sol = { ...btc, symbol: "SOLUSD" };
  const raw = { version: 1, source: "Dublin OCaml paper service", generatedAt: "2026-10-04T16:00:00Z", service: { active: true, mode: "PAPER_ORDER" },
    positions: [btc, sol, { ...btc, symbol: "AAPL", protected: true }],
    orders: [{ id: "sol-entry", clientOrderId: "jsbotmtf-sol", symbol: "SOLUSD", submittedAt: "2026-10-01T00:00:00Z" }], fills: [{ id: "old-fill" }], journal: [{ message: "old reason" }], cryptoFees: { usdNetAmount: "-10" } };
  const before = structuredClone(raw);
  const view = positionsView(raw);
  assert.deepEqual(view.positions, [btc, sol]);
  assert.deepEqual(Object.keys(view).sort(), ["generatedAt", "positions", "service", "source"]);
  assert.deepEqual(raw, before);
  assert.notStrictEqual(view.positions[0], raw.positions[0]);
  // A subsequent complete sync cannot restore old history to the public response.
  assert.deepEqual(positionsView({ ...raw, journal: [...raw.journal, { message: "new reason" }] }), view);
  assert.equal(positionsView(null), null);
  const receivedAt = "2026-10-04T15:59:30Z";
  assert.equal(positionsView({ ...raw, positionsReceivedAt: receivedAt }).generatedAt, receivedAt);
});
