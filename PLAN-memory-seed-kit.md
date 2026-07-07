# PLAN: memory-seed-kit

## Goal

Make the memory system useful on day one instead of starting empty. Two
pieces: (a) a canonical, paste-ready "memory protocol" file so every client
gets identical standing instructions, and (b) a seeding script that bulk-loads
an initial set of facts/preferences/projects from a simple file the user fills
in once.

**Leverage:** every other plan compounds on a memory that agents actually use.
An empty store with no protocol installed is infrastructure without a product.

## Files to touch

| File | Action |
|---|---|
| `client-configs/memory-protocol.md` | NEW — canonical protocol snippet |
| `seed-memories.example.jsonl` | NEW — template the user copies and fills in |
| `scripts/seed-memories.sh` | NEW — bulk loader |
| `docs/memory-conventions.md` | EDIT — replace the inline snippet with a link to `client-configs/memory-protocol.md` (single source of truth) |
| `SETUP.md` | EDIT — Part 8 points at `client-configs/memory-protocol.md`; add optional "seed your memory" step after Part 8 |
| `README.md` | EDIT — add the two new paths to the contents table |

## Implementation order

1. Create `client-configs/memory-protocol.md`: move the fenced markdown block
   ("## Persistent memory" …) verbatim out of `docs/memory-conventions.md`.
   Add a 3-line header saying where to paste it per client (CLAUDE.md,
   GEMINI.md, Claude Desktop personal preferences).
2. Edit `docs/memory-conventions.md` to link to that file instead of inlining
   the snippet. Keep the surrounding explanation.
3. Create `seed-memories.example.jsonl` — one JSON object per line:
   `{"content": "...", "tags": ["type:preference"], "memory_type": "preference"}`.
   Include ~10 commented-by-example lines covering each tag type from
   `docs/memory-conventions.md` (`type:preference`, `type:fact`,
   `type:decision`, `project:<name>`). JSONL, not JSON array — line-by-line
   parsing keeps the script trivial and one bad line doesn't kill the batch.
4. Write `scripts/seed-memories.sh <base-url> <api-key> <jsonl-file>`:
   - Follow the existing house style in `scripts/smoke-test.sh` (bash,
     `set -euo pipefail`, `X-API-Key` header, python3 for JSON).
   - For each non-empty, non-`#` line: validate it parses as JSON with a
     non-empty `content` (python3), then `POST /api/memories` with body
     `{"content": ..., "tags": [...], "memory_type": ...}`.
   - Count and report at the end: `stored N, skipped-duplicate N, failed N`.
     Exit 0 if failed == 0.
5. Add SETUP.md changes (step 8 pointer + optional seeding step showing the
   exact command).
6. Update README contents table.

## Edge cases (found while building/testing v1 — do not skip)

- **Duplicates are not errors.** The server dedupes by content hash. Before
  writing the loop, probe the behavior: POST the same content twice against a
  running server and observe the second response (expect HTTP 200 with
  `"success": false` and a duplicate message, but verify — do not assume).
  The script must count that case as `skipped-duplicate`, NOT a failure —
  otherwise re-running the seed (the normal case) exits nonzero.
- **Quoting.** Seed content will contain apostrophes, quotes, and unicode.
  Never interpolate JSONL content into a curl `-d '...'` string. Pass the raw
  line to curl via `--data @-` (stdin) or a temp file. This is the bug a
  weaker model will write.
- **`tags` must be a JSON array**, not a string. Validate per line and report
  the line number on failure; do not abort the whole file.
- **python f-strings:** the repo scripts must run on python3.9+; no
  backslashes inside f-string expressions (this exact bug was already fixed
  once in `scripts/backup.sh` — use `.format()` in `python3 -c` one-liners).
- `.jsonl` files with real personal data must not be committed:
  add `seed-memories.jsonl` (the non-example name) to `.gitignore`.

## Acceptance criteria

Run against a live server (local: `dockerd` + `docker compose up` from a
scratch dir with a test `.env`, as done for the v1 smoke test):

1. `scripts/seed-memories.sh http://127.0.0.1:8000 <key> seed-memories.example.jsonl`
   exits 0 and reports `stored 10` (or however many example lines).
2. Running the SAME command again exits 0 and reports `skipped-duplicate 10`,
   `stored 0`.
3. A line with malformed JSON produces `failed 1` with its line number, other
   lines still store, exit code nonzero.
4. `POST /api/search` for a phrase from one seed memory returns it.
5. `bash -n` passes on the script; `grep -rn 'memory protocol' docs/ SETUP.md`
   shows no remaining inline copy of the snippet (single source in
   `client-configs/`).
