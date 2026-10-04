export const runtime = "nodejs";
export async function GET() {
  // SOURCE: HTTP 410 indicates that the monitor history export has been removed.
  return Response.json(
    { error: "History was cleared from this monitor. Only open positions are displayed." },
    { status: 410, headers: { "Cache-Control": "no-store" } },
  );
}
