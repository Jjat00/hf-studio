import Link from "next/link";
import { BannerCard, FeatureCard } from "@/components/explore/feature-card";
import { HeroPrompt } from "@/components/explore/hero-prompt";
import { Recent } from "@/components/explore/recent";
import { FEATURES } from "@/lib/features";

export default function Explore() {
  const banners = FEATURES.slice(0, 3);
  const grid = FEATURES.slice(3, 9);
  const mcp = FEATURES[9];
  return (
    <div className="flex flex-col gap-14 pb-4">
      <section className="px-4 pt-2">
        <div className="grain relative flex min-h-[640px] flex-col items-center justify-center overflow-hidden rounded-[28px] px-6 text-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/art/explore-hero.webp" alt="" className="absolute inset-0 size-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-b from-black/55 via-black/25 to-black/70" />
          <div className="relative flex w-full flex-col items-center">
            <h1 className="headline max-w-4xl text-[44px] leading-[1.12] md:text-[64px]">
              Your own AI studio.
              <br />
              Every top model.
            </h1>
            <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-white/85">
              From prompt to cinematic video in minutes. Every top model, your own API,
              ready for you and your agents.
            </p>
            <Link href="/video" className="mt-6 rounded-xl bg-white px-6 py-3.5 text-[16px] font-semibold text-ink shadow-[inset_0_-3px_0_rgba(0,0,0,0.12)]">
              Create Video Now
            </Link>
            <HeroPrompt />
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-8 px-4 md:grid-cols-3">
        {banners.map((f) => (
          <BannerCard key={f.href} f={f} />
        ))}
      </section>

      <section className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Link href={mcp.href} className="grain group relative min-h-[400px] overflow-hidden rounded-[28px] bg-surface-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={mcp.art} alt="" className="absolute inset-0 size-full object-cover transition-transform duration-700 group-hover:scale-[1.02]" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/70 via-black/30 to-transparent" />
          <div className="relative flex h-full flex-col justify-between p-9">
            <div>
              <p className="headline text-[44px] leading-none md:text-[56px]">Your agents</p>
              <p className="headline text-[44px] leading-none text-lime md:text-[56px]">create too</p>
            </div>
            <ul className="space-y-2 text-[17px] text-white/85">
              <li>✓ Claude Code and Codex over MCP</li>
              <li>✓ The same API this interface uses</li>
              <li>✓ Shared history, per-client ownership</li>
            </ul>
          </div>
        </Link>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {grid.map((f) => (
            <FeatureCard key={f.href} f={f} />
          ))}
        </div>
      </section>

      <section className="px-4">
        <Link
          href="/use-cases"
          className="flex flex-col items-start justify-between gap-4 rounded-[22px] border border-line bg-surface-2 p-6 hover:border-line-2 hover:bg-surface-3 md:flex-row md:items-center"
        >
          <div>
            <p className="headline text-[26px]">What can I make?</p>
            <p className="mt-1 text-[16px] text-fg-3">12 use cases with step-by-step guides and prompts, in the UI or through your agents.</p>
          </div>
          <span className="rounded-xl bg-lime px-4 py-2.5 text-sm font-semibold text-ink">Browse use cases</span>
        </Link>
      </section>

      <Recent />
    </div>
  );
}
