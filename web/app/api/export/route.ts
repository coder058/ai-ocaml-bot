import { getTelemetry } from "@/lib/telemetry";
import { historyExport } from "@/lib/history-export";
export const runtime = "nodejs";
// SOURCE: HTTP 503 means data unavailable; 409 prevents exporting an invalid/incomplete history.
export async function GET(request: Request) {
  const t = await getTelemetry();
  if (!t)
    return Response.json(
      { error: "Broker snapshot unavailable" },
      { status: 503 },
    );
  try {
    const params = new URL(request.url).searchParams;
    return new Response(historyExport(t, params), {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="ai-ocaml-${params.get("kind") === "closed" ? "closed-fills" : "orders"}.csv"`,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch (e) {
    return Response.json(
      { error: e instanceof Error ? e.message : "Export unavailable" },
      { status: 409 },
    );
  }
}
