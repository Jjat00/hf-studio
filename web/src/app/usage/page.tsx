"use client";

import clsx from "clsx";
import { ExternalLink, Info, Loader2, Wallet } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { formatUsd, studio } from "@/lib/studio";
import type { ModelSummary, ProviderInfo, Usage, UsageGroup, VoiceStatus } from "@/lib/types";

const PERIODS = ["month", "d7", "d30", "d90", "all"] as const;
type Period = (typeof PERIODS)[number];
const ELEVENLABS_BILLING = "https://elevenlabs.io/app/subscription";
const TOP_MODELS = 8;

/** Días que pide cada período a la API (0 = todo); «este mes» cuenta desde el día 1 en la hora local. */
function daysOf(period: Period) {
  if (period === "month") return new Date().getDate();
  if (period === "all") return 0;
  return Number(period.slice(1));
}

/** Uso: gasto por día, proveedor y modelo (precio cotizado de cada generación terminada) y saldos actuales. */
export default function UsagePage() {
  const { t } = useI18n();
  const [period, setPeriod] = useState<Period>("month");
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Período de los datos que se ven: si no coincide con el elegido, hay una consulta en curso.
  const [loaded, setLoaded] = useState<Period | null>(null);
  const loading = loaded !== period;
  const [models, setModels] = useState<Map<string, ModelSummary>>(new Map());

  useEffect(() => {
    studio.models().then((r) => setModels(new Map(r.models.map((m) => [m.id, m])))).catch(() => undefined);
  }, []);

  useEffect(() => {
    let alive = true;
    studio
      .usage(daysOf(period), -new Date().getTimezoneOffset())
      .then((u) => alive && (setUsage(u), setError(null)))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => alive && setLoaded(period));
    return () => {
      alive = false;
    };
  }, [period]);

  const providerName = (name: string) => t.usage.names[name] ?? name;
  const priced = usage ? usage.generations - usage.unpriced : 0;

  return (
    <div className="px-4 py-8 md:px-8">
      <h1 className="headline text-[40px] md:text-[56px]">{t.usage.title}</h1>
      <p className="mt-2 max-w-3xl text-fg-3">{t.usage.intro}</p>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        {PERIODS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setPeriod(p)}
            aria-pressed={period === p}
            className={clsx(
              "h-10 rounded-xl px-4 text-[15px] font-medium transition-colors",
              period === p ? "bg-surface-4 text-fg" : "text-fg-3 hover:text-fg-2",
            )}
          >
            {t.usage.periods[p]}
          </button>
        ))}
        {loading && usage && <Loader2 className="size-4 animate-spin text-fg-3" />}
      </div>

      {error && <p className="mt-6 rounded-2xl bg-danger/10 p-4 text-sm text-danger">{error}</p>}
      {!usage && !error && <Loader2 className="mt-8 size-6 animate-spin text-lime" />}

      {usage && (
        <>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <Tile label={t.usage.total} value={formatUsd(usage.total_usd)} big>
              {usage.approx_usd > 0 && <p className="text-xs text-fg-3">{t.usage.approx(formatUsd(usage.approx_usd))}</p>}
            </Tile>
            <Tile label={t.usage.generations} value={String(usage.generations)}>
              {usage.unpriced > 0 && (
                <p className="flex items-center gap-1 text-xs text-fg-3" title={t.usage.unpricedHint}>
                  <Info className="size-3.5 shrink-0" /> {t.usage.unpriced(usage.unpriced)}
                </p>
              )}
            </Tile>
            <Tile label={t.usage.average} value={priced ? formatUsd(usage.total_usd / priced) : "—"} />
          </div>

          {usage.generations === 0 ? (
            <p className="mt-10 text-center text-fg-3">{t.usage.empty}</p>
          ) : (
            <>
              <section className="mt-6 rounded-card border border-line bg-surface-2 p-5">
                <h2 className="text-lg font-semibold">{t.usage.perDay}</h2>
                <DayChart days={usage.days} />
              </section>
              <div className="mt-6 grid gap-6 xl:grid-cols-2">
                <ShareTable
                  title={t.usage.byProvider}
                  head={t.usage.provider}
                  total={usage.total_usd}
                  rows={usage.providers.map((p) => ({ ...p, key: p.provider, name: providerName(p.provider) }))}
                />
                <ShareTable
                  title={t.usage.byModel}
                  head={t.usage.model}
                  total={usage.total_usd}
                  limit={TOP_MODELS}
                  rows={usage.models.map((m) => ({
                    ...m,
                    key: `${m.model}|${m.provider}`,
                    name: models.get(m.model)?.title.replace(/ API$/, "") ?? m.model,
                    detail: `${providerName(m.provider)} · ${m.model}`,
                  }))}
                />
              </div>
            </>
          )}
        </>
      )}

      <Balances />
    </div>
  );
}

function Tile({ label, value, big, children }: { label: string; value: string; big?: boolean; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 rounded-card border border-line bg-surface-2 p-5">
      <p className="text-sm text-fg-3">{label}</p>
      <p className={clsx("font-semibold tabular-nums", big ? "text-4xl text-lime" : "text-3xl")}>{value}</p>
      {children}
    </div>
  );
}

/** Un techo «redondo» para el eje: 1, 2 o 5 por una potencia de diez. */
function niceMax(max: number) {
  if (max <= 0) return 1;
  const step = 10 ** Math.floor(Math.log10(max));
  return ([1, 2, 5, 10].find((m) => m * step >= max) ?? 10) * step;
}

function shortDate(iso: string) {
  const [, m, d] = iso.split("-");
  return `${Number(d)}/${Number(m)}`;
}

/** Barras del gasto diario (una serie): eje con tres guías y tooltip al pasar sobre cada día. */
function DayChart({ days }: { days: Usage["days"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const top = niceMax(Math.max(...days.map((d) => d.usd)));
  const ticks = [top, top / 2, 0];
  const labels = days.length > 1 ? [0, Math.floor((days.length - 1) / 2), days.length - 1] : [0];
  const shown = hover != null ? days[hover] : null;
  return (
    <div className="mt-4 flex gap-3">
      <div className="flex h-48 flex-col justify-between pb-5 text-right text-[11px] text-fg-3 tabular-nums">
        {ticks.map((v) => (
          <span key={v} className="-translate-y-1/2 first:translate-y-0 last:translate-y-0">
            {formatUsd(v)}
          </span>
        ))}
      </div>
      <div className="relative min-w-0 flex-1">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-43 border-t border-b border-line">
          <div className="absolute inset-x-0 top-1/2 border-t border-dashed border-line" />
        </div>
        <div className="flex h-43 items-end gap-0.5" onMouseLeave={() => setHover(null)}>
          {days.map((d, i) => (
            <div
              key={d.date}
              role="img"
              aria-label={`${d.date}: ${formatUsd(d.usd)}`}
              onMouseEnter={() => setHover(i)}
              className="flex h-full min-w-0 flex-1 items-end justify-center"
            >
              <div
                className={clsx(
                  "w-full max-w-10 rounded-t-[3px] transition-colors",
                  d.usd > 0 ? (hover === i ? "bg-lime-300" : "bg-lime") : "bg-transparent",
                )}
                style={{ height: d.usd > 0 ? `max(${(d.usd / top) * 100}%, 2px)` : 0 }}
              />
            </div>
          ))}
        </div>
        <div className="relative mt-1 h-4 text-[11px] text-fg-3">
          {labels.map((i) => (
            <span
              key={i}
              className="absolute -translate-x-1/2 first:translate-x-0 last:-translate-x-full"
              style={{ left: `${((i + 0.5) / days.length) * 100}%` }}
            >
              {shortDate(days[i].date)}
            </span>
          ))}
        </div>
        {shown && hover != null && (
          <div
            className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full rounded-lg border border-line-2 bg-surface-4 px-2.5 py-1.5 text-xs whitespace-nowrap shadow-lg"
            style={{ left: `${((hover + 0.5) / days.length) * 100}%` }}
          >
            <span className="text-fg-3">{shortDate(shown.date)}</span>{" "}
            <span className="font-semibold tabular-nums">{formatUsd(shown.usd)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

type Row = UsageGroup & { key: string; name: string; detail?: string };

/** Tabla con la parte de cada fila en el total (barra fina) y su número de generaciones. */
function ShareTable({ title, head, rows, total, limit }: { title: string; head: string; rows: Row[]; total: number; limit?: number }) {
  const { t } = useI18n();
  const [all, setAll] = useState(false);
  const shown = limit && !all ? rows.slice(0, limit) : rows;
  return (
    <section className="rounded-card border border-line bg-surface-2 p-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      <table className="mt-3 w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-fg-3">
            <th className="pb-2 font-medium">{head}</th>
            <th className="w-1/4 pb-2 font-medium">{t.usage.share}</th>
            <th className="pb-2 text-right font-medium">USD</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => {
            const pct = total > 0 ? (r.usd / total) * 100 : 0;
            return (
              <tr key={r.key} className="border-t border-line">
                <td className="py-2 pr-3">
                  <p className="font-medium">{r.name}</p>
                  <p className="text-xs text-fg-3">
                    {r.detail ? `${r.detail} · ` : ""}
                    {t.usage.count(r.generations)}
                    {r.unpriced > 0 && ` · ${t.usage.unpriced(r.unpriced)}`}
                  </p>
                </td>
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 flex-1 rounded-full bg-surface-4">
                      <div className="h-full rounded-full bg-lime" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="w-9 text-right text-xs text-fg-3 tabular-nums">{Math.round(pct)}%</span>
                  </div>
                </td>
                <td className="py-2 text-right font-semibold tabular-nums">{formatUsd(r.usd)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {limit && rows.length > limit && (
        <button type="button" onClick={() => setAll(!all)} className="mt-3 text-sm font-medium text-lime hover:text-lime-300">
          {all ? t.usage.showLess : t.usage.showAll(rows.length)}
        </button>
      )}
    </section>
  );
}

/** Saldo actual de cada proveedor de video e imagen (GET /v1/providers) y los créditos de ElevenLabs. */
function Balances() {
  const { t, locale } = useI18n();
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);
  const [voice, setVoice] = useState<VoiceStatus | null>(null);
  useEffect(() => {
    studio.providers().then((r) => setProviders(r.providers)).catch(() => setProviders([]));
    studio.voiceStatus().then(setVoice).catch(() => setVoice({ configured: false }));
  }, []);
  const cards = useMemo(() => {
    const list = (providers ?? []).map((p) => ({
      key: p.name,
      title: p.title,
      value: !p.configured
        ? t.usage.missingKey
        : p.balance_usd != null
          ? formatUsd(p.balance_usd)
          : t.usage.noBalance,
      strong: p.configured && p.balance_usd != null,
      note: null as string | null,
      href: p.billing_url,
    }));
    if (voice?.configured) {
      const fmt = (n: number | null | undefined) => (n ?? 0).toLocaleString(locale);
      const known = voice.credits_left != null;
      list.push({
        key: "elevenlabs",
        title: "ElevenLabs",
        value: known ? fmt(voice.credits_left) : t.usage.noBalance,
        strong: known,
        note: known ? t.usage.credits(fmt(voice.credits_limit)) : null,
        href: ELEVENLABS_BILLING,
      });
    }
    return list;
  }, [providers, voice, t, locale]);

  return (
    <section className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-2xl font-semibold">{t.usage.balances}</h2>
          <p className="text-sm text-fg-3">{t.usage.balancesIntro}</p>
        </div>
        <Link href="/providers" className="text-sm font-medium text-lime hover:text-lime-300">
          {t.usage.manage}
        </Link>
      </div>
      {!providers ? (
        <Loader2 className="mt-4 size-5 animate-spin text-lime" />
      ) : (
        <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {cards.map((c) => (
            <article key={c.key} className="flex flex-col gap-2 rounded-card border border-line bg-surface-2 p-5">
              <h3 className="font-semibold">{c.title}</h3>
              <p className={clsx(c.strong ? "text-2xl font-semibold tabular-nums" : "text-sm text-fg-3")}>{c.value}</p>
              {c.note && <p className="-mt-1 text-xs text-fg-3">{c.note}</p>}
              {c.href && (
                <a
                  href={c.href}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-auto flex h-9 w-fit items-center gap-1.5 rounded-xl bg-surface-3 px-3 text-sm font-medium text-fg-2 transition-colors hover:text-fg"
                >
                  <Wallet className="size-4" /> {t.usage.recharge}
                  <ExternalLink className="size-3.5 text-fg-3" />
                </a>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
