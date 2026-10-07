import { getDict } from "@/lib/i18n/server";
import { FlowRunner } from "@/components/spaces/flow-runner";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.spaces} · HF Studio` };
}

export default async function FlowPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <FlowRunner spaceId={id} />;
}
