import { Suspense } from "react";
import { Studio } from "@/components/studio/studio";

export const metadata = { title: "Video · HF Studio" };

export default function VideoPage() {
  return (
    <Suspense>
      <Studio output="video" />
    </Suspense>
  );
}
