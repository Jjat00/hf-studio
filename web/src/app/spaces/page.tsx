import { getDict } from "@/lib/i18n/server";
import { SpacesList } from "@/components/spaces/spaces-list";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.spaces} · HF Studio` };
}

export default function SpacesPage() {
  return <SpacesList />;
}
