"use client";

import { useLayoutEffect, useRef, useState } from "react";

/**
 * Cuadrícula masonry: cada elemento va a la columna más corta, en orden (izquierda a derecha).
 * Se posiciona en absoluto dentro de un único contenedor y se mide con ResizeObserver, así que un
 * elemento no se desmonta al cambiar de columna (un video no se recarga) y se recoloca solo cuando
 * su medio termina de cargar y cambia de alto.
 */
export function Masonry<T>({
  items,
  itemKey,
  render,
  maxColumns,
  minColumnWidth = 260,
  gap = 16,
}: {
  items: T[];
  itemKey: (item: T) => string;
  render: (item: T) => React.ReactNode;
  maxColumns: number;
  minColumnWidth?: number;
  gap?: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const nodes = useRef(new Map<string, HTMLDivElement>());
  const [width, setWidth] = useState(0);
  const [heights, setHeights] = useState<Record<string, number>>({});

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const keys = items.map(itemKey).join("|");
  useLayoutEffect(() => {
    const ro = new ResizeObserver((entries) => {
      setHeights((prev) => {
        let next = prev;
        for (const e of entries) {
          const key = (e.target as HTMLElement).dataset.key!;
          const h = Math.round(e.borderBoxSize?.[0]?.blockSize ?? (e.target as HTMLElement).offsetHeight);
          if (prev[key] !== h) next = next === prev ? { ...prev, [key]: h } : Object.assign(next, { [key]: h });
        }
        return next;
      });
    });
    nodes.current.forEach((n) => ro.observe(n));
    return () => ro.disconnect();
  }, [keys]);

  const cols = Math.max(1, Math.min(maxColumns, Math.floor((width + gap) / (minColumnWidth + gap)) || 1));
  const colWidth = width ? (width - gap * (cols - 1)) / cols : 0;
  const tops = Array<number>(cols).fill(0);
  const placed = items.map((item) => {
    const key = itemKey(item);
    const col = tops.indexOf(Math.min(...tops));
    const pos = { key, x: col * (colWidth + gap), y: tops[col] };
    tops[col] += (heights[key] ?? (colWidth * 9) / 16) + gap;
    return { item, ...pos };
  });

  return (
    <div
      ref={box}
      className="relative w-full"
      style={{ height: Math.max(0, Math.max(...tops) - gap), visibility: width ? "visible" : "hidden" }}
    >
      {placed.map(({ item, key, x, y }) => (
        <div
          key={key}
          data-key={key}
          ref={(n) => {
            if (n) nodes.current.set(key, n);
            else nodes.current.delete(key);
          }}
          className="absolute top-0 left-0 transition-transform duration-300 ease-out"
          style={{ width: colWidth, transform: `translate(${x}px, ${y}px)` }}
        >
          {render(item)}
        </div>
      ))}
    </div>
  );
}
