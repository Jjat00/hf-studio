"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { studio } from "@/lib/studio";
import type { Generation } from "@/lib/types";

/**
 * Historial del cliente con sondeo adaptativo: cada 2,5 s mientras haya trabajos activos,
 * cada 20 s en reposo. El servidor ya hace el backoff contra Higgsfield; esto solo lee la BD propia.
 */
export function useGenerations() {
  const [items, setItems] = useState<Generation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const { generations } = await studio.list(80);
      setItems(generations);
      setError(null);
      return generations;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    const loop = async () => {
      const list = await refresh();
      if (!alive) return;
      const active = list?.some((g) => !g.terminal);
      timer.current = setTimeout(loop, active ? 2500 : 20000);
    };
    loop();
    return () => {
      alive = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [refresh]);

  /** Inserta una generación recién creada y acelera el siguiente sondeo. */
  const add = useCallback(
    (g: Generation) => {
      setItems((prev) => [g, ...prev.filter((p) => p.id !== g.id)]);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(async function tick() {
        const list = await refresh();
        const active = list?.some((x) => !x.terminal);
        timer.current = setTimeout(tick, active ? 2500 : 20000);
      }, 1500);
    },
    [refresh],
  );

  /** Borra del historial una generación terminada (optimista; si falla, se recarga). */
  const remove = useCallback(
    async (id: string) => {
      setItems((prev) => prev.filter((g) => g.id !== id));
      await studio.remove(id).catch(() => refresh());
    },
    [refresh],
  );

  return { items, loading, error, refresh, add, remove };
}
