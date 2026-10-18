import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, gateEnabled, validSession } from "@/lib/session";

/**
 * Con STUDIO_PASSWORD, manda a /login a quien no tenga sesión. Las rutas /api no pasan por aquí: el proxy
 * guarda en memoria el cuerpo de cada petición y lo corta en 10 MB, lo que truncaría las subidas. Por eso
 * /api/studio comprueba la sesión por su cuenta.
 */
export function proxy(req: NextRequest) {
  if (!gateEnabled() || validSession(req.cookies.get(SESSION_COOKIE)?.value)) return NextResponse.next();
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  url.searchParams.set("next", req.nextUrl.pathname + req.nextUrl.search);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!api/|login|_next/static|_next/image|favicon\\.ico|icon\\.svg|apple-icon\\.png).*)"],
};
