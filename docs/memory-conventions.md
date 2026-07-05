# Memory conventions

The memory server stores free-form text "memories" with tags and a memory type.
Because every AI agent on every device reads and writes the same store, a
consistent tagging scheme is what keeps the memory useful instead of becoming a
junk drawer. These conventions are enforced by habit (and by the prompt snippet
below), not by the server.

## Tagging scheme

Every memory gets at least one `type:` tag and, when it belongs to a project,
one `project:` tag.

| Tag | Meaning | Examples |
|---|---|---|
| `type:preference` | Durable personal preferences | "Prefers Python over JS for scripts", "Wants concise answers" |
| `type:fact` | Stable facts about you, your family, your setup | "NAS is a UGREEN DXP2800 at 100.x.y.z", "Uses Obsidian for notes" |
| `type:decision` | Decisions made, with the why | "Chose sqlite-vec over Qdrant to keep one container" |
| `type:status` | Current state of ongoing work — expect to supersede | "Watcher memory kit deployed, phase 2 not started" |
| `project:<name>` | Scopes a memory to a project (lowercase, hyphenated) | `project:watcher`, `project:kitchen-remodel` |
| `agent:<name>` | Which agent stored it (set automatically via the `X-Agent-ID` header when configured; add manually otherwise) | `agent:claude-code`, `agent:gemini-cli` |

Guidelines:

- **One idea per memory.** Small memories retrieve better with semantic search
  than one giant blob.
- **Write memories self-contained.** "The Watcher project uses branch
  claude/multi-ai-nas-memory" beats "we decided to use that branch" — the
  reader (a different AI, months later) has no surrounding context.
- **Supersede, don't hoard.** When a `type:status` memory is outdated, store the
  new status and delete the old one (or note that it's superseded).
- **Don't store secrets.** No passwords, API keys, or account numbers. Every
  connected agent — on every platform — can read the whole store.

## The memory protocol (prompt snippet)

Agents don't use memory unless you tell them to. Drop the snippet below into
each agent's standing instructions:

- **Claude Code:** `CLAUDE.md` in the project or `~/.claude/CLAUDE.md` globally
- **Gemini CLI:** `GEMINI.md` in the project or `~/.gemini/GEMINI.md`
- **Claude Desktop / claude.ai:** Settings → Profile / Project instructions
- **ChatGPT:** Settings → Personalization → Custom instructions

```markdown
## Persistent memory

You have access to my persistent memory server via MCP tools
(store/retrieve/search memories). This memory is shared across all my AI
assistants and devices. Follow this protocol:

1. **At the start of a conversation** about ongoing work, search memory for
   relevant context before answering (search by topic, and by
   `project:<name>` tag when a project is named).
2. **Store a memory when you learn something durable**: a preference of mine,
   a decision we made and why, a stable fact about my setup or life, or a
   project status change. Ask yourself: "would a different assistant on a
   different device need this next week?" If yes, store it.
3. **Tag every memory** with `type:preference|fact|decision|status` and
   `project:<name>` when applicable. Write each memory as a single,
   self-contained statement.
4. **Don't store** trivia, transient details, secrets/credentials, or
   anything I ask you to keep out of memory.
5. When I say "remember this", store it. When I say "what do you know
   about X", search memory and summarize.
```

## Retrieval patterns that work well

- "Load project watcher" → agent searches tag `project:watcher` and summarizes.
- "What do you know about my NAS setup?" → semantic search, no tags needed.
- Session start on a known project → search `project:<name>` plus a semantic
  query for the task at hand.
