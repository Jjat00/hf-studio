import type { NextRequest } from "next/server";

/**
 * Proxy hacia la API de HF Studio. La clave `hfs_…` vive solo aquí (HF_STUDIO_TOKEN),
 * nunca en el navegador; las credenciales de Higgsfield ni siquiera llegan a esta capa.
 */
const API = process.env.HF_STUDIO_URL ?? "http://127.0.0.1:8787";
const FORWARD_REQ = ["content-type", "idempotency-key", "range", "accept"];
const FORWARD_RES = ["content-type", "content-length", "content-range", "accept-ranges", "content-disposition", "etag", "last-modified"];

async function proxy(req: NextRequest, ctx: RouteContext<"/api/studio/[...path]">) {
  const { path } = await ctx.params;
  if (path[0] !== "v1" && path[0] !== "health") {
    return Response.json({ error: { code: "not_found", message: "Route not allowed" } }, { status: 404 });
  }
  const token = process.env.HF_STUDIO_TOKEN;
  if (!token) {
    return Response.json(
      { error: { code: "misconfigured", message: "HF_STUDIO_TOKEN is missing in web/.env.local" } },
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
      { error: { code: "api_down", message: `HF Studio API is not reachable at ${API}. Is \`hf-studio serve\` running?` } },
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

export { proxy as GET, proxy as POST, proxy as DELETE, proxy as PATCH, proxy as PUT };
