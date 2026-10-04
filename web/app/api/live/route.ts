import { getTelemetry } from "@/lib/telemetry";

export const runtime = "nodejs";

export async function GET() {
  const telemetry = await getTelemetry();
  return Response.json({
    generatedAt: new Date().toISOString(),
    telemetry,
  }, {
    headers: {
      // GUESS: # UNCALIBRATED GUESS — 15s edge cache gives a usable monitor
      // without a private Blob origin read for every visitor refresh.
      "Cache-Control": process.env.AI_OCAML_MONITOR_TELEMETRY_FILE ? "no-store" :
        "public, s-maxage=15, stale-while-revalidate=15",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
