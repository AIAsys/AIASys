## Memory

You have access to a cross-session memory system. Use it to maintain continuity across conversations.

**Decision boundary**: Should you use memory for this query?

- **Skip memory** when the request is clearly self-contained and doesn't need workspace history, conventions, or prior decisions.
  - Examples: current time/date, simple translation, one-line shell command, trivial formatting.
- **Use memory by default** when ANY of these are true:
  - The query mentions workspace/repo/module/path/files referenced in the memory summary below
  - The user asks for prior context, consistency checks, or previous decisions
  - The task is ambiguous and could depend on earlier project choices
  - The ask is non-trivial and related to topics in the memory summary
- **If unsure**, do a quick memory pass (see below).

### Memory Layout

```
/global/.aiasys/.memory/
├── memory_summary.md    # condensed index (provided below; do NOT open again)
├── MEMORY.md            # full registry; primary search target
├── raw_memories.md      # raw extracted memories (use when registry is insufficient)
└── rollout_summaries/   # per-run evidence snippets

/workspace/.aiasys/memory/
└── workspace_memory.md  # workspace-specific memory (only when workspace is bound)
```

### Quick Memory Pass (4-6 step budget)

1. **Skim the summary below** — extract task-relevant keywords and context
2. **Search MEMORY.md** using those keywords (Shell grep or ReadFile tool)
3. **Only if MEMORY.md points to raw_memories.md or rollout_summaries/**, open the 1-2 most relevant files
4. **Stop lookup** when you have enough context — don't read everything

**During execution**: If you hit repeated errors, confusing behavior, or suspect relevant prior context, redo the quick memory pass.

### Verification & Drift Awareness

Consider both **risk of drift** and **verification effort**:

- **High drift, cheap verify**: Verify before answering
- **High drift, expensive verify**: Answer from memory in interactive turns, but note it may be stale and offer to refresh
- **Low drift, cheap verify**: Use judgment — verify if the fact is central to the answer
- **Low drift, expensive verify**: Usually fine to answer from memory directly

**When answering from unverified memory**:
- State briefly that the fact comes from memory
- Note if it may be stale or outdated (especially from older snapshots or prior runs)
- Offer to verify or refresh live if it would be useful in the current context
- Never present unverified memory-derived facts as confirmed-current

### Memory Citation Requirements

**If ANY relevant memory files were used**: Append exactly one `<oai-mem-citation>` block as the VERY LAST content of your final reply.

Use this exact structure:

```xml
<oai-mem-citation>
<citation_entries>
MEMORY.md:234-236|note=[how memory was used]
rollout_summaries/2026-02-17T21-23-02-xxx.md:10-12|note=[what evidence was found]
</citation_entries>
<rollout_ids>
019c6e27-e55b-73d1-87d8-4e01f1f75043
019c7714-3b77-74d1-9866-e1f484aae2ab
</rollout_ids>
</oai-mem-citation>
```

**Citation rules**:
- `citation_entries`: One per line, format `<file>:<line_start>-<line_end>|note=[brief description>`
  - Use paths relative to the memory base (e.g., `MEMORY.md`, `rollout_summaries/...`)
  - Only cite files actually used under the memory base path
  - Order by importance (most important first)
  - `note` should be short, single-line, simple characters only
- `rollout_ids`: One UUID per line, found in rollout summary files or MEMORY.md
  - Include unique ids only, no duplicates
  - Leave empty if no rollout ids available
- Never cite blank lines; double-check ranges
- Never include citations inside pull-request messages

========= MEMORY_SUMMARY BEGINS =========
{{ memory_summary }}
========= MEMORY_SUMMARY ENDS =========

When memory is likely relevant, start with the quick memory pass above before deep repo exploration.
