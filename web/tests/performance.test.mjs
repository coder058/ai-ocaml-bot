import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, readFile, appendFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { performanceHistory } from "../lib/performance.ts";
// SOURCE: synthetic broker snapshots verify persistence, not trading performance.
const snapshot = () => ({
  generatedAt: "2026-10-04T12:00:00Z",
  ordersComplete: true,
  fillsComplete: true,
  orders: [],
  fills: [],
  positions: [],
  cryptoFees: {
    pagesComplete: true,
    attributedToBot: true,
    unclassifiedRows: 0,
    usdNetAmount: "-2",
    btcFeeQty: "0",
    btcFeeValueAtActivityPriceUsd: "0",
    activityRows: 1,
    usdFeeRows: 1,
    btcFeeRows: 0,
    fetchedAt: "2026-10-04T12:00:00Z",
  },
});
test("performance persists actual snapshots once under concurrent refreshes and rejects incomplete accounting", async () => {
  const dir = await mkdtemp(join(tmpdir(), "ocaml-performance-"));
  const file = join(dir, "telemetry.json");
  try {
    const s = snapshot();
    await Promise.all([
      performanceHistory(s, file),
      performanceHistory(s, file),
    ]);
    let points = await performanceHistory(s, file);
    assert.equal(points.length, 1);
    assert.equal(points[0].markedPnl, -2);
    const old = { ...s, generatedAt: "2026-10-04T11:00:00Z" };
    assert.equal((await performanceHistory(old, file)).length, 1);
    const broken = {
      ...s,
      generatedAt: "2026-10-04T12:01:00Z",
      fillsComplete: false,
    };
    assert.equal((await performanceHistory(broken, file)).length, 1);
    const next = { ...s, generatedAt: "2026-10-04T12:02:00Z" };
    assert.equal((await performanceHistory(next, file)).length, 2);
    assert.equal(
      (await readFile(join(dir, "performance.jsonl"), "utf8"))
        .trim()
        .split("\n").length,
      2,
    );
    assert.deepEqual(await performanceHistory(s, undefined), []);
    // SOURCE: an interrupted append must not swallow the next real observation.
    await appendFile(join(dir, "performance.jsonl"), '{"at":"truncated');
    const afterCrash = { ...s, generatedAt: "2026-10-04T12:03:00Z" };
    assert.equal((await performanceHistory(afterCrash, file)).length, 3);
    assert.equal((await performanceHistory(afterCrash, file)).length, 3);
  } finally {
    // SOURCE: only the explicitly created test directory is removed.
    assert.equal(
      resolve(dir).startsWith(resolve(tmpdir()) + "\\") ||
        resolve(dir).startsWith(resolve(tmpdir()) + "/"),
      true,
    );
    await rm(dir, { recursive: true, force: true });
  }
});
