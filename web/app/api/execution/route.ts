import { getTelemetry } from "@/lib/telemetry";
import { executionView } from "@/lib/execution-view";
export const runtime = "nodejs";

export async function GET() {
  return Response.json({ telemetry: executionView(await getTelemetry()) }, {
    headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
  });
}
