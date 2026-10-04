import type { PaperFill, PaperOrder, PaperTelemetry } from "./telemetry";
import {
  botAccounting,
  botFills,
  botOrders,
  marketSymbol,
} from "./bot-view.ts";

// SOURCE: Alpaca quantities support nine decimal places; the inspected complete
// broker fill snapshot had at most nine. Inventory matching uses integer units.
const SCALE = 1_000_000_000n;
const decimalQty = (text: string): bigint => {
  if (!/^\d+(?:\.\d{1,9})?$/.test(text))
    throw new Error("Fill quantity has unsupported decimal precision.");
  const [whole, fraction = ""] = text.split(".");
  return BigInt(whole) * SCALE + BigInt(fraction.padEnd(9, "0"));
};
const numeric = (quantity: bigint) => Number(quantity) / Number(SCALE);

export type ClosedTrade = {
  id: string;
  symbol: string;
  entryOrderId: string;
  exitOrderId: string;
  entryAt: string;
  exitAt: string;
  quantity: number;
  entryPrice: number;
  exitPrice: number;
  grossPnl: number;
  entryValue: number;
  exitValue: number;
  fillCount: number;
};
export type TradeLedger = {
  available: boolean;
  reason: string | null;
  closed: ClosedTrade[];
  grossRealized: number | null;
  unmatchedSells: string[];
  unrealized: number | null;
  realizedWithPostedCosts: number | null;
};

export function tradeLedger(t: PaperTelemetry): TradeLedger {
  const base: TradeLedger = {
    available: false,
    reason: null,
    closed: [],
    grossRealized: null,
    unmatchedSells: [],
    unrealized: null,
    realizedWithPostedCosts: null,
  };
  const accounting = botAccounting(t);
  if (!accounting.available) return { ...base, reason: accounting.reason };
  const orders = new Map(botOrders(t).map((o) => [o.id, o]));
  const queue = new Map<string, { remaining: bigint; fill: PaperFill }[]>();
  const matched = new Map<string, ClosedTrade>();
  try {
    const fills = [...botFills(t)].sort((a, b) => {
      if (!a.transactionTime || !b.transactionTime)
        throw new Error("A fill timestamp is missing.");
      const delta =
        Date.parse(a.transactionTime) - Date.parse(b.transactionTime);
      if (!Number.isFinite(delta))
        throw new Error("A fill timestamp is invalid.");
      return (
        delta ||
        a.transactionTime.localeCompare(b.transactionTime) ||
        a.id.localeCompare(b.id)
      );
    });
    for (const fill of fills) {
      const order = orders.get(fill.orderId);
      const symbol = marketSymbol(fill.symbol);
      if (
        !order ||
        !symbol ||
        marketSymbol(order.symbol) !== symbol ||
        order.side !== fill.side ||
        !fill.transactionTime ||
        !Number.isFinite(Date.parse(fill.transactionTime))
      )
        throw new Error("Fill identity/time is invalid.");
      let quantity = decimalQty(fill.qty);
      if (
        quantity <= 0n ||
        !Number.isFinite(Number(fill.price)) ||
        Number(fill.price) <= 0
      )
        throw new Error("Fill price/quantity is invalid.");
      const lots = queue.get(symbol) ?? [];
      queue.set(symbol, lots);
      if (fill.side === "buy") {
        lots.push({ remaining: quantity, fill });
        continue;
      }
      if (fill.side !== "sell") throw new Error("Unsupported fill side.");
      while (quantity > 0n && lots.length) {
        const lot = lots[0];
        const amount = quantity < lot.remaining ? quantity : lot.remaining;
        const units = numeric(amount);
        const cost = units * Number(lot.fill.price);
        const proceeds = units * Number(fill.price);
        const id = lot.fill.orderId + "|" + fill.orderId;
        const old = matched.get(id);
        const next: ClosedTrade = old ?? {
          id,
          symbol,
          entryOrderId: lot.fill.orderId,
          exitOrderId: fill.orderId,
          entryAt: lot.fill.transactionTime!,
          exitAt: fill.transactionTime,
          quantity: 0,
          entryPrice: 0,
          exitPrice: 0,
          grossPnl: 0,
          entryValue: 0,
          exitValue: 0,
          fillCount: 0,
        };
        next.quantity += units;
        next.entryValue += cost;
        next.exitValue += proceeds;
        next.grossPnl += proceeds - cost;
        next.fillCount++;
        if (lot.fill.transactionTime! < next.entryAt)
          next.entryAt = lot.fill.transactionTime!;
        if (fill.transactionTime > next.exitAt)
          next.exitAt = fill.transactionTime;
        next.entryPrice = next.entryValue / next.quantity;
        next.exitPrice = next.exitValue / next.quantity;
        matched.set(id, next);
        quantity -= amount;
        lot.remaining -= amount;
        if (lot.remaining === 0n) lots.shift();
      }
      if (quantity > 0n) base.unmatchedSells.push(fill.id);
    }
    if (base.unmatchedSells.length)
      return {
        ...base,
        reason:
          "Sell fills exceed recorded buy inventory; closed P&L is unavailable.",
      };
    const owned = new Set(
      [...orders.values()].map((o) => marketSymbol(o.symbol)),
    );
    const positions = t.positions.filter(
      (p) => !p.protected && owned.has(marketSymbol(p.symbol)),
    );
    const unrealized = positions.every(
      (p) => p.unrealizedPl != null && Number.isFinite(Number(p.unrealizedPl)),
    )
      ? positions.reduce((total, p) => total + Number(p.unrealizedPl), 0)
      : null;
    const marked = accounting.markedResultAfterPostedFees;
    return {
      ...base,
      available: true,
      closed: [...matched.values()].sort((a, b) =>
        b.exitAt.localeCompare(a.exitAt),
      ),
      grossRealized: [...matched.values()].reduce(
        (sum, r) => sum + r.grossPnl,
        0,
      ),
      unrealized,
      // SOURCE: portfolio result minus broker open-position unrealized P&L;
      // this includes posted costs, remains provisional, and is not per-trade net P&L.
      realizedWithPostedCosts:
        marked != null && unrealized != null ? marked - unrealized : null,
    };
  } catch (cause) {
    return {
      ...base,
      reason: cause instanceof Error ? cause.message : "Fill matching failed.",
    };
  }
}

export function csv(
  rows: Record<string, unknown>[],
  columns: string[],
): string {
  const escape = (value: unknown) =>
    '"' + String(value ?? "").replaceAll('"', '""') + '"';
  // SOURCE: RFC 4180 CSV quoting; all fields are quoted, including user text.
  // Spreadsheet formula prefixes are neutralized for exported reason text.
  const safe = (value: unknown) =>
    typeof value === "string" && /^\s*[=+@\-]/.test(value)
      ? "'" + value
      : value;
  return [
    columns.map(escape).join(","),
    ...rows.map((row) => columns.map((k) => escape(safe(row[k]))).join(",")),
  ].join("\r\n");
}

export const orderPolicy = (order: PaperOrder, t: PaperTelemetry) =>
  t.decisionHistory?.[order.id]?.policy ?? "unrecorded";
