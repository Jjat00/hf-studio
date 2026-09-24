/** Idiomas de la UI: español por defecto, inglés opcional. La elección vive en una cookie. */
export const LOCALES = ["es", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "es";
export const LOCALE_COOKIE = "hfs-lang";

/** Texto bilingüe para los datos (modos, portada, casos de uso). */
export type L = { es: string; en: string };
export const l = (es: string, en: string): L => ({ es, en });

export function toLocale(value: string | undefined | null): Locale {
  return value === "en" ? "en" : DEFAULT_LOCALE;
}

export { dictionaries, type Dict } from "./dictionaries";
