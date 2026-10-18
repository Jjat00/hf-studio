import type { NextRequest } from "next/server";
import { LOCALE_COOKIE, toLocale } from "@/lib/i18n";
import { SESSION_COOKIE, crossSite, gateEnabled, validSession } from "@/lib/session";

/**
 * Proxy hacia la API de HF Studio. La clave `hfs_…` vive solo aquí (HF_STUDIO_TOKEN),
 * nunca en el navegador; las credenciales de Higgsfield ni siquiera llegan a esta capa.
 */
const API = process.env.HF_STUDIO_URL ?? "http://127.0.0.1:8787";
const FORWARD_REQ = ["content-type", "idempotency-key", "range", "accept"];
/** Mensajes propios del proxy en el idioma de la UI (cookie hfs-lang; español por defecto). */
const MESSAGES = {
  es: {
    misconfigured: "Falta HF_STUDIO_TOKEN en web/.env.local",
    signedOut: "Tu sesión terminó: vuelve a entrar con la contraseña de acceso",
    apiDown: (url: string) => `La API de HF Studio no responde en ${url}. ¿Está corriendo \`hf-studio serve\`?`,
  },
  en: {
    misconfigured: "HF_STUDIO_TOKEN is missing in web/.env.local",
    signedOut: "Your session ended: sign in again with the access password",
    apiDown: (url: string) => `HF Studio API is not reachable at ${url}. Is \`hf-studio serve\` running?`,
  },
};
const FORWARD_RES = ["content-type", "content-length", "content-range", "accept-ranges", "content-disposition", "etag", "last-modified"];

async function proxy(req: NextRequest, ctx: RouteContext<"/api/studio/[...path]">) {
  const { path } = await ctx.params;
  const msg = MESSAGES[toLocale(req.cookies.get(LOCALE_COOKIE)?.value)];
  // Con STUDIO_PASSWORD, la sesión se comprueba aquí y no en proxy.ts (ver allí por qué). /health queda
  // abierto para el healthcheck del hosting, pero sin sesión solo dice si la API responde.
  if (gateEnabled() && (crossSite(req.headers) || !validSession(req.cookies.get(SESSION_COOKIE)?.value))) {
    if (path.length === 1 && path[0] === "health" && req.method === "GET") return publicHealth();
    return Response.json({ error: { code: "signed_out", message: msg.signedOut } }, { status: 401 });
  }
  if (path[0] !== "v1" && path[0] !== "health") {
    return Response.json({ error: { code: "not_found", message: "Route not allowed" } }, { status: 404 });
  }
  const token = process.env.HF_STUDIO_TOKEN;
  if (!token) {
    return Response.json(
      { error: { code: "misconfigured", message: msg.misconfigured } },
      { status: 500 },
    );
  }
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  for (const h of FORWARD_REQ) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(`${API}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`, {
      method: req.method,
      headers,
      body: hasBody ? req.body : undefined,
      // Necesario para reenviar el cuerpo como stream (subidas grandes) sin cargarlo en memoria.
      ...(hasBody ? { duplex: "half" } : {}),
      cache: "no-store",
      signal: req.signal,
    } as RequestInit);
  } catch {
    return Response.json(
      { error: { code: "api_down", message: msg.apiDown(API) } },
      { status: 502 },
    );
  }
  const out = new Headers();
  for (const h of FORWARD_RES) {
    const v = upstream.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

/** Salud sin detalles (qué proveedores tienen clave, etc.) para quien no ha entrado. */
async function publicHealth() {
  try {
    const res = await fetch(`${API}/health`, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    return Response.json({ ok: res.ok }, { status: res.ok ? 200 : 502 });
  } catch {
    return Response.json({ ok: false }, { status: 502 });
  }
}

export { proxy as GET, proxy as POST, proxy as DELETE, proxy as PATCH, proxy as PUT };
