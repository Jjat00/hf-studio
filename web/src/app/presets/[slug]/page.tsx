import { PresetRunner } from "@/components/presets/preset-runner";

export default async function PresetPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <PresetRunner slug={slug} />;
}
