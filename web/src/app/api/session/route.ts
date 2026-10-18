import type { NextRequest } from "next/server";
import { SESSION_COOKIE, attemptLogin, crossSite, gateEnabled, newSession } from "@/lib/session";

/** Abre una sesión con la contraseña de acceso (POST) o la cierra (DELETE). Sin STUDIO_PASSWORD no hace falta. */
export async function POST(req: NextRequest) {
  if (!gateEnabled()) return Response.json({ ok: true });
  if (crossSite(req.headers)) return Response.json({ error: { code: "cross_site" } }, { status: 403 });
  let password = "";
  try {
    const body = await req.json();
    password = typeof body?.password === "string" ? body.password : "";
  } catch {
    // Cuerpo vacío o inválido: cuenta como contraseña incorrecta.
  }
  const result = await attemptLogin(password);
  if (result === "limited") return Response.json({ error: { code: "too_many_attempts" } }, { status: 429 });
  if (result === "wrong") return Response.json({ error: { code: "wrong_password" } }, { status: 401 });
  const { value, expires } = newSession();
  const res = Response.json({ ok: true });
  res.headers.append("Set-Cookie", cookie(req, value, expires));
  return res;
}

export async function DELETE(req: NextRequest) {
  if (gateEnabled() && crossSite(req.headers)) return Response.json({ error: { code: "cross_site" } }, { status: 403 });
  const res = Response.json({ ok: true });
  res.headers.append("Set-Cookie", cookie(req, "", new Date(0)));
  return res;
}

function cookie(req: NextRequest, value: string, expires: Date): string {
  // Detrás del proxy HTTPS de Railway la petición llega por HTTP: se mira x-forwarded-proto.
  const https = req.nextUrl.protocol === "https:" || req.headers.get("x-forwarded-proto") === "https";
  return [
    `${SESSION_COOKIE}=${value}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    `Expires=${expires.toUTCString()}`,
    ...(https ? ["Secure"] : []),
  ].join("; ");
}
