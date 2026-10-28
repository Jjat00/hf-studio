"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { studio } from "@/lib/studio";
import type { Generation } from "@/lib/types";

/**
 * Historial del cliente con sondeo adaptativo: cada 2,5 s mientras haya trabajos activos,
 * cada 20 s en reposo. El servidor ya hace el backoff contra Higgsfield; esto solo lee la BD propia.
 *
 * Cada lectura lleva un número y solo se aplica si es de la consulta visible, la más nueva y posterior al último
 * cambio de la lista: una respuesta lenta de antes o de otro filtro no deshace lo que se ve ahora. Los cambios
 * (ocultar, favoritas, borrar) se aplican al momento, se envían en orden y, hasta que el servidor los confirma, se
 * vuelven a aplicar sobre cualquier lectura; al terminar, se relee la consulta vigente.
 */
export function useGenerations({ hidden = false, favorite = false }: { hidden?: boolean; favorite?: boolean } = {}) {
  const [items, setItems] = useState<Generation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const asked = useRef(0);
  const applied = useRef(0);
  const changedAt = useRef(0);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  // Cambios enviados y aún sin confirmar (en orden): se aplican encima de lo que llegue del servidor.
  const pending = useRef(new Map<number, (prev: Generation[]) => Generation[]>());
  const changes = useRef(0);
  const visible = useRef("");
  const latestRefresh = useRef<() => Promise<Generation[] | null>>(async () => null);

  // Otra consulta (otro filtro): no se muestra la lista de la anterior como si fuera de esta.
  const query = `${hidden}|${favorite}`;
  const [shownQuery, setShownQuery] = useState(query);
  if (shownQuery !== query) {
    setShownQuery(query);
    setItems([]);
    setLoading(true);
  }

  const refresh = useCallback(async () => {
    const id = ++asked.current;
    const mine = `${hidden}|${favorite}`;
    try {
      const { generations } = await studio.list(80, hidden, favorite);
      if (mine !== visible.current || id <= applied.current || id <= changedAt.current) return generations;
      applied.current = id;
      setItems([...pending.current.values()].reduce((list, apply) => apply(list), generations));
      setError(null);
      setLoading(false);
      return generations;
    } catch (e) {
      if (mine === visible.current && id > applied.current && id > changedAt.current) {
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      }
      return null;
    }
  }, [hidden, favorite]);

  /** Lo que esté en vuelo ya no vale: la lista cambió (otra consulta o un cambio hecho aquí). */
  const invalidate = useCallback(() => {
    changedAt.current = asked.current;
  }, []);

  useEffect(() => {
    visible.current = `${hidden}|${favorite}`;
    latestRefresh.current = refresh;
    invalidate();
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
  }, [refresh, invalidate, hidden, favorite]);

  /** Inserta una generación recién creada y acelera el siguiente sondeo. */
  const add = useCallback(
    (g: Generation) => {
      invalidate();
      setItems((prev) => [g, ...prev.filter((p) => p.id !== g.id)]);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(async function tick() {
        const list = await refresh();
        const active = list?.some((x) => !x.terminal);
        timer.current = setTimeout(tick, active ? 2500 : 20000);
      }, 1500);
    },
    [refresh, invalidate],
  );

  /** Un cambio de la lista: se ve al momento (`optimistic`), se envía en orden tras los anteriores y, al terminar
   * (bien o mal), se descarta lo leído mientras tanto y se vuelve a leer el estado confirmado. */
  const change = useCallback(
    <T,>(optimistic: (prev: Generation[]) => Generation[], send: () => Promise<T>): Promise<T> => {
      const key = ++changes.current;
      pending.current.set(key, optimistic);
      invalidate();
      setItems(optimistic);
      const run = queue.current.then(send, send);
      queue.current = run.catch(() => undefined);
      const settle = () => {
        // Confirmado (o rechazado): deja de reaplicarse y se relee la consulta que se ve ahora.
        pending.current.delete(key);
        invalidate();
        void latestRefresh.current();
      };
      run.then(settle, settle);
      return run;
    },
    [invalidate],
  );

  /** Borra del historial una generación terminada. */
  const remove = useCallback(
    async (id: string) => {
      await change((prev) => prev.filter((g) => g.id !== id), () => studio.remove(id)).catch(() => undefined);
    },
    [change],
  );

  /** Oculta o vuelve a mostrar varias: salen de esta lista al momento. */
  const setHidden = useCallback(
    (ids: string[], value: boolean) => {
      const gone = new Set(ids);
      return change((prev) => prev.filter((g) => !gone.has(g.id)), () => studio.hide(ids, value));
    },
    [change],
  );

  /** Marca o desmarca favoritas; en la vista de favoritas, las que se quitan salen al momento. */
  const setFavorite = useCallback(
    (ids: string[], value: boolean) => {
      const touched = new Set(ids);
      return change(
        (prev) => (favorite && !value ? prev.filter((g) => !touched.has(g.id)) : prev.map((g) => (touched.has(g.id) ? { ...g, favorite: value } : g))),
        () => studio.favorite(ids, value),
      );
    },
    [change, favorite],
  );

  return { items, loading, error, refresh, add, remove, setHidden, setFavorite };
}
