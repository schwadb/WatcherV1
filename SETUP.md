# Setup walkthrough — from zero to shared AI memory

Follow this top to bottom. Every part ends with a **✅ Checkpoint** — don't
move on until it passes. Everything on the NAS happens in the UGOS web
interface; no terminal needed there.

**What you need:**

- Your UGREEN NAS, powered on, with its web interface (UGOS Pro) reachable
  and an admin login.
- A computer (Mac or Windows) on the same account you'll use everywhere.
- About an hour, most of it waiting for downloads.

**What you'll have at the end:** every AI assistant you connect — on every
device — reads and writes one shared memory stored on your NAS. Tell Claude
something on your desktop; Gemini on your laptop knows it.

---

## Part 1 — Create a Tailscale account and install it on your computer

Tailscale is a free private network between your devices. It's what lets your
laptop reach the NAS from anywhere, with nothing exposed to the internet.

1. Go to <https://tailscale.com> and sign up (free "Personal" plan — sign in
   with Google/Microsoft/GitHub, whichever you'll remember).
2. Download and install Tailscale on this computer:
   <https://tailscale.com/download>.
3. Launch it and log in with the account from step 1.

**✅ Checkpoint:** open <https://login.tailscale.com/admin/machines> — your
computer appears in the machine list with a `100.x.y.z` address.

## Part 2 — Install Tailscale on the NAS

1. In the UGOS Pro web interface, open the **App Center**.
2. Search for **Tailscale** and install it. (If it's not in the App Center,
   download the UGREEN package from <https://pkgs.tailscale.com> and use App
   Center → Manual Install.)
3. Open the Tailscale app on the NAS and **log in** with the same account.
4. Back at <https://login.tailscale.com/admin/machines>: click the **⋯** menu
   next to the NAS → **Disable key expiry** (otherwise the NAS silently drops
   off the network in a few months).
5. Write down two things from that machine list:
   - the NAS's Tailscale IP (looks like `100.x.y.z`)
   - its name (e.g. `ugreen-nas`) — with MagicDNS it's reachable as
     `ugreen-nas.your-tailnet.ts.net`

Wherever this guide says `NAS-ADDRESS`, use that IP or name. Also install the
Tailscale app on your phone and any other computers now — same login, and
they all join the network.

**✅ Checkpoint:** both your computer and the NAS show in the admin console.
In a browser on your computer, `http://NAS-ADDRESS` (the Tailscale one, not
the home LAN IP) loads the UGOS login page.

## Part 3 — Prepare the configuration on your computer

1. Download this repository: on the GitHub page, **Code → Download ZIP**, and
   unzip it. (If you use git: `git clone` works too.)
2. In the unzipped folder, find `.env.example`. Make a copy of it named
   exactly **`.env`** (note: filenames starting with a dot can be hidden —
   enable "show hidden files" if it vanishes).
3. Generate your API key — the password every AI client will present:
   - **Mac:** open Terminal, run `openssl rand -hex 32`
   - **Windows:** open PowerShell, run
     `-join ((1..64) | ForEach-Object { '0123456789abcdef'[(Get-Random -Max 16)] })`
4. Open `.env` in a text editor and paste the key into the `MCP_API_KEY=`
   line, so it reads `MCP_API_KEY=a1b2c3...` (no spaces, no quotes).
5. Save the key in your password manager too — you'll paste it into every
   client in Part 7.

Leave everything else in `.env` at its defaults.

**✅ Checkpoint:** your `.env` file has a 64-character value on the
`MCP_API_KEY=` line.

## Part 4 — Upload to the NAS

In UGOS Pro, open **File Manager**:

1. Inside a shared folder (e.g. the default `docker` share — create one if
   you have none), create a folder `watcher-memory`.
2. Inside `watcher-memory`, create three empty subfolders: `data`, `backups`,
   `model-cache`.
3. Upload two files from your computer into `watcher-memory`:
   `docker-compose.yml` and your edited `.env`.

**✅ Checkpoint:** the NAS folder looks like this:

```
watcher-memory/
├── docker-compose.yml
├── .env
├── data/          (empty)
├── backups/       (empty)
└── model-cache/   (empty)
```

## Part 5 — Deploy the memory server

1. In UGOS Pro, open the **Docker** app.
2. Go to **Project** (UGREEN's name for Docker Compose) → **Create**.
3. Name it `watcher-memory` and select the `watcher-memory` folder from
   Part 4 as the project path — it should detect `docker-compose.yml`.
4. Deploy/start the project. The first start downloads about 200 MB, then
   the container comes up; give it 2–3 minutes total.
5. In the Docker app's container list, wait until **watcher-memory** shows
   status **healthy** (not just "running" — healthy means the built-in
   check passed).

**✅ Checkpoint:** on your computer, `http://NAS-ADDRESS:8000/` in a browser
shows the memory dashboard.

## Part 6 — Verify the round trip

In the dashboard at `http://NAS-ADDRESS:8000/` (it will ask for your API
key):

1. **Store** a test memory: content `My test memory: the sky over the NAS is
   green`, tag `smoke-test`.
2. **Search** for `what color is the sky` — semantic search should return
   your test memory even though the words don't match exactly. That's the
   local embedding model working.
3. **Delete** the test memory.

Prefer a terminal? `./scripts/smoke-test.sh http://NAS-ADDRESS:8000 YOUR-KEY`
does the same round trip automatically (Mac/Linux/WSL, needs curl + python3).

**✅ Checkpoint:** stored, found by meaning, deleted — all three worked.

## Part 7 — Connect your AI clients

Do this once per device. Replace `NAS-ADDRESS` and `YOUR-KEY` in each
snippet. (Full details and more clients: [docs/clients.md](docs/clients.md).)

### Claude Code

```bash
claude mcp add --transport http --scope user memory \
  http://NAS-ADDRESS:8000/mcp \
  --header "Authorization: Bearer YOUR-KEY"
```

Restart Claude Code.

### Gemini CLI

```bash
gemini mcp add --transport http --scope user memory http://NAS-ADDRESS:8000/mcp \
  --header "Authorization: Bearer YOUR-KEY"
```

### Claude Desktop

Needs [Node.js](https://nodejs.org) installed on the device (LTS version,
default options). Then: Claude Desktop → **Settings → Developer → Edit
Config**, and add:

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://NAS-ADDRESS:8000/mcp",
        "--header", "Authorization: Bearer YOUR-KEY",
        "--allow-http"
      ]
    }
  }
}
```

Restart Claude Desktop.

### ChatGPT, Kimi, DeepSeek

These can't join a private network (their connectors run from the vendor's
cloud). ChatGPT can be added later by publishing the server —
[docs/phase2-public-exposure.md](docs/phase2-public-exposure.md). For all of
them, the manual workflow works today: search the dashboard, paste the
relevant memories into the chat.

**✅ Checkpoint:** in each connected client, ask: *"What memory tools do you
have available?"* — it should list tools like `memory_store` and
`memory_search`.

## Part 8 — Teach the agents when to use memory

Connected tools sit unused unless the agent has standing instructions. Copy
the **memory protocol** snippet from
[docs/memory-conventions.md](docs/memory-conventions.md) into each client:

- **Claude Code:** add it to `~/.claude/CLAUDE.md`
- **Gemini CLI:** add it to `~/.gemini/GEMINI.md`
- **Claude Desktop:** Settings → Profile → personal preferences/instructions

While you're in that doc, skim the tagging scheme — `type:preference`,
`project:<name>` — it's what keeps the shared memory organized.

**✅ Checkpoint:** start a fresh chat and say *"Remember that my favorite
test fruit is dragonfruit."* The agent should call its memory-store tool and
confirm.

## Part 9 — The payoff test

1. On **device A**, in one agent (say Claude Code): *"Remember that my
   favorite test fruit is dragonfruit."*
2. On **device B** (or just a different agent on the same device, e.g.
   Gemini CLI): *"What do you know about my favorite test fruit?"*

**✅ Checkpoint:** the second agent answers "dragonfruit" — memory written by
one AI on one device, recalled by a different AI on a different device.
That's the whole system working. (Ask it to delete the test memory after.)

## Part 10 — Ongoing care

- **Backups are already automatic** — daily, kept in the `backups/` folder
  you created (rotation handled by the server). For a copy to a second disk
  or share, schedule [`scripts/backup.sh`](scripts/backup.sh) in UGOS
  **Task Scheduler**; the command is in the script's header.
- **Upgrades are deliberate, not automatic.** The server version is pinned in
  `.env` (`MEMORY_IMAGE_TAG=11.4.0-slim`). To upgrade: check the
  [release notes](https://codeberg.org/doobidoo/mcp-memory-service/releases),
  run a backup, change the tag in `.env`, redeploy the project in the Docker
  app, and re-run the Part 6 verification.
- **Hardening options** (HTTPS on the tailnet, restricting the port to
  Tailscale only): [docs/nas-setup.md](docs/nas-setup.md), section 5.
- **Don't store secrets in memory** — every connected agent can read
  everything. Conventions: [docs/memory-conventions.md](docs/memory-conventions.md).
