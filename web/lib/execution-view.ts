import type { FrameName, PaperTelemetry } from "./telemetry";
import type { ChartFrame } from "./chart-types";
import { botFills, botOrders, marketSymbol, orderDisplayStatus, orderFillSummary, reasonForOrder } from "./bot-view.ts";

// SOURCE: actual clock at the start of the user's new execution-trace work.
// The previous history reset remains intact; this is a separate, dated cohort.
export const TRACE_START = "2026-10-04T19:36:49Z";
// SOURCE: the five requested frames, also used by lib/frame_analysis.ml.
export const TRACE_FRAMES: FrameName[] = ["1m", "5m", "30m", "1h", "4h"];
// GUESS: # UNCALIBRATED GUESS — reuse Multi_paper.snapshot_max_age (120s).
// This is an operational freshness warning, not a market-derived threshold.
const STATUS_MAX_AGE_MS = 120_000;
export type TraceStep = { stage: string; state: "observed" | "blocked" | "unknown" | "context"; detail: string };
export type ExecutionRow = {
  id: string; symbol: string; venue: string; category: string; frame: FrameName;
  dataState: string; bar: string | null; candidate: string | null;
  route: string; routeReason: string; steps: TraceStep[];
};
const fresh = (at: string | undefined, now: number) => {
  const time = Date.parse(at ?? "");
  return Number.isFinite(time) && time <= now && now - time <= STATUS_MAX_AGE_MS;
};
const allowed = (symbol: string) => ["BTC/USD", "ETH/USD", "SOL/USD"].includes(marketSymbol(symbol) ?? "");
const canonical = (symbol: string) => marketSymbol(symbol) ?? symbol;

function routeFor(t: PaperTelemetry, symbol: string, venue: string, now: number) {
  if (venue === "Hyperliquid HIP-3") return { name: "Public data only", reason: "No paper execution adapter. Mainnet order authority is disabled." };
  if (venue === "Alpaca crypto") {
    if (!allowed(symbol)) return { name: "Excluded crypto", reason: "Only BTC, ETH and SOL are permitted." };
    if (canonical(symbol) === "BTC/USD") return { name: "Separate BTC engine", reason: "BTC uses quote_cross_30s_v1; these candle candidates do not route to its orderer." };
    if (!fresh(t.multiPaper?.asOf, now)) return { name: "Runtime unverified", reason: "Multiframe runtime status is absent, stale or future-dated." };
    if (t.multiPaper?.mode !== "PAPER_EXPERIMENT" || !t.multiPaper.newEntriesEnabled)
      return { name: "New entries paused", reason: "The multiframe paper runtime has new entries disabled. Existing exits and pending reconciliation are separate." };
    return { name: "Paper entry gate enabled", reason: "ETH/SOL long candidates may reach preflight; an enabled gate is not a passed risk check or an order." };
  }
  if (venue === "Alpaca equities") {
    const stocks = t.connections?.stocks;
    if (!stocks || !fresh(stocks.asOf, now)) return { name: "Runtime unverified", reason: "Stock connection status is absent, stale or future-dated." };
    const auto = t.connections?.stockAuto;
    if (auto) {
      if (!fresh(auto.asOf, now)) return { name: "Runtime unverified", reason: "Stock scheduler status is stale or future-dated." };
      if (auto.automaticStrategy && (auto.mode !== "PAPER_EXPERIMENT" || !auto.newEntriesEnabled))
        return { name: "Stock policy in observation", reason: `The automatic stock scheduler is installed, but its new-order route is disabled.${!stocks.sessionOpen ? ` Session closed; next open ${stocks.nextOpen}.` : ""} ${auto.stopHandling}` };
      if (!stocks.sessionOpen) return { name: "Stock session closed", reason: `Next regular session: ${stocks.nextOpen}. No after-hours queue.` };
      if (auto.automaticStrategy && auto.newEntriesEnabled && stocks.connected && stocks.accountReady && stocks.executionGateArmed && stocks.canSubmitNow)
        return { name: "Paper entry gate enabled", reason: "The automatic stock runtime reports an enabled route; actual ownership, fresh IEX quotes and per-order preflight are still required." };
    }
    if (!stocks?.automaticStrategy) return { name: "Stock automation missing", reason: `The stock router accepts explicit requests only.${stocks?.sessionOpen === false ? ` Session closed; next open ${stocks.nextOpen}.` : ""}` };
    if (!stocks.sessionOpen) return { name: "Stock session closed", reason: `Next regular session: ${stocks.nextOpen}. No after-hours queue.` };
    if (!stocks.connected || !stocks.accountReady || !stocks.executionGateArmed || !stocks.canSubmitNow)
      return { name: "Stock execution blocked", reason: "Broker connection, account, session or stock execution gate is not ready." };
    return { name: "Paper entry gate enabled", reason: "The stock runtime reports an enabled route; per-order preflight is still required." };
  }
  return { name: "Unsupported route", reason: "This venue has no verified paper order route." };
}

function rowFor(t: PaperTelemetry, market: NonNullable<PaperTelemetry["marketPipeline"]>["markets"][number], frame: FrameName, now: number): ExecutionRow {
  const r = market.frames[frame] as ChartFrame | undefined;
  const pipelineFresh = fresh(t.marketPipeline?.retrievedAt, now) && fresh(t.marketPipeline?.asOf, now);
  const route = routeFor(t, market.symbol, market.venue, now);
  const suite = r?.technicalSuite;
  const patterns = Object.values(suite?.patterns ?? {});
  const indicators = Object.values(suite?.indicators ?? {});
  const ticket = t.multiPaper?.activeTickets.find(ticket => canonical(ticket.symbol) === canonical(market.symbol));
  const runtimeFresh = fresh(t.multiPaper?.asOf, now);
  const runtimeReason = runtimeFresh ? t.multiPaper?.abstentions.filter(a => a.symbol === "all" || canonical(a.symbol) === canonical(market.symbol)).map(a => a.reason).join("; ") : "";
  const stockOwned = market.venue === "Alpaca equities" && fresh(t.connections?.stockAuto?.asOf, now)
    ? t.connections?.stockAuto?.ownedPositions?.find(p => p.symbol === market.symbol) : null;
  const policy = t.marketPipeline?.policy;
  const quote = r?.quoteReference;
  const quoteKnown = quote?.orderAuthority === false && quote.winProbability === null && quote.purpose === "observed_quote_reference_not_execution" &&
    typeof quote.quoteAt === "string" && typeof quote.receivedAt === "string" && typeof quote.bid === "number" && typeof quote.ask === "number";
  const quoteReasons=["provider_quote_missing","boolean_quote_fields","nonfinite_quote_fields","nonpositive_or_crossed_bid_ask","empty_or_negative_provider_size","invalid_or_missing_quote_fields","quote_after_actual_receipt","quote_older_than_receipt_guard","within_receipt_guard","provider_request_failed"];
  const quoteReason=typeof quote?.reason==="string" && quoteReasons.includes(quote.reason)?quote.reason.replaceAll("_"," "):null;
  const steps: TraceStep[] = [
    { stage: "Closed candles", state: !pipelineFresh ? "unknown" : !r || ["invalid", "no_data", "stale"].includes(r.status) ? "blocked" : "observed",
      detail: !pipelineFresh ? "Pipeline snapshot stale, missing or future-dated; current readiness cannot be verified." : `${r?.reason ?? "Frame missing"}. Closed bars ${r?.completeBars ?? "unknown"}; contiguous tail ${r?.contiguousTailBars ?? "unknown"}; last start ${r?.lastBarStart ?? "unknown"}.` },
    { stage: "Technical calculations", state: !pipelineFresh ? "unknown" : suite ? "observed" : "unknown",
      detail: suite ? `${patterns.filter(p => p.status === "ready").length}/${patterns.length} candlestick functions ready; ${indicators.filter(i => i.status === "ready").length}/${indicators.length} indicator functions ready. Suite ${suite.status}. Detection does not imply a trade.` : "Technical-suite evidence unavailable." },
    { stage: "Frozen OCaml policy", state: !pipelineFresh ? "unknown" : policy !== "trend_candle_confluence_v1" ? "unknown" : r?.candidate ? "observed" : "blocked",
      detail: policy !== "trend_candle_confluence_v1" ? `Unrecognized policy ${policy ?? "missing"}; no rule is inferred.` : `Trend ${r?.trend ?? "unknown"}; shapes ${(r?.candleShapes ?? []).join(", ") || "none"}; candidate ${r?.candidate ?? "none"}; invalidation ${r?.invalidationLevel ?? "none"}. Rule: fresh, warmed, open session, rising + bullish engulfing/hammer, or falling + bearish engulfing/shooting star. This is an uncalibrated exploratory rule; the full TA-Lib catalog does not drive entries.` },
    { stage: "Observed bid / ask reference", state: quoteKnown ? "context" : "unknown",
      detail: quoteKnown ? `${quote.feed}: bid ${quote.bid}, ask ${quote.ask}; quote ${quote.quoteAt}, received ${quote.receivedAt}; status at reception ${quote.status}${quoteReason ? ` (${quoteReason})` : ""}. Research reference, not a fill, current executable price or historical order reason. The order router fetches its own fresh quote at submission.` : `Quote reference ${quote?.status ?? "unavailable"}${quoteReason ? ` (${quoteReason})` : ""}. No bid/ask or fill price is inferred from the candle close.` },
    { stage: "Execution route", state: route.name === "Paper entry gate enabled" && r?.candidate !== "short" ? "observed" : "blocked", detail: `${route.reason}${r?.candidate === "short" && ["Alpaca equities", "Alpaca crypto"].includes(market.venue) ? " The multiframe policy supports long entries only; this short candidate cannot submit an entry." : ""}` },
    { stage: "Risk / ownership", state: ticket && runtimeFresh || stockOwned ? "blocked" : "unknown",
      detail: stockOwned ? `Owned stock quantity ${stockOwned.quantity}; managed origin ${stockOwned.frame ?? "unavailable"}.${stockOwned.pending ? " Pending stock order must reconcile." : ""} One position per instrument blocks further entries; manual positions are not adopted.` : ticket && runtimeFresh ? `An existing owned ticket on ${ticket.symbol}/${ticket.frame} blocks another entry for this instrument.${ticket.pending ? ` Pending ${ticket.pending.side} must reconcile first.` : ""}` : "This chart audit does not perform broker account, buying-power, open-order, executable-quote or ownership preflight. No pass is inferred." },
    { stage: "Broker acknowledgement", state: "context", detail: "Chart candidates have no order authority. Only an exact durable client ID joined to an actual broker order proves submission; see the new order cohort below." },
  ];
  if (runtimeReason && market.venue === "Alpaca crypto" && canonical(market.symbol) !== "BTC/USD")
    steps.push({ stage: "Latest runtime abstention", state: "blocked", detail: `${runtimeReason}. Runtime observation ${t.multiPaper?.asOf}; this is not a newly performed per-frame preflight.` });
  return { id: `${market.venue}|${market.symbol}|${frame}`, symbol: market.symbol, venue: market.venue, category: market.category, frame,
    dataState: !pipelineFresh ? "snapshot_unverified" : r?.status ?? "no_data", bar: r?.lastBarStart ?? null,
    candidate: pipelineFresh ? r?.candidate ?? null : null, route: route.name, routeReason: route.reason, steps };
}

const EVIDENCE_FIELDS = ["policy", "reason", "frame", "signal_bar", "observedAt", "quote_time", "trigger_quote_time", "reference_quote_time", "reference_bid", "reference_ask", "current_bid", "current_ask", "trigger_move_bps", "trigger_bid", "trigger_ask", "invalidation_level", "ema20", "ema50", "rsi14", "macd", "macd_signal", "trend", "candle_shapes", "bar_close", "preflight_evidence"];
function newOrders(t: PaperTelemetry, now: number) {
  const fills = botFills(t);
  return botOrders(t).filter(o => {
    const at = Date.parse(o.submittedAt ?? "");
    return Number.isFinite(at) && at >= Date.parse(TRACE_START) && at <= now &&
      (!o.clientOrderId.startsWith("jsbot") || allowed(o.symbol));
  }).map(order => {
    // SOURCE: exporter joins durable client IDs to broker IDs. Never use a
    // nearby chart or reconstruct a missing historical decision from today.
    const raw = t.decisionHistory?.[order.id];
    const observed = Date.parse(raw?.observedAt ?? "");
    const submitted = Date.parse(order.submittedAt!);
    const quote = raw?.trigger_quote_time ?? raw?.quote_time;
    const quoteAt = Date.parse(quote ?? "");
    // SOURCE: Multi_paper.stamp and exported HOT journal times have whole-
    // second resolution. Bound that interval; do not invent subsecond order.
    // 1000 milliseconds per second is a unit conversion, not a fitted value.
    const secondsOnly = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(raw?.observedAt ?? "");
    const observedEnd = observed + (secondsOnly ? 1_000 : 0);
    const prior = !!raw && Number.isFinite(observed) && observedEnd <= submitted &&
      (!quote || Number.isFinite(quoteAt) && (secondsOnly ? quoteAt < observedEnd : quoteAt <= observedEnd) && quoteAt <= submitted);
    const evidence = prior ? Object.fromEntries(EVIDENCE_FIELDS.filter(key => typeof raw[key] === "string").map(key => [key, raw[key]])) : null;
    const fill = orderFillSummary(order, fills.filter(f => canonical(f.symbol) === canonical(order.symbol) && f.side === order.side));
    return { id: order.id, clientOrderId: order.clientOrderId, symbol: canonical(order.symbol), side: order.side,
      submittedAt: order.submittedAt!, status: orderDisplayStatus(order), brokerFilledQty: order.filledQty,
      fill: { quantity: fill.quantity, notional: fill.notional, averagePrice: fill.averagePrice, fillCount: fill.fillCount },
      evidence, evidencePrecision: evidence ? secondsOnly ? "Journal time has one-second resolution; its full interval precedes broker submission." : "Recorded timestamp precedes broker submission." : null,
      reason: evidence ? reasonForOrder(order, evidence) : "Pre-submit evidence unavailable or its timing cannot be verified. No reason is reconstructed." };
  });
}

export function executionView(t: PaperTelemetry | null, now = Date.now()) {
  if (!t) return null;
  const rows = (t.marketPipeline?.markets ?? []).filter(m => m.symbol !== "AAPL").flatMap(m => TRACE_FRAMES.map(frame => rowFor(t, m, frame, now)));
  const counts = (key: "dataState" | "route") => Object.fromEntries([...new Set(rows.map(r => r[key]))].map(value => [value, rows.filter(r => r[key] === value).length]));
  const audit=t.quoteAudit;
  const count=(value: unknown): value is number => typeof value==="number" && Number.isSafeInteger(value) && value>=0;
  const quoteAudit=audit && audit.schema==="first_observed_long_quote_reference_v1" && audit.orderAuthority===false && audit.winProbability===null &&
    Number.isFinite(Date.parse(audit.generatedAt)) && Date.parse(audit.generatedAt)<=now && count(audit.labelCount) &&
    count(audit.foldCounts?.discovery) && count(audit.foldCounts?.validation) && audit.labelCount===audit.foldCounts.discovery+audit.foldCounts.validation &&
    count(audit.comparisonCount) && count(audit.horizonBars) && audit.horizonBars>0 && count(audit.maxExitLagSeconds) && Number.isFinite(Date.parse(audit.splitAt))
    ? {generatedAt:audit.generatedAt,labelCount:audit.labelCount,discovery:audit.foldCounts.discovery,validation:audit.foldCounts.validation,
       comparisonCount:audit.comparisonCount,horizonBars:audit.horizonBars,maxExitLagSeconds:audit.maxExitLagSeconds,splitAt:audit.splitAt,
       missingEntryQuotes:count(audit.rejected?.noFirstObservedFreshEntryQuote)?audit.rejected.noFirstObservedFreshEntryQuote:null,
       missingExitQuotes:count(audit.rejected?.noTimelyFreshExitReference)?audit.rejected.noTimelyFreshExitReference:null} : null;
  return { generatedAt: t.generatedAt, analysisAsOf: t.marketPipeline?.asOf ?? null, retrievedAt: t.marketPipeline?.retrievedAt ?? null,
    traceStart: TRACE_START, orderAuthority: false as const, winProbability: null,
    symbols: new Set(rows.map(r => `${r.venue}|${r.symbol}`)).size, frames: rows.length,
    candidates: rows.filter(r => r.candidate).length, dataCounts: counts("dataState"), routeCounts: counts("route"),
    fx: t.connections?.fx ? { connected: t.connections.fx.connected, reason: t.connections.fx.reason, executionAdapterAvailable: t.connections.fx.executionAdapterAvailable } : null,
    quoteAudit,
    rows, orders: newOrders(t, now), ordersComplete: t.ordersComplete, fillsComplete: t.fillsComplete === true,
    explanation: "Five timeframes describe the same instrument. Current multiframe execution permits one owned ticket per instrument; the number of open positions is not a count of analyses or completed trades." };
}
export type ExecutionView = NonNullable<ReturnType<typeof executionView>>;
