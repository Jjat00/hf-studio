import { Suspense } from "react";
import { CinemaHome } from "@/components/cinema/home";
import { getDict } from "@/lib/i18n/server";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.cinema} · HF Studio` };
}

export default function CinemaPage() {
  return (
    <Suspense fallback={null}>
      <CinemaHome />
    </Suspense>
  );
}
