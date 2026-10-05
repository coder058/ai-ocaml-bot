"use client";

import { useEffect, useRef, useState } from "react";
import type { FrameName } from "@/lib/telemetry";
import type { Bar, ChartFrame, ChartMarket, ChartPipeline, TechnicalSuite } from "@/lib/chart-types";
import { createChart, CandlestickSeries, LineSeries, HistogramSeries, createSeriesMarkers, ColorType } from "lightweight-charts";
import type { UTCTimestamp } from "lightweight-charts";

// SOURCE: user's five requested frames, matching the server engine.
const FRAMES: FrameName[] = ["1m", "5m", "30m", "1h", "4h"];
const time = (value: string) => Math.floor(Date.parse(value) / 1000) as UTCTimestamp;
const number = (v: number | null | undefined) => v == null ? "—" : new Intl.NumberFormat("en-US", { maximumSignificantDigits: 7 }).format(v);
// GUESS: # UNCALIBRATED GUESS — significant digits, colors and pixel geometry
// throughout this component are display choices, never signal thresholds.

function evidenceText(value: unknown): string {
  if (value == null) return "Unavailable";
  if (typeof value === "number") return number(value);
  if (typeof value === "string") return value.replaceAll("_", " ");
  if (Array.isArray(value)) return value.length ? value.map(item => {
    if (item && typeof item === "object" && "oscillator" in item && "direction" in item)
      return `${item.oscillator} ${item.direction}: price ${number(item.fromPrice)} → ${number(item.toPrice)}, momentum ${number(item.fromValue)} → ${number(item.toValue)}; confirmation close ${item.confirmationCloseAt}; evaluated ${item.evaluatedAsOf}`;
    if (item && typeof item === "object" && "ratio" in item && "price" in item)
      return `${number(Number(item.ratio) * 100)}%: ${number(Number(item.price))}`;
    if (item && typeof item === "object" && "fromPrice" in item && "toPrice" in item)
      return `${item.name}: ${number(Number(item.fromPrice))} → ${number(Number(item.toPrice))}`;
    return evidenceText(item);
  }).join(" · ") : "No confirmed geometry";
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) return "Unavailable";
    if (entries.length === 1 && entries[0][0] === "real") return evidenceText(entries[0][1]);
    if ("trend" in value && "status" in value) return `${evidenceText(value.trend)} (${evidenceText(value.status)})`;
    return entries.map(([key, item]) => `${key.replaceAll("_", " ")}: ${evidenceText(item)}`).join(" · ");
  }
  return String(value);
}

function MiniChart({ reading, title }: { reading: ChartFrame; title: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    let visible = false;
    function paint() {
      if (!node || !visible) return;
      const width = node.clientWidth, height = node.clientHeight;
      if (!width || !height) return;
      const dpr = window.devicePixelRatio;
      node.width = Math.round(width * dpr); node.height = Math.round(height * dpr);
      const ctx = node.getContext("2d"); if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const suite = reading.technicalSuite, bars = suite?.bars ?? [];
      ctx.fillStyle = "#0b141b"; ctx.fillRect(0, 0, width, height);
      if (!bars.length) { ctx.fillStyle = "#91a0aa"; ctx.font = "12px sans-serif"; ctx.fillText("No closed candles", 10, height / 2); return; }
      const low = Math.min(...bars.map(b => b.l)), high = Math.max(...bars.map(b => b.h));
      const range = high - low || high * .01;
      const y = (v: number) => 8 + (high - v) / range * (height - 40);
      const step = (width - 12) / bars.length;
      const x = (i: number) => 6 + (i + .5) * step;
      ctx.strokeStyle = "#1d2b35"; ctx.lineWidth = 1;
      for (const ratio of [0, .5, 1]) { const at = 8 + ratio * (height - 40); ctx.beginPath(); ctx.moveTo(0, at); ctx.lineTo(width, at); ctx.stroke(); }
      const maxVolume = Math.max(...bars.map(b => b.v));
      bars.forEach((b, i) => {
        ctx.strokeStyle = ctx.fillStyle = b.c >= b.o ? "#72d6a3" : "#f18f8c";
        ctx.beginPath(); ctx.moveTo(x(i), y(b.h)); ctx.lineTo(x(i), y(b.l)); ctx.stroke();
        ctx.fillRect(x(i) - step * .3, Math.min(y(b.o), y(b.c)), Math.max(1, step * .6), Math.max(1, Math.abs(y(b.o) - y(b.c))));
        ctx.globalAlpha = .35;
        if (maxVolume) ctx.fillRect(x(i) - step * .3, height - 3 - b.v / maxVolume * 20, Math.max(1, step * .6), b.v / maxVolume * 20);
        ctx.globalAlpha = 1;
      });
      Object.entries(suite?.overlays ?? {}).forEach(([name, values]) => {
        ctx.strokeStyle = name === "EMA20" ? "#e8bc72" : "#8dacfa";
        ctx.beginPath(); let started = false;
        values.forEach((v, i) => { if (v == null) { started = false; return; } if (started) ctx.lineTo(x(i), y(v)); else { ctx.moveTo(x(i), y(v)); started = true; } }); ctx.stroke();
      });
      const eventTimes = new Set(suite?.patternEvents.map(e => e.time));
      bars.forEach((b, i) => { if (eventTimes.has(b.t)) { ctx.fillStyle = "#e8bc72"; ctx.beginPath(); ctx.arc(x(i), y(b.h) - 4, 2, 0, 2 * Math.PI); ctx.fill(); } });
    }
    const observer = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; if (visible) paint(); });
    const resize = new ResizeObserver(paint);
    observer.observe(node); resize.observe(node);
    return () => { observer.disconnect(); resize.disconnect(); };
  }, [reading]);
  return <canvas ref={canvas} role="img" aria-label={`${title} closed candlestick chart`} />;
}

function LargeChart({ suite, title }: { suite: TechnicalSuite | undefined; title: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ bar: Bar; patterns: string[] } | null>(null);
  const [fib, setFib] = useState(false);
  const [markersVisible, setMarkersVisible] = useState(true);
  useEffect(() => {
    if (!container.current || !suite?.bars.length) return;
    const chart = createChart(container.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#0b141b" }, textColor: "#b6c4ce", attributionLogo: true },
      grid: { vertLines: { color: "#182631" }, horzLines: { color: "#182631" } },
      timeScale: { timeVisible: true },
    });
    // SOURCE: derive displayed price precision from the actual OHLC values.
    // GUESS: # UNCALIBRATED GUESS — cap display at eight decimals; no order rounding.
    const precision = Math.max(2, ...suite.bars.flatMap(b => [b.o, b.h, b.l, b.c]).map(v => Number(v.toFixed(8)).toString().split(".")[1]?.length ?? 0));
    const candles = chart.addSeries(CandlestickSeries, { upColor: "#72d6a3", downColor: "#f18f8c", borderVisible: false, wickUpColor: "#72d6a3", wickDownColor: "#f18f8c", priceFormat: { type: "price", precision, minMove: 10 ** -precision } });
    candles.setData(suite.bars.map(b => ({ time: time(b.t), open: b.o, high: b.h, low: b.l, close: b.c })));
    for (const [name, data] of Object.entries(suite.overlays ?? {})) {
      const line = chart.addSeries(LineSeries, { color: name === "EMA20" ? "#e8bc72" : "#8dacfa", lineWidth: 1, title: name, lastValueVisible: false, priceLineVisible: false, priceFormat: { type: "price", precision, minMove: 10 ** -precision } });
      line.setData(data.flatMap((v, i) => v == null ? [] : [{ time: time(suite.bars[i].t), value: v }]));
    }
    const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false }, 1);
    volume.setData(suite.bars.map(b => ({ time: time(b.t), value: b.v, color: b.c >= b.o ? "#245e48" : "#633a40" })));
    for (const [name, value] of Object.entries({ Support: suite.geometry?.support, Resistance: suite.geometry?.resistance })) {
      if (value != null) candles.createPriceLine({ price: value, color: name === "Support" ? "#72d6a3" : "#f18f8c", lineWidth: 1, title: name });
    }
    if (fib) for (const retracement of suite.geometry?.retracements ?? []) candles.createPriceLine({ price: retracement.price, color: "#625b87", lineWidth: 1, title: `${retracement.ratio * 100}%` });
    for (const trend of suite.geometry?.trendlines ?? []) {
      const start = suite.bars.find(b => b.t >= trend.from);
      if (!start || start.t >= trend.to) continue;
      const originalTime = time(trend.from), endTime = time(trend.to);
      const startPrice = trend.fromPrice + (trend.toPrice - trend.fromPrice) * (time(start.t) - originalTime) / (endTime - originalTime);
      const line = chart.addSeries(LineSeries, { color: "#d4a3e5", lineWidth: 1, lastValueVisible: false, priceLineVisible: false, title: `Swing ${trend.name}`, priceFormat: { type: "price", precision, minMove: 10 ** -precision } });
      line.setData([{ time: time(start.t), value: startPrice }, { time: endTime, value: trend.toPrice }]);
    }
    const grouped = new Map<string, { names: string[]; value: number }>();
    for (const e of suite.patternEvents) { const item = grouped.get(e.time) ?? { names: [], value: e.value }; item.names.push(e.name); grouped.set(e.time, item); }
    const markers = createSeriesMarkers(candles, markersVisible ? [...grouped].sort(([a], [b]) => a.localeCompare(b)).map(([at, e]) => ({ time: time(at), position: e.value > 0 ? "belowBar" as const : "aboveBar" as const, color: "#e8bc72", shape: "circle" as const })) : []);
    const barsByTime = new Map(suite.bars.map(bar => [time(bar.t), bar]));
    chart.subscribeCrosshairMove(event => {
      const bar = typeof event.time === "number" ? barsByTime.get(event.time as UTCTimestamp) : undefined;
      setHover(bar ? { bar, patterns: grouped.get(bar.t)?.names ?? [] } : null);
    });
    chart.timeScale().fitContent();
    return () => { markers.detach(); chart.remove(); };
  }, [suite, fib, markersVisible]);
  const current = hover?.bar ?? suite?.bars.at(-1);
  const currentPatterns = hover?.patterns ?? suite?.patternEvents.filter(e => e.time === current?.t).map(e => e.name) ?? [];
  return <><div className="chart-study-controls"><label><input type="checkbox" checked={markersVisible} onChange={e => setMarkersVisible(e.target.checked)} /> Pattern dots</label><label><input type="checkbox" checked={fib} onChange={e => setFib(e.target.checked)} /> Retracement levels</label></div>
    <div className="large-market-chart" ref={container} role="img" aria-label={`${title} interactive candlestick chart`}>{!suite?.bars.length && <p className="empty">No actual closed candles available.</p>}</div>
    {current && <div className="candle-readout"><strong>{current.t.replace("T", " ")}</strong><span>O {number(current.o)} · H {number(current.h)} · L {number(current.l)} · C {number(current.c)} · V {number(current.v)}</span><span>{currentPatterns.join(" · ") || "No pattern on this candle"}</span></div>}
    {suite && suite.contiguousBars != null && suite.contiguousBars < suite.bars.length && <p className="analysis-limit">Data gaps: the chart keeps actual earlier candles; indicators and pattern warmup use only the latest {suite.contiguousBars} consecutive bars.</p>}
  </>;
}

function PrimaryContextEvidence({ value }: { value: unknown }) {
  const context = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const frames = context.frames && typeof context.frames === "object" ? context.frames as Record<string, Record<string, unknown>> : {};
  const providerBlock = context.source === "Hyperliquid public native candles" || frames.Native1M != null;
  return <div className="primary-context">
    <p><strong>Native daily / weekly / {providerBlock ? "provider 1M" : "monthly"} context</strong><br />{evidenceText(context.source)} · received {evidenceText(context.retrievedAt)}</p>
    <div className="primary-context-frames">{["1Day", "1Week", providerBlock ? "Native1M" : "1Month"].map(frame => {
      const reading = frames[frame] ?? {};
      return <article key={frame}><header><strong>{frame === "1Day" ? "Daily" : frame === "1Week" ? "Weekly" : frame === "Native1M" ? reading.periodKind === "fixed_30_day_epoch_grid" ? "Native 30-day · 1M" : "Provider 1M" : "Monthly"}</strong><span>{evidenceText(reading.status ?? "unavailable")}</span></header>
        <dl><div><dt>Trend</dt><dd>{evidenceText(reading.trend)}</dd></div>
          <div><dt>Closed / consecutive bars</dt><dd>{evidenceText(reading.closedBars)} / {evidenceText(reading.contiguousBars)}</dd></div>
          <div><dt>EMA20 / EMA50</dt><dd>{evidenceText(reading.ema20)} / {evidenceText(reading.ema50)}</dd></div>
          <div><dt>Last actual bar</dt><dd>{evidenceText(reading.lastBarAt)}</dd></div>
          <div><dt>Bar closed at</dt><dd>{evidenceText(reading.lastBarClosedAt)}</dd></div>
          <div><dt>Expected latest closed bar</dt><dd>{evidenceText(reading.expectedLatestBarAt)}</dd></div></dl>
        <p>{evidenceText(reading.closure)}</p>
        {reading.source != null && <p>{evidenceText(reading.source)} · adjustment: {evidenceText(reading.adjustment)}</p>}
        {reading.retrievedAt != null && <p>Received {evidenceText(reading.retrievedAt)} · as of {evidenceText(reading.asOf)}</p>}
      </article>;
    })}</div>
    <p className="analysis-limit">Historical data as retrieved, not a point-in-time backtest. Each provider's native period boundary is shown above; open periods are withheld. {providerBlock ? "Hyperliquid 1M is a validated 30-day epoch block, not an Alpaca calendar month. Missing EMA50 history stays warming." : "Monthly equity prices are split-adjusted as retrieved, while daily/weekly remain raw."} No retrospective corporate-action knowledge, trade authority or win probability.</p>
    <p>{evidenceText(context.missing)}</p>
    {Array.isArray(context.errors) && context.errors.length > 0 && <p>Retrieval errors: {evidenceText(context.errors)}</p>}
  </div>;
}

function DerivativeContextEvidence({ value }: { value: unknown }) {
  const context = value && typeof value === "object" ? value as Record<string, unknown> : {};
  return <div className="primary-context">
    <p><strong>Current public derivative context</strong><br />{evidenceText(context.source)} · {evidenceText(context.status)}</p>
    <dl><div><dt>Open interest · native quantity</dt><dd>{evidenceText(context.openInterestRaw)}</dd></div>
      <div><dt>Funding rate · native, not annualized</dt><dd>{evidenceText(context.fundingRateRaw)}</dd></div>
      <div><dt>Provider day notional / base volume</dt><dd>{evidenceText(context.dayNotionalVolumeRaw)} / {evidenceText(context.dayBaseVolumeRaw)}</dd></div>
      <div><dt>Mark / oracle price</dt><dd>{evidenceText(context.markPriceRaw)} / {evidenceText(context.oraclePriceRaw)}</dd></div>
      <div><dt>Received at</dt><dd>{evidenceText(context.receivedAt)}</dd></div></dl>
    <p className="analysis-limit">One received observation; no historical open-interest trend confirmation. The provider supplies no observation timestamp. Native quantities and rate are not converted to USD or annualized funding. Public data only; no trade authority or win probability.</p>
    {Array.isArray(context.missing) && context.missing.length > 0 && <p>Unavailable fields: {evidenceText(context.missing)}</p>}
  </div>;
}

function Evidence({ suite, pipeline }: { suite: TechnicalSuite | undefined; pipeline: ChartPipeline }) {
  const [tab, setTab] = useState("Murphy");
  const [allPatterns, setAllPatterns] = useState(false);
  if (!suite || suite.detailLevel !== "full") return <p className="loading">Loading full Murphy, candlestick and indicator evidence for this instrument…</p>;
  const catalog = pipeline.technicalCoverage;
  return <div className="chart-evidence">
    <nav aria-label="Analysis details">{["Murphy", "Candlesticks", "Indicators"].map(name => <button key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>{name}</button>)}</nav>
    {tab === "Murphy" && <div className="murphy-laws">{suite.murphy?.map(law => <article key={law.law}>
      <header><strong>{law.law}. {law.name}</strong><span>{law.status}</span></header>
      {law.law === 1 && <PrimaryContextEvidence value={law.evidence.primaryContext} />}
      {law.law === 10 && law.evidence.currentDerivativeContext != null && <DerivativeContextEvidence value={law.evidence.currentDerivativeContext} />}
      <dl>{Object.entries(law.evidence).filter(([key]) => key !== "primaryContext" && key !== "currentDerivativeContext").map(([key, value]) => <div key={key}><dt>{key === key.toUpperCase() ? key.replaceAll("_", " ") : key.replace(/([a-z])([A-Z])/g, "$1 $2")}</dt><dd>{evidenceText(value)}</dd></div>)}</dl>
    </article>)}<p className="analysis-limit">Descriptive checklist. Swing divergences are exploratory warnings, not trade probabilities. Native history coverage varies by provider; missing or warming histories and historical volume/open-interest confirmation remain incomplete.</p></div>}
    {tab === "Candlesticks" && <><label className="pattern-toggle"><input type="checkbox" checked={allPatterns} onChange={e => setAllPatterns(e.target.checked)} /> Show every catalog pattern</label>
      <p>TA-Lib signed pattern codes are detections, not confidence or win probabilities.</p>
      <div className="pattern-list">{catalog?.patternCatalog.filter(p => allPatterns || !!suite.patterns[p.code]?.value).map(p => {
        const result = suite.patterns[p.code];
        return <article key={p.code}><div><strong>{p.name}</strong><small>{p.code}</small></div><span>{result?.status === "ready" ? result.value === 0 ? "Not detected" : `Detected (${result.value})` : `Warmup: ${p.lookback + 1} bars`}</span></article>;
      })}</div>
      {!allPatterns && !Object.values(suite.patterns).some(p => p.value) && <p className="empty">No catalog pattern detected on the latest closed candle.</p>}
      <h3>Detected on displayed candles</h3><div className="pattern-event-list">{[...suite.patternEvents].reverse().map(e => <article key={`${e.time}|${e.code}`}><strong>{e.name}</strong><span>{e.time.replace("T", " ")} · {e.value}</span></article>)}</div></>}
    {tab === "Indicators" && <div className="indicator-list">{catalog?.indicatorCatalog.map(item => {
      const result = suite.indicators[item.code];
      return <article key={item.code}><header><strong>{item.code}</strong><small>{item.name}</small><span>{result?.status ?? "Unavailable"}</span></header><p>{Object.entries(result?.values ?? {}).map(([key, v]) => `${key}: ${number(v)}`).join(" · ") || result?.reason || `Needs ${item.lookback + 1} contiguous bars`}</p></article>;
    })}</div>}
    {!!suite.geometry?.chartShapes.length && <p>Exploratory chart geometry: {suite.geometry.chartShapes.join(", ")}.</p>}
  </div>;
}

export default function ChartWall() {
  const [pipeline, setPipeline] = useState<ChartPipeline | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [venue, setVenue] = useState("All venues");
  const [frame, setFrame] = useState<FrameName | "All frames">("All frames");
  const [selected, setSelected] = useState<{ market: string; frame: FrameName } | null>(null);
  const [detail, setDetail] = useState<{ market: string; pipeline: ChartPipeline } | null>(null);
  const [detailError, setDetailError] = useState("");
  const chosenPreview = pipeline?.markets.find(m => `${m.venue}|${m.symbol}` === selected?.market);
  const selectedVenue = chosenPreview?.venue, selectedSymbol = chosenPreview?.symbol;
  useEffect(() => {
    if (!selectedVenue || !selectedSymbol) return;
    const controller = new AbortController();
    const marketKey = `${selectedVenue}|${selectedSymbol}`;
    setDetailError("");
    async function loadDetail() {
      try {
        const query = new URLSearchParams({ venue: selectedVenue!, symbol: selectedSymbol! });
        const response = await fetch(`/api/markets?${query}`, { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("Detail unavailable");
        const data = await response.json();
        const m = data.pipeline?.markets?.[0];
        if (!m || `${m.venue}|${m.symbol}` !== marketKey) throw new Error("Detail does not match instrument");
        if (!controller.signal.aborted) setDetail({ market: marketKey, pipeline: data.pipeline });
      } catch {
        if (!controller.signal.aborted) setDetailError("Full analysis refresh failed. Reopen this chart to retry; preview candles remain available.");
      }
    }
    void loadDetail();
    return () => controller.abort();
  }, [selectedVenue, selectedSymbol, pipeline?.asOf]);
  useEffect(() => {
    if (!selected) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [selected]);
  useEffect(() => {
    let mounted = true, busy = false;
    async function refresh() {
      if (busy) return; busy = true;
      try {
        const response = await fetch("/api/markets", { cache: "no-store" });
        if (!response.ok) throw new Error("Unavailable");
        const data = await response.json();
        if (mounted) { setPipeline(data.pipeline); setError(""); }
      } catch { if (mounted) setError("Market refresh failed. Last successful analysis retained."); }
      finally { busy = false; }
    }
    void refresh();
    // SOURCE: server analysis is scheduled each minute; polling cannot create a new candle.
    const timer = setInterval(refresh, 60_000);
    return () => { mounted = false; clearInterval(timer); };
  }, []);
  const coverage = pipeline?.technicalCoverage;
  const visibleFrames = frame === "All frames" ? FRAMES : [frame];
  const markets = pipeline?.markets.filter(m => (venue === "All venues" || m.venue === venue) && `${m.symbol} ${m.category}`.toLowerCase().includes(search.toLowerCase())) ?? [];
  const key = (m: ChartMarket) => `${m.venue}|${m.symbol}`;
  const detailPipeline = detail && detail.market === selected?.market ? detail.pipeline : null;
  const chosen = detailPipeline?.markets[0] ?? chosenPreview;
  const reading = chosen && selected ? chosen.frames[selected.frame] : null;
  return <section className="chart-workspace" id="charts">
    <div className="chart-wall-heading"><div><span className="eyebrow">Market analysis</span><h2>{pipeline ? pipeline.markets.length * FRAMES.length : "…"} candlestick charts</h2><p>Closed candles · EMA20 / EMA50 · volume · pattern markers</p></div><div className="snapshot-time"><strong>{pipeline?.asOf.replace("T", " ") ?? "Loading market data"}</strong><small>{pipeline ? `Last scan ${number(pipeline.processingSeconds)}s · minute schedule` : "Waiting for Dublin"}</small></div></div>
    {error && <p className="alert">{error}</p>}
    {coverage && <div className="coverage-strip"><span>{coverage.patternCount} candle patterns</span><span>{coverage.indicatorCount} indicator functions</span><span>{pipeline?.markets.reduce((n, m) => n + FRAMES.filter(f => !!m.frames[f].technicalSuite?.bars.length).length, 0)} charts with actual candles</span><span>10 Murphy laws: descriptive / partial</span><span>Analysis only · no order authority</span></div>}
    {pipeline && !coverage && <p className="alert">Expanded pattern scan is warming up. Chart candles will appear after the next completed scan.</p>}
    <div className="chart-filters"><label>Instrument / category<input value={search} onChange={e => setSearch(e.target.value)} placeholder="EUR, QQQ, energy…" /></label><label>Venue<select value={venue} onChange={e => setVenue(e.target.value)}>{["All venues", ...new Set(pipeline?.markets.map(m => m.venue))].map(v => <option key={v}>{v}</option>)}</select></label><label>Timeframe<select value={frame} onChange={e => setFrame(e.target.value as typeof frame)}>{["All frames", ...FRAMES].map(f => <option key={f}>{f}</option>)}</select></label><strong>{markets.length * visibleFrames.length} charts shown</strong></div>
    {!pipeline && <p className="loading">Loading the actual market snapshot…</p>}
    <div className={`chart-matrix ${frame !== "All frames" ? "single-frame" : ""}`}>
      {markets.map(m => <section className="market-chart-row" key={key(m)} aria-label={`${m.symbol} timeframe charts`}>
        <header><strong>{m.symbol}</strong><span>{m.category} · {m.venue}</span><small>{m.execution === "analysis_only" ? "Analysis only" : "Separate BTC quote execution"}</small></header>
        <div className="market-chart-frames">{visibleFrames.map(f => {
          const r = m.frames[f], suite = r.technicalSuite;
          const hits = Object.entries(suite?.patterns ?? {}).filter(([, p]) => !!p.value);
          return <button className="mini-chart-card" key={f} onClick={() => setSelected({ market: key(m), frame: f })} aria-label={`Expand ${m.symbol} ${f}`}>
            <div className="mini-chart-title"><strong>{f}</strong><span>{number(r.close)}</span></div>
            <MiniChart reading={r} title={`${m.symbol} ${f}`} />
            <div className="mini-chart-status"><span className={`frame-state ${r.status}`}>{r.status}</span><span>{r.trend ?? "—"}</span></div>
            <small title={r.reason}>{hits.length ? hits.map(([code]) => code.replace("CDL", "")).join(" · ") : r.reason}</small>
            <small>{suite?.bars.length ?? 0} real bars · {r.lastBarStart?.replace("T", " ") ?? "No close"}</small>
          </button>;
        })}</div>
      </section>)}
    </div>
    {pipeline && !markets.length && <p className="empty">No instrument matches these filters.</p>}
    {coverage && <details className="coverage-audit"><summary>Coverage, sources and remaining Murphy modules</summary><p>{coverage.source}. All catalog patterns are evaluated where their warmup is met. Geometry uses explicitly uncalibrated rules. No win probability is inferred.</p><ul>{coverage.remaining.map(item => <li key={item}>{item}</li>)}</ul>{coverage.sources.map(source => <a key={source} href={source} target="_blank" rel="noreferrer">{source.includes("ta-lib") ? "TA-Lib function catalog" : "Murphy reference"} ↗ </a>)}</details>}
    {chosen && selected && reading && <div className="chart-modal-backdrop" onClick={() => setSelected(null)}>
      <section className="chart-modal" role="dialog" aria-modal="true" aria-label={`${chosen.symbol} ${selected.frame} analysis`} onClick={e => e.stopPropagation()} onKeyDown={e => {
        if (e.key === "Escape") setSelected(null);
        if (e.key === "Tab") {
          const targets = [...e.currentTarget.querySelectorAll<HTMLElement>('button, input, select, a[href]')];
          const destination = e.shiftKey && document.activeElement === targets[0] ? targets.at(-1) : !e.shiftKey && document.activeElement === targets.at(-1) ? targets[0] : null;
          if (destination) { e.preventDefault(); destination.focus(); }
        }
      }}>
        <header className="chart-modal-header"><div><h2>{chosen.symbol} · {selected.frame}</h2><p>{chosen.venue} · {reading.status} · {reading.reason}</p></div><button autoFocus onClick={() => setSelected(null)} aria-label="Close chart">Close ×</button></header>
        <nav aria-label="Selected chart timeframe">{FRAMES.map(f => <button key={f} aria-pressed={selected.frame === f} onClick={() => setSelected({ ...selected, frame: f })}>{f}</button>)}</nav>
        {detailError && <p className="alert">{detailError}</p>}
        {detailPipeline && <small>Detail snapshot: {detailPipeline.asOf.replace("T", " ")}</small>}
        <LargeChart suite={reading.technicalSuite} title={`${chosen.symbol} ${selected.frame}`} />
        <p className="chart-legend">Amber: EMA20 · blue: EMA50 · purple: confirmed-swing trendlines · dots: candlestick detections. Hover a candle for its patterns. Drag to pan; scroll to zoom.</p>
        <Evidence suite={reading.technicalSuite} pipeline={detailPipeline ?? pipeline!} />
      </section>
    </div>}
  </section>;
}
