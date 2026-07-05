# Phase 2 (not implemented): public exposure for ChatGPT and claude.ai web

Phase 1 keeps the memory server reachable only inside your Tailscale network.
That covers Claude Code, Gemini CLI, and Claude Desktop (via the `mcp-remote`
bridge). Two clients cannot participate, because their MCP connections
originate from the vendor's cloud, not from your device:

- **ChatGPT** (web and desktop) — connectors run from OpenAI's servers and
  require a publicly reachable HTTPS endpoint.
- **claude.ai in the browser** — custom connectors are fetched from Anthropic's
  cloud; a tailnet IP is unreachable from there.

To include them, the memory server must be published to the internet. This is
a deliberate, opt-in step with real risk: your personal memory store becomes a
public endpoint, protected only by its authentication.

## Recommended design (when you're ready)

1. **Tailscale Funnel** — `tailscale funnel <port>` on the NAS publishes the
   server at `https://<nas-name>.<tailnet>.ts.net` with a valid TLS
   certificate, no port forwarding and no router changes. Traffic still
   terminates on the NAS.
2. **Enable OAuth 2.1 on mcp-memory-service** — the server supports OAuth 2.1
   with Dynamic Client Registration, which is exactly what claude.ai and
   ChatGPT connectors expect. API-key-only auth is not enough for a public
   endpoint.
3. **Register the connector**:
   - claude.ai → Settings → Connectors → Add custom connector → the Funnel URL.
   - ChatGPT → Settings → Connectors (Developer Mode for full read/write tools)
     → the Funnel URL.
4. **Harden before flipping the switch**:
   - Update to the latest pinned release first; a public endpoint should not
     run months-old code.
   - Verify backups are running (see `scripts/backup.sh`).
   - Keep Funnel scoped to the single memory port — nothing else on the NAS.
   - Periodically review the dashboard for memories you wouldn't want leaked;
     assume a public endpoint can eventually be breached and store accordingly
     (the "no secrets in memory" rule in `memory-conventions.md` becomes
     mandatory, not advisory).

## The fallback that always works

Without public exposure, ChatGPT / Kimi / DeepSeek can still benefit from the
shared memory manually: open the server's web dashboard from any tailnet
device, search the relevant memories, and paste them into the conversation.
Ask the agent to end the session with a "memories worth keeping" list, and
paste those back into the dashboard.
