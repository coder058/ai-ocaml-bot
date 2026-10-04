import { verify } from "node:crypto";
import { put } from "@vercel/blob";
import { isTelemetry } from "@/lib/telemetry";

export const runtime = "nodejs";

// SOURCE: public half of the Ed25519 key held only on the Dublin VPS.
const publicKey = `-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAtWzFhuT6Ev1ks0Juxu5weqtWQV15gIc6ZLyo3h4KjRA=
-----END PUBLIC KEY-----`;

export async function POST(request: Request) {
  // SOURCE: localhost receives snapshots through SSH, never through Blob writes.
  if (process.env.AI_OCAML_MONITOR_TELEMETRY_FILE)
    return Response.json({ error: "local monitor uses SSH synchronization" }, { status: 405 });
  const contentLength = Number(request.headers.get("content-length"));
  // GUESS: # UNCALIBRATED GUESS — 1 MiB bounds the ingestion payload;
  // calibrate against actual full account history and journal size.
  if (!Number.isFinite(contentLength) || contentLength < 1 || contentLength > 1_048_576)
    return Response.json({ error: "invalid payload length" }, { status: 413 });
  const body = Buffer.from(await request.arrayBuffer());
  if (body.length !== contentLength) return Response.json({ error: "length mismatch" }, { status: 400 });
  const signatureHeader = request.headers.get("x-ai-ocaml-signature") ?? "";
  if (!/^[A-Za-z0-9+/]{86}==$/.test(signatureHeader))
    return Response.json({ error: "signature required" }, { status: 401 });
  const valid = verify(null, body, publicKey, Buffer.from(signatureHeader, "base64"));
  if (!valid) return Response.json({ error: "signature invalid" }, { status: 401 });
  let payload: unknown;
  try { payload = JSON.parse(body.toString("utf8")); }
  catch { return Response.json({ error: "invalid JSON" }, { status: 400 }); }
  if (!isTelemetry(payload)) return Response.json({ error: "invalid telemetry" }, { status: 400 });
  const ageMs = Math.abs(Date.now() - Date.parse(payload.generatedAt));
  // GUESS: # UNCALIBRATED GUESS — a two-minute signed-message window limits replay.
  if (!Number.isFinite(ageMs) || ageMs > 120_000)
    return Response.json({ error: "stale telemetry" }, { status: 400 });
  await put("telemetry/latest.json", body, {
    access: "private", allowOverwrite: true, contentType: "application/json",
    // SOURCE: Vercel Blob's documented minimum cache duration is one minute.
    cacheControlMaxAge: 60,
  });
  return Response.json({ accepted: true, generatedAt: payload.generatedAt },
    { headers: { "Cache-Control": "no-store" } });
}
