import { ProjectList } from "@/components/projects/project-list";
import { getDict } from "@/lib/i18n/server";

export async function generateMetadata() {
  return { title: `${(await getDict()).meta.projects} · HF Studio` };
}

export default function ProjectsPage() {
  return <ProjectList />;
}
