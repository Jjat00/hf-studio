import { Suspense } from "react";
import { ElementLibrary } from "@/components/elements/element-library";

export default function ElementsPage() {
  return (
    <Suspense>
      <ElementLibrary />
    </Suspense>
  );
}
