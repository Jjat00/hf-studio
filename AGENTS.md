# AGENTS.md

Guide for AI agents (Claude Code, Codex, Cursor…) working with HF Studio. Humans: see [README.md](README.md).

HF Studio is a self-hosted studio on the Higgsfield (video, image) and ElevenLabs (audio) APIs: a FastAPI backend
(`src/hf_studio/`), an MCP server over stdio (`hf-studio mcp`) and a Next.js UI (`web/`). Generating spends the
owner's credits.

## Set it up for a user

1. Prerequisites: `uv`, and for the UI also Node.js 20+ and `pnpm`. `ffmpeg` is needed for the audio features
   (on macOS `brew install ffmpeg-full`: the plain formula lacks the `rubberband` filter).
2. The only required secret is the Higgsfield key (`HF_API_KEY`, format `KEY_ID:KEY_SECRET`, from
   https://console.higgsfield.ai). `ELEVENLABS_API_KEY` is optional and only enables audio. **Ask the user for the
   keys; never invent, print or commit them.** They go in `.env` (created from `.env.example`, git-ignored).
3. Run `uv run hf-studio setup --no-input` once `.env` has the key. It validates the key without spending credits and
   writes the UI key to `web/.env.local`. A human can just run `./dev.sh` (Windows: `.\dev`), which asks for the
   keys interactively.
4. Start it with `uv run hf-studio start` (API on `127.0.0.1:8787` and UI on `http://localhost:3000`) or
   `uv run hf-studio start --api-only` (API only, enough for MCP). Same command on Windows, macOS and Linux;
   `./dev.sh` and `dev.cmd` are shortcuts. It is a long-running process: start it in the background. Health check:
   `GET /health`.
5. Connect an agent: `uv run hf-studio connect claude-code` (or `codex`, `claude-desktop`, `json`). It creates a new
   key for that client (never rotates an existing one) and registers the server. `--print` prints the command or
   config (with a new key) instead. If `hf-studio` is already registered, it stops without changes. If the agent's
   CLI is missing, nothing is registered (exit code 0): run the printed command where that CLI is installed. The
   client must be restarted.

## Use it through MCP

- Flow: `recommend_models` or `find_models` → `get_model` (read `input_schema` and `studio_notes`) → `upload_media`
  for local files → `estimate_cost` → **tell the user the cost and wait for their OK** → `generate` with that
  `quote_id` → `get_generation` until `terminal` is true → `download_outputs`.
- Every paid tool needs a single-use `quote_id` (15 min) from quoting the exact same request. Paid tools say
  "spends credits" in their title. Never pass `confirm_unknown_cost=True` unless the user explicitly accepts an
  unknown price.
- After an ambiguous error, check `list_generations` before calling `generate` again, and reuse the same
  `idempotency_key` when retrying.
- Before generating a sound, search `list_sounds`: reusing one is free.
- The server instructions (in `src/hf_studio/mcp_server.py`, `INSTRUCTIONS`) are the source of truth.

## Work on the code

```bash
uv run pytest -q                 # Higgsfield and ElevenLabs are mocked: never spends credits
uv run ruff check src tests && uv run ruff format src tests
cd web && pnpm lint && pnpm exec next typegen && npx tsc --noEmit
```

- Map: `api.py` (REST routes), `service.py` (generation logic), `worker.py` (queue and polling),
  `higgsfield.py` (Higgsfield client), `voice.py` and `elevenlabs_audio.py` (ElevenLabs audio), `free_voices.py`
  (free Spanish voices with edge-tts: catalog and cached samples, used by the `/voices` page), `pricing.py`
  (quotes), `mcp_server.py` (MCP tools), `setup.py` (first run and `connect`), `launcher.py` (`start`), `catalog.json` (82 model schemas,
  regenerated with `hf-studio sync-catalog`).
- Every MCP tool declares `title` and all four hints (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
  `openWorldHint`); `tests/test_mcp_tools.py` pins them. Keep them true to what the handler does.
- The UI is Next.js 16, which differs from older versions: read `web/AGENTS.md` before touching `web/`.
- Do not make real generation calls in tests or checks. Do not expose the UI beyond `127.0.0.1`: its proxy does not
  authenticate visitors.
