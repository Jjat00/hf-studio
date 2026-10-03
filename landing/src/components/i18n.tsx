"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { DICTS, type Dict, type Locale } from "@/lib/dict";

const Ctx = createContext<{ locale: Locale; t: Dict; setLocale: (l: Locale) => void }>({
  locale: "es",
  t: DICTS.es,
  setLocale: () => {},
});

const KEY = "hfs-landing-lang";

/** Español por defecto (es lo que se prerenderiza); el inglés se recuerda en localStorage. */
export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("es");

  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem(KEY);
    } catch {}
    const initial = saved === "en" || saved === "es" ? saved : navigator.language.toLowerCase().startsWith("es") ? "es" : "en";
    // eslint-disable-next-line react-hooks/set-state-in-effect -- el idioma solo se conoce en el cliente
    if (initial !== "es") setLocaleState(initial);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = (l: Locale) => {
    setLocaleState(l);
    try {
      localStorage.setItem(KEY, l);
    } catch {}
  };

  return <Ctx.Provider value={{ locale, t: DICTS[locale], setLocale }}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);
