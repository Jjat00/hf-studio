import { Suspense } from "react";
import { Studio } from "@/components/studio/studio";

export const metadata = { title: "Image · HF Studio" };

export default function ImagePage() {
  return (
    <Suspense>
      <Studio output="image" />
    </Suspense>
  );
}
