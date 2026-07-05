# Connecting your AI clients

Every client talks to the same server. In the snippets below, replace:

- `NAS` — your NAS's Tailscale address: the `100.x.y.z` IP or, better, its
  MagicDNS name (`nas-name.your-tailnet.ts.net`).
- `PORT` — the port from `.env` (`MEMORY_PORT`, default `8000`).
- `KEY` — your `MCP_API_KEY` from `.env`.

The device must be on your tailnet (Tailscale installed and logged in).

| Client | Connection | Effort |
|---|---|---|
| Claude Code | Native HTTP MCP | One command |
| Gemini CLI | Native HTTP MCP | One command |
| Claude Desktop | `mcp-remote` bridge (needs Node.js) | Small config edit |
| ChatGPT, claude.ai (web) | Requires public exposure — [phase 2](phase2-public-exposure.md) | Not yet |
| Kimi, DeepSeek | No custom-connector support — dashboard copy/paste | Manual |

## Claude Code

```bash
claude mcp add --transport http --scope user memory \
  http://NAS:PORT/mcp \
  --header "Authorization: Bearer KEY"
```

`--scope user` makes it available in every project on that machine. Restart
Claude Code; the memory tools appear automatically. Repeat once per device.

## Gemini CLI

```bash
gemini mcp add --transport http --scope user memory http://NAS:PORT/mcp \
  --header "Authorization: Bearer KEY"
```

Or edit `~/.gemini/settings.json` directly:

```json
{
  "mcpServers": {
    "memory": {
      "httpUrl": "http://NAS:PORT/mcp",
      "headers": {
        "Authorization": "Bearer KEY"
      }
    }
  }
}
```

## Claude Desktop

Claude Desktop's built-in "custom connectors" are fetched from Anthropic's
cloud, so they can't reach a private tailnet address. Instead, use the
`mcp-remote` bridge — a small local process that Claude Desktop starts, which
forwards to the NAS. Requires [Node.js](https://nodejs.org) on the device.

Edit `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://NAS:PORT/mcp",
        "--header", "Authorization: Bearer KEY",
        "--allow-http"
      ]
    }
  }
}
```

Restart Claude Desktop. (`--allow-http` is needed because the tailnet URL is
plain HTTP; if you set up `tailscale serve` HTTPS per
[nas-setup.md](nas-setup.md), use the `https://…ts.net/mcp` URL and drop
`--allow-http`.)

## ChatGPT and claude.ai in the browser

Their connectors run from OpenAI's/Anthropic's servers, which cannot reach
your private tailnet. Connecting them requires deliberately publishing the
memory server to the internet — see
[phase2-public-exposure.md](phase2-public-exposure.md). Until then, use the
dashboard workflow below.

## Kimi, DeepSeek, and anything else without connector support

Manual, but workable:

1. Open the dashboard from any tailnet device: `http://NAS:PORT/`
2. Search the memories relevant to your conversation and paste them in as
   context ("Here's what my other assistants know: …").
3. At the end of a session, ask the agent: *"List any durable facts,
   preferences, or decisions from this conversation worth remembering."*
   Paste the keepers into the dashboard (with `type:` and `project:` tags per
   [memory-conventions.md](memory-conventions.md)).

## After connecting: teach the agent to use it

Connecting the tools isn't enough — agents need standing instructions on when
to store and retrieve. Add the "memory protocol" snippet from
[memory-conventions.md](memory-conventions.md) to each client's instructions
file (CLAUDE.md, GEMINI.md, custom instructions).
