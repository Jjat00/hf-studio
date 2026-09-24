import { Suspense } from "react";
import { VoiceStudio } from "@/components/voice/voice-studio";

export default function VoicePage() {
  return (
    <Suspense>
      <VoiceStudio />
    </Suspense>
  );
}
