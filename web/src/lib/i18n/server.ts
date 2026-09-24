import { cookies } from "next/headers";
import { dictionaries, LOCALE_COOKIE, toLocale, type Locale } from ".";

/** Idioma de la petición (componentes de servidor y metadatos). */
export async function getLocale(): Promise<Locale> {
  return toLocale((await cookies()).get(LOCALE_COOKIE)?.value);
}

export async function getDict() {
  return dictionaries[await getLocale()];
}
