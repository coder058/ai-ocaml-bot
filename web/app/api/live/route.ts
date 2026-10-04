import { getTelemetry } from "@/lib/telemetry";
import { positionsView } from "@/lib/positions-view";
export const runtime = "nodejs";

export async function GET() {
  return Response.json({
    generatedAt: new Date().toISOString(),
    view: "positions_only",
    telemetry: positionsView(await getTelemetry()),
  }, { headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } });
}
