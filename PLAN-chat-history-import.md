# PLAN: chat-history-import

## Goal

Bootstrap the memory store from the user's existing chat history. ChatGPT and
Claude both offer full-account exports; a Python importer parses those export
files and loads the conversations into the memory server as tagged, searchable
memories. Months of accumulated context becomes available to every agent on
day one instead of rebuilding it conversation by conversation.

## Files to touch

| File | Action |
|---|---|
| `scripts/import_chats.py` | NEW — one script, `--format chatgpt\|claude` |
| `docs/import.md` | NEW — how to request/download each export + run the import |
| `README.md` | EDIT — contents table row |
| `.gitignore` | EDIT — add `exports/` (users will drop real export files there) |

Python stdlib only (json, argparse, urllib) — the NAS-adjacent machines can't
be assumed to have pip packages.

## CLI contract

```
python3 scripts/import_chats.py --format chatgpt --input conversations.json \
    --url http://NAS:8000 --api-key KEY [--dry-run] [--limit N] [--since YYYY-MM-DD]
```

`--dry-run` parses and prints what WOULD be stored (count + first 3 samples),
no network calls. `--limit` caps stored memories (for a cautious first run).
`--since` skips conversations last updated before the date.

## Implementation order

1. **Parsers first, network last.** Write `parse_chatgpt(path)` and
   `parse_claude(path)`, each yielding
   `{"title", "date_iso", "text"}` per conversation:
   - **ChatGPT** `conversations.json`: a list of conversations; each has
     `title`, `update_time`, and `mapping` — a node **graph**, not a list.
     Reconstruct order by walking from the node whose `parent` is null,
     following `children[0]` down. Skip nodes where `message` is null, where
     `author.role` is `system`/`tool`, or where
     `content.content_type != "text"`. `content.parts` may contain non-string
     entries (multimodal) — keep only `str` parts.
   - **Claude** export `conversations.json`: list with `name`,
     `updated_at`, `chat_messages[]`, each having `sender`
     (`human`/`assistant`) and `text`.
   - Render each conversation as plain text: `Me: ...` / `AI: ...` lines.
2. **Chunker:** split each conversation's text into chunks of at most ~1,500
   characters, breaking on message boundaries (never mid-message). One
   memory per chunk. Prefix every chunk with a context header so each memory
   is self-contained:
   `[ChatGPT conversation "TITLE", 2025-11-03, part 2/5]`.
3. **Store:** `POST {url}/api/memories` per chunk with header
   `X-API-Key: KEY` and body:
   `{"content": chunk, "tags": ["source:chatgpt", "type:chat-history", "conversation:<slugified-title>"], "memory_type": "note"}`.
   Sequential requests (do NOT parallelize; the NAS embeds each memory on a
   small CPU). Treat a duplicate response (`success: false` with a duplicate
   message — probe once with a double-POST to confirm the shape) as
   `skipped`, not an error, so re-runs are idempotent.
4. Progress + summary: print a line every 25 conversations; end with
   `conversations N, chunks stored N, skipped N, failed N`; exit nonzero only
   if failed > 0.
5. Write `docs/import.md`: how to request the export (ChatGPT: Settings →
   Data controls → Export; Claude: Settings → Privacy → Export data — both
   arrive by email as a zip), which file to extract (`conversations.json`),
   the recommended sequence: `--dry-run` → `--limit 20` → verify by searching
   the dashboard → full run. Include the privacy warning: imported history is
   readable by EVERY connected agent; skim exports for anything sensitive
   before importing (`--since` to keep it recent).

## Edge cases (a weaker model would miss)

- **ChatGPT's `mapping` is a tree with branches** (regenerated responses).
  Following `children[0]` picks one branch deterministically; do not try to
  walk all branches (duplicated near-identical memories) and do not assume
  the JSON preserves order.
- **Nulls everywhere** in ChatGPT exports: `message`, `content`, `parts`,
  `update_time` can each be null. Guard each access; a bare KeyError 40k
  nodes in wastes the whole run.
- **Empty/tiny conversations** ("test", single "hi"): skip conversations
  whose total text is under ~80 characters — they pollute semantic search.
- **Idempotency via server-side dedup only works if chunk text is
  byte-stable across runs** — chunk headers must not embed run timestamps or
  positions that shift; derive everything (title, date, part numbers) from
  the export data alone.
- **Volume:** a heavy ChatGPT account is thousands of conversations → tens of
  thousands of chunks at ~50–100 ms of embedding each. Print an estimate
  after parsing and require a `--yes` flag (or interactive confirm) above
  1,000 chunks.
- Windows paths and UTF-8: open files with `encoding="utf-8"`; exports
  contain emoji and multilingual text.

## Acceptance criteria

1. **Unit-style check without real exports:** craft
   `tests/fixtures/chatgpt-mini.json` (2 conversations, one with a branched
   mapping and a null message) and `tests/fixtures/claude-mini.json`
   (1 conversation) by hand from the documented structures; `--dry-run`
   reports the expected conversation and chunk counts for each.
2. Against a live local container: full run of the ChatGPT fixture stores
   its chunks; immediate re-run stores 0 and skips them all.
3. `--limit 1` stores exactly 1 chunk. `--since 2100-01-01` stores 0.
4. `POST /api/search/by-tag` with `{"tags": ["source:chatgpt"]}` returns the
   imported memories; a semantic `POST /api/search` for a distinctive phrase
   from the fixture finds its chunk.
5. `python3 -m py_compile scripts/import_chats.py` passes; script runs on
   stock python3 with no third-party imports.
