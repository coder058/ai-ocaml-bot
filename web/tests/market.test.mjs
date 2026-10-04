import assert from "node:assert/strict";
import test from "node:test";
import { analyzeSnapshot } from "../lib/market.ts";

// SOURCE: SYNTHETIC candles test closed-time, gap and venue boundaries only.
const bar = (t, o, c) => ({ t, closeTime: t + 300_000,
  o, h: Math.max(o, c) + 1, l: Math.min(o, c) - 1, c, closed: true });
const wrap = (frames) => ({ symbol: "BTC", venue: "Hyperliquid", asOf: 600_000,
  frames: { "5m": frames } });

test("closed adjacent bars produce a time-stamped descriptive frame", () => {
  const result = analyzeSnapshot("BTC", wrap([bar(0, 100, 100), bar(300_000, 101, 102)]), 600_000);
  assert.equal(result.frames.length, 1);
  // SOURCE: round only the SYNTHETIC floating-point assertion, not market data.
  assert.equal(Number(result.frames[0].returnPct.toFixed(6)), 2);
  assert.equal(result.frames[0].closeTime, "1970-01-01T00:10:00.000Z");
});

test("future or gapped candles do not enter the reading", () => {
  assert.equal(analyzeSnapshot("BTC", wrap([bar(0, 100, 100), bar(300_000, 101, 102)]), 599_999).frames.length, 0);
  assert.equal(analyzeSnapshot("BTC", wrap([bar(0, 100, 100), bar(600_000, 101, 102)]), 900_000).frames.length, 0);
});

test("venue and symbol mismatches do not enter the reading", () => {
  const snapshot = wrap([bar(0, 100, 100), bar(300_000, 101, 102)]);
  assert.equal(analyzeSnapshot("ETH", snapshot, 600_000).frames.length, 0);
  assert.equal(analyzeSnapshot("BTC", { ...snapshot, venue: "other" }, 600_000).frames.length, 0);
});
