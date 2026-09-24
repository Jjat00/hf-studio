"use client";

import clsx from "clsx";
import { humanize, type Field } from "@/lib/schema";

/** Tarjeta de ajuste al estilo de Higgsfield: etiqueta gris arriba, valor en blanco. */
export function SettingCard({ label, children, error, className }: { label: string; children: React.ReactNode; error?: string; className?: string }) {
  return (
    <div className={clsx("rounded-2xl border bg-surface-3 px-4 py-3", error ? "border-danger/60" : "border-line", className)}>
      <p className="mb-2 text-[13px] text-fg-3">{label}</p>
      {children}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}

function formatOption(key: string, v: string | number) {
  if (key === "duration") return `${v}s`;
  return String(v);
}

export function FieldControl({
  field,
  value,
  onChange,
  error,
}: {
  field: Exclude<Field, { kind: "prompt" } | { kind: "media" }>;
  value: unknown;
  onChange: (v: unknown) => void;
  error?: string;
}) {
  const label = humanize(field.key) + (field.required ? "" : "");
  switch (field.kind) {
    case "enum": {
      const many = field.options.length > 6;
      return (
        <SettingCard label={label} error={error}>
          {many ? (
            <select
              value={value === undefined ? "" : String(value)}
              onChange={(e) => {
                const raw = e.target.value;
                const opt = field.options.find((o) => String(o) === raw);
                onChange(raw === "" ? undefined : opt);
              }}
              className="w-full rounded-lg bg-surface-4 px-2.5 py-2 text-sm font-semibold outline-none"
            >
              {!field.required && <option value="">Auto</option>}
              {field.options.map((o) => (
                <option key={String(o)} value={String(o)}>
                  {formatOption(field.key, o)}
                </option>
              ))}
            </select>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {!field.required && field.schema.default === undefined && (
                <Chip active={value === undefined} onClick={() => onChange(undefined)}>
                  Auto
                </Chip>
              )}
              {field.options.map((o) => (
                <Chip key={String(o)} active={value === o} onClick={() => onChange(o)}>
                  {formatOption(field.key, o)}
                </Chip>
              ))}
            </div>
          )}
        </SettingCard>
      );
    }
    case "range": {
      const current = typeof value === "number" ? value : (field.schema.default as number | undefined) ?? field.min;
      return (
        <SettingCard label={label} error={error}>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={field.min}
              max={field.max}
              step={field.integer ? 1 : (field.max - field.min) / 100}
              value={current}
              onChange={(e) => onChange(field.integer ? parseInt(e.target.value, 10) : parseFloat(e.target.value))}
              className="h-1 flex-1 cursor-pointer"
            />
            <span className="w-12 text-right font-semibold tabular-nums">
              {field.key === "duration" ? `${current}s` : current}
            </span>
          </div>
        </SettingCard>
      );
    }
    case "toggle": {
      const on = value === true;
      return (
        <button
          type="button"
          onClick={() => onChange(!on)}
          className="flex w-full items-center justify-between rounded-2xl border border-line bg-surface-3 px-4 py-3 text-left"
        >
          <span>
            <span className="block text-[13px] text-fg-3">{label}</span>
            <span className="text-[15px] font-semibold">{on ? "On" : "Off"}</span>
          </span>
          <span className={clsx("relative h-6 w-10 rounded-full transition-colors", on ? "bg-lime" : "bg-surface-5")}>
            <span
              className={clsx(
                "absolute top-1 size-4 rounded-full transition-all",
                on ? "left-5 bg-ink" : "left-1 bg-fg-2",
              )}
            />
          </span>
        </button>
      );
    }
    case "number":
      return (
        <SettingCard label={label} error={error}>
          <input
            type="number"
            value={typeof value === "number" ? value : ""}
            onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
            placeholder={field.schema.description ?? "Empty = random"}
            className="w-full bg-transparent text-[15px] font-semibold outline-none placeholder:font-normal placeholder:text-fg-4"
          />
        </SettingCard>
      );
    case "text":
      return (
        <SettingCard label={label} error={error}>
          {field.multiline ? (
            <textarea
              value={typeof value === "string" ? value : ""}
              onChange={(e) => onChange(e.target.value || undefined)}
              rows={2}
              className="w-full resize-none bg-transparent text-[15px] outline-none placeholder:text-fg-4"
              placeholder={field.schema.description}
            />
          ) : (
            <input
              value={typeof value === "string" ? value : ""}
              onChange={(e) => onChange(e.target.value || undefined)}
              className="w-full bg-transparent text-[15px] outline-none placeholder:text-fg-4"
              placeholder={field.schema.description}
            />
          )}
        </SettingCard>
      );
    case "json":
      return <JsonControl label={label} value={value} onChange={onChange} error={error} />;
  }
}

function JsonControl({ label, value, onChange, error }: { label: string; value: unknown; onChange: (v: unknown) => void; error?: string }) {
  return (
    <SettingCard label={`${label} (JSON)`} error={error}>
      <textarea
        defaultValue={value === undefined ? "" : JSON.stringify(value, null, 2)}
        onBlur={(e) => {
          const raw = e.target.value.trim();
          if (!raw) return onChange(undefined);
          try {
            onChange(JSON.parse(raw));
          } catch {
            /* se deja tal cual; el backend devolverá el error de validación */
          }
        }}
        rows={4}
        spellCheck={false}
        className="w-full resize-y bg-transparent font-mono text-xs outline-none"
      />
    </SettingCard>
  );
}

export function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "h-8 rounded-lg border-2 px-2.5 text-xs font-semibold transition-colors",
        active ? "border-lime/70 bg-lime/10 text-lime" : "border-transparent bg-glass text-fg hover:bg-white/10",
      )}
    >
      {children}
    </button>
  );
}
