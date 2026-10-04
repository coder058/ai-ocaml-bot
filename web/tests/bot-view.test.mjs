import assert from "node:assert/strict";
import test from "node:test";
import { botAccounting, botExecutions, botOrders, decisionForOrder, orderDisplayStatus, orderFillSummary,
  quoteEvidence, reasonForOrder } from "../lib/bot-view.ts";

// SOURCE: synthetic values test accounting guards and partial-fill display only.
const snapshot = () => ({
  ordersComplete: true, fillsComplete: true,
  orders: [{ id: "one", clientOrderId: "jsbotbtcbuy20260927T000000Z", symbol: "BTCUSD",
    side: "buy", status: "canceled", filledQty: "0.01", submittedAt: "2026-09-27T00:00:00Z" }],
  fills: [{ id: "fill", orderId: "one", clientOrderId: "jsbotbtcbuy20260927T000000Z",
    symbol: "BTCUSD", side: "buy", qty: "0.01", price: "100",
    transactionTime: "2026-09-27T00:00:01Z" }],
  positions: [{ symbol: "BTCUSD", qty: "0.009975", marketValue: "1.10", protected: false },
    { symbol: "AAPL", qty: "10", marketValue: "1000", protected: true }],
});

test("multi-asset marks and fee quantities are reconciled in their own units", () => {
  const data = snapshot();
  data.orders.push({ id: "eth", clientOrderId: "jsbotmtfexample", symbol: "ETHUSD", side: "buy", filledQty: "1" });
  data.fills.push({ id: "ethfill", orderId: "eth", symbol: "ETH/USD", side: "buy", qty: "1", price: "100" });
  data.positions.push({ symbol: "ETHUSD", qty: "0.999", marketValue: "102", protected: false });
  data.cryptoFees = { pagesComplete: true, attributedToBot: true, activityRows: 3,
    usdFeeRows: 1, btcFeeRows: 1, unclassifiedRows: 0, usdNetAmount: "-0.55",
    btcFeeQty: "-0.000025", btcFeeValueAtActivityPriceUsd: "-0.0025", fetchedAt: "2026-09-27T00:00:03Z",
    assetFees: { "BTC/USD": { qty: "-0.000025" }, "ETH/USD": { qty: "-0.001" } } };
  const result = botAccounting(data);
  assert.equal(botExecutions(data).length, 2);
  assert.equal(Number(result.markedResultAfterPostedFees.toFixed(6)), 1.55);
  assert.equal(Number(result.quantityResiduals["ETH/USD"].toFixed(9)), 0);
  assert.equal(Number(result.quantityResiduals["BTC/USD"].toFixed(9)), 0);
});

test("foreign activity in a new traded asset blocks attribution", () => {
  const data = snapshot();
  data.orders.push({ id: "eth", clientOrderId: "jsbotmtfexample", symbol: "ETHUSD" },
    { id: "external", clientOrderId: "manual", symbol: "ETH/USD" });
  assert.equal(botAccounting(data).available, false);
});

test("multi-frame order explanations retain their actual signal reason", () => {
  assert.equal(reasonForOrder({side:"buy"}, {policy:"trend_candle_confluence_v1", frame:"4h", reason:"Synthetic candle trigger"}),
    "4h: Synthetic candle trigger.");
});

test("marked bot result excludes protected AAPL and remains indicative", () => {
  const result = botAccounting(snapshot());
  assert.equal(result.available, true);
  assert.equal(Number(result.markedResult.toFixed(6)), 0.1);
  assert.equal(result.flat, false);
});

test("posted cash fees reduce marked result while BTC fees are not counted twice", () => {
  const data = snapshot();
  data.cryptoFees = { pagesComplete: true, attributedToBot: true,
    activityRows: 2, usdFeeRows: 1, btcFeeRows: 1, unclassifiedRows: 0,
    usdNetAmount: "-0.25", btcFeeQty: "-0.000025", fetchedAt: "2026-09-27T00:00:03Z",
    btcFeeValueAtActivityPriceUsd: "-0.002500", lastActivityAt: "2026-09-27T00:00:02Z" };
  const result = botAccounting(data);
  assert.equal(Number(result.markedResult.toFixed(6)), 0.1);
  assert.equal(result.postedUsdFees, -0.25);
  assert.equal(Number(result.markedResultAfterPostedFees.toFixed(6)), -0.15);
  assert.equal(Number(result.quantityResidual.toFixed(9)), 0);
});

test("fee-adjusted value stays unavailable when fee pages cannot be attributed", () => {
  const data = snapshot();
  data.cryptoFees = { pagesComplete: true, attributedToBot: false,
    activityRows: 2, usdFeeRows: 1, btcFeeRows: 1, unclassifiedRows: 0,
    usdNetAmount: "-0.25", btcFeeQty: "-0.000025", fetchedAt: "2026-09-27T00:00:03Z",
    btcFeeValueAtActivityPriceUsd: "-0.002500", lastActivityAt: null };
  const result = botAccounting(data);
  assert.equal(result.available, true);
  assert.equal(result.markedResultAfterPostedFees, null);
  assert.equal(Number(result.markedResult.toFixed(6)), 0.1);
});

test("incomplete or external BTC history hides the result", () => {
  const incomplete = snapshot();
  incomplete.fillsComplete = false;
  assert.equal(botAccounting(incomplete).available, false);
  const external = snapshot();
  external.orders.push({ id: "outside", clientOrderId: "manual", symbol: "BTCUSD" });
  assert.equal(botAccounting(external).available, false);
  const missingMark = snapshot();
  missingMark.positions[0].marketValue = null;
  assert.equal(botAccounting(missingMark).available, false);
});

test("partial canceled order is not presented as an empty cancellation", () => {
  const data = snapshot();
  assert.equal(orderDisplayStatus(data.orders[0]), "Partial fill · rest canceled");
  assert.deepEqual(orderFillSummary(data.orders[0], data.fills), {
    quantity: 0.01, notional: 1, averagePrice: 100, fillCount: 1,
    firstAt: "2026-09-27T00:00:01Z", lastAt: "2026-09-27T00:00:01Z",
  });
  assert.equal(botExecutions(data).length, 1);
  data.orders.push({ id: "empty", clientOrderId: "jsbotbtcsell20260927T000002Z", symbol: "BTCUSD",
    side: "sell", status: "canceled", filledQty: "0" });
  assert.equal(botExecutions(data).length, 1);
});

test("duplicate broker pagination rows do not duplicate displayed executions", () => {
  const data = snapshot();
  data.orders.push({ ...data.orders[0] });
  assert.equal(botOrders(data).length, 1);
  assert.equal(botExecutions(data).length, 1);
  assert.equal(botExecutions(data)[0].fill.notional, 1);
});

test("decision links by encoded quote time, not nearest journal row", () => {
  const order = snapshot().orders[0];
  const decision = decisionForOrder(order, [
    { message: "HOT_DECISION quote_time=2026-09-27T00:00:00Z policy=quote_cross_30s_v1 trend=rising" },
    { message: "HOT_DECISION quote_time=2026-09-27T00:00:01Z policy=wrong" },
  ]);
  assert.equal(decision.policy, "quote_cross_30s_v1");
  assert.equal(reasonForOrder(order, decision), "Buy trigger: the current bid crossed above the earlier sampled ask.");
  assert.equal(decisionForOrder(order, [], { one: { policy: "stored", quote_time: "old" } }).policy,
    "stored");
});

test("quote trigger evidence is visible only when the actual quote fields were retained", () => {
  // SOURCE: synthetic quote values chosen to encode an exact 10 bp upward cross.
  const evidence = quoteEvidence({ reference_bid: "99.5", reference_ask: "100",
    current_bid: "100.1", current_ask: "100.2", cross_direction: "up",
    trigger_move_bps: "10.00000000" });
  assert.deepEqual(evidence, { referenceBid: 99.5, referenceAsk: 100, currentBid: 100.1,
    currentAsk: 100.2, triggerMoveBps: 10, direction: "up" });
  assert.equal(quoteEvidence({ policy: "quote_cross_30s_v1" }), null);
  assert.equal(quoteEvidence({ reference_bid: "NaN", reference_ask: "100",
    current_bid: "100.1", current_ask: "100.2", cross_direction: "up",
    trigger_move_bps: "10" }), null);
});
