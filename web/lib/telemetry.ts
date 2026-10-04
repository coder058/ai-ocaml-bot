import { get } from "@vercel/blob";
import { readFile } from "node:fs/promises";

export type PaperOrder = {
  id: string;
  clientOrderId: string;
  symbol: string;
  side: string;
  status: string;
  filledQty: string;
  submittedAt: string | null;
  assetClass?: string;
  orderType?: string;
  timeInForce?: string;
};

export type PaperFill = {
  id: string;
  orderId: string;
  symbol: string;
  side: string;
  qty: string;
  price: string;
  transactionTime: string | null;
};

export type PaperPosition = {
  symbol: string;
  qty: string;
  side: string;
  avgEntryPrice: string;
  marketValue: string | null;
  currentPrice?: string | null;
  unrealizedPl?: string | null;
  protected: boolean;
  assetClass?: string;
};

export type CryptoFeeSummary = {
  assetFees?: Record<
    string,
    { qty: string; valueAtActivityPriceUsd: string; rows: number }
  >;
  pagesComplete: boolean;
  attributedToBot: boolean;
  activityRows: number;
  usdFeeRows: number;
  btcFeeRows: number;
  unclassifiedRows: number;
  usdNetAmount: string;
  btcFeeQty: string;
  btcFeeValueAtActivityPriceUsd: string;
  lastActivityAt: string | null;
  fetchedAt: string | null;
};

export type JournalEvent = {
  at: string;
  message: string;
};

export type FrameName = "1m" | "5m" | "30m" | "1h" | "4h";
export type FrameReading = {
  status:
    | "invalid"
    | "no_data"
    | "stale"
    | "warming"
    | "ready"
    | "candidate"
    | "market_closed";
  reason: string;
  completeBars?: number;
  contiguousTailBars?: number;
  lastBarStart?: string;
  close?: number;
  trend?: string;
  structure?: string;
  candleShapes?: string[];
  ema20?: number | null;
  ema50?: number | null;
  rsi14?: number | null;
  macd?: number | null;
  macdSignal?: number | null;
  candidate: "long" | "short" | null;
  invalidationLevel?: number | null;
  orderAuthority: false;
  winProbability: null;
};
export type MarketPipeline = {
  asOf: string;
  retrievedAt: string;
  engine: string;
  policy: string;
  marketsAnalyzed: number;
  currentCandidates: number;
  brokerOrderSymbols: string[];
  markets: {
    symbol: string;
    venue: string;
    category: string;
    execution: string;
    frames: Record<FrameName, FrameReading>;
  }[];
  errors: { venue: string; symbol?: string; frame?: string; error: string }[];
};

export type PaperTelemetry = {
  version: 1;
  generatedAt: string;
  source: "Dublin OCaml paper service";
  connections?: {
    stockAuto?: {
      asOf: string;
      mode: "OBSERVE" | "PAPER_EXPERIMENT";
      automaticStrategy: boolean;
      newEntriesEnabled: boolean;
      sessionOpen: boolean;
      eligibleLongSignals: number;
      routerInvocations: number;
      ownedPositions: { symbol: string; quantity: string; managed: boolean; pending: boolean; frame: string | null }[];
      abstentions: { symbol: string; reason: string }[];
      stopHandling: string;
    };
    stocks?: {
      asOf: string;
      connected: boolean;
      accountReady?: boolean;
      sessionOpen: boolean;
      nextOpen: string;
      automaticStrategy: boolean;
      executionGateArmed: boolean;
      canSubmitNow: boolean;
      feed: string;
    };
    stockStream?: {
      asOf: string;
      connected: boolean;
      symbols: string[];
      quoteCount: number;
      barCount: number;
      lastMarketEventAt: string | null;
      reason: string;
      fullNbbo: false;
    };
    orderStream?: {
      asOf: string;
      connected: boolean;
      eventCount: number;
      lastOrderEventAt: string | null;
      reason: string;
    };
    fx?: {
      asOf: string;
      connected: boolean;
      reason: string;
      catalogCount: number | null;
      monitoredPairs: string[] | null;
      executionAdapterAvailable: boolean;
      orderAuthority: false;
    };
    catalog?: {
      asOf: string;
      stockEtfCount: number;
      monitoredStocks: string[];
      cryptoAllowed: string[];
    };
  };
  marketPipeline?: MarketPipeline;
  multiPaper?: {
    asOf: string;
    mode: "OBSERVE" | "PAPER_EXPERIMENT";
    newEntriesEnabled?: boolean;
    policy: string;
    calibrated: false;
    winProbability: null;
    entryUsd: number;
    maxOpenTickets: number;
    eligibleLongSignals: number;
    activeTickets: {
      symbol: string;
      frame: FrameName;
      bar: string;
      entryClientOrderId: string;
      invalidationLevel: number;
      ownedMaximumQty: number;
      entryAveragePrice: number | null;
      entryFilledQty: number;
      exitFilledQty: number;
      pending: { clientOrderId: string; side: string; reason: string } | null;
    }[];
    abstentions: { symbol: string; reason: string }[];
    stopHandling: string;
  };
  service: { active: boolean; mode: "MONITOR" | "PAPER_ORDER" | "STOPPED" };
  capture?: { active: boolean; lastEventAt: string | null; bytesToday: number };
  analysis?: {
    fiveMinute: {
      observedAt: string | null;
      retrievedAt: string | null;
      lastBarAt: string | null;
      contiguousBars: number;
      trend: string;
      probability: null;
      orderAuthority: false;
    } | null;
    lastDecision: {
      observedAt: string | null;
      quoteTime: string | null;
      policy: string | null;
      receiveToDecisionMs: string | null;
      contextFrame: string | null;
      contextBar: string | null;
      trend: string | null;
    } | null;
  };
  positions: PaperPosition[];
  orders: PaperOrder[];
  ordersComplete: boolean;
  fills?: PaperFill[];
  fillsComplete?: boolean;
  cryptoFees?: CryptoFeeSummary;
  decisionHistory?: Record<string, Record<string, string>>;
  journal: JournalEvent[];
  journalComplete: boolean;
};

export function isTelemetry(value: unknown): value is PaperTelemetry {
  if (!value || typeof value !== "object") return false;
  const data = value as Record<string, unknown>;
  return (
    data.version === 1 &&
    typeof data.generatedAt === "string" &&
    data.source === "Dublin OCaml paper service" &&
    Array.isArray(data.positions) &&
    Array.isArray(data.orders) &&
    Array.isArray(data.journal) &&
    typeof data.ordersComplete === "boolean" &&
    typeof data.journalComplete === "boolean"
  );
}

export async function getTelemetry(): Promise<PaperTelemetry | null> {
  try {
    const localFile = process.env.AI_OCAML_MONITOR_TELEMETRY_FILE;
    if (localFile) {
      const data: unknown = JSON.parse(await readFile(localFile, "utf8"));
      // SOURCE: local mode uses the SSH-synchronized public projection only;
      // a missing or invalid local snapshot must not fall back to Blob.
      return isTelemetry(data) ? data : null;
    }
    const blob = await get("telemetry/latest.json", {
      access: "private",
      // SOURCE: Vercel recommends useCache:false when a just-overwritten blob
      // must be observed immediately; the API response is separately cached.
      useCache: false,
    });
    if (!blob || blob.statusCode !== 200) return null;
    const data: unknown = await new Response(blob.stream).json();
    return isTelemetry(data) ? data : null;
  } catch {
    return null;
  }
}
