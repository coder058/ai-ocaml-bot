import type { FrameName, FrameReading, MarketPipeline } from "./telemetry";

export type Bar = { t: string; o: number; h: number; l: number; c: number; v: number };
export type CatalogItem = { code: string; name: string; group?: string; lookback: number; parameters: Record<string, number> };
export type TechnicalSuite = {
  detailLevel?: "preview" | "full";
  status: string; reason?: string; bars: Bar[]; contiguousBars?: number;
  patterns: Record<string, { status: string; value: number | null; requiredBars?: number }>;
  patternEvents: { time: string; code: string; name: string; value: number }[];
  indicators: Record<string, { status: string; values: Record<string, number | null>; reason?: string; parameters?: Record<string, number> }>;
  geometry?: {
    support: number | null; resistance: number | null;
    retracements: { ratio: number; price: number; from: string; to: string }[];
    trendlines: { name: string; from: string; fromPrice: number; to: string; toPrice: number }[];
    chartShapes: string[]; calibrated: false;
  };
  overlays?: Record<string, (number | null)[]>;
  murphy?: { law: number; name: string; status: string; evidence: Record<string, unknown> }[];
  source?: string; patternCount?: number; indicatorCount?: number;
};
export type ChartFrame = FrameReading & { technicalSuite?: TechnicalSuite };
export type ChartMarket = Omit<MarketPipeline["markets"][number], "frames"> & { frames: Record<FrameName, ChartFrame> };
export type ChartPipeline = Omit<MarketPipeline, "markets"> & {
  markets: ChartMarket[];
  processingSeconds?: number;
  technicalCoverage?: {
    patternCatalog: CatalogItem[]; indicatorCatalog: CatalogItem[];
    patternCount: number; indicatorCount: number; murphyLaws: string[];
    source: string; displayBars: number; seedBars: number;
    completeMurphyBook: false; remaining: string[]; sources: string[];
  };
};
