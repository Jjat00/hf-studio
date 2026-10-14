import { ArrowRight, Sparkles } from "lucide-react";
import Link from "next/link";
import { AppCard, BannerCard, FeatureCard } from "@/components/explore/feature-card";
import { HeroPrompt } from "@/components/explore/hero-prompt";
import { Recent } from "@/components/explore/recent";
import { APPS, BANNERS, TILES } from "@/lib/features";
import { getDict } from "@/lib/i18n/server";

/** Portada con la estructura de la de Higgsfield: banners, promo con accesos, AI Influencer, apps y agentes. */
export default async function Explore() {
  const t = await getDict();
  const e = t.explore;
  return (
    <div className="flex flex-col gap-12 pb-4">
      <section className="hide-scrollbar flex snap-x gap-4 overflow-x-auto px-4 pt-2 sm:grid sm:grid-cols-3 sm:overflow-visible">
        {BANNERS.map((f) => (
          <BannerCard key={f.href} f={f} />
        ))}
      </section>

      <section className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Link href="/video" className="grain group relative flex min-h-[400px] flex-col justify-between overflow-hidden rounded-[24px] bg-surface-3 p-8">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/art/explore-hero.webp" alt="" className="absolute inset-0 size-full object-cover transition-transform duration-700 group-hover:scale-[1.02]" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-black/45 to-black/10" />
          <div className="relative">
            <p className="headline text-[40px] leading-[1.02] text-lime uppercase md:text-[52px]">{e.promoTitle1}</p>
            <p className="headline text-[40px] leading-[1.02] uppercase md:text-[52px]">{e.promoTitle2}</p>
            <p className="mt-4 max-w-md text-[16px] text-white/80">{e.promoBody}</p>
          </div>
          <span className="relative mt-6 inline-flex w-fit items-center gap-2 rounded-xl bg-lime px-5 py-3 text-[16px] font-semibold text-ink shadow-[inset_0_-3px_0_rgba(80,100,0,0.35)]">
            {e.promoCta} <ArrowRight className="size-4" />
          </span>
        </Link>
        <div className="grid grid-cols-2 gap-4 xl:grid-cols-3">
          {TILES.map((f) => (
            <FeatureCard key={f.href + f.icon} f={f} />
          ))}
        </div>
      </section>

      <section className="px-4">
        <Link href="/influencer" className="grain group relative flex min-h-[380px] items-center justify-center overflow-hidden rounded-[24px] border border-line bg-surface-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/art/use-cases/portrait-alive.webp" alt="" className="absolute inset-y-0 left-0 hidden h-full w-[34%] object-cover opacity-80 [mask-image:linear-gradient(to_right,black_40%,transparent)] md:block" />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/art/use-cases/character-scenes.webp" alt="" className="absolute inset-y-0 right-0 hidden h-full w-[34%] object-cover opacity-80 [mask-image:linear-gradient(to_left,black_40%,transparent)] md:block" />
          <div className="relative flex flex-col items-center px-6 py-10 text-center">
            <span className="flex items-center gap-1.5 rounded-lg bg-lime/15 px-2.5 py-1 text-[13px] font-semibold text-lime">
              <Sparkles className="size-3.5" /> {e.influencerTag}
            </span>
            <p className="headline mt-4 text-[18px] uppercase">{e.influencerKicker}</p>
            <p className="headline mt-1 text-[40px] leading-[1.02] uppercase md:text-[56px]">{e.influencerTitle1}</p>
            <p className="headline text-[40px] leading-[1.02] text-fg-3 uppercase md:text-[56px]">{e.influencerTitle2}</p>
            <p className="mt-3 text-[17px] text-fg-3">{e.influencerBody}</p>
            <span className="mt-6 rounded-xl bg-lime px-5 py-3 text-[15px] font-semibold text-ink">{e.influencerCta}</span>
          </div>
        </Link>
      </section>

      <section className="px-4">
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <p className="headline text-[28px] text-lime uppercase">{e.appsTitle}</p>
            <p className="text-[15px] text-fg-3">{e.appsBody}</p>
          </div>
          <Link href="/presets?c=Apps" className="shrink-0 rounded-xl bg-lime px-4 py-2.5 text-sm font-semibold text-ink">
            {e.appsAll}
          </Link>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 2xl:grid-cols-8">
          {APPS.map((f) => (
            <AppCard key={f.href} f={f} />
          ))}
        </div>
      </section>

      <section className="px-4">
        <div className="grain relative flex flex-col items-center overflow-hidden rounded-[24px] border border-line bg-surface-2 px-6 py-12 text-center">
          <p className="headline text-[34px] uppercase md:text-[44px]">{e.promptTitle}</p>
          <p className="mt-2 max-w-xl text-[16px] text-fg-3">{e.heroBody}</p>
          <HeroPrompt />
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Link href="/mcp" className="grain group relative min-h-[340px] overflow-hidden rounded-[24px] bg-surface-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/art/mcp.webp" alt="" className="absolute inset-0 size-full object-cover transition-transform duration-700 group-hover:scale-[1.02]" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/75 via-black/35 to-transparent" />
          <div className="relative flex h-full flex-col justify-between p-8">
            <div>
              <p className="headline text-[40px] leading-none uppercase md:text-[52px]">{e.agentsTitle1}</p>
              <p className="headline text-[40px] leading-none text-lime uppercase md:text-[52px]">{e.agentsTitle2}</p>
            </div>
            <ul className="space-y-2 text-[16px] text-white/85">
              {e.agentsBullets.map((b) => (
                <li key={b}>✓ {b}</li>
              ))}
            </ul>
          </div>
        </Link>
        <Link
          href="/use-cases"
          className="flex flex-col justify-between gap-4 rounded-[24px] border border-line bg-surface-2 p-8 hover:border-line-2 hover:bg-surface-3"
        >
          <div>
            <p className="headline text-[30px] uppercase">{e.useCasesTitle}</p>
            <p className="mt-2 text-[16px] text-fg-3">{e.useCasesBody}</p>
          </div>
          <span className="w-fit rounded-xl bg-lime px-4 py-2.5 text-sm font-semibold text-ink">{e.useCasesCta}</span>
        </Link>
      </section>

      <Recent />
    </div>
  );
}
