import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * Puerta de acceso para una UI expuesta fuera de 127.0.0.1 (p. ej. en Railway). Solo está activa si existe
 * STUDIO_PASSWORD: entonces cada página y cada llamada a /api/studio exigen una cookie de sesión firmada.
 * La firma depende solo de la contraseña: cambiarla cierra todas las sesiones abiertas. No usa HF_STUDIO_TOKEN
 * porque `hf-studio cloud` lo rota en cada arranque y cada reinicio sacaría a todos.
 */
export const SESSION_COOKIE = "hfs-session";
export const SESSION_DAYS = 30;

export function gateEnabled(): boolean {
  return Boolean(process.env.STUDIO_PASSWORD);
}

function signingKey(): string {
  return `hfs-session\0${process.env.STUDIO_PASSWORD ?? ""}`;
}

function sign(payload: string): string {
  return createHmac("sha256", signingKey()).update(payload).digest("base64url");
}

function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  return ab.length === bb.length && timingSafeEqual(ab, bb);
}

/** Valor de la cookie: `<caducidad en ms>.<firma>`. */
export function newSession(now = Date.now()): { value: string; expires: Date } {
  const expires = now + SESSION_DAYS * 24 * 60 * 60 * 1000;
  return { value: `${expires}.${sign(String(expires))}`, expires: new Date(expires) };
}

export function validSession(value: string | undefined, now = Date.now()): boolean {
  if (!value) return false;
  const [expires, signature] = value.split(".");
  if (!expires || !signature || !/^\d+$/.test(expires) || Number(expires) < now) return false;
  return safeEqual(signature, sign(expires));
}

/** Compara en tiempo constante (sobre los HMAC, que tienen la misma longitud aunque las cadenas no). */
export function passwordMatches(candidate: string): boolean {
  const expected = process.env.STUDIO_PASSWORD;
  if (!expected) return false;
  return safeEqual(sign(`pw:${candidate}`), sign(`pw:${expected}`));
}

/** Solo rutas internas como destino tras entrar: evita redirecciones abiertas (`//otro.sitio`, `/\\…`, y
 * `/\t/otro.sitio`, porque el parser de URL borra tabuladores y saltos de línea antes de leer la ruta). */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || /[\u0000-\u001f\u007f\\]/.test(next)) return "/";
  const base = "http://studio.invalid";
  try {
    const url = new URL(next, base);
    // Se valida también el resultado: normalizar `/.//otro.sitio` o `/a/..//otro.sitio` deja `//otro.sitio`.
    const target = url.pathname + url.search + url.hash;
    const ok = url.origin === base && !target.startsWith("//") && new URL(target, base).origin === base;
    return ok ? target : "/";
  } catch {
    return "/";
  }
}

/** Con la puerta activa, una petición que el navegador marca como de otro sitio (Sec-Fetch-Site) no usa la
 * sesión: SameSite=Lax deja pasar la cookie en una navegación GET iniciada desde otra página. Sin la cabecera
 * (curl, healthchecks) o con `none` (URL escrita a mano) se acepta. */
export function crossSite(headers: Headers): boolean {
  const site = headers.get("sec-fetch-site");
  return site === "cross-site" || site === "same-site";
}

/**
 * Límite de intentos de contraseña, global para el proceso (un solo servidor de Node; no depende de cabeceras de
 * IP que un cliente puede falsificar): las comprobaciones van de una en una, cada fallo retiene la cola un
 * segundo, no esperan más de MAX_QUEUED a la vez y, tras MAX_FAILURES fallos en WINDOW_MS, se responde 429 hasta
 * que la ventana pase. Quien ataca puede bloquear el login unos minutos, pero no probar más de ~1 clave/s.
 */
const MAX_QUEUED = 10;
const MAX_FAILURES = 30;
const WINDOW_MS = 15 * 60 * 1000;
const FAIL_DELAY_MS = 1000;
let queue: Promise<unknown> = Promise.resolve();
let queued = 0;
let failures: number[] = [];

export type Attempt = "ok" | "wrong" | "limited";

export async function attemptLogin(candidate: string, now = () => Date.now()): Promise<Attempt> {
  failures = failures.filter((t) => now() - t < WINDOW_MS);
  if (failures.length >= MAX_FAILURES || queued >= MAX_QUEUED) return "limited";
  queued++;
  const run = queue.then(async (): Promise<Attempt> => {
    if (failures.length >= MAX_FAILURES) return "limited";
    if (passwordMatches(candidate)) return "ok";
    failures.push(now());
    await new Promise((r) => setTimeout(r, FAIL_DELAY_MS));
    return "wrong";
  });
  queue = run.catch(() => undefined);
  try {
    return await run;
  } finally {
    queued--;
  }
}
