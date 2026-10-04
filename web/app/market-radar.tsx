"use client";

import { useState } from "react";
import type {
  FrameName,
  FrameReading,
  MarketPipeline,
  PaperTelemetry,
} from "@/lib/telemetry";

// SOURCE: the user's requested analysis frames; labels match the OCaml engine.
const frames: FrameName[] = ["1m", "5m", "30m", "1h", "4h"];
const value = (number: number | null | undefined) =>
  number == null
    ? "—"
    : // GUESS: # UNCALIBRATED GUESS — eight significant digits for price readability;
      // this display precision is not order rounding or a calibrated threshold.
      new Intl.NumberFormat("en-US", { maximumSignificantDigits: 8 }).format(
        number,
      );
const label = (reading: FrameReading | undefined) =>
  !reading
    ? "No data"
    : reading.status === "candidate"
      ? `${reading.candidate?.toUpperCase()} signal`
      : reading.status === "ready"
        ? (reading.trend ?? "Ready")
        : reading.status === "warming"
          ? `Warmup ${reading.contiguousTailBars ?? 0}/50`
          : reading.status === "market_closed"
            ? "Closed"
            : reading.status === "no_data"
              ? "No data"
              : reading.status;
// SOURCE: the warmup denominator is the shared Pattern Forge EMA50 window.

export default function MarketRadar({
  pipeline,
  experiment,
}: {
  pipeline: MarketPipeline | undefined;
  experiment?: PaperTelemetry["multiPaper"];
}) {
  // SOURCE: revised user focus on equities, index proxies, FX and energy.
  const [category, setCategory] = useState("Traditional markets");
  const [search, setSearch] = useState("");
  const [frameFilter, setFrameFilter] = useState<FrameName | "All frames">(
    "All frames",
  );
  const [selection, setSelection] = useState<{
    market: string;
    frame: FrameName;
  } | null>(null);
  if (!pipeline)
    return (
      <section className="market-radar">
        <h2>Markets &amp; timeframes</h2>
        <p>Waiting for the Dublin multi-market pipeline snapshot.</p>
      </section>
    );
  const categories = [
    ...new Set(pipeline.markets.map((market) => market.category)),
  ];
  const markets = pipeline.markets.filter(
    (market) =>
      (category === "All" ||
        (category === "Traditional markets"
          ? market.venue !== "Alpaca crypto"
          : market.category === category)) &&
      market.symbol.toLowerCase().includes(search.toLowerCase()),
  );
  const selected = pipeline.markets.find(
    (market) => `${market.venue}|${market.symbol}` === selection?.market,
  );
  const reading =
    selected && selection ? selected.frames[selection.frame] : undefined;
  const visibleFrames = frameFilter === "All frames" ? frames : [frameFilter];
  const ready = markets
    .flatMap((market) => visibleFrames.map((frame) => market.frames[frame]))
    .filter(
      (frame) => frame.status === "ready" || frame.status === "candidate",
    ).length;
  return (
    <section className="market-radar" aria-label="Market analysis pipeline">
      <div className="radar-heading">
        <div>
          <span className="eyebrow">
            DATA → CLOSED CANDLES → OCAML ANALYSIS → RISK → PAPER ORDERS
          </span>
          <h2>Markets &amp; timeframes</h2>
        </div>
        <span>
          {markets.length} visible markets · {ready} ready frames
        </span>
      </div>
      <p className="radar-scope">
        BTC / ETH / SOL only in crypto. Stocks/ETF paper transport is connected;
        its automatic strategy is off. Hyperliquid contracts remain public-data
        analysis. Click a frame for indicators, candle timestamp and the
        concrete blocker. Signals do not have a calibrated winning probability.
      </p>
      <div className="radar-controls">
        <label>
          Market group{" "}
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            <option>Traditional markets</option>
            <option>All</option>
            {categories.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          Instrument{" "}
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="EUR, QQQ, ETH…"
          />
        </label>
        <label>
          Timeframe{" "}
          <select
            value={frameFilter}
            onChange={(e) =>
              setFrameFilter(e.target.value as FrameName | "All frames")
            }
          >
            <option>All frames</option>
            {frames.map((f) => (
              <option key={f}>{f}</option>
            ))}
          </select>
        </label>
        <small>
          Analysis as of{" "}
          {new Date(pipeline.asOf).toLocaleString("en-GB", { timeZone: "UTC" })}{" "}
          UTC
        </small>
      </div>
      <div className="radar-table">
        <table>
          <thead>
            <tr>
              <th>Instrument / venue</th>
              {visibleFrames.map((frame) => (
                <th key={frame}>{frame}</th>
              ))}
              <th>Execution</th>
            </tr>
          </thead>
          <tbody>
            {markets.map((market) => (
              <tr key={`${market.venue}|${market.symbol}`}>
                <th>
                  {market.symbol}
                  <small>{market.venue}</small>
                </th>
                {visibleFrames.map((frame) => (
                  <td key={frame}>
                    <button
                      className={`frame-chip ${market.frames[frame]?.status}`}
                      title={market.frames[frame]?.reason}
                      onClick={() =>
                        setSelection({
                          market: `${market.venue}|${market.symbol}`,
                          frame,
                        })
                      }
                    >
                      {label(market.frames[frame])}
                    </button>
                  </td>
                ))}
                <td className="execution-scope">
                  {pipeline.brokerOrderSymbols.includes(market.symbol)
                    ? "Legacy paper"
                    : market.venue === "Alpaca crypto" &&
                        experiment?.mode === "PAPER_EXPERIMENT"
                      ? experiment.newEntriesEnabled === false
                        ? "Exits only"
                        : "Paper experiment"
                      : market.venue === "Alpaca equities"
                        ? "Connected · strategy off"
                        : "Analysis only"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!markets.length && <p>No matching instrument.</p>}
      </div>
      {selected && reading && selection && (
        <div className="frame-detail" aria-label="Selected frame analysis">
          <div>
            <strong>
              {selected.symbol} · {selection.frame}
            </strong>
            <button
              onClick={() => setSelection(null)}
              aria-label="Close frame analysis"
            >
              ×
            </button>
          </div>
          <p>{reading.reason}</p>
          <p>
            Last closed candle start: {reading.lastBarStart ?? "Unavailable"} ·
            contiguous bars {reading.contiguousTailBars ?? "Unavailable"} ·
            status {reading.status}.
          </p>
          <dl>
            <div>
              <dt>Trend / structure</dt>
              <dd>
                {reading.trend ?? "—"} /{" "}
                {reading.structure?.replaceAll("_", " ") ?? "—"}
              </dd>
            </div>
            <div>
              <dt>Candle patterns</dt>
              <dd>
                {reading.candleShapes?.join(", ").replaceAll("_", " ") ||
                  "None"}
              </dd>
            </div>
            <div>
              <dt>EMA20 / EMA50</dt>
              <dd>
                {value(reading.ema20)} / {value(reading.ema50)}
              </dd>
            </div>
            <div>
              <dt>RSI14</dt>
              <dd>{value(reading.rsi14)}</dd>
            </div>
            <div>
              <dt>MACD / signal</dt>
              <dd>
                {value(reading.macd)} / {value(reading.macdSignal)}
              </dd>
            </div>
            <div>
              <dt>Pattern invalidation level</dt>
              <dd>{value(reading.invalidationLevel)} · no stop order placed</dd>
            </div>
          </dl>
          <p className="radar-scope">
            Native historical candles, known after retrieval. Selected Pattern
            Forge formulas and minimal high/low trend structure; this is not the
            full Murphy method. No winning probability or automatic $500 tier is
            claimed.
          </p>
        </div>
      )}
      {pipeline.errors.length > 0 && (
        <p className="radar-error">
          {pipeline.errors.length} provider fetch failures in this scan;
          affected rows retain their timestamp and coverage.
        </p>
      )}
    </section>
  );
}
