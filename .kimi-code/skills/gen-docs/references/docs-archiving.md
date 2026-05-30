# Docs Archiving

Use this reference when the task is specifically about moving outdated docs out of the live `docs/` entry layer.

## Core rule

Archiving means **physical relocation**, not leaving the file in place with a comment that says "archived".

If a doc is determined to be archival:

- move it under `archive/`
- fix links from current indexes and READMEs
- keep `docs/` reserved for current, maintained entrypoints

## Triage rules

### 1. One-off historical material

Usually archive directly:

- audit reports
- phase summaries
- completion reports
- old implementation plans
- old test plans

### 2. Drafts / abandoned designs

Usually archive directly:

- `_drafts/`
- early architecture explorations
- superseded proposal docs

### 3. AI-rule-like material disguised as human docs

Do not keep these in `docs/` by default.

Instead:

- move reusable rules into skill / AGENTS / task session
- archive or delete the old doc

### 4. Long-lived human-facing documentation

Usually keep in `docs/`:

- current user guides
- current deployment docs
- current product / architecture entrypoints

## Link repair rules

Before moving, check references from:

- `docs/README.md`
- section READMEs
- active task sessions
- any current skill or AGENTS entrypoints

After moving, do one of:

1. remove the old link entirely
2. repoint it to `archive/...`
3. repoint it to a new canonical location if the content was merged elsewhere

## Archive directory naming

Prefer readable batch-style paths such as:

- `archive/docs-legacy-YYYY-MM-DD/`

If the repo already has a clear archive batch for this cleanup, reuse that batch instead of creating random folders.

## Execution checklist

- [ ] Identify candidate docs
- [ ] Decide keep / merge into skill / archive
- [ ] Physically move archived docs
- [ ] Repair current entry links
- [ ] Verify no fake "archived" docs still occupy current `docs/` paths

This reference was migrated from the old standalone `docs-archiving` skill.
