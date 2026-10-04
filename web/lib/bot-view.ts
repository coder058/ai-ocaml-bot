import type { PaperFill, PaperOrder, PaperTelemetry } from "./telemetry";

export type BotAccounting = {
  available: boolean;
  flat: boolean;
  buyNotional: number;
  sellNotional: number;
  marketValue: number;
  cashDifference: number;
  markedResult: number | null;
  postedUsdFees: number | null;
  markedResultAfterPostedFees: number | null;
  postedBtcFeeQty: number | null;
  postedBtcFeeValueUsd: number | null;
  quantityResidual: number | null;
  quantityResiduals: Record<string, number>;
  feeActivityRows: number | null;
  reason: string | null;
};

const botOrder = (id: string) =>
  id.startsWith("jsbotbtc") ||
  id.startsWith("jsbotmtf") ||
  id.startsWith("aibotstk");
const btc = (symbol: string) => symbol === "BTCUSD" || symbol === "BTC/USD";
export const cryptoSymbol = (symbol: string): string | null => {
  if (!/^[A-Z0-9]+\/?USD$/.test(symbol)) return null;
  const compact = symbol.replace("/", "");
  return compact.length > "USD".length
    ? `${compact.slice(0, -"USD".length)}/USD`
    : null;
};
export const assetUnit = (symbol: string) =>
  cryptoSymbol(symbol)?.split("/")[0] ?? symbol;
export const marketSymbol = (symbol: string): string | null =>
  cryptoSymbol(symbol) ??
  (symbol !== "AAPL" && /^[A-Z0-9][A-Z0-9.-]*$/.test(symbol) ? symbol : null);
const labOrder = (order: PaperOrder) =>
  botOrder(order.clientOrderId) &&
  (order.clientOrderId.startsWith("aibotstk")
    ? !cryptoSymbol(order.symbol) && !!marketSymbol(order.symbol)
    : !!cryptoSymbol(order.symbol) &&
      (order.clientOrderId.startsWith("jsbotmtf") || btc(order.symbol)));

export function botOrders(t: PaperTelemetry): PaperOrder[] {
  const unique = new Map<string, PaperOrder>();
  for (const order of t.orders) {
    if (labOrder(order) && !unique.has(order.id)) unique.set(order.id, order);
  }
  return [...unique.values()].sort((left, right) =>
    (right.submittedAt ?? "").localeCompare(left.submittedAt ?? ""),
  );
}

export function botFills(t: PaperTelemetry): PaperFill[] {
  const botOrderIds = new Set(botOrders(t).map((order) => order.id));
  const unique = new Map<string, PaperFill>();
  for (const fill of t.fills ?? [])
    if (
      botOrderIds.has(fill.orderId) &&
      marketSymbol(fill.symbol) &&
      !unique.has(fill.id)
    )
      unique.set(fill.id, fill);
  return [...unique.values()].sort((left, right) =>
    (right.transactionTime ?? "").localeCompare(left.transactionTime ?? ""),
  );
}

export function botAccounting(t: PaperTelemetry): BotAccounting {
  const unavailable = (reason: string): BotAccounting => ({
    available: false,
    flat: false,
    buyNotional: 0,
    sellNotional: 0,
    marketValue: 0,
    cashDifference: 0,
    markedResult: null,
    postedUsdFees: null,
    markedResultAfterPostedFees: null,
    postedBtcFeeQty: null,
    postedBtcFeeValueUsd: null,
    quantityResidual: null,
    quantityResiduals: {},
    feeActivityRows: null,
    reason,
  });
  if (!t.ordersComplete || !t.fillsComplete || !Array.isArray(t.fills))
    return unavailable("Broker order or fill history is incomplete.");
  const orders = botOrders(t);
  // SOURCE: broker fill activity IDs identify immutable executions. Repeated
  // pagination rows may be deduplicated; conflicting executions must not be.
  const rawFillIds = new Map<string, PaperFill>();
  for (const fill of t.fills) {
    const prior = rawFillIds.get(fill.id);
    if (
      prior &&
      (prior.orderId !== fill.orderId ||
        marketSymbol(prior.symbol) !== marketSymbol(fill.symbol) ||
        prior.side !== fill.side ||
        prior.qty !== fill.qty ||
        prior.price !== fill.price ||
        prior.transactionTime !== fill.transactionTime)
    )
      return unavailable(
        "Conflicting duplicate broker fill IDs prevent attribution.",
      );
    rawFillIds.set(fill.id, fill);
  }
  const ownedSymbols = new Set([
    "BTC/USD",
    ...orders.map((order) => marketSymbol(order.symbol)!),
  ]);
  if (
    t.orders.some(
      (order) =>
        ownedSymbols.has(marketSymbol(order.symbol) ?? "") && !labOrder(order),
    )
  )
    return unavailable(
      "Activity outside this lab prevents attribution for a traded asset.",
    );
  const positions = t.positions.filter(
    (position) =>
      !position.protected &&
      ownedSymbols.has(marketSymbol(position.symbol) ?? ""),
  );
  const quantities: Record<string, number> = {};
  let marketValue = 0;
  for (const position of positions) {
    const symbol = marketSymbol(position.symbol)!;
    const quantity = Number(position.qty);
    const mark = Number(position.marketValue);
    if (symbol in quantities)
      return unavailable(
        "Multiple positions for the same asset prevent attribution.",
      );
    if (
      position.marketValue == null ||
      !Number.isFinite(quantity) ||
      quantity < 0 ||
      !Number.isFinite(mark) ||
      mark < 0
    )
      return unavailable("Broker asset quantity or mark is missing.");
    quantities[symbol] = quantity;
    marketValue += mark;
  }
  const byId = new Map(orders.map((order) => [order.id, order]));
  let buyNotional = 0;
  let sellNotional = 0;
  const fillNetQty: Record<string, number> = {};
  for (const fill of botFills(t)) {
    const qty = Number(fill.qty);
    const price = Number(fill.price);
    const symbol = marketSymbol(fill.symbol)!;
    if (
      marketSymbol(byId.get(fill.orderId)?.symbol ?? "") !== symbol ||
      byId.get(fill.orderId)?.side !== fill.side ||
      !Number.isFinite(qty) ||
      !Number.isFinite(price) ||
      qty <= 0 ||
      price <= 0
    )
      return unavailable(
        "A bot fill cannot be matched to a valid broker order.",
      );
    if (fill.side === "buy") {
      buyNotional += qty * price;
      fillNetQty[symbol] = (fillNetQty[symbol] ?? 0) + qty;
    } else if (fill.side === "sell") {
      sellNotional += qty * price;
      fillNetQty[symbol] = (fillNetQty[symbol] ?? 0) - qty;
    } else return unavailable("A bot fill has an unexpected side.");
  }
  const cashDifference = sellNotional - buyNotional;
  const fees = t.cryptoFees;
  const feeNumbers = fees
    ? [
        Number(fees.usdNetAmount),
        Number(fees.btcFeeQty),
        Number(fees.btcFeeValueAtActivityPriceUsd),
      ]
    : [];
  // SOURCE: unclassified crypto fees prevent assigning account-wide fees to this bot.
  const feeDataValid =
    !!fees &&
    fees.pagesComplete &&
    fees.attributedToBot &&
    fees.unclassifiedRows === 0 &&
    feeNumbers.every(Number.isFinite) &&
    typeof fees.fetchedAt === "string" &&
    Number.isFinite(Date.parse(fees.fetchedAt)) &&
    Number.isInteger(fees.activityRows) &&
    fees.activityRows >= 0 &&
    fees.usdFeeRows >= 0 &&
    fees.btcFeeRows >= 0;
  const postedUsdFees = feeDataValid ? feeNumbers[0] : null;
  const postedBtcFeeQty = feeDataValid ? feeNumbers[1] : null;
  const postedBtcFeeValueUsd = feeDataValid ? feeNumbers[2] : null;
  // SOURCE: Alpaca crypto fees debit the received asset; posted BTC debits
  // reflected in broker inventory must not be subtracted from the mark twice.
  const quantityResiduals: Record<string, number> = {};
  for (const symbol of ownedSymbols) {
    const debit = feeDataValid
      ? Number(
          fees?.assetFees?.[symbol]?.qty ??
            (symbol === "BTC/USD" ? (postedBtcFeeQty ?? 0) : 0),
        )
      : 0;
    if (!Number.isFinite(debit))
      return unavailable("Posted asset fee quantity is invalid.");
    quantityResiduals[symbol] =
      (quantities[symbol] ?? 0) - ((fillNetQty[symbol] ?? 0) + debit);
  }
  return {
    available: true,
    flat: positions.length === 0,
    buyNotional,
    sellNotional,
    marketValue,
    cashDifference,
    markedResult: cashDifference + marketValue,
    postedUsdFees,
    markedResultAfterPostedFees:
      postedUsdFees == null
        ? null
        : cashDifference + marketValue + postedUsdFees,
    postedBtcFeeQty,
    postedBtcFeeValueUsd,
    quantityResidual: quantityResiduals["BTC/USD"] ?? 0,
    quantityResiduals,
    feeActivityRows: feeDataValid ? fees.activityRows : null,
    reason: null,
  };
}

export type OrderFillSummary = {
  quantity: number;
  notional: number;
  averagePrice: number | null;
  fillCount: number;
  firstAt: string | null;
  lastAt: string | null;
};

export function orderFillSummary(
  order: PaperOrder,
  fills: PaperFill[],
): OrderFillSummary {
  const matching = fills.filter((fill) => fill.orderId === order.id);
  const quantity = matching.reduce((sum, fill) => sum + Number(fill.qty), 0);
  const notional = matching.reduce(
    (sum, fill) => sum + Number(fill.qty) * Number(fill.price),
    0,
  );
  const times = matching
    .map((fill) => fill.transactionTime)
    .filter((value): value is string => !!value)
    .sort();
  return {
    quantity,
    notional,
    averagePrice: quantity > 0 ? notional / quantity : null,
    fillCount: matching.length,
    firstAt: times[0] ?? null,
    lastAt: times.at(-1) ?? null,
  };
}

export function botExecutions(
  t: PaperTelemetry,
): { order: PaperOrder; fill: OrderFillSummary }[] {
  const fills = botFills(t);
  return botOrders(t)
    .map((order) => ({ order, fill: orderFillSummary(order, fills) }))
    .filter(
      ({ fill }) =>
        fill.fillCount > 0 &&
        Number.isFinite(fill.notional) &&
        fill.quantity > 0,
    )
    .sort((left, right) =>
      (right.fill.lastAt ?? "").localeCompare(left.fill.lastAt ?? ""),
    );
}

export function orderDisplayStatus(order: PaperOrder): string {
  const filled = Number(order.filledQty);
  if (order.status === "canceled" && filled > 0)
    return "Partial fill · rest canceled";
  if (order.status === "canceled") return "Canceled · no fill";
  if (order.status === "filled") return "Filled";
  return order.status.replaceAll("_", " ");
}

export function decisionForOrder(
  order: PaperOrder,
  journal: PaperTelemetry["journal"],
  history?: PaperTelemetry["decisionHistory"],
): Record<string, string> | null {
  if (history?.[order.id]) return history[order.id];
  const suffix = order.clientOrderId.replace(/^jsbotbtc(?:buy|sell)/, "");
  const decision = journal.findLast((entry) => {
    if (!entry.message.startsWith("HOT_DECISION ")) return false;
    const quoteTime = entry.message.match(/(?:^| )quote_time=([^ ]+)/)?.[1];
    return quoteTime?.replace(/[^A-Za-z0-9]/g, "") === suffix;
  });
  if (!decision) return null;
  return Object.fromEntries(
    decision.message
      .split(" ")
      .slice(1)
      .filter((part) => part.includes("="))
      .map((part) => part.split(/=(.*)/s).slice(0, 2)),
  );
}

export function reasonForOrder(
  order: PaperOrder,
  decision: Record<string, string> | null,
): string {
  if (!decision) return "Decision trace unavailable for this order.";
  if (decision.policy === "trend_candle_confluence_v1")
    return `${decision.frame ?? "Unknown frame"}: ${decision.reason ?? "Decision reason missing"}.`;
  if (decision.policy !== "quote_cross_30s_v1")
    return (
      decision.reason ?? `Recorded policy: ${decision.policy ?? "unknown"}.`
    );
  return order.side === "buy"
    ? "Buy trigger: the current bid crossed above the earlier sampled ask."
    : "Sell trigger: the current ask crossed below the earlier sampled bid.";
}

export function quoteEvidence(decision: Record<string, string> | null) {
  if (!decision) return null;
  const values = [
    decision.reference_bid,
    decision.reference_ask,
    decision.current_bid,
    decision.current_ask,
    decision.trigger_move_bps,
  ].map(Number);
  if (
    !values.every(Number.isFinite) ||
    values.slice(0, 4).some((value) => value <= 0) ||
    values[4] <= 0 ||
    !["up", "down"].includes(decision.cross_direction ?? "")
  )
    return null;
  return {
    referenceBid: values[0],
    referenceAsk: values[1],
    currentBid: values[2],
    currentAsk: values[3],
    triggerMoveBps: values[4],
    direction: decision.cross_direction as "up" | "down",
  };
}
