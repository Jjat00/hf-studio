import { Suspense } from "react";
import { SkillLibrary } from "@/components/skills/skill-library";
import { getDict } from "@/lib/i18n/server";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.skills} · HF Studio` };
}

export default function SkillsPage() {
  return (
    <Suspense fallback={null}>
      <SkillLibrary />
    </Suspense>
  );
}
