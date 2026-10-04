import { getTelemetry } from "@/lib/telemetry";
import { chartView } from "@/lib/chart-view";
export const runtime = "nodejs";
export async function GET(request: Request) {
  const query = new URL(request.url).searchParams;
  const symbol = query.get("symbol"), venue = query.get("venue");
  if ((symbol != null || venue != null) && (!symbol || !venue))
    return Response.json({ error: "Both symbol and venue are required for chart detail" }, { status: 400 });
  const t = await getTelemetry();
  const pipeline = chartView(t?.marketPipeline, symbol && venue ? { symbol, venue } : { preview: true });
  if (symbol && venue && pipeline && !pipeline.markets.length)
    return Response.json({ error: "Instrument absent from current market snapshot" }, { status: 404 });
  // Only public market data; the display reset continues excluding broker history.
  return Response.json({ pipeline }, {
    headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
  });
}
