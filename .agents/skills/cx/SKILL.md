---
name: cx
description: Use cx for semantic code navigation and exploration — when you need to understand code structure, find symbols, look up definitions, or trace references without reading entire files. Use this tool whenever you're exploring an unfamiliar codebase, searching for specific functions or classes, navigating through complex code relationships, or trying to minimize token usage while understanding code structure. Always prefer cx over raw file reads for initial exploration.
---

# cx - Semantic Code Navigation

A fast, lightweight code navigation tool that uses tree-sitter to index and query code structure. Designed specifically for AI agents to efficiently explore codebases without wasting tokens on full file reads.

## Why Use cx?

**Token Efficiency:**
- `cx overview <file>`: ~200 tokens vs. ~1,200 tokens for full file read
- `cx symbols`: ~70 tokens to list all functions in a project
- `cx definition`: ~200 tokens to get a specific function body
- Overall: **58% fewer Read calls**, **40-55% fewer tokens** on code navigation

**Comparison with alternatives:**

| Tool | What cx does differently |
|------|-------------------------|
| Raw file reads | cx overview gives you structure without full content |
| ripgrep | cx is semantic — finds definitions, not just text matches |
| LSP | No daemon, no setup, no compilation — just parse and query |
| ctags | Tree-sitter instead of regex, persistent database |

## Installation

```bash
curl -sL https://raw.githubusercontent.com/ind-igo/cx/master/install.sh | sh
```

Or with Cargo:
```bash
cargo install cx
```

## Core Commands

### 1. Overview — File Table of Contents

Get a structured summary of any file without reading it entirely:

```bash
$ cx overview src/main.rs

[9]{name,kind,signature}:
  Cli,struct,struct Cli
  Commands,enum,enum Commands
  main,fn,fn main()
  resolve_root,fn,"fn resolve_root(project: Option<PathBuf>) -> PathBuf"
  ...
```

**When to use:**
- First time exploring a file
- Understanding the structure before diving into details
- Deciding which parts of a file are relevant

### 2. Symbols — Search Across Project

Find all symbols (functions, classes, etc.) in the codebase:

```bash
# List all functions
$ cx symbols --kind fn

[15]{file,name,kind,signature}:
  src/output.rs,print_toon,fn,"pub fn print_toon<T: Serialize>(value: &T)"
  src/query.rs,symbols,fn,"pub fn symbols(...) -> i32"
  ...

# Search by name (glob patterns supported)
$ cx symbols --name "*parse*"

# Filter by file
$ cx symbols --file src/parser.rs
```

**When to use:**
- Looking for a function but don't know which file it's in
- Understanding the API surface of a module
- Finding all classes/enums in a project

### 3. Definition — Get Function/Class Body

Retrieve the complete body of a specific symbol without the surrounding file:

```bash
$ cx definition --name resolve_root

file: src/main.rs
line: 76
---
fn resolve_root(project: Option<PathBuf>) -> PathBuf {
    match project {
        Some(p) => p,
        None => {
            let cwd = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
            util::git::find_project_root(&cwd)
        }
    }
}
```

**Options:**
- `--from src/foo.rs` — Disambiguate when multiple files define the same name
- `--kind fn` — Filter by symbol kind
- `--max-lines 50` — Truncate large bodies (default: 200)

**When to use:**
- You need to understand a specific function's implementation
- The function is in a large file and you want to avoid reading the whole thing
- You've found the symbol name via `cx symbols` and want details

### 4. References — Find All Usages

Trace where a symbol is used throughout the codebase:

```bash
$ cx references --name Symbol

[17]{file,line,kind,context}:
  src/index.rs,23,type_arguments,"pub exports: HashMap<PathBuf, Vec<Symbol>>,"
  src/index.rs,33,struct_item,"pub struct Symbol {"
  src/language/mod.rs,1,use_list,"use crate::index::{Language, Symbol, SymbolKind};"
  src/query.rs,43,field_declaration,"symbol: Symbol,"
  ...
```

The `kind` column shows how the symbol is used:
- `struct_item` / `function_item` — Definition
- `use_list` — Import
- `type_arguments` — Type reference
- `field_declaration` — Field usage

**Options:**
- `--file src/index.rs` — Scope search to a single file
- `--kind` — Filter by usage type

**When to use:**
- Understanding the impact of changing a function
- Finding all call sites
- Tracing data flow through the codebase

## Workflow Patterns

### Pattern 1: Initial Codebase Exploration

```bash
# 1. Get an overview of the main file
cx overview src/main.py

# 2. Find relevant functions
cx symbols --kind fn --file src/core.py

# 3. Read specific function definition
cx definition --name process_data

# 4. See where it's used
cx references --name process_data
```

### Pattern 2: Understanding a Feature

```bash
# 1. Search for symbols related to the feature
cx symbols --name "*auth*"

# 2. Get the main authentication function
cx definition --name authenticate_user

# 3. Find all places that call it
cx references --name authenticate_user
```

### Pattern 3: Refactoring Preparation

```bash
# 1. Find the function to refactor
cx definition --name old_function_name

# 2. Find all its usages
cx references --name old_function_name > usages.txt

# 3. Check each usage context
cx overview src/file_with_usage.rs
```

## Language Support

Install language grammars on demand:

```bash
# Add languages
cx lang add rust typescript python go

# See installed languages
cx lang list

# Remove a language
cx lang remove lua
```

**Supported languages:** Run `cx lang list` to see all available languages.

## Project Setup

**Index location:** `.cx-index.db` in the project root (add to `.gitignore`)

**Project root detection:** cx walks up from the current directory looking for `.git/`

**Override project root:**
```bash
cx --root /path/to/project overview src/main.rs
```

**Excluding files:**
- cx respects `.gitignore` automatically
- Add `.cx-ignore` files to additional directories to exclude them from indexing

## Output Formats

**Default (TOON):** Compact, token-efficient structured format for `overview`, `symbols`, and `references`

**Definition:** Plain text with metadata header + raw code body for readability

**JSON:** Use `--json` on any command for machine-readable output

## Best Practices

1. **Start cheap, escalate only when needed:**
   ```
   cx symbols --name X      (~70 tokens)  → Find it
   cx definition --name X   (~200 tokens) → Read it
   cat src/file.rs          (~1200 tokens) → Full context
   ```

2. **Use filters to narrow results:**
   - `--kind fn` for functions only
   - `--file src/specific.rs` to scope to one file
   - `--name "pattern*"` for glob matching

3. **Disambiguate with `--from`:**
   When `cx definition --name X` finds multiple matches, use `--from` to specify which file

4. **Incremental exploration:**
   Don't read full files until you've confirmed they're relevant via overview

## Integration with AI Agents

To teach any coding agent to prefer cx:

```bash
# Claude Code (CLAUDE.md)
cx skill > ~/.claude/CX.md
# Then add @CX.md to ~/.claude/CLAUDE.md

# Codex, Copilot, Zed, and other AGENTS.md-compatible tools
cx skill >> AGENTS.md
```

## Troubleshooting

**"No language grammars installed":**
```bash
# Check what languages are in your project
cx  # Will auto-detect and suggest installation

# Install the suggested languages
cx lang add rust typescript
```

**"Symbol not found":**
- Check spelling (cx is case-sensitive)
- Try `cx symbols --name "*partial*"` for partial matches
- Ensure the file has been indexed (check `.cx-index.db` exists)

**Index out of date:**
- cx incrementally updates on each invocation
- For a full rebuild: `rm .cx-index.db && cx overview src/main.rs`

## Examples

### Example 1: Understanding a Rust Project

```bash
# What's in the main module?
cx overview src/main.rs
# → Shows: Config struct, run function, 3 modules

# Find all public functions
cx symbols --kind fn | grep "pub fn"

# Read the main entry point
cx definition --name run

# Find where Config is used
cx references --name Config
```

### Example 2: Tracing a Python Function

```bash
# Search for parse functions
cx symbols --kind fn --name "*parse*"

# Read the implementation
cx definition --name parse_config --file config.py

# Find all call sites
cx references --name parse_config
```

### Example 3: Exploring TypeScript API

```bash
# Get the API module structure
cx overview src/api/index.ts

# Find all exported functions
cx symbols --kind fn --file src/api/

# Read the authentication handler
cx definition --name handleAuth
```

## When NOT to Use cx

- **Reading config files** (JSON, YAML) — use `cat` or `read`
- **Small scripts** (< 50 lines) — full read is fine
- **Searching for arbitrary text** — use `grep` or `rg`
- **Need line-by-line analysis** — use full file read
- **Binary files or data** — cx only parses source code

## Summary

| Task | Use This | Tokens |
|------|----------|--------|
| Understand file structure | `cx overview` | ~200 |
| Find symbols in project | `cx symbols` | ~70 |
| Read specific function | `cx definition` | ~200 |
| Find usages | `cx references` | 1 query |
| Full file content | `cat` / `read` | ~1,200+ |

**Remember:** Start with cx for exploration, escalate to full reads only when necessary. This saves tokens and improves navigation speed.
