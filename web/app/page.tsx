"use client";

import { useEffect, useState } from "react";
import type { PositionsView } from "@/lib/positions-view";
import { marketSymbol } from "@/lib/bot-view";
import ChartWall from "./chart-wall";

type Live = { telemetry: PositionsView | null };
// SOURCE: USD amounts use the currency's two standard display decimals.
const usd = (v: string | number | null | undefined) => v == null || !Number.isFinite(Number(v))
  ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(v));
// SOURCE: preserve broker quantity text instead of introducing display rounding.
const tone = (v: string | number | null | undefined) => v == null ? "" : Number(v) > 0 ? "positive" : Number(v) < 0 ? "negative" : "";
const stamp = (v: string) => new Date(v).toLocaleString("en-GB", { timeZone: "UTC" }) + " UTC";
const sum = (values: (string | null | undefined)[]) => values.every(v => v != null && Number.isFinite(Number(v)))
  ? values.reduce((total, v) => total + Number(v), 0) : null;

export default function Home() {
  const [live, setLive] = useState<Live | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let mounted = true;
    let busy = false;
    async function refresh() {
      if (busy) return;
      busy = true;
      try {
        const response = await fetch("/api/live", { cache: "no-store" });
        if (!response.ok) throw new Error("Snapshot unavailable");
        const data: Live = await response.json();
        if (mounted) { setLive(data); setError(""); }
      } catch {
        if (mounted) setError("Connection interrupted. The last successful snapshot remains visible.");
      } finally { busy = false; }
    }
    void refresh();
    // SOURCE: preserve the monitor's existing 15-second refresh cadence.
    const timer = setInterval(refresh, 15_000);
    return () => { mounted = false; clearInterval(timer); };
  }, []);
  const t = live?.telemetry;
  const positions = t?.positions ?? [];
  const pnl = t ? sum(positions.map(p => p.unrealizedPl)) : null;
  const exposure = t ? sum(positions.map(p => p.marketValue == null ? null : String(Math.abs(Number(p.marketValue))))) : null;
  // GUESS: # UNCALIBRATED GUESS — preserve the existing two-minute snapshot warning.
  const stale = !!t && (Date.now() - Date.parse(t.generatedAt) > 120_000 || Date.parse(t.generatedAt) > Date.now());
  return <main className="positions-reset">
    <header className="topbar">
      <div className="brand"><span className="brand-mark">AI</span><div><strong>AI OCaml Bot</strong><small>Alpaca paper trading</small></div></div>
      <span className="reset-badge">Positions + market charts</span>
    </header>
    <div className="monitor-meta">
      <div><h1>Open positions</h1><p>History cleared from this monitor.</p></div>
      <div className="snapshot-time"><span>Broker snapshot</span><strong>{t ? stamp(t.generatedAt) : "Waiting for data"}</strong><small>{t ? t.service.active ? "Paper service active" : "Paper service stopped" : "Connecting"}</small></div>
    </div>
    {error && <div className="alert" role="status">{error}</div>}
    {stale && <div className="alert" role="status">Snapshot is delayed. Prices and positions may have changed.</div>}
    {!live && <p className="loading">Loading current positions…</p>}
    {live && !t && <p className="alert">Broker snapshot unavailable. Open positions cannot be verified.</p>}
    <section className="metric-grid">
      <article className="metric"><span>Open positions</span><strong>{t ? positions.length : "—"}</strong></article>
      <article className="metric"><span>Open exposure</span><strong>{usd(exposure)}</strong></article>
      <article className="metric"><span>Unrealized P&amp;L</span><strong className={tone(pnl)}>{usd(pnl)}</strong><small>Current positions · broker mark</small></article>
    </section>
    {t && <section className="panel">
      <div className="section-heading"><h2>Current inventory</h2><span>Alpaca paper</span></div>
      <div className="table-scroll positions-table"><table className="desk-table"><thead><tr>
        <th>Instrument</th><th>Side</th><th>Quantity</th><th>Entry price</th><th>Current price</th><th>Market value</th><th>Unrealized P&amp;L</th>
      </tr></thead><tbody>{positions.map(p => <tr key={p.symbol}>
        <th>{marketSymbol(p.symbol) ?? p.symbol}</th><td>{p.side}</td><td>{p.qty}</td><td>{usd(p.avgEntryPrice)}</td><td>{usd(p.currentPrice)}</td><td>{usd(p.marketValue)}</td><td className={tone(p.unrealizedPl)}>{usd(p.unrealizedPl)}</td>
      </tr>)}</tbody></table></div>
      <div className="mobile-positions">{positions.map(p => <article key={p.symbol}>
        <div><strong>{marketSymbol(p.symbol) ?? p.symbol}</strong><b className={tone(p.unrealizedPl)}>{usd(p.unrealizedPl)} unrealized</b></div>
        <dl><div><dt>Side / quantity</dt><dd>{p.side} · {p.qty}</dd></div><div><dt>Market value</dt><dd>{usd(p.marketValue)}</dd></div><div><dt>Entry price</dt><dd>{usd(p.avgEntryPrice)}</dd></div><div><dt>Current price</dt><dd>{usd(p.currentPrice)}</dd></div></dl>
      </article>)}</div>
      {!positions.length && <p className="empty">No bot-owned open positions.</p>}
    </section>}
    <ChartWall />
  </main>;
}
