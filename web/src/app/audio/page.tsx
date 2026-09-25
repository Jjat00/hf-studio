import { Suspense } from "react";
import { AudioStudio } from "@/components/audio/audio-studio";

export default function AudioPage() {
  return (
    <Suspense>
      <AudioStudio />
    </Suspense>
  );
}
