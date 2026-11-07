import { ContentFactory } from "@/components/factory/content-factory";
import { getDict } from "@/lib/i18n/server";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.factory} · HF Studio` };
}

export default function FactoryPage() {
  return <ContentFactory />;
}
