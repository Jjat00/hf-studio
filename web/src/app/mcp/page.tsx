import Link from "next/link";
import { CopyBlock } from "@/components/copy-block";
import { getDict } from "@/lib/i18n/server";

export const metadata = { title: "MCP · HF Studio" };

const claude = (comment: string) => `uv run hf-studio create-key claude-code   ${comment}

claude mcp add hf-studio --scope user \\
  -e HF_STUDIO_URL=http://127.0.0.1:8787 -e HF_STUDIO_TOKEN=hfs_… \\
  -- uv run --directory /ruta/absoluta/a/hf-studio hf-studio mcp`;

const CODEX = `# ~/.codex/config.toml
[mcp_servers.hf-studio]
command = "uv"
args = ["run", "--directory", "/ruta/absoluta/a/hf-studio", "hf-studio", "mcp"]
env = { HF_STUDIO_URL = "http://127.0.0.1:8787", HF_STUDIO_TOKEN = "hfs_…" }`;

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
];

export default async function McpPage() {
  const t = await getDict();
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
      <section className="mx-auto grid w-full max-w-5xl grid-cols-1 gap-4 lg:grid-cols-2">
        <CopyBlock title="Claude Code" code={claude(t.mcp.saveKey)} />
        <CopyBlock title="Codex" code={CODEX} />
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
