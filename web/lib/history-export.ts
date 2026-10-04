import type { PaperTelemetry } from "./telemetry";
import {
  botOrders,
  botFills,
  marketSymbol,
  orderFillSummary,
  decisionForOrder,
  reasonForOrder,
} from "./bot-view.ts";
import { tradeLedger, csv, orderPolicy } from "./trade-ledger.ts";
export function historyExport(
  t: PaperTelemetry,
  params: URLSearchParams,
): string {
  const kind = params.get("kind");
  if (!["closed", "orders"].includes(kind ?? ""))
    throw new Error("Invalid export kind.");
  if (!t.ordersComplete || !t.fillsComplete)
    throw new Error("Complete broker history is required.");
  const symbol = params.get("symbol"),
    policy = params.get("policy"),
    from = params.get("from"),
    to = params.get("to"),
    side = params.get("side");
  // SOURCE: filters use the same ISO UTC calendar date as the visible desk.
  if (
    [from, to].some((d) => d && !/^\d{4}-\d{2}-\d{2}$/.test(d)) ||
    (from && to && from > to)
  )
    throw new Error("Invalid UTC date range.");
  const orders = botOrders(t),
    fills = botFills(t),
    byId = new Map(orders.map((o) => [o.id, o]));
  const matches = (o: (typeof orders)[number], at: string | null) =>
    (!symbol ||
      symbol === "All instruments" ||
      marketSymbol(o.symbol) === symbol) &&
    (!policy || policy === "All policies" || orderPolicy(o, t) === policy) &&
    (!from || (!!at && at.slice(0, 10) >= from)) &&
    (!to || (!!at && at.slice(0, 10) <= to));
  if (kind === "closed") {
    const ledger = tradeLedger(t);
    if (!ledger.available)
      throw new Error(ledger.reason ?? "Closed fill matching unavailable.");
    return csv(
      ledger.closed
        .filter((c) => {
          const o = byId.get(c.exitOrderId);
          return !!o && matches(o, c.exitAt);
        })
        .map((c) => ({
          ...c,
          snapshotAt: t.generatedAt,
          pnlBasis: "FIFO matched fills before fees",
          fees: "Not attributable per trade",
        })),
      [
        "snapshotAt",
        "symbol",
        "entryAt",
        "exitAt",
        "quantity",
        "entryPrice",
        "exitPrice",
        "grossPnl",
        "pnlBasis",
        "fees",
        "entryOrderId",
        "exitOrderId",
      ],
    );
  }
  return csv(
    orders
      .filter((o) => matches(o, o.submittedAt))
      .flatMap((o) => {
        const summary = orderFillSummary(o, fills);
        const executed = summary.fillCount > 0;
        if (
          (side === "Unfilled attempts" && executed) ||
          (["Executions", "Buy", "Sell"].includes(side ?? "") && !executed) ||
          (["Buy", "Sell"].includes(side ?? "") &&
            o.side !== side!.toLowerCase())
        )
          return [];
        return [
          {
            ...o,
            ...summary,
            snapshotAt: t.generatedAt,
            policy: orderPolicy(o, t),
            reason: reasonForOrder(
              o,
              decisionForOrder(o, t.journal, t.decisionHistory),
            ),
          },
        ];
      }),
    [
      "snapshotAt",
      "symbol",
      "side",
      "submittedAt",
      "status",
      "quantity",
      "notional",
      "averagePrice",
      "fillCount",
      "policy",
      "reason",
      "id",
      "clientOrderId",
    ],
  );
}
