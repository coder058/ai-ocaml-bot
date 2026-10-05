"use client";

import { useEffect, useRef, useState } from "react";
import type { ExecutionView } from "@/lib/execution-view";
import { TRACE_FRAMES } from "@/lib/execution-view";

const stamp = (at: string | null) => at ? new Date(at).toLocaleString("en-GB", { timeZone: "UTC" }) + " UTC" : "Unavailable";
const money = (v: number | null) => v == null || !Number.isFinite(v) ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(v);

export default function ExecutionDesk() {
  const [view, setView] = useState<ExecutionView | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [route, setRoute] = useState("all");
  const [candidates, setCandidates] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const pathPanel = useRef<HTMLElement>(null);
  useEffect(() => { if (selected) pathPanel.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [selected]);
  useEffect(() => {
    let mounted = true, busy = false;
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const response = await fetch("/api/execution", { cache: "no-store" });
        if (!response.ok) throw new Error("Unavailable");
        const data = await response.json();
        if (mounted) { setView(data.telemetry); setError(data.telemetry ? "" : "Execution snapshot unavailable."); }
      } catch { if (mounted) setError("Execution connection interrupted. The last snapshot remains visible with its original timestamp."); }
      finally { busy = false; }
    };
    void refresh();
    // SOURCE: same 15-second UI cadence as the current positions monitor.
    const timer = setInterval(refresh, 15_000);
    return () => { mounted = false; clearInterval(timer); };
  }, []);
  const rows = (view?.rows ?? []).filter(r => `${r.symbol} ${r.venue} ${r.category}`.toLowerCase().includes(query.toLowerCase()) &&
    (route === "all" || r.route === route) && (!candidates || r.candidate));
  const groups = [...new Set(rows.map(r => `${r.venue}|${r.symbol}`))].map(key => rows.filter(r => `${r.venue}|${r.symbol}` === key));
  const detail = view?.rows.find(r => r.id === selected);
  return <section className="execution-workspace" id="execution">
    <div className="chart-wall-heading"><div><span className="eyebrow">DATA → POLICY → RISK → PAPER BROKER</span><h2>Analysis &amp; execution</h2>
      <p>Every frame has a route and a reason. Select a cell to inspect the recorded evidence.</p></div>
      <div className="snapshot-time"><span>Analysis close / retrieval</span><strong>{stamp(view?.analysisAsOf ?? null)}</strong><small>{stamp(view?.retrievedAt ?? null)}</small></div></div>
    {error && <p className="alert" role="status">{error}</p>}
    {!view && !error && <p className="loading">Checking execution coverage…</p>}
    {view && <>
      <div className="execution-summary"><article><span>Instruments / frames</span><strong>{view.symbols} / {view.frames}</strong></article>
        <article><span>Current candle candidates</span><strong>{view.candidates}</strong><small>Not orders or calibrated probabilities</small></article>
        <article><span>New cohort broker orders</span><strong>{view.orders.length}</strong><small>{view.orders.filter(o => Number(o.brokerFilledQty) > 0).length} with a reported fill</small></article></div>
      <p className="execution-note">{view.explanation}</p>
      <div className="route-summary">{Object.entries(view.routeCounts).map(([name, count]) => <button key={name} type="button" aria-pressed={route === name} onClick={() => setRoute(route === name ? "all" : name)}><strong>{count}</strong><span>{name}</span></button>)}</div>
      <div className="coverage-strip">{Object.entries(view.dataCounts).map(([state, count]) => <span key={state}>{count} {state.replaceAll("_", " ")}</span>)}</div>
      {view.fx && !view.fx.connected && <p className="execution-note">Spot FX connection: {view.fx.reason.replaceAll("_", " ")}. Hyperliquid FX-like products are public analysis; no spot-FX paper execution is implied.</p>}
      <details className="cohort-order" aria-label="Quote reference research audit"><summary><strong>Pattern policy validation</strong><span>Not validated for execution</span><small>{view.quoteAudit ? `${view.quoteAudit.labelCount} quote references · dated research snapshot` : "Quote research unavailable"}</small></summary>
        <div className="cohort-detail">{view.quoteAudit ? <>
          <p>Report: {stamp(view.quoteAudit.generatedAt)}. {view.quoteAudit.discovery} discovery / {view.quoteAudit.validation} later-fold references; {view.quoteAudit.comparisonCount} exploratory pattern comparisons. Related frames overlap; these are not independent trades.</p>
          <dl><div><dt>Missing fresh first entry quotes</dt><dd>{view.quoteAudit.missingEntryQuotes ?? "Unknown"}</dd></div><div><dt>No timely fresh exit</dt><dd>{view.quoteAudit.missingExitQuotes ?? "Unknown"}</dd></div><div><dt>Frozen reference horizon / exit lag limit</dt><dd>{view.quoteAudit.horizonBars} frame duration / {view.quoteAudit.maxExitLagSeconds}s · uncalibrated research choices</dd></div></dl>
          {view.quoteAudit.discovery===0 && <p className="alert">No quote-aware discovery sample. This later fold cannot validate a previously selected quote policy.</p>}
        </> : <p>No checked, dated quote-reference report is available. Candle counts alone cannot justify an execution policy.</p>}
          <p className="execution-note">Reference asks/bids are not broker fills or guaranteed executable prices. No calibrated winning probability, allocated broker P&amp;L or policy promotion is inferred. Paper/reference results do not establish live profitability.</p>
        </div></details>
      <div className="chart-filters"><label>Find instrument<input aria-label="Execution instrument search" value={query} onChange={e => setQuery(e.target.value)} placeholder="ETH, QQQ, energy, EUR…" /></label>
        <label>Execution route<select aria-label="Execution route" value={route} onChange={e => setRoute(e.target.value)}><option value="all">All routes</option>{Object.keys(view.routeCounts).map(name => <option key={name}>{name}</option>)}</select></label>
        <label className="execution-toggle"><input type="checkbox" checked={candidates} onChange={e => setCandidates(e.target.checked)} /> Candle candidates only</label><strong>{rows.length} / {view.frames} frames</strong></div>
      {detail && <article ref={pathPanel} className="decision-path" aria-label="Selected frame decision path"><header><div><span className="eyebrow">FACTUAL DECISION PATH</span><h3>{detail.symbol} · {detail.frame}</h3><p>{detail.venue} · last closed bar start {stamp(detail.bar)}</p></div><button type="button" onClick={() => setSelected(null)} aria-label="Close decision path">Close</button></header>
        <ol>{detail.steps.map(step => <li key={step.stage} className={`trace-${step.state}`}><div><strong>{step.stage}</strong><span>{step.state}</span></div><p>{step.detail}</p></li>)}</ol>
        <p className="execution-note">This is a current-state audit. It does not reconstruct an earlier trade or claim that unperformed checks passed.</p></article>}
      <div className="execution-matrix table-scroll"><table><caption>All instruments × five timeframes · click a cell for its decision path</caption><thead><tr><th>Instrument / route</th>{TRACE_FRAMES.map(frame => <th key={frame}>{frame}</th>)}</tr></thead><tbody>{groups.map(group => <tr key={`${group[0].venue}|${group[0].symbol}`}><th><strong>{group[0].symbol}</strong><small>{group[0].venue}</small><span>{group[0].route}</span></th>{TRACE_FRAMES.map(frame => {
        const r = group.find(row => row.frame === frame);
        return <td key={frame}>{r ? <button type="button" aria-label={`Inspect ${r.venue} ${r.symbol} ${frame}`} aria-pressed={selected === r.id} onClick={() => setSelected(r.id)}><b className={`frame-state ${r.dataState}`}>{r.dataState.replaceAll("_", " ")}</b><small>{r.candidate ? `${r.candidate} candidate` : "No candle candidate"}</small></button> : <span className="filtered-frame">Filtered</span>}</td>;
      })}</tr>)}</tbody></table>{!rows.length && <p className="empty">No frames match these filters.</p>}</div>
      <section className="new-order-cohort" id="orders"><div className="section-heading"><div><span className="eyebrow">EXACT BROKER ORDER / DURABLE DECISION JOIN</span><h3>New paper orders</h3></div><span>Since {stamp(view.traceStart)}</span></div>
        <p className="execution-note">Broker order snapshot: {stamp(view.generatedAt)}. Analysis has its own retrieval timestamp above.</p>
        <p className="execution-note">The earlier history reset is preserved. These orders start a new, explicitly dated cohort. Accepted, canceled and partial orders are not counted as completed trades.</p>
        <div className="execution-summary"><article><span>Matched exit groups</span><strong>{view.cohortAccounting.matchedExitGroups ?? "Unavailable"}</strong><small>Entry and exit both in this dated cohort</small></article>
          <article><span>Closed-lot P&amp;L · before costs</span><strong>{money(view.cohortAccounting.grossRealized)}</strong><small>Gross FIFO matches · excludes open positions</small></article>
          <article><span>Net closed-lot P&amp;L</span><strong>Unavailable</strong><small>Posted fees need exact cohort allocation</small></article></div>
        <p className="execution-note">{view.cohortAccounting.available ? `Partial exits can form multiple entry/exit groups; these are not independent round trips. ${view.cohortAccounting.carryInExitGroups} carry-in exit groups excluded. No old trade rows are restored. Gross paper P&L before costs does not demonstrate live profitability.` : view.cohortAccounting.reason}</p>
        {(!view.ordersComplete || !view.fillsComplete) && <p className="alert">Broker order or fill pagination is incomplete. Totals are partial.</p>}
        {view.orders.map(order => <details key={order.id} className="cohort-order"><summary><strong>{order.symbol} · {order.side.toUpperCase()}</strong><span>{order.status}</span><b>{order.request.notional!=null && <>{money(order.request.notional)} requested · </>}{money(order.fill.notional)} filled</b><small>{stamp(order.submittedAt)}</small></summary>
          <div className="cohort-detail"><p>{order.reason}</p><dl><div><dt>Requested value · {order.request.basis}</dt><dd>{money(order.request.notional)}</dd></div><div><dt>Broker requested / filled quantity</dt><dd>{order.request.quantity ?? "Unavailable"} / {order.brokerFilledQty}</dd></div><div><dt>Captured fills / average</dt><dd>{order.fill.fillCount} / {money(order.fill.averagePrice)}</dd></div><div><dt>Durable client order ID</dt><dd>{order.clientOrderId}</dd></div></dl>
            {order.evidence ? <><p className="execution-note">{order.evidencePrecision}</p><dl className="recorded-evidence">{Object.entries(order.evidence).filter(([name])=>name!=="preflight_evidence").map(([name, value]) => <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd>{value}</dd></div>)}</dl>
              {order.preflight ? <><h4>Recorded pre-submit checks</h4><p className="execution-note">Observed {order.preflight.observedAt.replace("T"," ")}. Facts from this order's retained intent; current chart values are separate.</p><dl className="recorded-evidence">{order.preflight.facts.map(fact=><div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl></> : <p className="execution-note">Pre-submit risk facts were not retained or their timing could not be verified.</p>}
            </> : <p className="execution-note">No verified pre-submit trace is available. Current chart values will not be used as a substitute.</p>}
            <p className="execution-note">This view has no inferred preflight passes or net trade P&amp;L. Broker fees and matched entry/exit lots are required for net accounting; paper fills do not demonstrate live profitability.</p></div></details>)}
        {!view.orders.length && <p className="empty">No broker orders in this new cohort. Candidate and route blocks are visible above.</p>}
      </section>
    </>}
  </section>;
}
