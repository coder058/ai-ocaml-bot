"use client";

import { useState } from "react";
import type { FrameName, FrameReading, MarketPipeline, PaperTelemetry } from "@/lib/telemetry";

// SOURCE: the user's requested analysis frames; labels match the OCaml engine.
const frames: FrameName[] = ["1m", "5m", "30m", "1h", "4h"];
const value = (number: number | null | undefined) => number == null ? "—" :
  // GUESS: # UNCALIBRATED GUESS — eight significant digits for price readability;
  // this display precision is not order rounding or a calibrated threshold.
  new Intl.NumberFormat("en-US", { maximumSignificantDigits: 8 }).format(number);
const label = (reading: FrameReading | undefined) => !reading ? "No data" :
  reading.status === "candidate" ? `${reading.candidate?.toUpperCase()} signal` :
  reading.status === "ready" ? reading.trend ?? "Ready" :
  reading.status === "warming" ? `Warmup ${reading.contiguousTailBars ?? 0}/50` :
  reading.status === "market_closed" ? "Closed" :
  reading.status === "no_data" ? "No data" : reading.status;
// SOURCE: the warmup denominator is the shared Pattern Forge EMA50 window.

export default function MarketRadar({ pipeline, experiment }: { pipeline: MarketPipeline | undefined;
  experiment?: PaperTelemetry["multiPaper"] }) {
  const [category, setCategory] = useState("All");
  const [search, setSearch] = useState("");
  const [selection, setSelection] = useState<{ market: string; frame: FrameName } | null>(null);
  if (!pipeline) return <section className="market-radar"><h2>Markets &amp; timeframes</h2>
    <p>Waiting for the Dublin multi-market pipeline snapshot.</p></section>;
  const categories = [...new Set(pipeline.markets.map((market) => market.category))];
  const markets = pipeline.markets.filter((market) => (category === "All" || market.category === category)
    && market.symbol.toLowerCase().includes(search.toLowerCase()));
  const selected = pipeline.markets.find((market) => `${market.venue}|${market.symbol}` === selection?.market);
  const reading = selected && selection ? selected.frames[selection.frame] : undefined;
  const ready = pipeline.markets.flatMap((market) => Object.values(market.frames))
    .filter((frame) => frame.status === "ready" || frame.status === "candidate").length;
  return <section className="market-radar" aria-label="Market analysis pipeline">
    <div className="radar-heading"><div><span className="eyebrow">DATA → CLOSED CANDLES → OCAML ANALYSIS → RISK → PAPER ORDERS</span>
      <h2>Markets &amp; timeframes</h2></div>
      <span>{pipeline.markets.length} markets · {ready} ready frames · {pipeline.currentCandidates} signals</span></div>
    <p className="radar-scope">BTC uses the legacy paper rule. {experiment?.mode === "PAPER_EXPERIMENT" ?
      "Other Alpaca crypto can enter the multi-frame paper experiment when its gates pass." :
      "Other instruments currently have analysis only."} Equity and Hyperliquid rows have no broker order authority.
      Signals have no calibrated win probability. Click a frame to see its analysis and blocker.</p>
    <div className="radar-controls"><label>Market group <select value={category} onChange={(event) => setCategory(event.target.value)}>
      <option>All</option>{categories.map((item) => <option key={item}>{item}</option>)}</select></label>
      <label>Instrument <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="EUR, QQQ, ETH…" /></label>
      <small>Analysis as of {new Date(pipeline.asOf).toLocaleString("en-GB", { timeZone: "UTC" })} UTC</small></div>
    <div className="radar-table"><table><thead><tr><th>Instrument / venue</th>{frames.map((frame) => <th key={frame}>{frame}</th>)}
      <th>Execution</th></tr></thead><tbody>{markets.map((market) => <tr key={`${market.venue}|${market.symbol}`}>
        <th>{market.symbol}<small>{market.venue}</small></th>{frames.map((frame) => <td key={frame}>
          <button className={`frame-chip ${market.frames[frame]?.status}`} title={market.frames[frame]?.reason}
            onClick={() => setSelection({ market: `${market.venue}|${market.symbol}`, frame })}>
            {label(market.frames[frame])}</button></td>)}
        <td className="execution-scope">{pipeline.brokerOrderSymbols.includes(market.symbol) ? "Legacy paper" :
          market.venue === "Alpaca crypto" && experiment?.mode === "PAPER_EXPERIMENT" ? "Paper experiment" : "Analysis only"}</td>
      </tr>)}</tbody></table>{!markets.length && <p>No matching instrument.</p>}</div>
    {selected && reading && selection && <div className="frame-detail" aria-label="Selected frame analysis">
      <div><strong>{selected.symbol} · {selection.frame}</strong><button onClick={() => setSelection(null)} aria-label="Close frame analysis">×</button></div>
      <p>{reading.reason}</p>
      <dl><div><dt>Trend / structure</dt><dd>{reading.trend ?? "—"} / {reading.structure?.replaceAll("_", " ") ?? "—"}</dd></div>
        <div><dt>Candle patterns</dt><dd>{reading.candleShapes?.join(", ").replaceAll("_", " ") || "None"}</dd></div>
        <div><dt>EMA20 / EMA50</dt><dd>{value(reading.ema20)} / {value(reading.ema50)}</dd></div>
        <div><dt>RSI14</dt><dd>{value(reading.rsi14)}</dd></div>
        <div><dt>MACD / signal</dt><dd>{value(reading.macd)} / {value(reading.macdSignal)}</dd></div>
        <div><dt>Pattern invalidation level</dt><dd>{value(reading.invalidationLevel)} · no stop order placed</dd></div>
      </dl><p className="radar-scope">Native historical candles, known after retrieval. Selected Pattern Forge formulas and minimal
        high/low trend structure; this is not the full Murphy method. No winning probability or automatic $500 tier is claimed.</p>
    </div>}
    {pipeline.errors.length > 0 && <p className="radar-error">{pipeline.errors.length} provider fetch failures in this scan; affected rows retain their timestamp and coverage.</p>}
  </section>;
}
