import { Suspense } from "react";
import { UseCaseGallery } from "@/components/use-cases/use-case-gallery";

export const metadata = { title: "Use cases · HF Studio" };

export default function UseCasesPage() {
  return (
    <Suspense>
      <UseCaseGallery />
    </Suspense>
  );
}
