// Dominio de producción (o otro con NEXT_PUBLIC_SITE_URL); en local, el servidor de desarrollo.
export const SITE =
  process.env.NEXT_PUBLIC_SITE_URL ?? (process.env.VERCEL ? "https://hf-studio.jato.run" : "http://localhost:3100");
