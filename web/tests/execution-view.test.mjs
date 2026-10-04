import test from "node:test";
import assert from "node:assert/strict";
import { executionView, TRACE_FRAMES, TRACE_START } from "../lib/execution-view.ts";

// SOURCE: synthetic fixtures exercise gates and joins, not market performance.
const now = Date.parse("2026-10-04T20:00:00Z");
const at = "2026-10-04T19:59:30Z";
const reading = () => ({ status: "candidate", reason: "Synthetic closed candle", candidate: "long", trend: "rising", candleShapes: ["hammer_shape"], lastBarStart: "2026-10-04T19:30:00Z", orderAuthority: false, winProbability: null,
  technicalSuite: { status: "ready", patterns: { CDLHAMMER: { status: "ready", value: 100 } }, indicators: { RSI: { status: "warming" } } } });
const market = (symbol, venue) => ({ symbol, venue, category: "Fixture", execution: "analysis", frames: Object.fromEntries(TRACE_FRAMES.map(frame => [frame, reading()])) });
const fixture = () => ({ generatedAt: at, orders: [], fills: [], positions: [], journal: [], ordersComplete: true, fillsComplete: true,
  marketPipeline: { policy: "trend_candle_confluence_v1", asOf: at, retrievedAt: at, markets: [market("BTC/USD", "Alpaca crypto"), market("ETH/USD", "Alpaca crypto"), market("SOL/USD", "Alpaca crypto"),
    ...Array.from({ length: 69 }, (_, i) => market(`STOCK${i}`, "Alpaca equities")), ...Array.from({ length: 19 }, (_, i) => market(`xyz:FIXTURE${i}`, "Hyperliquid HIP-3"))] },
  multiPaper: { asOf: at, mode: "PAPER_EXPERIMENT", newEntriesEnabled: false, activeTickets: [], abstentions: [] },
  connections: { stocks: { asOf: at, connected: true, sessionOpen: false, nextOpen: "2026-10-05T09:30:00-04:00", automaticStrategy: false, executionGateArmed: false }, fx: { connected: false, reason: "practice_credentials_missing", executionAdapterAvailable: false, accountId: "PRIVATE" } } });

test("all 455 cells distinguish the separate BTC engine, paused entries, stocks and public-only HIP-3", () => {
  const t = fixture();
  const result = executionView(t, now);
  assert.equal(result.symbols, 91); assert.equal(result.frames, 455);
  assert.deepEqual(result.routeCounts, { "Separate BTC engine": 5, "New entries paused": 10, "Stock automation missing": 345, "Public data only": 95 });
  const eth = result.rows.find(r => r.symbol === "ETH/USD" && r.frame === "30m");
  assert.equal(eth.candidate, "long");
  assert.equal(eth.steps.find(s => s.stage === "Execution route").state, "blocked");
  assert.equal(eth.steps.find(s => s.stage === "Risk / ownership").state, "unknown");
  assert.match(eth.steps.find(s => s.stage === "Technical calculations").detail, /1\/1 candlestick.*0\/1 indicator/);
  assert.equal(result.orders.length, 0);
  assert.equal(JSON.stringify(result).includes("PRIVATE"), false);
  assert.equal(executionView(null, now), null);
});

test("stale or future runtime/analysis never reports current gate readiness or a current candidate", () => {
  for (const invalid of ["2026-10-04T18:00:00Z", "2026-10-05T00:00:00Z", "not a time"]) {
    const t = fixture();
    t.marketPipeline.retrievedAt = invalid; t.multiPaper.asOf = invalid;
    t.multiPaper.newEntriesEnabled = true;
    const result = executionView(t, now);
    assert.equal(result.candidates, 0);
    assert.equal(result.dataCounts.snapshot_unverified, 455);
    assert.equal(result.rows.find(r => r.symbol === "ETH/USD").route, "Runtime unverified");
  }
});

test("an enabled entry gate is not a passed preflight and existing owned positions block all five frames", () => {
  const t = fixture(); t.multiPaper.newEntriesEnabled = true;
  t.multiPaper.activeTickets = [{ symbol: "ETHUSD", frame: "1m", pending: { side: "buy" } }];
  const result = executionView(t, now);
  for (const row of result.rows.filter(r => r.symbol === "ETH/USD")) {
    assert.equal(row.route, "Paper entry gate enabled");
    const risk = row.steps.find(s => s.stage === "Risk / ownership");
    assert.equal(risk.state, "blocked"); assert.match(risk.detail, /Pending buy/);
  }
  assert.equal(result.rows.find(r => r.symbol === "SOL/USD").steps.find(s => s.stage === "Risk / ownership").state, "unknown");
});

test("closed sessions, missing frames and unknown policies remain distinct", () => {
  const t = fixture();
  t.connections.stocks.automaticStrategy = true;
  delete t.marketPipeline.markets[3].frames["4h"];
  t.marketPipeline.markets[3].frames["1m"].status = "market_closed";
  t.marketPipeline.markets[3].frames["1m"].candidate = null;
  t.marketPipeline.policy = "not_the_frozen_policy";
  const result = executionView(t, now);
  assert.equal(result.rows.find(r => r.symbol === "STOCK0" && r.frame === "4h").dataState, "no_data");
  assert.equal(result.rows.find(r => r.symbol === "STOCK0" && r.frame === "1m").dataState, "market_closed");
  assert.equal(result.rows.find(r => r.symbol === "STOCK0").route, "Stock session closed");
  assert.equal(result.rows[0].steps.find(s => s.stage === "Frozen OCaml policy").state, "unknown");
});

const order = (id, submittedAt = "2026-10-04T19:50:00Z") => ({ id, clientOrderId: `jsbotmtf-${id}`, symbol: "ETHUSD", side: "buy", status: "canceled", filledQty: "0.5", submittedAt });
test("new cohort excludes old, future, private and excluded-crypto orders without restoring the reset history", () => {
  const t = fixture();
  t.orders = [order("new"), order("old", "2026-10-04T19:00:00Z"), order("future", "2026-10-05T00:00:00Z"), { ...order("aapl"), clientOrderId: "aibotstk-private", symbol: "AAPL" }, { ...order("excluded"), symbol: "DOGEUSD" }];
  t.journal = [{ message: "PRIVATE old historical log" }];
  t.decisionHistory = { old: { reason: "OLD REASON" }, new: { policy: "trend_candle_confluence_v1", observedAt: "2026-10-04T19:49:59Z", trigger_quote_time: "2026-10-04T19:49:58Z", reason: "Recorded synthetic hammer", frame: "30m", secret: "PRIVATE" } };
  t.fills = [{ id: "f", orderId: "new", symbol: "ETHUSD", side: "buy", qty: "0.5", price: "100" }, { id: "old-f", orderId: "old", symbol: "ETHUSD", side: "buy", qty: "1", price: "999" }, { id: "wrong-symbol", orderId: "new", symbol: "SOLUSD", side: "buy", qty: "99", price: "100" }];
  const before = structuredClone(t);
  const result = executionView(t, now);
  assert.equal(result.traceStart, TRACE_START);
  assert.deepEqual(result.orders.map(o => o.id), ["new"]);
  assert.equal(result.orders[0].status, "Partial fill · rest canceled");
  assert.equal(result.orders[0].fill.notional, 50);
  assert.equal(result.orders[0].fill.fillCount, 1);
  assert.match(result.orders[0].reason, /Recorded synthetic hammer/);
  assert.equal(JSON.stringify(result).includes("PRIVATE"), false);
  assert.equal(JSON.stringify(result).includes("OLD REASON"), false);
  assert.deepEqual(t, before);
});

test("missing timestamps and retrospective/future quote evidence are never sold as a pre-trade explanation", () => {
  for (const evidence of [undefined, { reason: "Retrospective", observedAt: "2026-10-04T19:50:01Z" }, { reason: "Undated" }, { reason: "Future quote", observedAt: "2026-10-04T19:49:59Z", quote_time: "2026-10-04T19:50:00Z" }]) {
    const t = fixture(); t.orders = [order("new")]; t.decisionHistory = { new: evidence };
    const o = executionView(t, now).orders[0];
    assert.equal(o.evidence, null); assert.match(o.reason, /No reason is reconstructed/);
  }
});

test("whole-second journal precision accepts a bounded earlier quote but never invents within-second ordering", () => {
  const t = fixture(); t.orders = [order("new", "2026-10-04T19:50:01.400Z")];
  t.decisionHistory = { new: { observedAt: "2026-10-04T19:50:00Z", quote_time: "2026-10-04T19:50:00.799Z", policy: "quote_cross_30s_v1" } };
  assert.notEqual(executionView(t, now).orders[0].evidence, null);
  assert.match(executionView(t, now).orders[0].evidencePrecision, /one-second resolution/);
  t.orders[0].submittedAt = "2026-10-04T19:50:00.900Z";
  assert.equal(executionView(t, now).orders[0].evidence, null);
});
