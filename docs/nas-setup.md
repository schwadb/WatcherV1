# NAS setup (UGREEN UGOS Pro)

One-time setup: install Tailscale, deploy the memory server with Docker
Compose, and verify it. Total time is roughly 30 minutes, most of it waiting
for downloads.

## 1. Install Tailscale on the NAS

Tailscale ships a UGREEN package and is the only networking piece you need —
no port forwarding, no dynamic DNS.

1. In UGOS Pro, open the **App Center** and install **Tailscale** (if it isn't
   listed, download the UGREEN package from
   <https://tailscale.com/download/synology> → UGREEN section, and install it
   via App Center → manual install).
2. Open the Tailscale app and **log in** with your Tailscale account.
3. In the [Tailscale admin console](https://login.tailscale.com/admin/machines),
   find the NAS, and (recommended) **disable key expiry** for it so you never
   get silently logged out.
4. Note the NAS's Tailscale IP (a `100.x.y.z` address) — you'll use it in
   every client config. Better: use its **MagicDNS name**
   (`<nas-name>.<tailnet>.ts.net`), which survives IP changes.
5. Install Tailscale on every device that should reach the memory: laptop,
   desktop, phone. Same account, and they're all on one private network.

## 2. Prepare folders on the NAS

Create a shared folder for the memory data, e.g. `docker/watcher-memory`, with
subfolders:

```
watcher-memory/
├── data/         # the sqlite-vec database lives here
├── backups/      # rotated backups land here
└── model-cache/  # embedding model, downloaded once on first start
```

## 3. Deploy with Docker Compose

1. Copy this repository's `docker-compose.yml` and `.env.example` into
   `watcher-memory/` (via SMB, or `git clone` if you have SSH access).
2. Rename `.env.example` to `.env` and edit it:
   - Set `MCP_API_KEY` to a fresh random secret:
     `openssl rand -hex 32` (any machine), or any long random string.
   - Adjust the three data paths if your folder layout differs.
3. In UGOS Pro open the **Docker** app → **Project** → **Create**:
   - Point it at the `watcher-memory/` folder containing `docker-compose.yml`.
   - Deploy. First start downloads the image (~200 MB) and then the embedding
     model (~90 MB, cached in `model-cache/` so it never downloads again).
4. Wait until the container reports **healthy** (the compose file includes a
   healthcheck).

> Alternative if you prefer a terminal: enable SSH in UGOS control panel, then
> `cd` to the folder and run `docker compose up -d`.

## 4. Verify

From any device on your tailnet:

```bash
./scripts/smoke-test.sh http://<nas-tailscale-ip>:8000 <your-api-key>
```

The script checks health, stores a test memory, finds it via semantic search,
and deletes it. You can also open the dashboard in a browser:
`http://<nas-tailscale-ip>:8000/` — you should see the memory dashboard.

Then connect your AI clients — see [clients.md](clients.md).

## 5. Optional hardening

- **HTTPS on the tailnet:** some clients insist on HTTPS. Run
  `tailscale serve --bg https / http://localhost:8000` on the NAS to get
  `https://<nas-name>.<tailnet>.ts.net` with a real certificate — still
  private to your tailnet (this is *serve*, not *funnel*; nothing public).
- **Don't expose the port beyond the tailnet.** The compose file publishes the
  port on all NAS interfaces, which means devices on your home LAN can also
  reach it (fine for most homes). To restrict it strictly to Tailscale, set
  `MEMORY_BIND_IP` in `.env` to the NAS's `100.x.y.z` address.
- **Backups:** the server backs itself up automatically (daily, into
  `backups/` — tune with the `MCP_BACKUP_*` settings in `.env`). For an
  off-site copy to a second disk or share, schedule `scripts/backup.sh` via
  UGOS **Task Scheduler** (Control Panel → Task Scheduler → user-defined
  script); see the script header for the exact command.

## Upgrading the server

The image tag is pinned in `.env` (`MEMORY_IMAGE_TAG`). To upgrade: check the
project's release notes at
<https://codeberg.org/doobidoo/mcp-memory-service/releases>, run a backup,
bump the tag in `.env`, redeploy the project, and re-run the smoke test.
