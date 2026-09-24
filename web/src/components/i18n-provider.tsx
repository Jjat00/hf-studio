"use client";

import { useRouter } from "next/navigation";
import { createContext, use, useCallback, useEffect, useState } from "react";
import { dictionaries, LOCALE_COOKIE, toLocale, type Dict, type L, type Locale } from "@/lib/i18n";

type I18n = { locale: Locale; t: Dict; pick: (text: L) => string; setLocale: (next: Locale) => void };

const I18nContext = createContext<I18n | null>(null);

function cookieLocale() {
  const raw = document.cookie.split("; ").find((c) => c.startsWith(`${LOCALE_COOKIE}=`));
  return toLocale(raw?.split("=")[1]);
}

/**
 * Recibe el idioma leído de la cookie en el servidor. El botón lo cambia al instante (estado local)
 * y reescribe la cookie; si la cookie cambia desde otra pestaña, al volver a esta se sincroniza y
 * se refrescan los componentes de servidor. Cuando el servidor trae otro idioma, gana el del servidor.
 */
export function I18nProvider({ locale: fromServer, children }: { locale: Locale; children: React.ReactNode }) {
  const router = useRouter();
  const [locale, setState] = useState(fromServer);
  const [seen, setSeen] = useState(fromServer);
  if (seen !== fromServer) {
    setSeen(fromServer);
    setState(fromServer);
  }

  const setLocale = useCallback(
    (next: Locale) => {
      document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
      setState(next);
      router.refresh();
    },
    [router],
  );

  useEffect(() => {
    document.documentElement.lang = locale;
    const sync = () => {
      if (document.visibilityState !== "visible") return;
      const current = cookieLocale();
      if (current === locale) return;
      setState(current);
      router.refresh();
    };
    window.addEventListener("focus", sync);
    document.addEventListener("visibilitychange", sync);
    return () => {
      window.removeEventListener("focus", sync);
      document.removeEventListener("visibilitychange", sync);
    };
  }, [locale, router]);

  const pick = useCallback((text: L) => text[locale], [locale]);
  return <I18nContext value={{ locale, t: dictionaries[locale], pick, setLocale }}>{children}</I18nContext>;
}

export function useI18n() {
  const ctx = use(I18nContext);
  if (!ctx) throw new Error("useI18n fuera de I18nProvider");
  return ctx;
}
