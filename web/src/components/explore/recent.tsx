"use client";

import Link from "next/link";
import { GenerationCard } from "@/components/generations/generation-card";
import { useGenerations } from "@/components/generations/use-generations";

/** Últimas creaciones del cliente en la portada. */
export function Recent() {
  const { items, loading, remove } = useGenerations();
  if (loading || items.length === 0) return null;
  return (
    <section className="px-4 pb-16">
      <div className="mb-5 flex items-end justify-between">
        <h2 className="headline text-[32px]">Your latest creations</h2>
        <Link href="/history" className="text-sm font-medium text-fg-3 hover:text-fg">
          View all →
        </Link>
      </div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {items.slice(0, 8).map((g) => (
          <GenerationCard key={g.id} g={g} layout="grid" onDelete={remove} />
        ))}
      </div>
    </section>
  );
}
