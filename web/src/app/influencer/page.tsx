import clsx from "clsx";
import Link from "next/link";
import { PresetRunner } from "@/components/presets/preset-runner";
import { getDict } from "@/lib/i18n/server";

/** AI Influencer, como en Higgsfield: primero creas el personaje por rasgos y luego le das movimiento. */
export default async function InfluencerPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const t = await getDict();
  const motion = (await searchParams).tab === "motion";
  const slug = motion ? "influencer-motion" : "ai-influencer";
  const tabs = (
    <div className="grid shrink-0 grid-cols-2 gap-1 rounded-2xl bg-surface-2 p-1">
      {[
        ["/influencer", t.influencer.create, !motion],
        ["/influencer?tab=motion", t.influencer.motion, motion],
      ].map(([href, label, active]) => (
        <Link
          key={href as string}
          href={href as string}
          className={clsx(
            "rounded-xl py-2 text-center text-sm font-semibold transition-colors",
            active ? "bg-surface-4 text-fg" : "text-fg-3 hover:text-fg",
          )}
        >
          {label as string}
        </Link>
      ))}
    </div>
  );
  return <PresetRunner key={slug} slug={slug} back="/" tabs={tabs} />;
}
