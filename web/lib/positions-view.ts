import type { PaperPosition, PaperTelemetry } from "./telemetry";
import { botOrders, marketSymbol } from "./bot-view.ts";

export type PositionsView = {
  generatedAt: string;
  source: PaperTelemetry["source"];
  service: PaperTelemetry["service"];
  positions: PaperPosition[];
};

// SOURCE: retain the existing bot ownership and protected-position boundary.
// The full broker snapshot stays internal; no history is included here.
export function positionsView(t: PaperTelemetry | null): PositionsView | null {
  if (!t) return null;
  const owned = new Set(["BTC/USD", ...botOrders(t).map(o => marketSymbol(o.symbol))]);
  return {
    generatedAt: t.generatedAt,
    source: t.source,
    service: { ...t.service },
    positions: t.positions.filter(p => !p.protected && owned.has(marketSymbol(p.symbol)))
      .map(p => ({ ...p })),
  };
}
