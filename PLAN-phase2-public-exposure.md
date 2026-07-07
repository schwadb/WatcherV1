# PLAN: phase2-public-exposure

## Goal

Promote ChatGPT and claude.ai (web) from copy/paste bystanders to full memory
clients by publishing the memory server at a public HTTPS URL via Tailscale
Funnel, with OAuth 2.1 login. This is the deferred phase 2 sketched in
`docs/phase2-public-exposure.md`.

**Precondition (do not skip):** phase 1 deployed and in daily use, backups
verified restorable (PLAN-restore-runbook executed at least once). Publishing
a memory store you can't restore is gambling.

## Files to touch

| File | Action |
|---|---|
| `docker-compose.yml` | EDIT — add OAuth/streamable-HTTP env vars (gated by `.env` values so tailnet-only users are unaffected) |
| `.env.example` | EDIT — new commented-out `PHASE2_*` / OAuth block |
| `docs/phase2-public-exposure.md` | REWRITE — from design sketch to executed instructions |
| `docs/clients.md` | EDIT — ChatGPT and claude.ai sections become real connection guides |
| `scripts/smoke-test.sh` | no change (must still pass over the tailnet afterward) |

## Implementation order

1. **Verify upstream's OAuth story at the pinned version.** Read
   `docs/remote-mcp-setup.md` and the OAuth docs in the
   `mcp-memory-service` repo (https://codeberg.org/doobidoo/mcp-memory-service,
   tag matching `.env`'s `MEMORY_IMAGE_TAG`). Known from the v11.4.0 research
   pass: OAuth 2.1 with Dynamic Client Registration exists
   (`MCP_OAUTH_ENABLED=true`); a streamable-HTTP mode for browser clients is
   documented (`MCP_STREAMABLE_HTTP_MODE=1`, historically port 8765). Confirm
   exact variable names and the issuer/base-URL variable at the pinned tag
   before editing anything — do not trust memory or this plan for the exact
   names; trust the tag's docs.
2. **Local rehearsal before touching the NAS**: bring the container up
   locally with OAuth enabled; confirm (a) `/.well-known/oauth-authorization-server`
   (or the documented metadata path) serves metadata, (b) `/mcp` returns
   401 with OAuth challenge instead of the API-key 401, (c) **API-key auth
   still works simultaneously** for tailnet clients — if it does not, stop
   and document mixed-auth strategy (e.g. second bound port) before
   proceeding.
3. **Compose/env changes:** OAuth env vars driven by `.env`, all defaulting
   to phase-1 behavior when unset. The public base URL must be a variable
   (`MEMORY_PUBLIC_URL`) — OAuth issuer metadata must match the Funnel URL
   exactly or clients will reject the flow.
4. **Funnel on the NAS.** Funnel requires: HTTPS certificates enabled on the
   tailnet, a `funnel` node attribute in the tailnet policy file (the admin
   console prompts to add it), and it only serves ports **443, 8443, 10000**.
   The UGREEN Tailscale app may not expose Funnel in its UI — the documented
   path is the Tailscale CLI on the NAS
   (`tailscale funnel --bg --set-path=/ 8000` style, exact syntax per current
   Tailscale docs). This is the ONE place the no-SSH rule bends; the doc must
   walk the user through enabling SSH temporarily in UGOS, running the two
   Funnel commands, and disabling SSH again.
5. **Scope what's public.** Funnel a path, not the whole server, if
   supported: `/mcp` (and the OAuth paths) need exposure; the dashboard does
   NOT — check whether upstream serves OAuth metadata under paths that make
   path-scoping viable; otherwise document that the dashboard is also public
   behind login and set a strong key.
6. **Connect the clients** and write the real instructions into
   `docs/clients.md`: claude.ai → Settings → Connectors → add the Funnel URL,
   complete OAuth; ChatGPT → Settings → Connectors (requires Developer Mode
   for read/write tools), same URL, same flow.
7. Update SETUP.md Part 7's "can't join" wording to point to the now-real
   phase 2 doc.

## Edge cases (a weaker model would miss)

- **Issuer URL mismatch** is the classic OAuth failure: metadata must
  advertise the exact public HTTPS URL (scheme, host, port, no trailing
  slash drift) or DCR silently fails.
- **Funnel port allowlist** (443/8443/10000): you cannot funnel :8000
  directly; map Funnel 443 → local 8000.
- **Don't break the tailnet path.** After every change, re-run
  `scripts/smoke-test.sh` against the tailnet address with the API key —
  existing Claude Code/Gemini/Desktop configs must keep working unchanged.
- **ChatGPT write-tool consent:** without Developer Mode, ChatGPT connectors
  may mount search/fetch only — memory_store won't be callable. Say so in
  the doc rather than letting the user think it's broken.
- **Threat model note in the doc:** public endpoint = assume eventual probe
  traffic; the "no secrets in memory" convention is now mandatory; check
  `docker compose logs` for the OAuth server's failed-auth logging and
  mention how to watch it (ties into PLAN-health-watchdog).

## Acceptance criteria

1. From a device OFF the tailnet (e.g. phone on cellular, Tailscale off):
   the Funnel URL's OAuth metadata endpoint responds over HTTPS; `/mcp`
   without credentials returns an auth challenge, not data.
2. claude.ai (web) custom connector completes OAuth and lists the memory
   tools; a memory stored from claude.ai is found by Claude Code over the
   tailnet (cross-path round trip).
3. ChatGPT connector added; at minimum memory search works from a ChatGPT
   chat; store works with Developer Mode on (document actual result).
4. `scripts/smoke-test.sh` still passes over the tailnet with the API key.
5. With the phase-2 `.env` block commented back out and the project
   redeployed, behavior is byte-identical to phase 1 (rollback path proven).
