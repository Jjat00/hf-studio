import { Suspense } from "react";
import { getDict } from "@/lib/i18n/server";
import { Studio } from "@/components/studio/studio";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.video} · HF Studio` };
}

export default function VideoPage() {
  return (
    <Suspense>
      <Studio output="video" />
    </Suspense>
  );
}
