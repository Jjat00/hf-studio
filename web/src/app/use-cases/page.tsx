import { Suspense } from "react";
import { getDict } from "@/lib/i18n/server";
import { UseCaseGallery } from "@/components/use-cases/use-case-gallery";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.useCases} · HF Studio` };
}

export default function UseCasesPage() {
  return (
    <Suspense>
      <UseCaseGallery />
    </Suspense>
  );
}
