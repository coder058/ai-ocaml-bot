"use client";

import { useEffect, useMemo, useState } from "react";
import {
  assetUnit,
  marketSymbol,
  botAccounting,
  botFills,
  botOrders,
  decisionForOrder,
  orderDisplayStatus,
  orderFillSummary,
  quoteEvidence,
  reasonForOrder,
} from "@/lib/bot-view";
import type { PaperFill, PaperOrder, PaperTelemetry } from "@/lib/telemetry";
import MarketRadar from "./market-radar";
import type { ClosedTrade } from "@/lib/trade-ledger";
import { tradeLedger, orderPolicy } from "@/lib/trade-ledger";
import type { PerformancePoint } from "@/lib/performance";

type Live = {
  generatedAt: string;
  telemetry: PaperTelemetry | null;
  performance?: PerformancePoint[];
};

const money = (value: number | string | null | undefined, digits = 2) => {
  const number = Number(value);
  return value == null || !Number.isFinite(number)
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(number);
};
// GUESS: # UNCALIBRATED GUESS — up to nine display decimals for sub-dollar prices; no order rounding.
const price = (v: number | string | null | undefined) => {
  const n = Number(v);
  return v == null || !Number.isFinite(n)
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: n < 1 ? 9 : 2,
      }).format(n);
};
const signedMoney = (value: number | string | null | undefined, digits = 2) => {
  const number = Number(value);
  return value == null || !Number.isFinite(number)
    ? "—"
    : `${number > 0 ? "+" : ""}${money(number, digits)}`;
};
const quantity = (value: number | string | null | undefined) => {
  const number = Number(value);
  return value == null || !Number.isFinite(number)
    ? "—"
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: 9 }).format(
        number,
      );
};
const clock = (value: string | null | undefined) =>
  value && !Number.isNaN(Date.parse(value))
    ? new Intl.DateTimeFormat("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZone: "UTC",
      }).format(new Date(value))
    : "—";
const fullTime = (value: string | null | undefined) =>
  value && !Number.isNaN(Date.parse(value))
    ? new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "medium",
        timeZone: "UTC",
      }).format(new Date(value)) + " UTC"
    : "—";
const tone = (value: number | null) =>
  value == null ? "" : value > 0 ? "positive" : value < 0 ? "negative" : "";

function shortReason(
  order: PaperOrder,
  decision: Record<string, string> | null,
): string {
  const quote = quoteEvidence(decision);
  if (!quote) return reasonForOrder(order, decision);
  const crossed = quote.direction === "up" ? "prior ask" : "prior bid";
  // GUESS: # UNCALIBRATED GUESS — three displayed bps decimals are for scan readability only.
  return `Quote crossed ${crossed} by ${quote.triggerMoveBps.toFixed(3)} bps`;
}

function OrderInspector({
  order,
  fills,
  telemetry,
}: {
  order: PaperOrder | undefined;
  fills: PaperFill[];
  telemetry: PaperTelemetry;
}) {
  if (!order)
    return <div className="inspect-empty">No order in this selection.</div>;
  const executed = orderFillSummary(order, fills);
  const decision = decisionForOrder(
    order,
    telemetry.journal,
    telemetry.decisionHistory,
  );
  const quote = quoteEvidence(decision);
  // GUESS: # UNCALIBRATED GUESS — keep the latest four broker events in the inspector for scanability.
  const evidence = telemetry.journal
    .filter(
      (event) =>
        event.message.includes(order.clientOrderId) &&
        /^(SEND|ACK|reconcile|REJECTED|UNCERTAIN|HALT) /.test(event.message),
    )
    .slice(-4);
  return (
    <div className="inspector-body">
      <div className="inspector-head">
        <span className={`side-pill ${order.side}`}>
          {order.side === "buy" ? "ENTRY · BUY" : "EXIT · SELL"}
        </span>
        <span className={`status-word ${order.status}`}>
          {orderDisplayStatus(order)}
        </span>
      </div>
      <p className="inspect-time">
        {fullTime(executed.lastAt ?? order.submittedAt)}
      </p>
      <div className="inspect-stats">
        <div>
          <small>Filled value</small>
          <strong>{money(executed.notional)}</strong>
        </div>
        <div>
          <small>Average fill</small>
          <strong>{money(executed.averagePrice)}</strong>
        </div>
        <div>
          <small>Quantity</small>
          <strong>
            {quantity(executed.quantity)} {assetUnit(order.symbol)}
          </strong>
        </div>
        <div>
          <small>Broker fills</small>
          <strong>{executed.fillCount}</strong>
        </div>
      </div>
      <section className="reason-card" aria-label="Order reason">
        <span className="eyebrow">WHY IT TRADED</span>
        <h3>{reasonForOrder(order, decision)}</h3>
        {quote ? (
          <>
            <div className="quote-grid">
              <div>
                <small>Earlier bid / ask</small>
                <strong>
                  {money(quote.referenceBid)} / {money(quote.referenceAsk)}
                </strong>
              </div>
              <div>
                <small>Trigger bid / ask</small>
                <strong>
                  {money(quote.currentBid)} / {money(quote.currentAsk)}
                </strong>
              </div>
            </div>
            {/* GUESS: # UNCALIBRATED GUESS — three displayed bps decimals are for scan readability only. */}
            <p className="trigger-line">
              {quote.direction === "up" ? "Upward" : "Downward"} cross ·{" "}
              {quote.triggerMoveBps.toFixed(3)} bps
              {decision?.receive_to_decision_ms
                ? ` · ${decision.receive_to_decision_ms} ms local decision`
                : ""}
            </p>
          </>
        ) : decision?.policy === "trend_candle_confluence_v1" ? (
          <>
            <div className="quote-grid">
              <div>
                <small>Frame / signal candle</small>
                <strong>
                  {decision.frame} · {fullTime(decision.signal_bar)}
                </strong>
              </div>
              <div>
                <small>Candle pattern</small>
                <strong>
                  {decision.candle_shapes?.replaceAll("_", " ") ||
                    "Exit of existing ticket"}
                </strong>
              </div>
              <div>
                <small>EMA20 / EMA50</small>
                <strong>
                  {quantity(decision.ema20)} / {quantity(decision.ema50)}
                </strong>
              </div>
              <div>
                <small>Trigger bid / ask</small>
                <strong>
                  {money(decision.trigger_bid, 6)} /{" "}
                  {money(decision.trigger_ask, 6)}
                </strong>
              </div>
              <div>
                <small>Entry invalidation</small>
                <strong>{money(decision.invalidation_level, 6)}</strong>
              </div>
              <div>
                <small>Winning probability</small>
                <strong>Not calibrated</strong>
              </div>
            </div>
            <p className="trigger-line">
              Paper experiment. Exit at the entry candle low or falling EMA
              trend on its origin frame. The invalidation exit is monitored
              locally; no resting broker stop.
            </p>
          </>
        ) : (
          <p className="trigger-line">
            Exact quote evidence was not retained for this order.
          </p>
        )}
        <p className="policy-line">
          {decision?.policy ?? "Policy trace unavailable"}
          {decision?.trend ? ` · bar context: ${decision.trend}` : ""}
          {decision?.trend && decision.policy === "quote_cross_30s_v1"
            ? " (descriptive only)"
            : ""}
        </p>
      </section>
      {order.status === "canceled" && executed.quantity > 0 && (
        <p className="partial-note">
          Partial execution. The broker canceled the unfilled remainder.
        </p>
      )}
      {order.status === "canceled" && executed.quantity === 0 && (
        <p className="partial-note">
          No fill. This canceled attempt did not create a position.
        </p>
      )}
      <details className="broker-trace">
        <summary>Broker event trace</summary>
        {evidence.length ? (
          evidence.map((event) => (
            <p key={`${event.at}-${event.message}`}>
              <time>{clock(event.at)}</time>
              {event.message.replace(order.clientOrderId, "this order")}
            </p>
          ))
        ) : (
          <p>No retained broker event rows for this order.</p>
        )}
        <code>{order.clientOrderId}</code>
      </details>
    </div>
  );
}

// GUESS: # UNCALIBRATED GUESS — pagination is a presentation choice, not a trading threshold.
const PAGE_SIZE = 20;
// GUESS: # UNCALIBRATED GUESS — show five recent partial closures on the overview.
const RECENT_CLOSURES = 5;
type View =
  "Overview" | "Closed trades" | "Orders & fills" | "Markets" | "Connections";
function ClosedCards({
  rows,
  onInspect,
}: {
  rows: ClosedTrade[];
  onInspect: (id: string) => void;
}) {
  return (
    <div className="mobile-history">
      {rows.map((c) => (
        <article key={c.id}>
          <div>
            <strong>{c.symbol}</strong>
            <b className={tone(c.grossPnl)}>
              {signedMoney(c.grossPnl, 4)} gross
            </b>
          </div>
          <p>Closed {fullTime(c.exitAt)}</p>
          <dl>
            <div>
              <dt>Quantity</dt>
              <dd>{quantity(c.quantity)}</dd>
            </div>
            <div>
              <dt>Entry → exit</dt>
              <dd>
                {price(c.entryPrice)} → {price(c.exitPrice)}
              </dd>
            </div>
          </dl>
          <div>
            <button onClick={() => onInspect(c.entryOrderId)}>
              Entry reason
            </button>
            <button onClick={() => onInspect(c.exitOrderId)}>
              Exit reason
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
function OrderCards({
  orders,
  fills,
  t,
  selected,
  onInspect,
}: {
  orders: PaperOrder[];
  fills: Map<string, PaperFill[]>;
  t: PaperTelemetry;
  selected?: string;
  onInspect: (id: string) => void;
}) {
  return (
    <div className="mobile-history">
      {orders.map((o) => {
        const f = orderFillSummary(o, fills.get(o.id) ?? []);
        const d = decisionForOrder(o, t.journal, t.decisionHistory);
        return (
          <article key={o.id} className={selected === o.id ? "active" : ""}>
            <div>
              <strong>
                {marketSymbol(o.symbol)} ·{" "}
                <span className={o.side === "buy" ? "positive" : "negative"}>
                  {o.side.toUpperCase()}
                </span>
              </strong>
              <b>{money(f.notional)}</b>
            </div>
            <p>
              {fullTime(o.submittedAt)} · {orderDisplayStatus(o)}
            </p>
            <dl>
              <div>
                <dt>Filled quantity / avg price</dt>
                <dd>
                  {quantity(f.quantity)} / {price(f.averagePrice)}
                </dd>
              </div>
              <div>
                <dt>Fills</dt>
                <dd>{f.fillCount}</dd>
              </div>
            </dl>
            <p>{shortReason(o, d)}</p>
            <button
              onClick={() => onInspect(o.id)}
              aria-pressed={selected === o.id}
            >
              Inspect order &amp; fills
            </button>
          </article>
        );
      })}
    </div>
  );
}
function PnlChart({ points }: { points: PerformancePoint[] }) {
  if (points.length < 2)
    return (
      <div className="chart-empty">
        Collecting actual P&amp;L snapshots. The curve starts when this monitor
        is opened; historical points are never invented.
      </div>
    );
  // GUESS: # UNCALIBRATED GUESS — SVG coordinates and padding are visual choices.
  const width = 900,
    height = 170,
    pad = 12;
  const values = points.map((p) => p.markedPnl),
    low = Math.min(...values),
    high = Math.max(...values);
  const first = Date.parse(points[0].at),
    last = Date.parse(points.at(-1)!.at);
  const path = points
    .map(
      (p, i) =>
        `${i ? "L" : "M"}${pad + ((Date.parse(p.at) - first) / (last - first || 1)) * (width - 2 * pad)},${height - pad - ((p.markedPnl - low) / (high - low || 1)) * (height - 2 * pad)}`,
    )
    .join(" ");
  return (
    <div className="pnl-chart">
      <div>
        <span>{signedMoney(high)} high</span>
        <span>{signedMoney(low)} low</span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Actual provisional marked paper P&L over recorded snapshots"
      >
        <path
          d={path}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div>
        <span>{fullTime(points[0].at)}</span>
        <span>{fullTime(points.at(-1)?.at)}</span>
      </div>
    </div>
  );
}
export default function Home() {
  const [data, setData] = useState<Live | null>(null),
    [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("Overview"),
    [symbol, setSymbol] = useState("All instruments"),
    [policy, setPolicy] = useState("All policies");
  const [side, setSide] = useState("Executions"),
    [from, setFrom] = useState(""),
    [to, setTo] = useState("");
  const [page, setPage] = useState(0),
    [selectedId, setSelectedId] = useState<string | null>(null);
  useEffect(() => {
    if (view === "Orders & fills" && selectedId)
      document
        .getElementById("order-detail")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [view, selectedId]);
  useEffect(() => {
    let active = true,
      inflight = false;
    const load = async () => {
      if (inflight) return;
      inflight = true;
      try {
        const response = await fetch("/api/live", { cache: "no-store" });
        if (!response.ok) throw new Error(`Monitor API ${response.status}`);
        const incoming = (await response.json()) as Live;
        if (active) {
          setData(incoming);
          setError(null);
        }
      } catch (e) {
        if (active)
          setError(e instanceof Error ? e.message : "Monitor unavailable");
      } finally {
        inflight = false;
      }
    };
    void load();
    // GUESS: # UNCALIBRATED GUESS — 15 seconds is the visible refresh cadence.
    const timer = window.setInterval(() => void load(), 15_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  const t = data?.telemetry ?? null;
  const orders = useMemo(() => (t ? botOrders(t) : []), [t]),
    fills = useMemo(() => (t ? botFills(t) : []), [t]);
  const accounting = useMemo(() => (t ? botAccounting(t) : null), [t]),
    ledger = useMemo(() => (t ? tradeLedger(t) : null), [t]);
  const symbols = [
    ...new Set(orders.map((o) => marketSymbol(o.symbol)!)),
  ].sort();
  const policies = t
    ? [...new Set(orders.map((o) => orderPolicy(o, t)))].sort()
    : [];
  const byId = new Map(orders.map((o) => [o.id, o]));
  const fillMap = useMemo(() => {
    const map = new Map<string, PaperFill[]>();
    for (const f of fills) {
      const list = map.get(f.orderId) ?? [];
      list.push(f);
      map.set(f.orderId, list);
    }
    return map;
  }, [fills]);
  const matches = (o: PaperOrder, at: string | null) =>
    (symbol === "All instruments" || marketSymbol(o.symbol) === symbol) &&
    (policy === "All policies" || (t && orderPolicy(o, t) === policy)) &&
    (!from || (!!at && at.slice(0, 10) >= from)) &&
    (!to || (!!at && at.slice(0, 10) <= to));
  const filtered = orders.filter(
    (o) =>
      matches(o, o.submittedAt) &&
      (side === "All orders" || side === "Unfilled attempts"
        ? side === "All orders" || !fillMap.has(o.id)
        : fillMap.has(o.id) &&
          (side === "Executions" || o.side === side.toLowerCase())),
  );
  const closed = (ledger?.closed ?? []).filter((c) => {
    const order = byId.get(c.exitOrderId);
    return !!order && matches(order, c.exitAt);
  });
  const rowCount = view === "Closed trades" ? closed.length : filtered.length;
  const safePage = Math.min(
    page,
    Math.max(0, Math.ceil(rowCount / PAGE_SIZE) - 1),
  );
  const selected = selectedId ? byId.get(selectedId) : filtered[0];
  const owned = new Set(["BTC/USD", ...symbols]);
  const positions =
    t?.positions.filter(
      (p) => !p.protected && owned.has(marketSymbol(p.symbol) ?? ""),
    ) ?? [];
  // GUESS: # UNCALIBRATED GUESS — two minutes warns when broker fetch cycles fall behind.
  const fresh =
    !!t &&
    Date.now() - Date.parse(t.generatedAt) >= 0 &&
    Date.now() - Date.parse(t.generatedAt) < 120_000;
  // GUESS: # UNCALIBRATED GUESS — two minutes is also the per-connection warning,
  // not a measured feed guarantee. Display the source timestamp separately.
  const connectionFresh = (at: string | undefined | null) =>
    !!at &&
    Date.now() - Date.parse(at) >= 0 &&
    Date.now() - Date.parse(at) < 120_000;
  const result = accounting?.markedResultAfterPostedFees ?? null;
  const pending = orders.filter(
    (o) =>
      !["filled", "canceled", "expired", "rejected", "replaced"].includes(
        o.status,
      ),
  );
  const switchView = (v: View) => {
    setView(v);
    setPage(0);
  };
  const filters = (
    <div className="toolbar">
      <label>
        Instrument
        <select
          value={symbol}
          onChange={(e) => {
            setSymbol(e.target.value);
            setPage(0);
            setSelectedId(null);
          }}
        >
          <option>All instruments</option>
          {symbols.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <label>
        Policy
        <select
          value={policy}
          onChange={(e) => {
            setPolicy(e.target.value);
            setPage(0);
            setSelectedId(null);
          }}
        >
          <option>All policies</option>
          {policies.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
      </label>
      {view === "Orders & fills" && (
        <label>
          Order type
          <select
            value={side}
            onChange={(e) => {
              setSide(e.target.value);
              setPage(0);
              setSelectedId(null);
            }}
          >
            {[
              "Executions",
              "Buy",
              "Sell",
              "Unfilled attempts",
              "All orders",
            ].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
      )}
      <label>
        From · UTC
        <input
          type="date"
          value={from}
          onChange={(e) => {
            setFrom(e.target.value);
            setPage(0);
            setSelectedId(null);
          }}
        />
      </label>
      <label>
        To · UTC
        <input
          type="date"
          value={to}
          onChange={(e) => {
            setTo(e.target.value);
            setPage(0);
            setSelectedId(null);
          }}
        />
      </label>
      <button
        onClick={() => {
          setSymbol("All instruments");
          setPolicy("All policies");
          setFrom("");
          setTo("");
          setPage(0);
          setSelectedId(null);
        }}
      >
        Reset
      </button>
      <a
        className="export-link"
        href={`/api/export?${new URLSearchParams({ kind: view === "Closed trades" ? "closed" : "orders", symbol, policy, from, to, side }).toString()}`}
        download
      >
        Export CSV
      </a>
    </div>
  );
  const pager = (
    <div className="pagination">
      <span>
        {rowCount} matching rows · page {safePage + 1} /{" "}
        {Math.max(1, Math.ceil(rowCount / PAGE_SIZE))}
      </span>
      <div>
        <button disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>
          Previous
        </button>
        <button
          disabled={(safePage + 1) * PAGE_SIZE >= rowCount}
          onClick={() => setPage(safePage + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
  return (
    <main className="dashboard">
      <header className="topbar">
        <a className="brand" href="#" onClick={() => switchView("Overview")}>
          <span className="brand-mark">OC</span>
          <span>
            <strong>AI OCaml Bot</strong>
            <small>Paper execution &amp; market research</small>
          </span>
        </a>
        <span className="paper-badge">PAPER · NO LIVE FUNDS</span>
      </header>
      <div className="monitor-meta">
        <div>
          <h1>Trading desk</h1>
          <p>
            Bot-owned positions and broker executions. Unrelated account
            holdings are excluded.
          </p>
        </div>
        <div className="snapshot-time">
          <span className={fresh ? "positive" : "negative"}>
            {fresh ? "Snapshot current" : "Snapshot stale"}
          </span>
          <strong>{fullTime(t?.generatedAt)}</strong>
          <small>UTC · broker fetch + 60s pause · display 15s</small>
        </div>
      </div>
      {error && (
        <div className="alert">{error}. Last good snapshot retained.</div>
      )}
      {!t && (
        <div className="loading">
          Waiting for the broker snapshot over authenticated SSH…
        </div>
      )}
      {t && (
        <>
          {!fresh && (
            <div className="alert">
              Stale broker snapshot. Values below are historical, not current.
            </div>
          )}
          <section className="metric-grid" aria-label="Paper P&L summary">
            <div className="metric main-metric">
              <span>Net marked P&amp;L</span>
              <strong className={tone(result)}>{signedMoney(result)}</strong>
              <small>Provisional · posted USD fees included</small>
            </div>
            <div className="metric">
              <span>Open-position P&amp;L</span>
              <strong className={tone(ledger?.unrealized ?? null)}>
                {signedMoney(ledger?.unrealized)}
              </strong>
              <small>Unrealized · broker cost basis</small>
            </div>
            <div className="metric">
              <span>Realized &amp; posted costs</span>
              <strong className={tone(ledger?.realizedWithPostedCosts ?? null)}>
                {signedMoney(ledger?.realizedWithPostedCosts)}
              </strong>
              <small>Provisional · net marked minus unrealized</small>
            </div>
            <div className="metric">
              <span>Open exposure</span>
              <strong>
                {money(accounting?.available ? accounting.marketValue : null)}
              </strong>
              <small>
                {positions.length} positions · {pending.length} pending orders
              </small>
            </div>
          </section>
          <nav className="desk-tabs" aria-label="Trading desk views">
            {(
              [
                "Overview",
                "Closed trades",
                "Orders & fills",
                "Markets",
                "Connections",
              ] as View[]
            ).map((v) => (
              <button
                key={v}
                aria-current={view === v ? "page" : undefined}
                className={view === v ? "selected" : ""}
                onClick={() => switchView(v)}
              >
                {v}
              </button>
            ))}
          </nav>
          {view === "Overview" && (
            <>
              <section className="panel">
                <div className="section-heading">
                  <div>
                    <h2>Open positions</h2>
                    <p>
                      Actual broker inventory · local exits are not resting stop
                      orders.
                    </p>
                  </div>
                  <span>{positions.length} open</span>
                </div>
                <div className="table-scroll positions-table">
                  <table className="desk-table">
                    <thead>
                      <tr>
                        <th>Instrument</th>
                        <th>Quantity</th>
                        <th>Entry price</th>
                        <th>Current price</th>
                        <th>Exposure</th>
                        <th>Unrealized P&amp;L</th>
                        <th>Exit handling</th>
                      </tr>
                    </thead>
                    <tbody>
                      {positions.map((p) => {
                        const ticket = t.multiPaper?.activeTickets.find(
                          (x) => x.symbol === marketSymbol(p.symbol),
                        );
                        return (
                          <tr key={p.symbol}>
                            <th>
                              {marketSymbol(p.symbol)}
                              <small>Alpaca paper</small>
                            </th>
                            <td>{quantity(p.qty)}</td>
                            <td>{price(p.avgEntryPrice)}</td>
                            <td>{price(p.currentPrice)}</td>
                            <td>{money(p.marketValue)}</td>
                            <td
                              className={tone(
                                p.unrealizedPl == null
                                  ? null
                                  : Number(p.unrealizedPl),
                              )}
                            >
                              {signedMoney(p.unrealizedPl)}
                            </td>
                            <td>
                              {ticket
                                ? `${ticket.frame} · local invalidation ${money(ticket.invalidationLevel)}`
                                : "Legacy quote rule"}
                              <small>
                                {ticket?.pending
                                  ? `Pending ${ticket.pending.side}`
                                  : "No resting stop verified"}
                              </small>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {!positions.length && (
                    <p className="empty">No bot-owned open positions.</p>
                  )}
                </div>
                <div className="mobile-positions">
                  {positions.map((p) => {
                    const ticket = t.multiPaper?.activeTickets.find(
                      (x) => x.symbol === marketSymbol(p.symbol),
                    );
                    return (
                      <article key={p.symbol}>
                        <div>
                          <strong>{marketSymbol(p.symbol)}</strong>
                          <b
                            className={tone(
                              p.unrealizedPl == null
                                ? null
                                : Number(p.unrealizedPl),
                            )}
                          >
                            {signedMoney(p.unrealizedPl)} unrealized
                          </b>
                        </div>
                        <dl>
                          <div>
                            <dt>Quantity</dt>
                            <dd>{quantity(p.qty)}</dd>
                          </div>
                          <div>
                            <dt>Exposure</dt>
                            <dd>{money(p.marketValue)}</dd>
                          </div>
                          <div>
                            <dt>Entry price</dt>
                            <dd>{price(p.avgEntryPrice)}</dd>
                          </div>
                          <div>
                            <dt>Current price</dt>
                            <dd>{price(p.currentPrice)}</dd>
                          </div>
                        </dl>
                        <p>
                          {ticket
                            ? `${ticket.frame} · local invalidation ${price(ticket.invalidationLevel)}`
                            : "Legacy quote exit"}{" "}
                          · no resting stop verified
                        </p>
                      </article>
                    );
                  })}
                  {!positions.length && (
                    <p className="empty">No bot-owned open positions.</p>
                  )}
                </div>
              </section>
              <section className="panel">
                <div className="section-heading">
                  <div>
                    <h2>Marked paper P&amp;L</h2>
                    <p>
                      Actual recorded snapshots · includes posted USD fees ·
                      provisional.
                    </p>
                  </div>
                  <span>{data?.performance?.length ?? 0} samples</span>
                </div>
                <PnlChart points={data?.performance ?? []} />
              </section>
              <section className="panel">
                <div className="section-heading">
                  <div>
                    <h2>Recent closing executions</h2>
                    <p>
                      FIFO matched quantities. Gross P&amp;L before fees;
                      partial closures can span multiple rows.
                    </p>
                  </div>
                  <button onClick={() => switchView("Closed trades")}>
                    Full closed history →
                  </button>
                </div>
                <div className="table-scroll history-table">
                  <ClosedCards
                    rows={closed.slice(0, RECENT_CLOSURES)}
                    onInspect={(id) => {
                      setSelectedId(id);
                      switchView("Orders & fills");
                    }}
                  />
                  <table className="desk-table">
                    <thead>
                      <tr>
                        <th>Instrument</th>
                        <th>Closed at · UTC</th>
                        <th>Quantity</th>
                        <th>Entry → exit</th>
                        <th>Gross P&amp;L</th>
                        <th>Detail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {closed.slice(0, RECENT_CLOSURES).map((c) => (
                        <tr key={c.id}>
                          <th>{c.symbol}</th>
                          <td>{fullTime(c.exitAt)}</td>
                          <td>{quantity(c.quantity)}</td>
                          <td>
                            {price(c.entryPrice)} → {price(c.exitPrice)}
                          </td>
                          <td className={tone(c.grossPnl)}>
                            {signedMoney(c.grossPnl, 4)}
                          </td>
                          <td>
                            <button
                              onClick={() => {
                                setSelectedId(c.exitOrderId);
                                switchView("Orders & fills");
                              }}
                            >
                              Why it exited
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!ledger?.available && (
                  <p className="alert">{ledger?.reason}</p>
                )}
              </section>
              <div className="operating-note">
                Trading: {t.service.active ? t.service.mode : "Stopped"} · BTC
                legacy rule · ETH/SOL confluence{" "}
                {t.multiPaper?.newEntriesEnabled ? "armed" : "exits only"} ·
                stocks/ETF connected, automatic strategy off ·{" "}
                {t.connections?.fx?.connected
                  ? "FX practice data connected"
                  : "FX credentials missing"}
                .
              </div>
            </>
          )}
          {view === "Closed trades" && (
            <section className="panel">
              <div className="section-heading">
                <div>
                  <h2>Closed fill history</h2>
                  <p>
                    FIFO matching of actual broker fills. P&amp;L is before
                    fees, not a settled net return per trade.
                  </p>
                </div>
                <span>{ledger?.closed.length ?? 0} matched closures</span>
              </div>
              {filters}
              {!ledger?.available ? (
                <p className="alert">{ledger?.reason}</p>
              ) : (
                <div className="table-scroll history-table">
                  <ClosedCards
                    rows={closed.slice(
                      safePage * PAGE_SIZE,
                      (safePage + 1) * PAGE_SIZE,
                    )}
                    onInspect={(id) => {
                      setSelectedId(id);
                      switchView("Orders & fills");
                    }}
                  />
                  <table className="desk-table">
                    <thead>
                      <tr>
                        <th>Instrument</th>
                        <th>Entry · UTC</th>
                        <th>Exit · UTC</th>
                        <th>Quantity</th>
                        <th>Entry → exit</th>
                        <th>Gross P&amp;L</th>
                        <th>Reasons</th>
                      </tr>
                    </thead>
                    <tbody>
                      {closed
                        .slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE)
                        .map((c) => (
                          <tr key={c.id}>
                            <th>{c.symbol}</th>
                            <td>{fullTime(c.entryAt)}</td>
                            <td>{fullTime(c.exitAt)}</td>
                            <td>{quantity(c.quantity)}</td>
                            <td>
                              {price(c.entryPrice)} → {price(c.exitPrice)}
                            </td>
                            <td className={tone(c.grossPnl)}>
                              {signedMoney(c.grossPnl, 4)}
                            </td>
                            <td>
                              <button
                                onClick={() => {
                                  setSelectedId(c.entryOrderId);
                                  switchView("Orders & fills");
                                }}
                              >
                                Entry
                              </button>{" "}
                              <button
                                onClick={() => {
                                  setSelectedId(c.exitOrderId);
                                  switchView("Orders & fills");
                                }}
                              >
                                Exit
                              </button>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                  {!closed.length && (
                    <p className="empty">
                      No closed fills match these filters.
                    </p>
                  )}
                </div>
              )}
              {pager}
            </section>
          )}
          {view === "Orders & fills" && (
            <>
              <section className="panel">
                <div className="section-heading">
                  <div>
                    <h2>Orders &amp; fills</h2>
                    <p>
                      Executions are grouped by broker order. Unfilled attempts
                      have no realized trade P&amp;L.
                    </p>
                  </div>
                  <span>{fills.length} broker fills</span>
                </div>
                {filters}
                <div className="table-scroll history-table">
                  <OrderCards
                    orders={filtered.slice(
                      safePage * PAGE_SIZE,
                      (safePage + 1) * PAGE_SIZE,
                    )}
                    fills={fillMap}
                    t={t}
                    selected={selected?.id}
                    onInspect={(id) => setSelectedId(id)}
                  />
                  <table className="desk-table">
                    <thead>
                      <tr>
                        <th>Instrument / side</th>
                        <th>Submitted · UTC</th>
                        <th>Filled value</th>
                        <th>Qty / avg price</th>
                        <th>Broker status</th>
                        <th>Policy / reason</th>
                        <th>Inspect</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered
                        .slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE)
                        .map((o) => {
                          const f = orderFillSummary(
                            o,
                            fillMap.get(o.id) ?? [],
                          );
                          const decision = decisionForOrder(
                            o,
                            t.journal,
                            t.decisionHistory,
                          );
                          return (
                            <tr
                              key={o.id}
                              className={selected?.id === o.id ? "active" : ""}
                            >
                              <th>
                                {marketSymbol(o.symbol)}
                                <small
                                  className={
                                    o.side === "buy" ? "positive" : "negative"
                                  }
                                >
                                  {o.side.toUpperCase()}
                                </small>
                              </th>
                              <td>{fullTime(o.submittedAt)}</td>
                              <td>
                                {money(f.notional)}
                                <small>{f.fillCount} fills</small>
                              </td>
                              <td>
                                {quantity(f.quantity)}
                                <small>{price(f.averagePrice)}</small>
                              </td>
                              <td>{orderDisplayStatus(o)}</td>
                              <td className="reason-cell">
                                {orderPolicy(o, t)}
                                <small>{shortReason(o, decision)}</small>
                              </td>
                              <td>
                                <button
                                  aria-pressed={selected?.id === o.id}
                                  onClick={() => setSelectedId(o.id)}
                                >
                                  Inspect
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                  {!filtered.length && (
                    <p className="empty">No orders match these filters.</p>
                  )}
                </div>
                {pager}
              </section>
              <section className="panel order-detail" id="order-detail">
                <div className="section-heading">
                  <div>
                    <h2>
                      Order detail{" "}
                      {selected ? `· ${marketSymbol(selected.symbol)}` : ""}
                    </h2>
                    <p>
                      Selection stays fixed while new broker snapshots arrive.
                    </p>
                  </div>
                </div>
                <OrderInspector
                  order={selected}
                  fills={selected ? (fillMap.get(selected.id) ?? []) : []}
                  telemetry={t}
                />
                {selected && (
                  <div className="table-scroll">
                    <table className="desk-table">
                      <thead>
                        <tr>
                          <th>Fill time · UTC</th>
                          <th>Quantity</th>
                          <th>Price</th>
                          <th>Notional</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(fillMap.get(selected.id) ?? []).map((f) => (
                          <tr key={f.id}>
                            <td>{fullTime(f.transactionTime)}</td>
                            <td>{quantity(f.qty)}</td>
                            <td>{price(f.price)}</td>
                            <td>{money(Number(f.qty) * Number(f.price))}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
          {view === "Markets" && (
            <MarketRadar
              pipeline={t.marketPipeline}
              experiment={t.multiPaper}
            />
          )}
          {view === "Connections" && (
            <>
              <section className="connection-grid">
                {[
                  {
                    title: "Alpaca stocks / ETF",
                    checkedAt: t.connections?.stocks?.asOf,
                    ok: t.connections?.stocks?.connected,
                    description: t.connections?.stocks?.sessionOpen
                      ? "Market session open"
                      : "Market session closed",
                    detail: `${t.connections?.catalog?.stockEtfCount ?? "—"} tradable catalog products · ${t.connections?.catalog?.monitoredStocks?.length ?? 0} scanned · next open ${fullTime(t.connections?.stocks?.nextOpen)}. Automatic strategy off.`,
                  },
                  {
                    title: "Stock real-time feed · IEX",
                    checkedAt: t.connections?.stockStream?.asOf,
                    ok: t.connections?.stockStream?.connected,
                    description: `${t.connections?.stockStream?.symbols?.length ?? 0} subscriptions · ${t.connections?.stockStream?.quoteCount ?? 0} received quotes`,
                    detail: `IEX only, not consolidated NBBO. Last market event: ${fullTime(t.connections?.stockStream?.lastMarketEventAt)}.`,
                  },
                  {
                    title: "Alpaca broker order updates",
                    checkedAt: t.connections?.orderStream?.asOf,
                    ok: t.connections?.orderStream?.connected,
                    description:
                      t.connections?.orderStream?.reason ??
                      "No connection snapshot",
                    detail: `${t.connections?.orderStream?.eventCount ?? 0} streamed lab updates; full REST history remains the reconciliation authority.`,
                  },
                  {
                    title: "Crypto · BTC / ETH / SOL only",
                    checkedAt: t.capture?.lastEventAt,
                    ok: t.capture?.active,
                    description: t.capture?.active
                      ? "Public market capture running"
                      : "Capture not active",
                    detail:
                      "Excluded altcoin positions were wound down. BTC legacy entries remain active; ETH/SOL confluence new entries are paused.",
                  },
                  {
                    title: "Hyperliquid public data",
                    checkedAt: t.marketPipeline?.asOf,
                    ok: !!t.marketPipeline?.markets.some(
                      (m) =>
                        m.venue === "Hyperliquid HIP-3" &&
                        Object.values(m.frames).some(
                          (f) =>
                            f.status === "ready" || f.status === "candidate",
                        ),
                    ),
                    description:
                      "Catalog observed · no mainnet order authority",
                    detail:
                      "FX-like perpetuals, index and commodity contracts are not conventional spot FX accounts. Individual frame freshness appears in Markets.",
                  },
                  {
                    title: "Spot FX · OANDA practice",
                    checkedAt: t.connections?.fx?.asOf,
                    ok: t.connections?.fx?.connected,
                    description: t.connections?.fx?.reason ?? "Not configured",
                    detail:
                      "Practice-only data connector prepared. A demo account/token is required. FX order execution adapter has not been completed.",
                  },
                ].map((c) => (
                  <article className="connection-card" key={c.title}>
                    <span
                      className={
                        c.ok && connectionFresh(c.checkedAt)
                          ? "positive"
                          : "negative"
                      }
                    >
                      {c.ok && connectionFresh(c.checkedAt)
                        ? "CONNECTED / CURRENT"
                        : c.ok
                          ? "STALE HEALTH"
                          : "BLOCKED / UNAVAILABLE"}
                    </span>
                    <h2>{c.title}</h2>
                    <strong>{c.description}</strong>
                    <p>{c.detail}</p>
                    <small>Source checked {fullTime(c.checkedAt)}</small>
                  </article>
                ))}
              </section>
              <section className="panel">
                <div className="section-heading">
                  <div>
                    <h2>Simple pipeline</h2>
                    <p>
                      Provider data → closed candles → OCaml indicators →
                      candidate → ownership &amp; risk → paper broker →
                      reconciled monitor.
                    </p>
                  </div>
                </div>
                <p className="operating-note">
                  Data access does not arm strategies. Stocks and FX strategy
                  development follows connection verification. Polymarket live
                  bets are outside this paper system.
                </p>
              </section>
            </>
          )}
          <details className="accounting-details">
            <summary>Accounting &amp; data audit</summary>
            <p>
              Net marked P&amp;L = sell fills − buy fills + actual open broker
              marks + posted USD crypto fees. Asset-denominated fees are
              reflected in inventory, not subtracted twice. It is provisional:
              fees can post later and quantity reconciliation remains
              incomplete.
            </p>
            <p>
              Fill cash flow{" "}
              {signedMoney(
                accounting?.available ? accounting.cashDifference : null,
              )}{" "}
              · open marks{" "}
              {money(accounting?.available ? accounting.marketValue : null)} ·
              posted USD fees {signedMoney(accounting?.postedUsdFees)}. Fee
              fetch {fullTime(t.cryptoFees?.fetchedAt)}.
            </p>
            <p>
              Orders {t.ordersComplete ? "complete" : "INCOMPLETE"} · fills{" "}
              {t.fillsComplete ? "complete" : "INCOMPLETE"} · decision journal{" "}
              {t.journalComplete ? "complete" : "INCOMPLETE"}. Closed matches
              use exact nine-decimal integer quantities; displayed
              prices/P&amp;L use numeric rounding.
            </p>
            {!accounting?.available && (
              <p className="negative">{accounting?.reason}</p>
            )}
            <p>
              Winning probabilities are not calibrated. Paper fills do not
              establish live profitability. This is not a demonstrated HFT or
              profitable AI strategy.
            </p>
          </details>
        </>
      )}
      <footer>
        <span>AI OCaml Bot · localhost · paper only</span>
        <a
          href="https://github.com/coder058/ai-ocaml-bot"
          target="_blank"
          rel="noreferrer"
        >
          Source &amp; documentation ↗
        </a>
      </footer>
    </main>
  );
}
