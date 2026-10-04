import { getTelemetry } from "@/lib/telemetry";
import { chartView } from "@/lib/chart-view";
export const runtime = "nodejs";
export async function GET() {
  const t = await getTelemetry();
  // Only public market data; the display reset continues excluding broker history.
  return Response.json({ pipeline: chartView(t?.marketPipeline) }, {
    headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
  });
}
