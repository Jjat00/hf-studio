"use client";

import clsx from "clsx";
import { Check, Copy, ExternalLink, KeyRound, Loader2, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { formatUsd, studio } from "@/lib/studio";
import type { ProviderInfo } from "@/lib/types";

/** Proveedores: estado de cada clave, saldo y los enlaces para crear cuenta, copiar la clave o recargar. */
export default function ProvidersPage() {
  const { t } = useI18n();
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    studio
      .providers()
      .then((r) => setProviders(r.providers))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  return (
    <div className="px-4 py-8 md:px-8">
      <h1 className="headline text-[40px] md:text-[56px]">{t.providers.title}</h1>
      <p className="mt-2 max-w-3xl text-fg-3">{t.providers.intro}</p>
      {error && <p className="mt-6 text-danger">{error}</p>}
      {!providers && !error && <Loader2 className="mt-8 size-6 animate-spin text-lime" />}
      <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {providers?.map((p) => <ProviderCard key={p.name} p={p} />)}
      </div>
    </div>
  );
}

function ProviderCard({ p }: { p: ProviderInfo }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const state = !p.configured
    ? { label: t.providers.missing, tone: "bg-surface-3 text-fg-3" }
    : p.valid === false
      ? { label: t.providers.invalid, tone: "bg-danger/15 text-danger" }
      : p.valid
        ? { label: t.providers.ok, tone: "bg-success/15 text-success" }
        : { label: t.providers.unknown, tone: "bg-warning/15 text-warning" };
  const command = `uv run hf-studio providers --add ${p.name}`;
  const link = (href: string | null, label: string, Icon: typeof ExternalLink) =>
    href ? (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="flex h-9 items-center gap-1.5 rounded-xl bg-surface-3 px-3 text-sm font-medium text-fg-2 transition-colors hover:text-fg"
      >
        <Icon className="size-4" /> {label}
      </a>
    ) : null;
  return (
    <article className="flex flex-col gap-3 rounded-card border border-line bg-surface-2 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">{p.title}</h2>
          <p className="text-xs text-fg-3">{p.required ? t.providers.required : t.providers.optional}</p>
        </div>
        <span className={clsx("rounded-md px-2 py-0.5 text-xs font-semibold", state.tone)}>{state.label}</span>
      </div>
      <p className="text-sm text-fg-2">{t.providers.blurbs[p.name] ?? p.blurb}</p>
      {p.balance_usd != null && <p className="text-sm font-semibold">{t.providers.balance(formatUsd(p.balance_usd))}</p>}
      {p.message && (
        <p className="text-xs text-fg-3">{p.message.includes("minimum") ? t.providers.belowMinimum : p.message}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {!p.configured && link(p.signup_url, t.providers.signup, ExternalLink)}
        {link(p.key_url, t.providers.key, KeyRound)}
        {link(p.billing_url, t.providers.billing, Wallet)}
      </div>
      {!p.configured && (
        <div className="mt-auto text-xs text-fg-3">
          <p>{t.providers.howToAdd}</p>
          <button
            type="button"
            onClick={() => {
              void navigator.clipboard.writeText(command);
              setCopied(true);
            }}
            className="mt-1 flex w-full items-center justify-between gap-2 rounded-lg bg-surface-3 px-2.5 py-1.5 font-mono text-fg-2"
          >
            <span className="truncate">{command}</span>
            {copied ? <Check className="size-3.5 text-lime" /> : <Copy className="size-3.5" />}
          </button>
          <p className="mt-1">
            <code>{p.env_var}=…</code> · {t.providers.reload}
          </p>
        </div>
      )}
    </article>
  );
}
