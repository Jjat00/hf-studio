"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { studio } from "@/lib/studio";
import type { Generation } from "@/lib/types";

/**
 * Historial del cliente con sondeo adaptativo: cada 2,5 s mientras haya trabajos activos,
 * cada 20 s en reposo. El servidor ya hace el backoff contra Higgsfield; esto solo lee la BD propia.
 *
 * El sondeo lee solo la primera página (las más recientes) y la funde con las anteriores que ya se cargaron con
 * `loadMore` (scroll): cada página siguiente se pide por cursor (la última cargada), así lo que llega nuevo arriba
 * no repite ni salta tarjetas.
 *
 * Cada lectura lleva un número y solo se aplica si es de la consulta visible, la más nueva y posterior al último
 * cambio de la lista: una respuesta lenta de antes o de otro filtro no deshace lo que se ve ahora. Los cambios
 * (ocultar, favoritas, borrar) se aplican al momento, se envían en orden y, hasta que el servidor los confirma, se
 * vuelven a aplicar sobre cualquier lectura; al terminar, se relee la consulta vigente.
 */
/** Consulta de la lista: biblioteca, ocultas o favoritas. */
type Query = { hidden: boolean; favorite: boolean };
/** Un cambio aplicado a una lista según su consulta (quitar una estrella saca la tarjeta de Favoritas, no de Todo). */
type Change = (prev: Generation[], query: Query) => Generation[];

/** Tamaño de cada página: la primera (la que se sondea) y las que trae el scroll. */
const PAGE = 60;

/** `a` va después que `b` en el orden de la lista (más reciente primero; desempate por id, como el servidor). */
function olderThan(a: Generation, b: Generation): boolean {
  return a.created_at < b.created_at || (a.created_at === b.created_at && a.id < b.id);
}

/** La primera página recién leída más las anteriores ya cargadas que quedan por debajo de ella. */
function mergeHead(head: Generation[], prev: Generation[]): Generation[] {
  const last = head.at(-1);
  // Página incompleta: es toda la lista (lo que estaba debajo ya no existe en esta consulta).
  if (!last || head.length < PAGE) return head;
  const inHead = new Set(head.map((g) => g.id));
  return [...head, ...prev.filter((g) => !inHead.has(g.id) && olderThan(g, last))];
}

export function useGenerations({ hidden = false, favorite = false }: { hidden?: boolean; favorite?: boolean } = {}) {
  const [items, setItems] = useState<Generation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const asked = useRef(0);
  const applied = useRef(0);
  const changedAt = useRef(0);
  // Sube con cada invalidación: una página del scroll pedida antes de un cambio se descarta y se vuelve a pedir.
  const epoch = useRef(0);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  // Cambios enviados y aún sin confirmar (en orden): se aplican encima de lo que llegue del servidor.
  const pending = useRef(new Map<number, Change>());
  const changes = useRef(0);
  const visible = useRef("");
  const latestRefresh = useRef<() => Promise<Generation[] | null>>(async () => null);
  const itemsRef = useRef(items);
  const moreBusy = useRef(false);

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  // Otra consulta (otro filtro): no se muestra la lista de la anterior como si fuera de esta.
  const query = `${hidden}|${favorite}`;
  const [shownQuery, setShownQuery] = useState(query);
  if (shownQuery !== query) {
    setShownQuery(query);
    setItems([]);
    setLoading(true);
    setHasMore(true);
  }

  const withPending = useCallback(
    (list: Generation[]) => [...pending.current.values()].reduce((acc, apply) => apply(acc, { hidden, favorite }), list),
    [hidden, favorite],
  );

  const refresh = useCallback(async () => {
    const id = ++asked.current;
    const mine = `${hidden}|${favorite}`;
    try {
      const { generations } = await studio.list(PAGE, hidden, favorite);
      if (mine !== visible.current || id <= applied.current || id <= changedAt.current) return generations;
      applied.current = id;
      setItems((prev) => withPending(mergeHead(generations, prev)));
      if (generations.length < PAGE) setHasMore(false);
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
  }, [hidden, favorite, withPending]);

  /** Lo que esté en vuelo ya no vale: la lista cambió (otra consulta o un cambio hecho aquí). */
  const invalidate = useCallback(() => {
    changedAt.current = asked.current;
    epoch.current += 1;
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

  /** Trae la página siguiente (las anteriores a la última que se ve) y la añade al final. */
  const loadMore = useCallback(async () => {
    if (moreBusy.current) return;
    const mine = `${hidden}|${favorite}`;
    moreBusy.current = true;
    setLoadingMore(true);
    try {
      // Si la lista cambió mientras llegaba (un cambio confirmado, otra consulta), la página puede ser vieja:
      // se vuelve a pedir desde la última tarjeta vigente.
      for (let tries = 0; tries < 3; tries++) {
        const last = itemsRef.current.at(-1);
        if (!last || mine !== visible.current) return;
        const started = epoch.current;
        const { generations } = await studio.list(PAGE, hidden, favorite, last.id);
        if (mine !== visible.current) return;
        if (started !== epoch.current) continue;
        setItems((prev) => {
          const known = new Set(prev.map((g) => g.id));
          return [...prev, ...withPending(generations.filter((g) => !known.has(g.id)))];
        });
        if (generations.length < PAGE) setHasMore(false);
        return;
      }
    } catch (e) {
      if (mine === visible.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      moreBusy.current = false;
      setLoadingMore(false);
    }
  }, [hidden, favorite, withPending]);

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
    <T,>(optimistic: Change, send: () => Promise<T>): Promise<T> => {
      const key = ++changes.current;
      pending.current.set(key, optimistic);
      invalidate();
      setItems((prev) => optimistic(prev, { hidden, favorite }));
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
    [invalidate, hidden, favorite],
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
      const touched = new Set(ids);
      // Sale de la lista que ya no le corresponde (la biblioteca o las ocultas) y queda marcada en la otra.
      return change(
        (prev, q) => (q.hidden !== value ? prev.filter((g) => !touched.has(g.id)) : prev.map((g) => (touched.has(g.id) ? { ...g, hidden: value } : g))),
        () => studio.hide(ids, value),
      );
    },
    [change],
  );

  /** Marca o desmarca favoritas; en la vista de favoritas, las que se quitan salen al momento. */
  const setFavorite = useCallback(
    (ids: string[], value: boolean) => {
      const touched = new Set(ids);
      return change(
        (prev, q) => (q.favorite && !value ? prev.filter((g) => !touched.has(g.id)) : prev.map((g) => (touched.has(g.id) ? { ...g, favorite: value } : g))),
        () => studio.favorite(ids, value),
      );
    },
    [change],
  );

  return { items, loading, error, refresh, add, remove, setHidden, setFavorite, hasMore, loadingMore, loadMore };
}
