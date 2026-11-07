import { Suspense } from "react";
import { CinemaProject } from "@/components/cinema/project";
import { getDict } from "@/lib/i18n/server";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.cinema} · HF Studio` };
}

export default async function CinemaProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense fallback={null}>
      <CinemaProject id={id} />
    </Suspense>
  );
}
