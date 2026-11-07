import { redirect } from "next/navigation";

/** Los proyectos viven ahora en Cinema Studio. */
export default function ProjectsPage() {
  redirect("/cinema");
}
