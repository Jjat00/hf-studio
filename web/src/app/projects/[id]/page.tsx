import { ProjectView } from "@/components/projects/project-view";
import { getDict } from "@/lib/i18n/server";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.projects} · HF Studio` };
}

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProjectView id={id} />;
}
