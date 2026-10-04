import test from "node:test";
import assert from "node:assert/strict";
import { chartView } from "../lib/chart-view.ts";

test("chart projection preserves actual candles and detections, excluding broker history and redundant parameters", () => {
  // SOURCE: synthetic market-only fixture; it is not an observed market result.
  const bars = [{ t: "2026-10-04T16:00:00Z", o: 100, h: 102, l: 99, c: 101, v: 5 }];
  const raw = { asOf: "2026-10-04T16:01:00Z", markets: [{ symbol: "XYZ", venue: "Alpaca equities", category: "Stocks", execution: "analysis_only", frames: { "1m": {
    status: "warming", technicalSuite: { status: "ready", bars, patterns: { CDLHAMMER: { status: "ready", value: 100, requiredBars: 12 } }, indicators: { ADX: { status: "ready", values: { real: 25 }, parameters: { timeperiod: 14 } } }, patternEvents: [], overlays: {}, murphy: [] }, orders: [{ id: "private" }] } }, positions: [{ id: "private" }] }], orders: [{ id: "private" }] };
  const result = chartView(raw);
  const frame = result.markets[0].frames["1m"];
  assert.deepEqual(frame.technicalSuite.bars, bars);
  assert.deepEqual(frame.technicalSuite.patterns.CDLHAMMER, { status: "ready", value: 100 });
  assert.equal(frame.technicalSuite.indicators.ADX.values.real, 25);
  assert.equal(frame.technicalSuite.indicators.ADX.parameters, undefined);
  assert.equal(frame.orderAuthority, false);
  assert.equal(frame.winProbability, null);
  assert.equal(JSON.stringify(result).includes("private"), false);
  assert.equal(chartView(undefined), null);
});
