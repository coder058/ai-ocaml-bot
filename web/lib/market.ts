export type Timeframe = "5m" | "1h" | "1d";

export type MarketSignal = {
  symbol: string;
  timeframe: Timeframe;
  at: string;
  label: string;
  direction: "up" | "down" | "neutral";
  source: "Pattern Forge / Hyperliquid";
  calibrated: false;
};

export type MarketFrame = {
  timeframe: Timeframe;
  close: number;
  previousClose: number;
  returnPct: number;
  closeTime: string;
  ema20: number | null;
  ema50: number | null;
  rsi14: number | null;
  sparkline: number[];
};

export type MarketSymbol = {
  symbol: string;
  venue: "Hyperliquid";
  asOf: string;
  frames: MarketFrame[];
  signals: MarketSignal[];
  errors: string[];
};

type Bar = {
  t: number;
  closeTime: number;
  o: number;
  h: number;
  l: number;
  c: number;
  closed: true;
};

const intervals: Record<Timeframe, number> = {
  // SOURCE: Pattern Forge uses closed UTC 5-minute, hourly and daily bars.
  "5m": 300_000,
  "1h": 3_600_000,
  "1d": 86_400_000,
};

function validBar(value: unknown, interval: number, now: number): value is Bar {
  if (!value || typeof value !== "object") return false;
  const bar = value as Record<string, unknown>;
  const { t, closeTime, o, h, l, c } = bar;
  return bar.closed === true && [t, closeTime, o, h, l, c].every(
    (n) => typeof n === "number" && Number.isFinite(n),
  ) && (t as number) >= 0 && closeTime === (t as number) + interval &&
    (closeTime as number) <= now && (l as number) > 0 &&
    (h as number) >= Math.max(o as number, c as number, l as number) &&
    (l as number) <= Math.min(o as number, c as number);
}

function ema(closes: number[], period: number): number | null {
  if (closes.length < period) return null;
  // SOURCE: Pattern Forge seeds the EMA with a full-period simple average.
  let value = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
  const alpha = 2 / (period + 1);
  for (const close of closes.slice(period)) value = close * alpha + value * (1 - alpha);
  return value;
}

function rsi(closes: number[], period: number): number | null {
  if (closes.length <= period) return null;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const delta = closes[i] - closes[i - 1];
    gain += Math.max(delta, 0) / period;
    loss += Math.max(-delta, 0) / period;
  }
  for (let i = period + 1; i < closes.length; i++) {
    const delta = closes[i] - closes[i - 1];
    gain = (gain * (period - 1) + Math.max(delta, 0)) / period;
    loss = (loss * (period - 1) + Math.max(-delta, 0)) / period;
  }
  // SOURCE: Wilder RSI, matching Pattern Forge's descriptive implementation.
  return gain === 0 && loss === 0 ? 50 : loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
}

function shapeSignals(symbol: string, timeframe: Timeframe, bars: Bar[]): MarketSignal[] {
  const signals: MarketSignal[] = [];
  // GUESS: # UNCALIBRATED GUESS — Pattern Forge's geometric reading controls.
  const dojiRatio = 0.1;
  const wickRatio = 2;
  // GUESS: # UNCALIBRATED GUESS — show the most recent 20 closed bars, not a validated lookback.
  for (let i = Math.max(0, bars.length - 20); i < bars.length; i++) {
    const bar = bars[i];
    const prior = bars[i - 1];
    const range = bar.h - bar.l;
    const body = Math.abs(bar.c - bar.o);
    const lower = Math.min(bar.o, bar.c) - bar.l;
    const upper = bar.h - Math.max(bar.o, bar.c);
    const add = (label: string, direction: MarketSignal["direction"]) =>
      signals.push({
        symbol, timeframe, at: new Date(bar.closeTime).toISOString(),
        label, direction, source: "Pattern Forge / Hyperliquid", calibrated: false,
      });
    if (range > 0 && body / range <= dojiRatio) add("Doji shape", "neutral");
    if (body > 0 && lower >= wickRatio * body && upper <= body) add("Hammer shape", "up");
    if (body > 0 && upper >= wickRatio * body && lower <= body) add("Shooting-star shape", "down");
    if (prior && prior.closeTime === bar.t) {
      if (prior.c < prior.o && bar.c > bar.o && bar.o <= prior.c && bar.c >= prior.o)
        add("Bullish engulfing shape", "up");
      if (prior.c > prior.o && bar.c < bar.o && bar.o >= prior.c && bar.c <= prior.o)
        add("Bearish engulfing shape", "down");
    }
  }
  return signals;
}

export function analyzeSnapshot(symbol: string, input: unknown, now = Date.now()): MarketSymbol {
  const result: MarketSymbol = {
    symbol, venue: "Hyperliquid", asOf: new Date(now).toISOString(),
    frames: [], signals: [], errors: [],
  };
  if (!input || typeof input !== "object") {
    result.errors.push("Pattern Forge returned no valid snapshot.");
    return result;
  }
  const source = input as Record<string, unknown>;
  if (source.symbol !== symbol || source.venue !== "Hyperliquid" ||
      !source.frames || typeof source.frames !== "object") {
    result.errors.push("Pattern Forge symbol, venue or frames did not match.");
    return result;
  }
  if (typeof source.asOf === "number" && Number.isFinite(source.asOf))
    result.asOf = new Date(source.asOf).toISOString();
  for (const timeframe of ["5m", "1h", "1d"] as Timeframe[]) {
    const raw = (source.frames as Record<string, unknown>)[timeframe];
    if (!Array.isArray(raw) || raw.length < 2 ||
        !raw.every((bar) => validBar(bar, intervals[timeframe], now))) {
      result.errors.push(`${timeframe}: no complete valid candle sequence`);
      continue;
    }
    const bars = raw as Bar[];
    if (bars.some((bar, i) => i > 0 && bar.t <= bars[i - 1].t)) {
      result.errors.push(`${timeframe}: candles are not strictly ordered`);
      continue;
    }
    const latest = bars.at(-1)!;
    const previous = bars.at(-2)!;
    if (latest.t !== previous.closeTime) {
      result.errors.push(`${timeframe}: latest candles have a gap`);
      continue;
    }
    const closes = bars.map((bar) => bar.c);
    result.frames.push({
      timeframe,
      close: latest.c,
      previousClose: previous.c,
      // SOURCE: adjacent closed-candle percentage return.
      returnPct: (latest.c / previous.c - 1) * 100,
      closeTime: new Date(latest.closeTime).toISOString(),
      // SOURCE: conventional indicator periods used by Pattern Forge.
      ema20: ema(closes, 20), ema50: ema(closes, 50), rsi14: rsi(closes, 14),
      // GUESS: # UNCALIBRATED GUESS — 40 recent points balance chart legibility and payload.
      sparkline: closes.slice(-40),
    });
    result.signals.push(...shapeSignals(symbol, timeframe, bars));
  }
  result.signals.sort((a, b) => b.at.localeCompare(a.at));
  return result;
}

export async function getMarket(): Promise<MarketSymbol[]> {
  return Promise.all(["BTC", "ETH", "SOL"].map(async (symbol) => {
    try {
      const response = await fetch(`https://pattern-forge-five.vercel.app/api/markets/${symbol}`, {
        // GUESS: # UNCALIBRATED GUESS — cache for 30 seconds to bound upstream load.
        next: { revalidate: 30 }, signal: AbortSignal.timeout(15_000),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return analyzeSnapshot(symbol, await response.json());
    } catch (error) {
      return {
        symbol, venue: "Hyperliquid" as const,
        asOf: new Date().toISOString(), frames: [], signals: [],
        errors: [`Pattern Forge unavailable: ${error instanceof Error ? error.message : "unknown error"}`],
      };
    }
  }));
}
