import { KatanaStudio } from "@/components/katana/katana-studio";
import { getDict } from "@/lib/i18n/server";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.katana} · HF Studio` };
}

export default function KatanaPage() {
  return <KatanaStudio />;
}
