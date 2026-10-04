"use client";

import { useEffect, useMemo, useState } from "react";
import { assetUnit, cryptoSymbol, botAccounting, botExecutions, botFills, botOrders, decisionForOrder,
  orderDisplayStatus, orderFillSummary, quoteEvidence, reasonForOrder } from "@/lib/bot-view";
import type { PaperFill, PaperOrder, PaperTelemetry } from "@/lib/telemetry";
import MarketRadar from "./market-radar";

type Live = { generatedAt: string; telemetry: PaperTelemetry | null };
type SideFilter = "trades" | "buy" | "sell" | "attempts";

const money = (value: number | string | null | undefined, digits = 2) => {
  const number = Number(value);
  return value == null || !Number.isFinite(number) ? "—" :
    new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits,
      maximumFractionDigits: digits }).format(number);
};
const signedMoney = (value: number | string | null | undefined, digits = 2) => {
  const number = Number(value);
  return value == null || !Number.isFinite(number) ? "—" : `${number > 0 ? "+" : ""}${money(number, digits)}`;
};
const quantity = (value: number | string | null | undefined) => {
  const number = Number(value);
  return value == null || !Number.isFinite(number) ? "—" :
    new Intl.NumberFormat("en-US", { maximumFractionDigits: 9 }).format(number);
};
const clock = (value: string | null | undefined) => value && !Number.isNaN(Date.parse(value)) ?
  new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC" })
    .format(new Date(value)) : "—";
const fullTime = (value: string | null | undefined) => value && !Number.isNaN(Date.parse(value)) ?
  new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "medium", timeZone: "UTC" })
    .format(new Date(value)) + " UTC" : "—";
const tone = (value: number | null) => value == null ? "" : value > 0 ? "positive" : value < 0 ? "negative" : "";

function shortReason(order: PaperOrder, decision: Record<string, string> | null): string {
  const quote = quoteEvidence(decision);
  if (!quote) return reasonForOrder(order, decision);
  const crossed = quote.direction === "up" ? "prior ask" : "prior bid";
  // GUESS: # UNCALIBRATED GUESS — three displayed bps decimals are for scan readability only.
  return `Quote crossed ${crossed} by ${quote.triggerMoveBps.toFixed(3)} bps`;
}

function OrderInspector({ order, fills, telemetry }: { order: PaperOrder | undefined; fills: PaperFill[];
  telemetry: PaperTelemetry }) {
  if (!order) return <div className="inspect-empty">No order in this selection.</div>;
  const executed = orderFillSummary(order, fills);
  const decision = decisionForOrder(order, telemetry.journal, telemetry.decisionHistory);
  const quote = quoteEvidence(decision);
  // GUESS: # UNCALIBRATED GUESS — keep the latest four broker events in the inspector for scanability.
  const evidence = telemetry.journal.filter((event) => event.message.includes(order.clientOrderId)
    && /^(SEND|ACK|reconcile|REJECTED|UNCERTAIN|HALT) /.test(event.message)).slice(-4);
  return <div className="inspector-body">
    <div className="inspector-head"><span className={`side-pill ${order.side}`}>{order.side === "buy" ? "ENTRY · BUY" : "EXIT · SELL"}</span>
      <span className={`status-word ${order.status}`}>{orderDisplayStatus(order)}</span></div>
    <p className="inspect-time">{fullTime(executed.lastAt ?? order.submittedAt)}</p>
    <div className="inspect-stats">
      <div><small>Filled value</small><strong>{money(executed.notional)}</strong></div>
      <div><small>Average fill</small><strong>{money(executed.averagePrice)}</strong></div>
      <div><small>Quantity</small><strong>{quantity(executed.quantity)} {assetUnit(order.symbol)}</strong></div>
      <div><small>Broker fills</small><strong>{executed.fillCount}</strong></div>
    </div>
    <section className="reason-card" aria-label="Order reason">
      <span className="eyebrow">WHY IT TRADED</span>
      <h3>{reasonForOrder(order, decision)}</h3>
      {quote ? <>
        <div className="quote-grid"><div><small>Earlier bid / ask</small><strong>{money(quote.referenceBid)} / {money(quote.referenceAsk)}</strong></div>
          <div><small>Trigger bid / ask</small><strong>{money(quote.currentBid)} / {money(quote.currentAsk)}</strong></div></div>
        {/* GUESS: # UNCALIBRATED GUESS — three displayed bps decimals are for scan readability only. */}
        <p className="trigger-line">{quote.direction === "up" ? "Upward" : "Downward"} cross · {quote.triggerMoveBps.toFixed(3)} bps
          {decision?.receive_to_decision_ms ? ` · ${decision.receive_to_decision_ms} ms local decision` : ""}</p>
      </> : decision?.policy === "trend_candle_confluence_v1" ? <>
        <div className="quote-grid"><div><small>Frame / signal candle</small><strong>{decision.frame} · {fullTime(decision.signal_bar)}</strong></div>
          <div><small>Candle pattern</small><strong>{decision.candle_shapes?.replaceAll("_", " ") || "Exit of existing ticket"}</strong></div>
          <div><small>EMA20 / EMA50</small><strong>{quantity(decision.ema20)} / {quantity(decision.ema50)}</strong></div>
          <div><small>Trigger bid / ask</small><strong>{money(decision.trigger_bid, 6)} / {money(decision.trigger_ask, 6)}</strong></div>
          <div><small>Entry invalidation</small><strong>{money(decision.invalidation_level, 6)}</strong></div>
          <div><small>Winning probability</small><strong>Not calibrated</strong></div></div>
        <p className="trigger-line">Paper experiment. Exit at the entry candle low or falling EMA trend on its origin frame.
          The invalidation exit is monitored locally; no resting broker stop.</p>
      </> : <p className="trigger-line">Exact quote evidence was not retained for this order.</p>}
      <p className="policy-line">{decision?.policy ?? "Policy trace unavailable"}
        {decision?.trend ? ` · bar context: ${decision.trend}` : ""}
        {decision?.trend && decision.policy === "quote_cross_30s_v1" ? " (descriptive only)" : ""}</p>
    </section>
    {order.status === "canceled" && executed.quantity > 0 &&
      <p className="partial-note">Partial execution. The broker canceled the unfilled remainder.</p>}
    {order.status === "canceled" && executed.quantity === 0 &&
      <p className="partial-note">No fill. This canceled attempt did not create a position.</p>}
    <details className="broker-trace"><summary>Broker event trace</summary>
      {evidence.length ? evidence.map((event) => <p key={`${event.at}-${event.message}`}><time>{clock(event.at)}</time>
        {event.message.replace(order.clientOrderId, "this order")}</p>) : <p>No retained broker event rows for this order.</p>}
      <code>{order.clientOrderId}</code>
    </details>
  </div>;
}

export default function Home() {
  const [data, setData] = useState<Live | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<SideFilter>("trades");
  const [showAll, setShowAll] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch("/api/live", { cache: "no-store" });
        if (!response.ok) throw new Error(`Monitor API returned ${response.status}`);
        const incoming = await response.json() as Live;
        if (active) { setData(incoming); setError(null); }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Monitor unavailable");
      }
    };
    void load();
    // GUESS: # UNCALIBRATED GUESS — refresh the visible snapshot every 15s.
    const timer = window.setInterval(() => void load(), 15_000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const t = data?.telemetry ?? null;
  const orders = useMemo(() => t ? botOrders(t) : [], [t]);
  const fills = useMemo(() => t ? botFills(t) : [], [t]);
  const executions = useMemo(() => t ? botExecutions(t) : [], [t]);
  const accounting = useMemo(() => t ? botAccounting(t) : null, [t]);
  const displayedBotResult = accounting?.markedResultAfterPostedFees ?? accounting?.markedResult ?? null;
  const hasPostedFeeResult = accounting?.markedResultAfterPostedFees != null;
  const filtered = filter === "attempts" ? orders : executions.map(({ order }) => order)
    .filter((order) => filter === "trades" || order.side === filter);
  // GUESS: # UNCALIBRATED GUESS — ten initial rows keep the latest fills scannable.
  const visible = showAll ? filtered : filtered.slice(0, 10);
  const selected = visible.find((order) => order.id === selectedId) ?? visible[0];
  const positions = t?.positions.filter((position) => !position.protected && cryptoSymbol(position.symbol)) ?? [];
  const positionMark = positions.every((position) => position.marketValue != null &&
    Number.isFinite(Number(position.marketValue))) ?
    positions.reduce((total, position) => total + Number(position.marketValue), 0) : null;
  // GUESS: # UNCALIBRATED GUESS — warn after two one-minute broker sync cycles.
  const snapshotFreshnessMs = 2 * 60_000;
  const snapshotAge = t ? Date.now() - Date.parse(t.generatedAt) : Infinity;
  const fresh = !!t && snapshotAge >= 0 && snapshotAge < snapshotFreshnessMs;
  const healthy = !!t && fresh && t.service.active && t.capture?.active;
  const buyCount = executions.filter(({ order }) => order.side === "buy").length;
  const sellCount = executions.filter(({ order }) => order.side === "sell").length;
  const lastExecution = executions[0]?.fill.lastAt ?? null;
  // SOURCE: ISO 8601 date-time begins with its YYYY-MM-DD calendar date.
  const snapshotDay = t?.generatedAt.slice(0, 10) ?? null;
  const ordersOnSnapshotDay = orders.filter((order) => order.submittedAt?.slice(0, 10) === snapshotDay).length;

  return <main className="dashboard">
    <header className="topbar">
      <a className="brand" href="#top" aria-label="AI OCaml Bot home">
        <span className="brand-mark">OC</span>
        <span><strong>AI OCaml Bot</strong><small>Independent execution research</small></span>
      </a>
      <div className="topbar-right"><span className="venue-tag">CRYPTO / USD <i>ALPACA PAPER</i></span>
        <span className={`health ${healthy ? "healthy" : "unhealthy"}`}><i />
          {healthy ? "FEED LIVE" : !fresh ? "STALE SNAPSHOT" : "CHECK SERVICE"}</span></div>
    </header>

    <div className="monitor-meta" id="top">
      <div><span className="eyebrow">PAPER EXECUTION MONITOR</span>
        <p>Bot-owned crypto · Protected stocks and unrelated account holdings are excluded.</p></div>
      <div className="snapshot-time"><span>LAST BROKER SNAPSHOT</span><strong>{fullTime(t?.generatedAt)}</strong>
        <small>Broker sync 60s · display refresh 15s · UTC</small></div>
    </div>

    {error && <div className="alert">{error}. Showing the last successful snapshot.</div>}
    {!t && !error && <div className="loading">Loading signed broker data…</div>}
    {t && <>
      {!fresh && <div className="stale-alert"><b>Snapshot is stale.</b> The last broker data is from {fullTime(t.generatedAt)}; do not use it as a current position or account state.</div>}

      <section className="overview-grid" aria-label="Bot performance and position">
        <div className="pnl-panel">
          <div className="panel-topline"><span className="eyebrow">BOT PAPER RESULT · ALL TRADED CRYPTO</span>
            <span className="verification-badge">{hasPostedFeeResult ? "PROVISIONAL · POSTED FEES" : "FEES NOT INCLUDED"}</span></div>
          <strong className={`pnl-value ${tone(displayedBotResult)}`}>
            {accounting?.available ? signedMoney(displayedBotResult) : "—"}</strong>
          <p className="pnl-label">{hasPostedFeeResult ? "Fill cash flow + crypto marks + posted USD fees" : "Fill cash flow + crypto marks · before fees"}</p>
          <div className="pnl-breakdown"><div><span>Fill cash flow</span><b>{accounting?.available ? signedMoney(accounting.cashDifference) : "—"}</b></div>
            <div><span>Open crypto marks</span><b>{accounting?.available ? signedMoney(accounting.marketValue) : "—"}</b></div>
            <div><span>Posted USD fees</span><b>{accounting?.available && accounting.postedUsdFees != null ? signedMoney(accounting.postedUsdFees) : "—"}</b></div></div>
          <p className="pnl-note">Provisional marked result, not realized P&amp;L. Fees can post later. Other account holdings are excluded from this bot view.</p>
          <details className="pnl-audit"><summary>Calculation and fee reconciliation</summary>
            {accounting?.available && hasPostedFeeResult ? <>
              <p>{money(accounting.sellNotional)} sells − {money(accounting.buyNotional)} buys + {money(accounting.marketValue)} open crypto marks + {signedMoney(accounting.postedUsdFees)} posted USD crypto fees = {signedMoney(accounting.markedResultAfterPostedFees)}.</p>
              <p>{accounting.feeActivityRows} posted fee activities · fetched {fullTime(t.cryptoFees?.fetchedAt)}. Fees debited in crypto are already reflected in broker inventory and are not subtracted twice.</p>
              <p>Quantity residuals, each in its own asset: {Object.entries(accounting.quantityResiduals).map(([symbol, residual]) =>
                `${assetUnit(symbol)} ${quantity(residual)}`).join(" · ")}. Same-day fees may still post; starting inventory and closed lots are not fully reconciled.</p>
            </> : <p>Complete, attributable broker fee activity is not available in this snapshot; the result cannot yet include posted crypto fees.</p>}
          </details>
        </div>

        <div className="position-panel">
          <div className="panel-topline"><span className="eyebrow">OPEN POSITIONS</span>
            <span className={`position-state ${positions.length ? "is-open" : ""}`}>{positions.length ? `${positions.length} OPEN` : "FLAT"}</span></div>
          <strong className="position-value">{money(positionMark)}</strong>
          <span className="position-sub">Broker market value · actual filled quantities</span>
          <div className="open-position-list">{positions.map((position) => {
            const ticket = t.multiPaper?.activeTickets.find((item) => item.symbol === cryptoSymbol(position.symbol));
            return <div key={position.symbol}><span><b>{cryptoSymbol(position.symbol)}</b><small>{quantity(position.qty)} {assetUnit(position.symbol)} · {ticket?.frame ?? "legacy quote rule"}</small></span>
              <span><b>{money(position.marketValue)}</b><small className={tone(Number(position.unrealizedPl))}>{signedMoney(position.unrealizedPl)} unrealized</small></span></div>;
          })}{!positions.length && <p>No bot crypto exposure.</p>}</div>
        </div>
      </section>

      <section className="stat-strip" aria-label="Execution summary">
        <div><span>ORDERS WITH FILLS · ALL TIME</span><strong>{executions.length}</strong><small>{fills.length} broker fill rows</small></div>
        <div><span>ORDERS SUBMITTED · {snapshotDay} UTC</span><strong>{ordersOnSnapshotDay}</strong><small>Broker snapshot day, not a live counter</small></div>
        <div><span>ENTRIES / EXITS</span><strong>{buyCount} <i>/</i> {sellCount}</strong></div>
        <div><span>LAST EXECUTION</span><strong className="last-time">{fullTime(lastExecution)}</strong></div>
      </section>

      <details className="policy-note"><summary>Execution: <b>BTC quote rule</b> · multi-frame crypto experiment <b>{t.multiPaper?.mode !== "PAPER_EXPERIMENT" ? "OBSERVE" : t.multiPaper.newEntriesEnabled === false ? "EXITS ONLY" : "ARMED"}</b></summary>
        {t.multiPaper?.newEntriesEnabled === false && <p>New crypto confluence entries are paused. Owned positions retain exit checks and pending-order reconciliation. Research now focuses on stocks, index proxies, FX-like contracts and energy. Their broker execution adapter is not connected yet.</p>}
        <p>BTC keeps its original quote-cross rule and $500 exposure ceiling. The new experiment uses rising EMA trend plus a bullish candle pattern on 1m, 5m, 30m, 1h or 4h,
          with one position per symbol, $100 entry target and ten experimental tickets maximum. That ticket limit is an uncalibrated operational choice.
          Alpaca crypto is long only. Hyperliquid perps and listed equity rows remain analysis only. Neither rule has demonstrated an after-fee edge; paper fills do not establish live profitability.</p>
        {t.multiPaper && <p>Router checked {fullTime(t.multiPaper.asOf)} · {t.multiPaper.eligibleLongSignals} fresh long signals.
          {t.multiPaper.abstentions.length > 0 && ` ${t.multiPaper.abstentions.map((item) => `${item.symbol}: ${item.reason}`).join("; ")}`}</p>}
      </details>

      <section className="history-layout" id="orders" aria-label="Broker execution history">
        <div className="history-panel">
          <div className="history-heading"><div><span className="eyebrow">ALPACA PAPER · BROKER FILLS</span>
            <h1>Execution history</h1><p>One row per order. Partial fills are grouped; canceled attempts without fills are filtered out by default.</p></div>
            <span className="history-total">{executions.length} ORDERS WITH FILLS</span></div>
          <div className="filter-row" role="group" aria-label="Filter order history">
            {(["trades", "buy", "sell", "attempts"] as SideFilter[]).map((side) => <button key={side} type="button"
              className={filter === side ? "selected" : ""} onClick={() => { setFilter(side); setShowAll(false); setSelectedId(null); }}>
              {side === "trades" ? "Executions" : side === "buy" ? "Entries" : side === "sell" ? "Exits" : "Attempts"}</button>)}
            <span>{filtered.length} rows</span></div>
          <div className="order-list">{visible.map((order) => {
            const executed = orderFillSummary(order, fills);
            const decision = decisionForOrder(order, t.journal, t.decisionHistory);
            return <button type="button" key={order.id} className={`order-row ${selected?.id === order.id ? "active" : ""}`}
              onClick={() => { setSelectedId(order.id); document.getElementById("trade-detail")?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }}
              aria-pressed={selected?.id === order.id}>
              <span className={`order-side ${order.side}`}>{order.side === "buy" ? "BUY" : "SELL"}</span>
              <span className="order-main"><strong>{order.side === "buy" ? "Entry" : "Exit"} · {cryptoSymbol(order.symbol)}{decision?.frame ? ` · ${decision.frame}` : ""}</strong>
                <small>{shortReason(order, decision)}</small></span>
              <span className="order-amount"><strong>{executed.fillCount ? money(executed.notional) : "No fill"}</strong>
                <small>{executed.fillCount ? `${quantity(executed.quantity)} ${assetUnit(order.symbol)} · ${money(executed.averagePrice, 6)}` : orderDisplayStatus(order)}</small></span>
              <span className="order-status"><b className={order.status === "canceled" ? "cancelled" : ""}>{orderDisplayStatus(order)}</b>
                <time>{fullTime(executed.lastAt ?? order.submittedAt)}</time></span>
            </button>;
          })}{!visible.length && <p className="empty">No orders in this filter.</p>}</div>
          {filtered.length > 10 && <button type="button" className="show-more" onClick={() => setShowAll(!showAll)}>
            {showAll ? "Show latest 10" : `Show all ${filtered.length} rows`}</button>}
        </div>
        <aside className="inspector-panel" id="trade-detail" aria-label="Selected order details">
          <div className="inspector-heading"><span className="eyebrow">SELECTED ORDER</span><h2>Decision &amp; fills</h2></div>
          <OrderInspector order={selected} fills={fills} telemetry={t} />
        </aside>
      </section>

      <MarketRadar pipeline={t.marketPipeline} experiment={t.multiPaper} />

      <footer><span>Independent project · simulated fills · not affiliated with Alpaca.</span>
        <a href="https://github.com/coder058/ai-ocaml-bot/blob/main/docs/POLICY-ATTEMPTS.md" target="_blank" rel="noreferrer">Policy evidence ↗</a></footer>
    </>}
  </main>;
}
