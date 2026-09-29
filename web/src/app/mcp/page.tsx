import path from "node:path";
import Link from "next/link";
import { CopyBlock } from "@/components/copy-block";
import { getDict } from "@/lib/i18n/server";

export const metadata = { title: "MCP · HF Studio" };

const TOOLS = [
  "find_models",
  "get_model",
  "upload_media",
  "estimate_cost",
  "generate",
  "get_generation",
  "list_generations",
  "cancel_generation",
  "download_outputs",
  "recommend_models",
  "generate_batch",
  "wait_generations",
  "list_presets",
  "run_preset",
  "save_preset",
  "list_voices",
  "change_voice",
  "text_to_speech",
  "sound_effect",
  "compose_music",
  "isolate_voice",
  "elevenlabs_account",
  "list_sounds",
  "label_sound",
  "import_elevenlabs_history",
];

export default async function McpPage() {
  const t = await getDict();
  // La UI corre en web/: el repo es la carpeta de arriba. Va en el prompt para que el agente no la adivine.
  const root = path.resolve(process.cwd(), "..");
  const windows = process.platform === "win32";
  // Comillas simples literales: PowerShell en Windows ('' escapa la comilla), POSIX en el resto.
  const dir = windows ? `'${root.replaceAll("'", "''")}'` : `'${root.replaceAll("'", "'\\''")}'`;
  // UI en Windows y agente en WSL: la misma carpeta es /mnt/<unidad>/…
  const drive = windows ? /^([A-Za-z]):\\(.*)$/.exec(root) : null;
  const wsl = drive ? `/mnt/${drive[1].toLowerCase()}/${drive[2].replaceAll("\\", "/")}` : null;
  const run = `uv run --directory ${dir} hf-studio connect`;
  const byHand = [
    { title: "Claude Code", code: `${run} claude-code` },
    { title: "Codex", code: `${run} codex` },
    { title: "Claude Desktop", code: `${run} claude-desktop   ${t.mcp.byHandComments.claudeDesktop}` },
    { title: t.mcp.otherClient, code: `${run} json   ${t.mcp.byHandComments.other}` },
  ];
  return (
    <div className="flex flex-col gap-10 px-4 pb-16">
      <section className="grain relative mt-2 overflow-hidden rounded-[28px] px-6 py-24 text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/art/mcp.webp" alt="" className="absolute inset-0 size-full object-cover" />
        <div className="absolute inset-0 bg-black/35" />
        <div className="relative">
          <p className="text-[26px] font-semibold tracking-[-0.02em] text-white/90">{t.mcp.heroLead}</p>
          <h1 className="headline mt-2 bg-gradient-to-b from-[#ffb58a] to-[#e0663b] bg-clip-text text-[52px] text-transparent md:text-[88px]">
            Claude Code · Codex
          </h1>
          <p className="mx-auto mt-4 max-w-md text-[17px] leading-relaxed text-white/80">
            {t.mcp.heroBody}
          </p>
        </div>
      </section>
      <section className="mx-auto flex w-full max-w-5xl flex-col gap-4">
        <div>
          <h2 className="headline text-[32px]">{t.mcp.askTitle}</h2>
          <p className="mt-1 text-[15px] text-fg-3">{t.mcp.askBody}</p>
        </div>
        <CopyBlock title="Prompt" code={t.mcp.askPrompt(root, dir, wsl ? t.mcp.askWsl(wsl) : "")} wrap />
        <h3 className="mt-2 text-lg font-semibold">
          {t.mcp.byHand}
          {windows ? " · PowerShell" : ""}
        </h3>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {byHand.map((b) => (
            <CopyBlock key={b.title} title={b.title} code={b.code} wrap />
          ))}
        </div>
      </section>
      <Link
        href="/use-cases"
        className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 rounded-2xl border border-lime/25 bg-lime/5 px-5 py-4 hover:bg-lime/10"
      >
        <span>
          <span className="block font-semibold">{t.mcp.notSure}</span>
          <span className="text-[15px] text-fg-3">{t.mcp.notSureBody}</span>
        </span>
        <span className="shrink-0 text-sm font-semibold text-lime">{t.mcp.useCasesLink}</span>
      </Link>
      <section className="mx-auto w-full max-w-5xl">
        <h2 className="headline text-[32px]">{t.mcp.tools(TOOLS.length)}</h2>
        <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
          {TOOLS.map((name) => (
            <div key={name} className="rounded-[22px] border border-line bg-surface-2 p-5">
              <p className="font-mono text-[15px] font-semibold text-lime">{name}</p>
              <p className="mt-2 text-[15px] leading-snug text-fg-3">{t.mcp.toolDocs[name]}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
