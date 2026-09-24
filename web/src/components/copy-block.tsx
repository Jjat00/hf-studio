"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/components/i18n-provider";

export function CopyBlock({ title, code }: { title: string; code: string }) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface-2">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <p className="text-sm font-semibold">{title}</p>
        <button
          type="button"
          onClick={() => {
            navigator.clipboard.writeText(code);
            setDone(true);
            setTimeout(() => setDone(false), 1500);
          }}
          className="flex items-center gap-1.5 rounded-lg bg-glass px-2.5 py-1 text-xs font-medium text-fg-2 hover:text-fg"
        >
          {done ? <Check className="size-3.5 text-lime" /> : <Copy className="size-3.5" />}
          {done ? t.copy.copied : t.copy.copy}
        </button>
      </div>
      <pre className="thin-scrollbar overflow-x-auto p-4 font-mono text-[13px] leading-relaxed text-fg-2">{code}</pre>
    </div>
  );
}
