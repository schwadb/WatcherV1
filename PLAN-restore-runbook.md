# PLAN: restore-runbook

## Goal

Backups exist (automatic daily + `scripts/backup.sh`), but there is no restore
path. A backup you've never restored is a hope, not a backup. Deliver a
restore script + a documented, rehearsed drill so recovering the memory
database is a 10-minute checklist, not an improvisation during a bad day.

**Leverage:** small effort; protects everything the rest of the system
accumulates. Becomes more valuable every day the memory grows.

## Files to touch

| File | Action |
|---|---|
| `scripts/restore.sh` | NEW |
| `docs/restore.md` | NEW — the runbook, including a practice drill |
| `SETUP.md` | EDIT — Part 10 gains one line linking the runbook |
| `README.md` | EDIT — contents table row |

## Key facts (verified against the live v11.4.0-slim container)

- Live DB on the host: `data/sqlite_vec.db` (mounted at
  `/app/sqlite_db/sqlite_vec.db` in-container).
- Backups on the host: `backups/memory_backup_YYYYMMDD_HHMMSS.db` — plain
  SQLite snapshot files.
- Restore = replace the live DB file with a backup file **while the container
  is stopped**. The user's NAS path has no SSH: the script does FILE
  OPERATIONS ONLY and instructs the user to stop/start the project in the
  UGOS Docker app around it. Do not shell out to `docker` in the script.

## Implementation order

1. Write `scripts/restore.sh <data-dir> <backup-file> [<base-url>]`
   (house style: bash, `set -euo pipefail`, python3 for anything nontrivial):
   1. **Refuse to run if the server is up**: if a base-url is given, curl
      `/api/health` — if it responds, abort with "stop the watcher-memory
      project in the Docker app first." If no base-url, prompt the user to
      confirm the container is stopped (read from stdin, require literal
      `yes`).
   2. **Integrity-check the chosen backup** before touching anything:
      `python3 -c "import sqlite3; ..."` → `PRAGMA integrity_check` must
      return `ok`.
   3. **Preserve the current state**: move (not copy) `sqlite_vec.db` to
      `sqlite_vec.db.pre-restore.<timestamp>` inside the data dir.
   4. **Remove sidecar files** `sqlite_vec.db-wal` and `sqlite_vec.db-shm`
      if present — restoring a .db while stale WAL/SHM files remain corrupts
      the database on next open. This is the step a weaker model will miss.
   5. Copy the backup file into place as `sqlite_vec.db`.
   6. Print the exact next steps: start the project in the Docker app, then
      run `scripts/smoke-test.sh`, then how to delete the `.pre-restore.*`
      file once satisfied.
2. Write `docs/restore.md`:
   - When to restore (corruption, bad bulk import, accidental mass delete).
   - The checklist: pick backup (dashboard `GET /api/backup/list` or File
     Manager) → stop project in Docker app → run script (from any machine
     with the NAS share mounted, or via File Station copy steps as the
     zero-terminal alternative — document both) → start project → verify.
   - **The drill** (do once now, then yearly): store a marker memory → run
     `scripts/backup.sh` → delete the marker → restore per the checklist →
     confirm the marker is back.
3. One-line additions to SETUP.md Part 10 and the README table.

## Edge cases (a weaker model would miss)

- **WAL/SHM sidecars** (step 1.4 above) — the single most likely way to turn
  a good backup into a corrupt restore.
- **Never restore over a running server** — the container holds the SQLite
  file open; replacing it underneath causes silent corruption. Hence the
  health-probe refusal, not just a doc warning.
- **Move, don't delete, the current DB.** If the user picked the wrong backup
  file, the pre-restore copy is the undo.
- **Ownership:** the container runs as root, so restored files created by a
  NAS user account still work (root container reads any mode), but the script
  should `chmod 644` the restored file to be safe.
- The `.pre-restore.*` files accumulate; the runbook (not the script) tells
  the user to delete them after verification — the script must never
  auto-delete anything.

## Acceptance criteria

Run the full drill against a local container (same harness as the v1 smoke
test):

1. Store marker memory → `backup.sh` → delete marker → `docker compose stop`
   → `restore.sh ./data <newest backup> http://127.0.0.1:8000` → compose
   start → `POST /api/search` finds the marker again. This exact sequence
   passes end-to-end.
2. With the container RUNNING, `restore.sh` with the base-url argument exits
   nonzero and changes no files.
3. Point `restore.sh` at a deliberately truncated copy of a backup file →
   integrity check fails, exits nonzero, live DB untouched.
4. After the successful drill, `sqlite_vec.db.pre-restore.*` exists in the
   data dir.
5. `bash -n scripts/restore.sh` passes.
