"use client";

import { Lock } from "lucide-react";
import { useState } from "react";
import { useI18n } from "./i18n-provider";
import { Logo } from "./logo";

export function LoginForm({ next }: { next: string }) {
  const { t } = useI18n();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        // Navegación completa: el proxy vuelve a leer la cookie recién puesta.
        window.location.assign(next);
        return;
      }
      setError(res.status === 401 ? t.login.wrong : res.status === 429 ? t.login.limited : t.login.failed);
    } catch {
      setError(t.login.failed);
    }
    setBusy(false);
  }

  return (
    <div className="flex flex-1 items-center justify-center px-4 py-16">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl border border-line bg-surface-1 p-6">
        <div className="mb-5 flex items-center gap-2">
          <Logo />
          <span className="text-[15px] font-semibold">HF Studio</span>
        </div>
        <h1 className="text-xl font-semibold">{t.login.title}</h1>
        <p className="mt-2 text-sm text-fg-2">{t.login.body}</p>
        <label className="mt-5 flex items-center gap-2 rounded-xl border border-line-2 bg-surface-2 px-3">
          <Lock className="size-4 text-fg-3" />
          <input
            type="password"
            autoFocus
            required
            autoComplete="current-password"
            aria-label={t.login.password}
            placeholder={t.login.password}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-11 flex-1 bg-transparent text-[15px] outline-none placeholder:text-fg-3"
          />
        </label>
        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={busy || !password}
          className="mt-5 flex h-11 w-full items-center justify-center rounded-xl bg-lime text-sm font-semibold text-ink disabled:opacity-50"
        >
          {t.login.submit}
        </button>
      </form>
    </div>
  );
}
