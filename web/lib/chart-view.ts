import type { ChartPipeline, TechnicalSuite } from "./chart-types";
import type { MarketPipeline } from "./telemetry";

function suiteView(suite: TechnicalSuite | undefined, preview: boolean): TechnicalSuite | undefined {
  if (!suite) return undefined;
  return {
    detailLevel: preview ? "preview" : "full",
    status: suite.status, reason: suite.reason, bars: suite.bars,
    contiguousBars: suite.contiguousBars, source: suite.source,
    patternCount: suite.patternCount, indicatorCount: suite.indicatorCount,
    patterns: Object.fromEntries(Object.entries(suite.patterns).filter(([, row]) => !preview || !!row.value).map(([name, row]) =>
      [name, { status: row.status, value: row.value }] )) as TechnicalSuite["patterns"],
    indicators: preview ? {} : Object.fromEntries(Object.entries(suite.indicators).map(([name, row]) =>
      [name, { status: row.status, values: row.values, reason: row.reason }])),
    // Preview dots only need one actual detection per candle. The expanded
    // endpoint retains every detection and its catalog identity.
    patternEvents: preview ? [...new Map(suite.patternEvents.map(event => [event.time, event])).values()] : suite.patternEvents,
    overlays: suite.overlays,
    geometry: !preview && suite.geometry ? {
      support: suite.geometry.support, resistance: suite.geometry.resistance,
      retracements: suite.geometry.retracements,
      trendlines: suite.geometry.trendlines.map(line => ({ name: line.name, from: line.from,
        fromPrice: line.fromPrice, to: line.to, toPrice: line.toPrice })),
      chartShapes: suite.geometry.chartShapes, calibrated: false,
    } : undefined,
    murphy: preview ? undefined : suite.murphy,
  };
}

// Keep only market-analysis fields. Duplicate per-function parameters live in
// the catalog; broker histories/holdings never enter the chart response.
export function chartView(raw: MarketPipeline | undefined, options: { preview?: boolean; venue?: string; symbol?: string } = {}): ChartPipeline | null {
  if (!raw) return null;
  const p = raw as ChartPipeline;
  return {
    asOf: p.asOf, retrievedAt: p.retrievedAt, engine: p.engine, policy: p.policy,
    marketsAnalyzed: p.marketsAnalyzed, currentCandidates: p.currentCandidates,
    brokerOrderSymbols: p.brokerOrderSymbols, errors: p.errors,
    processingSeconds: p.processingSeconds, technicalCoverage: p.technicalCoverage,
    markets: p.markets.filter(m => (!options.venue || m.venue === options.venue) && (!options.symbol || m.symbol === options.symbol)).map(m => ({ symbol: m.symbol, venue: m.venue,
      category: m.category, execution: m.execution,
      frames: Object.fromEntries(Object.entries(m.frames).map(([name, r]) => [name, {
        status: r.status, reason: r.reason, completeBars: r.completeBars,
        contiguousTailBars: r.contiguousTailBars, lastBarStart: r.lastBarStart,
        close: r.close, trend: r.trend, structure: r.structure, candleShapes: r.candleShapes,
        ema20: r.ema20, ema50: r.ema50, rsi14: r.rsi14, macd: r.macd,
        macdSignal: r.macdSignal, candidate: r.candidate,
        invalidationLevel: r.invalidationLevel, orderAuthority: false as const,
        winProbability: null, technicalSuite: suiteView(r.technicalSuite, options.preview === true),
      }])) as ChartPipeline["markets"][number]["frames"],
    })),
  };
}
