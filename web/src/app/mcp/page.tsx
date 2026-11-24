import path from "node:path";
import Link from "next/link";
import { CopyBlock } from "@/components/copy-block";
import { getDict } from "@/lib/i18n/server";

export const metadata = { title: "MCP · HF Studio" };

const TOOLS = [
  "find_models",
  "get_model",
  "recommend_models",
  "list_styles",
  "list_model_options",
  "upload_media",
  "list_uploads",
  "estimate_cost",
  "generate",
  "generate_batch",
  "get_generation",
  "wait_generations",
  "show_generations",
  "generation_preview",
  "list_generations",
  "list_approvals",
  "approve_fallback",
  "cancel_generation",
  "download_outputs",
  "use_output",
  "favorite_generations",
  "hide_generations",
  "delete_generation",
  "providers_status",
  "get_usage",
  "list_presets",
  "run_preset",
  "save_preset",
  "delete_preset",
  "list_voices",
  "change_voice",
  "clone_voice",
  "design_voice",
  "save_voice",
  "delete_voice",
  "list_free_voices",
  "free_text_to_speech",
  "text_to_speech",
  "sound_effect",
  "compose_music",
  "isolate_voice",
  "elevenlabs_account",
  "list_sounds",
  "label_sound",
  "import_elevenlabs_history",
  "list_elements",
  "create_element",
  "delete_element",
  "list_spaces",
  "get_space",
  "create_space",
  "update_space",
  "delete_space",
  "estimate_space_run",
  "run_space",
  "get_space_run",
  "approve_space_run",
  "cancel_space_run",
  "katana_presets",
  "katana_create",
  "katana_plan",
  "katana_get",
];

/** Clientes, como la barra de Higgsfield (ChatGPT, Claude, Claude Code…): cada uno cambia el titular y el comando. */
const CLIENTS = [
  { key: "claude-code", title: "Claude Code" },
  { key: "codex", title: "Codex" },
  { key: "claude-desktop", title: "Claude Desktop" },
  { key: "json", title: null },
] as const;

export default async function McpPage({ searchParams }: { searchParams: Promise<{ client?: string }> }) {
  const t = await getDict();
  const wanted = (await searchParams).client;
  const client = CLIENTS.find((c) => c.key === wanted) ?? CLIENTS[0];
  const clientTitle = client.title ?? t.mcp.otherClient;
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
  const chosen = byHand[CLIENTS.indexOf(client)];
  return (
    <div className="flex flex-col gap-10 px-4 pb-16">
      <nav className="hide-scrollbar -mb-6 flex justify-center gap-1 overflow-x-auto border-b border-line">
        {CLIENTS.map((c) => (
          <Link
            key={c.key}
            href={`/mcp?client=${c.key}`}
            scroll={false}
            aria-current={c === client ? "page" : undefined}
            className={
              c === client
                ? "border-b-2 border-fg px-3 py-2.5 text-[14px] font-semibold whitespace-nowrap text-fg"
                : "border-b-2 border-transparent px-3 py-2.5 text-[14px] font-medium whitespace-nowrap text-fg-3 hover:text-fg"
            }
          >
            {c.title ?? t.mcp.otherClient}
          </Link>
        ))}
      </nav>
      <section className="grain relative mt-2 overflow-hidden rounded-[28px] px-6 py-24 text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/art/mcp.webp" alt="" className="absolute inset-0 size-full object-cover" />
        <div className="absolute inset-0 bg-black/35" />
        <div className="relative">
          <p className="text-[26px] font-semibold tracking-[-0.02em] text-white/90">{t.mcp.heroLead}</p>
          <h1 className="headline mt-2 bg-gradient-to-b from-[#ffb58a] to-[#e0663b] bg-clip-text text-[52px] text-transparent md:text-[88px]">
            {clientTitle}
          </h1>
          <p className="mx-auto mt-4 max-w-md text-[17px] leading-relaxed text-white/80">
            {t.mcp.heroBody}
          </p>
        </div>
      </section>
      <section className="mx-auto flex w-full max-w-5xl flex-col gap-4">
        <div>
          <h2 className="headline text-[32px]">{t.mcp.connectTitle}</h2>
          <p className="mt-1 text-[15px] text-fg-3">{t.mcp.connectBody}</p>
        </div>
        <CopyBlock title={clientTitle} code={chosen.code} wrap />
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
