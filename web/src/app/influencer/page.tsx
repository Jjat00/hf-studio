import { InfluencerStudio } from "@/components/influencer/influencer-studio";

/** AI Influencer, como en Higgsfield: personaje por rasgos (con el modelo que elijas) y luego su movimiento. */
export default async function InfluencerPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const motion = (await searchParams).tab === "motion";
  return <InfluencerStudio key={motion ? "motion" : "create"} initialTab={motion ? "motion" : "create"} />;
}
