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

test("observed quote reference never replaces risk readiness or historical order evidence", () => {
  const t=fixture(); const r=t.marketPipeline.markets[1].frames['30m'];
  r.quoteReference={purpose:'observed_quote_reference_not_execution',orderAuthority:false,winProbability:null,status:'stale',feed:'synthetic',quoteAt:at,receivedAt:at,bid:100,ask:101};
  const row=executionView(t,now).rows.find(r=>r.symbol==='ETH/USD'&&r.frame==='30m');
  const stage=row.steps.find(s=>s.stage==='Observed bid / ask reference');
  assert.equal(stage.state,'context');assert.match(stage.detail,/status at reception stale/);
  assert.match(stage.detail,/not a fill/);
  assert.equal(row.steps.find(s=>s.stage==='Risk / ownership').state,'unknown');
  assert.equal(executionView(t,now).orders.length,0);
  r.quoteReference.transport='existing_archived_websocket';
  assert.match(executionView(t,now).rows.find(r=>r.symbol==='ETH/USD'&&r.frame==='30m').steps.find(s=>s.stage==='Observed bid / ask reference').detail,/existing captured WebSocket/);
  r.quoteReference.transport='PRIVATE_TRANSPORT';
  assert.equal(JSON.stringify(executionView(t,now)).includes('PRIVATE_TRANSPORT'),false);
  r.quoteReference.orderAuthority=true;
  assert.equal(executionView(t,now).rows.find(r=>r.symbol==='ETH/USD'&&r.frame==='30m').steps.find(s=>s.stage==='Observed bid / ask reference').state,'unknown');
  r.quoteReference={purpose:'observed_quote_reference_not_execution',orderAuthority:false,winProbability:null,status:'invalid',reason:'empty_or_negative_provider_size'};
  assert.match(executionView(t,now).rows.find(r=>r.symbol==='ETH/USD'&&r.frame==='30m').steps.find(s=>s.stage==='Observed bid / ask reference').detail,/empty or negative provider size/);
  r.quoteReference.reason='PRIVATE_EXCEPTION_TEXT';
  assert.equal(JSON.stringify(executionView(t,now)).includes('PRIVATE_EXCEPTION_TEXT'),false);
});

test("dated research summary cannot publish private labels, returns, future data or execution authority", () => {
  const t=fixture();
  t.quoteAudit={schema:'first_observed_long_quote_reference_v1',generatedAt:at,orderAuthority:false,winProbability:null,
    labelCount:2,foldCounts:{discovery:0,validation:2},comparisonCount:1,horizonBars:1,maxExitLagSeconds:120,splitAt:TRACE_START,
    rejected:{noFirstObservedFreshEntryQuote:10,noTimelyFreshExitReference:3},labels:[{private:'PRIVATE'}],summary:{netPnl:'PRIVATE'}};
  const result=executionView(t,now);
  assert.equal(result.quoteAudit.labelCount,2);assert.equal(result.quoteAudit.discovery,0);
  assert.equal(result.quoteAudit.missingEntryQuotes,10);assert.equal(result.quoteAudit.generatedAt,at);
  assert.equal(JSON.stringify(result).includes('PRIVATE'),false);
  for (const change of [{orderAuthority:true},{winProbability:.8},{labelCount:true},{labelCount:3},{generatedAt:'2099-01-01T00:00:00Z'}]) {
    const invalid={...t,quoteAudit:{...t.quoteAudit,...change}};assert.equal(executionView(invalid,now).quoteAudit,null);
  }
  assert.equal(executionView(fixture(),now).quoteAudit,null);
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

test("installed stock observation, stale scheduler, owned inventory and long-only routing are explicit", () => {
  const t = fixture();
  t.connections.stockAuto = { asOf: at, mode: "OBSERVE", automaticStrategy: true, newEntriesEnabled: false, stopHandling: "Regular session local exits", ownedPositions: [] };
  assert.equal(executionView(t, now).routeCounts["Stock policy in observation"], 345);
  t.connections.stockAuto.asOf = "2000-01-01T00:00:00Z";
  assert.equal(executionView(t, now).routeCounts["Runtime unverified"], 345);
  Object.assign(t.connections.stockAuto, { asOf: at, mode: "PAPER_EXPERIMENT", newEntriesEnabled: true, ownedPositions: [{ symbol: "STOCK0", quantity: "0.4", frame: "4h", pending: true }] });
  Object.assign(t.connections.stocks, { sessionOpen: true, accountReady: true, executionGateArmed: true, canSubmitNow: true });
  t.marketPipeline.markets[3].frames["1m"].candidate = "short";
  const r = executionView(t, now).rows.find(r => r.symbol === "STOCK0" && r.frame === "1m");
  assert.equal(r.steps.find(s => s.stage === "Risk / ownership").state, "blocked");
  assert.match(r.steps.find(s => s.stage === "Risk / ownership").detail, /Pending stock order/);
  assert.equal(r.steps.find(s => s.stage === "Execution route").state, "blocked");
  assert.match(r.steps.find(s => s.stage === "Execution route").detail, /long entries only/);
});

test("retained order risk facts have their own prior clock and public whitelist",()=>{
  const t=fixture();
  t.orders=[{id:'risk',clientOrderId:'jsbotbtcbuyRisk',symbol:'BTC/USD',side:'buy',status:'filled',filledQty:'0.001',
    submittedAt:'2026-10-04T19:59:50.500Z'}];
  t.decisionHistory={risk:{policy:'quote_cross_30s_v1',observedAt:'2026-10-04T19:59:49.100Z',
    quote_time:'2026-10-04T19:59:49Z',preflight_observed_at:'2026-10-04T19:59:50.100Z',
    preflight_evidence:JSON.stringify({accountReady:true,pendingIntentClear:true,requestedQty:'0.001',buyingPowerCheck:'passed',
      unknown:'PRIVATE',ownedQuantity:'PRIVATE',receiptQuoteAgeNs:'100000000'})}};
  let result=executionView(t,now).orders[0];
  assert.equal(result.preflight.observedAt,'2026-10-04T19:59:50.100Z');
  assert.deepEqual(result.preflight.facts.find(f=>f.label==='No unresolved durable intent'),{label:'No unresolved durable intent',value:'Yes'});
  assert.equal(JSON.stringify(result).includes('PRIVATE'),false);
  t.decisionHistory.risk.preflight_observed_at='2026-10-04T19:59:51Z';
  assert.equal(executionView(t,now).orders[0].preflight,null);
  assert.ok(executionView(t,now).orders[0].evidence);
  t.decisionHistory.risk.preflight_observed_at='2026-10-04T19:59:48Z';
  assert.equal(executionView(t,now).orders[0].preflight,null);
  t.decisionHistory.risk.preflight_observed_at='2026-10-04T19:59:50.100Z';
  t.decisionHistory.risk.preflight_evidence='invalid json';
  assert.equal(executionView(t,now).orders[0].preflight,null);
});

test("original broker budget is distinct from a partial fill and unknown market valuation",()=>{
  const t=fixture();
  t.orders=[{id:'budget',clientOrderId:'jsbotbtcbuyBudget',symbol:'BTC/USD',side:'buy',status:'canceled',
    orderType:'limit',requestedQty:'1',limitPrice:'100',filledQty:'0.1',submittedAt:at}];
  t.fills=[{id:'fill',orderId:'budget',symbol:'BTC/USD',side:'buy',qty:'0.1',price:'100',transactionTime:at}];
  let result=executionView(t,now).orders[0];
  assert.equal(result.request.notional,100);assert.equal(result.fill.notional,10);
  assert.equal(result.request.basis,'Broker quantity × limit price');
  t.orders[0].orderType='market';
  assert.equal(executionView(t,now).orders[0].request.notional,null);
  t.orders[0].requestedNotional='50';
  assert.equal(executionView(t,now).orders[0].request.notional,50);
  t.orders[0].requestedNotional='NaN';t.orders[0].requestedQty='PRIVATE';
  result=executionView(t,now).orders[0];
  assert.equal(result.request.notional,null);assert.equal(result.request.quantity,null);
  assert.equal(JSON.stringify(result).includes('PRIVATE'),false);
});
