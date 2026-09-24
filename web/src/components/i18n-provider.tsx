"use client";

import { useRouter } from "next/navigation";
import { createContext, use, useCallback, useState } from "react";
import { dictionaries, LOCALE_COOKIE, type Dict, type L, type Locale } from "@/lib/i18n";

type I18n = { locale: Locale; t: Dict; pick: (text: L) => string; setLocale: (next: Locale) => void };

const I18nContext = createContext<I18n | null>(null);

/** Recibe el idioma leído de la cookie en el servidor; cambiarlo reescribe la cookie y refresca los componentes de servidor. */
export function I18nProvider({ locale: initial, children }: { locale: Locale; children: React.ReactNode }) {
  const router = useRouter();
  const [locale, setState] = useState(initial);
  const setLocale = useCallback(
    (next: Locale) => {
      document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
      document.documentElement.lang = next;
      setState(next);
      router.refresh();
    },
    [router],
  );
  const pick = useCallback((text: L) => text[locale], [locale]);
  return <I18nContext value={{ locale, t: dictionaries[locale], pick, setLocale }}>{children}</I18nContext>;
}

export function useI18n() {
  const ctx = use(I18nContext);
  if (!ctx) throw new Error("useI18n fuera de I18nProvider");
  return ctx;
}
