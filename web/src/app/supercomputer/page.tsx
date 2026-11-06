import { Suspense } from "react";
import { Supercomputer } from "@/components/supercomputer/supercomputer";
import { getDict } from "@/lib/i18n/server";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.supercomputer} · HF Studio` };
}

export default function SupercomputerPage() {
  return (
    <Suspense fallback={null}>
      <Supercomputer />
    </Suspense>
  );
}
