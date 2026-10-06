import { getDict } from "@/lib/i18n/server";
import { SpaceEditor } from "@/components/spaces/space-editor";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.spaces} · HF Studio` };
}

export default async function SpacePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SpaceEditor id={id} />;
}
