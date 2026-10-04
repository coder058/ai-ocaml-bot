import { readFile, appendFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import type { PaperTelemetry } from "./telemetry";
import { botAccounting } from "./bot-view.ts";

export type PerformancePoint = {
  at: string;
  markedPnl: number;
  openValue: number;
  postedUsdFees: number;
};
// SOURCE: one public accounting point per distinct authenticated broker snapshot.
// Collection happens when the localhost API is polled, not while it is closed.
let queue: Promise<unknown> = Promise.resolve();
export async function performanceHistory(
  t: PaperTelemetry | null,
  file: string | undefined,
): Promise<PerformancePoint[]> {
  if (!file || !t) return [];
  const task = queue.then(async () => {
    const path = join(dirname(file), "performance.jsonl");
    let points: PerformancePoint[] = [];
    let needsNewline = false;
    try {
      const content = await readFile(path, "utf8");
      // SOURCE: separate a truncated crash tail from the next complete point.
      needsNewline = content.length > 0 && !content.endsWith("\n");
      points = content
        .split("\n")
        .filter(Boolean)
        .flatMap((line) => {
          try {
            const p = JSON.parse(line);
            return typeof p.at === "string" &&
              Number.isFinite(Date.parse(p.at)) &&
              [p.markedPnl, p.openValue, p.postedUsdFees].every(Number.isFinite)
              ? [p]
              : [];
          } catch {
            return [];
          }
        });
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== "ENOENT") throw e;
    }
    const a = botAccounting(t);
    const last = points.at(-1);
    if (
      a.available &&
      a.markedResultAfterPostedFees != null &&
      a.postedUsdFees != null &&
      Number.isFinite(Date.parse(t.generatedAt)) &&
      (!last || Date.parse(t.generatedAt) > Date.parse(last.at))
    ) {
      const point = {
        at: t.generatedAt,
        markedPnl: a.markedResultAfterPostedFees,
        openValue: a.marketValue,
        postedUsdFees: a.postedUsdFees,
      };
      await appendFile(
        path,
        (needsNewline ? "\n" : "") + JSON.stringify(point) + "\n",
      );
      points.push(point);
    }
    // GUESS: # UNCALIBRATED GUESS — return the latest 4000 actual points for browser
    // memory bounds. The append-only local file retains the complete collected series.
    return points.slice(-4000);
  });
  queue = task.catch(() => undefined);
  try {
    return await task;
  } catch {
    return [];
  }
}
