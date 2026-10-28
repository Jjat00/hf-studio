"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { studio } from "@/lib/studio";
import type { Generation } from "@/lib/types";

/**
 * Historial del cliente con sondeo adaptativo: cada 2,5 s mientras haya trabajos activos,
 * cada 20 s en reposo. El servidor ya hace el backoff contra Higgsfield; esto solo lee la BD propia.
 */
export function useGenerations({ hidden = false, favorite = false }: { hidden?: boolean; favorite?: boolean } = {}) {
  const [items, setItems] = useState<Generation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const { generations } = await studio.list(80, hidden, favorite);
      setItems(generations);
      setError(null);
      return generations;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setLoading(false);
    }
  }, [hidden, favorite]);

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

  /** Oculta o vuelve a mostrar varias (optimista: salen de esta lista al momento; si falla, se recarga). */
  const setHidden = useCallback(
    async (ids: string[], value: boolean) => {
      const gone = new Set(ids);
      setItems((prev) => prev.filter((g) => !gone.has(g.id)));
      try {
        const res = await studio.hide(ids, value);
        if (res.skipped.length) await refresh();
        return res;
      } catch (e) {
        await refresh();
        throw e;
      }
    },
    [refresh],
  );

  /** Marca o desmarca favoritas (optimista; en la vista de favoritas, las que se quitan salen al momento). */
  const setFavorite = useCallback(
    async (ids: string[], value: boolean) => {
      const touched = new Set(ids);
      setItems((prev) =>
        favorite && !value ? prev.filter((g) => !touched.has(g.id)) : prev.map((g) => (touched.has(g.id) ? { ...g, favorite: value } : g)),
      );
      try {
        return await studio.favorite(ids, value);
      } catch (e) {
        await refresh();
        throw e;
      }
    },
    [refresh, favorite],
  );

  return { items, loading, error, refresh, add, remove, setHidden, setFavorite };
}
