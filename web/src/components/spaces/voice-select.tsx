"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { SettingCard } from "@/components/studio/controls";
import { studio } from "@/lib/studio";
import type { Voice } from "@/lib/types";

/** Voz de un nodo de voz en off: las voces de la cuenta de ElevenLabs (sin escribir su voice_id a mano). */
export function VoiceSelect({ value, onChange }: { value: string | undefined; onChange: (id: string | undefined) => void }) {
  const { t } = useI18n();
  const s = t.spaces;
  const [voices, setVoices] = useState<Voice[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    studio.voices("", false).then(
      (r) => setVoices(r.voices),
      () => {
        setError(true);
        setVoices([]);
      },
    );
  }, []);

  const known = voices?.some((v) => v.voice_id === value);
  return (
    <SettingCard label={s.voice}>
      {voices === null ? (
        <div className="shimmer h-9 rounded-lg" />
      ) : (
        <select
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value || undefined)}
          className="w-full rounded-lg bg-surface-4 px-2.5 py-2 text-sm font-semibold outline-none"
        >
          <option value="">{s.pickVoice}</option>
          {value && !known && <option value={value}>{value}</option>}
          {voices.map((v) => (
            <option key={v.voice_id} value={v.voice_id}>
              {v.name}
            </option>
          ))}
        </select>
      )}
      {error && <p className="mt-1.5 text-xs text-danger">{s.voicesError}</p>}
      {voices?.length === 0 && !error && <p className="mt-1.5 text-xs text-fg-3">{s.noVoices}</p>}
    </SettingCard>
  );
}
