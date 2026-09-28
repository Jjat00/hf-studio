# Security

## Reporting a vulnerability

Please do not open a public issue. Use [GitHub private vulnerability reporting](https://github.com/Jjat00/hf-studio/security/advisories/new)
or write to userjjat00@gmail.com with the steps to reproduce. You will get an answer within a week.

## Model

- HF Studio is meant to run on your own machine. The API and the web UI listen on `127.0.0.1` by default.
- Only the API knows the Higgsfield and ElevenLabs keys. Agents and the UI use their own revocable `hfs_…` keys, and
  each key only sees its own generations unless you grant `see-all`.
- The UI proxy does not authenticate visitors. Do not expose it to other machines without authentication in front.
- Paid MCP tools require a single-use quote of the same request, so an agent cannot spend credits without quoting
  first; showing that price to a person is up to the agent. The REST API trusts the `hfs_…` key holder: its Higgsfield
  routes do not require a quote. MCP tools declare `readOnlyHint`, `destructiveHint`, `idempotentHint` and
  `openWorldHint`.
- ffmpeg only opens your own uploads and outputs, over `file` and `https` (no arbitrary URLs).
