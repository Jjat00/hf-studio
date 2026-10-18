import { redirect } from "next/navigation";
import { LoginForm } from "@/components/login-form";
import { gateEnabled, safeNext } from "@/lib/session";

export const metadata = { title: "HF Studio" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const { next } = await searchParams;
  const target = safeNext(typeof next === "string" ? next : undefined);
  if (!gateEnabled()) redirect(target);
  return <LoginForm next={target} />;
}
