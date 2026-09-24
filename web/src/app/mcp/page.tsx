import { CopyBlock } from "@/components/copy-block";

export const metadata = { title: "MCP · HF Studio" };

const CLAUDE = `uv run hf-studio create-key claude-code   # save the hfs_… key

claude mcp add hf-studio --scope user \\
  -e HF_STUDIO_URL=http://127.0.0.1:8787 -e HF_STUDIO_TOKEN=hfs_… \\
  -- uv run --directory ~/projects/hf-studio hf-studio mcp`;

const CODEX = `# ~/.codex/config.toml
[mcp_servers.hf-studio]
command = "uv"
args = ["run", "--directory", "/home/jjat00/projects/hf-studio", "hf-studio", "mcp"]
env = { HF_STUDIO_URL = "http://127.0.0.1:8787", HF_STUDIO_TOKEN = "hfs_…" }`;

const TOOLS = [
  ["find_models", "Search by capability: first-last-frame, video-input, reference-to-video…"],
  ["get_model", "Input schema and usage notes for any model"],
  ["upload_media", "Upload a local image, video or audio file"],
  ["estimate_cost", "Credits and USD before you generate"],
  ["generate", "Queue a generation with an idempotency key"],
  ["get_generation", "Wait until it finishes (long-poll)"],
  ["list_generations", "History shared with this interface"],
  ["cancel_generation", "Cancel anything that has not started yet"],
  ["download_outputs", "Download results to a local folder"],
];

export default function McpPage() {
  return (
    <div className="flex flex-col gap-10 px-4 pb-16">
      <section className="grain relative mt-2 overflow-hidden rounded-[28px] px-6 py-24 text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/art/mcp.webp" alt="" className="absolute inset-0 size-full object-cover" />
        <div className="absolute inset-0 bg-black/35" />
        <div className="relative">
          <p className="text-[26px] font-semibold tracking-[-0.02em] text-white/90">Use HF Studio MCP with</p>
          <h1 className="headline mt-2 bg-gradient-to-b from-[#ffb58a] to-[#e0663b] bg-clip-text text-[52px] text-transparent md:text-[88px]">
            Claude Code · Codex
          </h1>
          <p className="mx-auto mt-4 max-w-md text-[17px] leading-relaxed text-white/80">
            Generate images and videos from your coding agents, with the same API and history as this interface.
          </p>
        </div>
      </section>
      <section className="mx-auto grid w-full max-w-5xl grid-cols-1 gap-4 lg:grid-cols-2">
        <CopyBlock title="Claude Code" code={CLAUDE} />
        <CopyBlock title="Codex" code={CODEX} />
      </section>
      <section className="mx-auto w-full max-w-5xl">
        <h2 className="headline text-[32px]">9 tools</h2>
        <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
          {TOOLS.map(([name, body]) => (
            <div key={name} className="rounded-[22px] border border-line bg-surface-2 p-5">
              <p className="font-mono text-[15px] font-semibold text-lime">{name}</p>
              <p className="mt-2 text-[15px] leading-snug text-fg-3">{body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
