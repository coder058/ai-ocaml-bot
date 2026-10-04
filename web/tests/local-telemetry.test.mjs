import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { getTelemetry } from "../lib/telemetry.ts";

test("local mode serves complete histories larger than the old upload limit and fails closed", async () => {
  const directory = await mkdtemp(join(tmpdir(), "local-telemetry-"));
  const file = join(directory, "telemetry.json");
  const prior = process.env.AI_OCAML_MONITOR_TELEMETRY_FILE;
  process.env.AI_OCAML_MONITOR_TELEMETRY_FILE = file;
  try {
    // SOURCE: synthetic history deliberately exceeds the existing 1 MiB guard.
    const snapshot = { version: 1, source: "Dublin OCaml paper service",
      generatedAt: "2026-10-01T21:00:00Z", orders: [], fills: [], positions: [],
      ordersComplete: true, fillsComplete: true, journalComplete: false,
      journal: [{ at: "2026-10-01T21:00:00Z", message: "x".repeat(1_048_577) }] };
    await writeFile(file, JSON.stringify(snapshot));
    assert.deepEqual(await getTelemetry(), snapshot);
    await writeFile(file, "invalid JSON");
    assert.equal(await getTelemetry(), null);
    await rm(file);
    assert.equal(await getTelemetry(), null);
  } finally {
    if (prior === undefined) delete process.env.AI_OCAML_MONITOR_TELEMETRY_FILE;
    else process.env.AI_OCAML_MONITOR_TELEMETRY_FILE = prior;
    await rm(directory, { recursive: true, force: true });
  }
});
