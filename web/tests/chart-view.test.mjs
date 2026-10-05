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
  assert.equal(frame.technicalSuite.detailLevel, "full");
});

test("wall previews keep actual bars and overlays while chart details retain the complete analysis", () => {
  // SOURCE: synthetic projection fixture, not market data or performance.
  const events = [{ time: "2026-10-04T16:00:00Z", code: "CDLHAMMER", name: "Hammer", value: 100 },
    { time: "2026-10-04T16:00:00Z", code: "CDLDOJI", name: "Doji", value: 100 }];
  const suite = { status: "ready", bars: [{ t: events[0].time, o: 1, h: 2, l: 1, c: 2, v: 1 }],
    patterns: { CDLHAMMER: { status: "ready", value: 100 }, CDLENGULFING: { status: "ready", value: 0 } },
    patternEvents: events, indicators: { RSI: { status: "ready", values: { real: 50 } } },
    murphy: [{ law: 1, evidence: { missing: "Primary history" } }], overlays: { EMA20: [null] } };
  const raw = { markets: ["A", "B"].map(symbol => ({ symbol, venue: "fixture", frames: { "1m": { technicalSuite: suite } } })) };
  const wall = chartView(raw, { preview: true });
  assert.equal(wall.markets.length, 2);
  const preview = wall.markets[0].frames["1m"].technicalSuite;
  assert.equal(preview.detailLevel, "preview");
  assert.deepEqual(preview.bars, suite.bars);
  assert.deepEqual(preview.overlays, suite.overlays);
  assert.equal(preview.patternEvents.length, 1);
  assert.deepEqual(preview.indicators, {});
  assert.equal(preview.murphy, undefined);
  assert.equal(preview.patterns.CDLHAMMER.value, 100);
  const expanded = chartView(raw, { venue: "fixture", symbol: "B" });
  assert.deepEqual(expanded.markets.map(m => m.symbol), ["B"]);
  assert.deepEqual(expanded.markets[0].frames["1m"].technicalSuite.patternEvents, events);
  assert.deepEqual(JSON.parse(JSON.stringify(expanded.markets[0].frames["1m"].technicalSuite.indicators)), suite.indicators);
  assert.equal(chartView(raw, { venue: "fixture", symbol: "unknown" }).markets.length, 0);
  assert.equal(suite.patternEvents.length, 2);
});

test("native provenance stays in details with an allowlist and no fabricated older proof", () => {
  // SOURCE: synthetic hashes test projection only, never broker execution.
  const proof = { inputSha256: "a".repeat(64), inputBars: 100, analysisAsOf: "2026-10-05T13:31:00Z",
    engineSha256: "b".repeat(64), technicalAnalysisSha256: "c".repeat(64),
    frameFetchRetrievedAt: "2026-10-05T13:31:01Z", nativeInputArchive: "retained", scope: "native inputs",
    privateFile: "private path", orderAuthority: false };
  const raw = { markets: [{ symbol: "QQQ", venue: "Alpaca equities", frames: { "1m": { dataEvidence: proof } } }] };
  const detail = chartView(raw).markets[0].frames["1m"].dataEvidence;
  assert.equal(detail.inputSha256, proof.inputSha256);
  assert.equal(detail.orderAuthority, false);
  assert.equal(JSON.stringify(detail).includes("private path"), false);
  assert.equal(chartView(raw, { preview: true }).markets[0].frames["1m"].dataEvidence, undefined);
  delete raw.markets[0].frames["1m"].dataEvidence;
  assert.equal(chartView(raw).markets[0].frames["1m"].dataEvidence, undefined);
});
