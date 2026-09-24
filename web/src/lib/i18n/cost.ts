import type { Locale } from ".";

/**
 * La API describe el costo en inglés (`basis`, `missing`) porque también lo leen el MCP y los agentes.
 * Aquí se traducen las frases conocidas; lo que no encaje (p. ej. el mensaje de Higgsfield) se deja tal cual.
 */
const BASIS_ES: [RegExp, string][] = [
  [/Higgsfield estimate/g, "Estimación de Higgsfield"],
  [/\(media not uploaded yet\)/g, "(medios aún sin subir)"],
  [/ · before discounts/g, " · antes de descuentos"],
  [/\(16:9 assumed\)/g, "(se asume 16:9)"],
  [/\/s of input video at /g, "/s de video de entrada a "],
  [/s of input video × /g, "s de video de entrada × "],
  [/\/s at /g, "/s a "],
  [/ extra refs × /g, " refs. extra × "],
  [/usage-based pricing \(final cost depends on actual tokens\)/g, "precio por uso (el costo final depende de los tokens reales)"],
  [/^Invalid input: /g, "Entrada no válida: "],
  [/Higgsfield needs the real media to price this model; upload it first/g, "Higgsfield necesita los medios reales para cotizar este modelo; súbelos primero"],
  [/Higgsfield could not price this request/g, "Higgsfield no pudo cotizar esta petición"],
];

const MISSING_ES: Record<string, string> = {
  "input video duration": "la duración del video de entrada",
};

export function costBasis(text: string, locale: Locale) {
  if (locale === "en") return text;
  return BASIS_ES.reduce((acc, [re, to]) => acc.replace(re, to), text);
}

export function costMissing(items: string[], locale: Locale) {
  return items.map((m) => (locale === "es" ? (MISSING_ES[m] ?? m) : m)).join(", ");
}
