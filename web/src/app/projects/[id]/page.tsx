import { redirect } from "next/navigation";

/** Un proyecto se abre en su espacio de Cinema Studio. */
export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/cinema/${id}`);
}
