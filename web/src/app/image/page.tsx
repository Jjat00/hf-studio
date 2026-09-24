import { Suspense } from "react";
import { getDict } from "@/lib/i18n/server";
import { Studio } from "@/components/studio/studio";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.image} · HF Studio` };
}

export default function ImagePage() {
  return (
    <Suspense>
      <Studio output="image" />
    </Suspense>
  );
}
