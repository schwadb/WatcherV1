# PLAN: health-watchdog

## Goal

The memory server fails silently today: if the container dies, backups stop,
or the disk fills, nothing tells the user — agents just quietly lose their
memory tools until someone notices. Add a watchdog script for UGOS Task
Scheduler that checks health hourly and pushes a phone notification (via
ntfy.sh, free) when something is actually wrong — with state tracking so it
alerts on *transitions*, not every hour forever.

## Files to touch

| File | Action |
|---|---|
| `scripts/watchdog.sh` | NEW |
| `docs/nas-setup.md` | EDIT — section 5 gains "set up the watchdog" |
| `SETUP.md` | EDIT — Part 10 bullet linking it |
| `README.md` | EDIT — contents table row |
| `.env.example` | EDIT — optional `NTFY_TOPIC=` entry (blank = log-only mode) |

## Design

`watchdog.sh <base-url> <api-key> [<ntfy-topic>]` — runs anywhere that can
reach the server; intended home is UGOS Task Scheduler on the NAS itself
(hourly), where it survives laptop shutdowns.

Checks, in order:
1. **Liveness:** `GET /api/health` (no auth) with `--max-time 10`.
2. **Backup freshness:** `GET /api/backup/list` (auth); newest backup
   `age_days` must be `<= 2` (automatic backups are daily; 2 gives slack).
3. **Storage sanity:** `GET /api/health/detailed` (auth); alert if it reports
   a failing/degraded status. Probe the real response shape on a live server
   first and key off fields that exist — do not invent field names.

State machine (the part that matters):
- Keep a state file next to the script (`.watchdog-state`, one word:
  `ok` or `failing`, plus a consecutive-failure counter).
- Liveness must fail **twice consecutively** before alerting — the container
  has `restart: unless-stopped` and a transient restart should self-heal
  invisibly.
- Send ONE notification on `ok → failing` (with which check failed and the
  first remedy: "Docker app → is watcher-memory running?") and ONE on
  `failing → ok` ("memory server recovered"). Repeat alerts at most every
  24 h while failing.
- Notification = `curl -d "<message>" https://ntfy.sh/<topic>`; if no topic
  configured, append to `watchdog.log` only. Always append to the log either
  way (timestamped single line per run).

## Implementation order

1. Probe `/api/health/detailed` and `/api/backup/list` responses on a live
   local container; note exact field names in a comment block at the top of
   the script.
2. Write the script (house style: bash, `set -euo pipefail`, python3 for
   JSON), with the state machine above. All paths derived from the script's
   own location (`$(dirname "$0")`), never the cwd — Task Scheduler runs
   with an arbitrary cwd.
3. Trim `watchdog.log` to the last 1,000 lines each run (`tail` to temp file,
   move back) so it can't grow unbounded over years.
4. Docs: ntfy.sh setup is two sentences (pick a random topic name, install
   the ntfy app, subscribe to the topic — the topic name IS the secret, so
   generate something unguessable, e.g. `watcher-<openssl rand -hex 8>`).
   UGOS Task Scheduler walkthrough mirrors the existing backup.sh
   instructions.

## Edge cases (a weaker model would miss)

- **`set -e` vs expected failures:** every curl that is ALLOWED to fail
  (that's the whole point of a health check) must be wrapped
  (`if ! out=$(curl ...); then` / `|| true`) or the script dies at the first
  down-check and never writes state or notifies.
- **Alert on transition, not state** — an hourly cron that alerts every hour
  while failing trains the user to ignore it. The state file is the feature.
- **Two-strike liveness rule** (restart policy self-heals transients).
- **The state file must be writable by the Task Scheduler user** — create it
  with the script on first run; don't assume it exists.
- **ntfy topic is a bearer secret in a URL** — say so; a guessable topic
  means strangers can read your alerts and spam you.
- If the NAS itself is down, an on-NAS watchdog can't tell you. State this
  limitation honestly in the docs (the fix — off-NAS monitoring — is out of
  scope; Tailscale's admin console machine list is the manual fallback).

## Acceptance criteria

Against a local container:

1. Healthy server: run → log line written, state `ok`, no notification.
2. `docker compose stop` → run twice → FIRST run: counter 1, no alert;
   SECOND run: state flips to `failing`, exactly one notification sent (test
   with a real throwaway ntfy topic — message arrives in the ntfy web app).
3. Third consecutive failing run: no additional notification.
4. `docker compose start`, wait healthy → run → ONE recovery notification,
   state `ok`.
5. Delete the newest backups and set the remaining one's mtime/age so
   `age_days > 2` (or temporarily lower the threshold): backup-staleness
   alert fires while liveness stays green.
6. With no ntfy topic configured, the same sequence produces log lines only
   and exit code 0 throughout. `bash -n` passes.
