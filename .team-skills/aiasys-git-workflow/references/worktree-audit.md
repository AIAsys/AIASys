# Worktree Audit

Use this reference when the user asks:

- which worktrees can be cleaned up
- which branches are already merged
- which worktrees still have dirty changes

## Safe audit rule

Do **not** assume the current main worktree is clean enough for `git pull`.

Default sequence:

1. `git fetch origin main`
2. Inspect all worktrees
3. For branches that look unmerged, do content-diff verification
4. Only suggest cleanup after both `clean` and `merged/squash-merged`

This is safer than forcing a `git pull origin main` into an arbitrary dirty checkout.

## Procedure

### 1. Refresh remote main safely

```bash
cd "$(git rev-parse --show-toplevel)"
git fetch origin main
```

### 2. Collect worktree info

```bash
PROJECT_DIR="$(git rev-parse --show-toplevel)"

for wt in $(git worktree list --porcelain | grep "^worktree " | sed 's/^worktree //' | grep -v "$PROJECT_DIR$"); do
  branch=$(git -C "$wt" branch --show-current 2>/dev/null)
  [ -z "$branch" ] && branch="(detached)"
  name=$(basename "$wt")

  if [ -z "$(git -C "$wt" status --short 2>/dev/null)" ]; then
    dirty="clean"
  else
    dirty="DIRTY"
  fi

  if [ "$branch" != "(detached)" ]; then
    if git merge-base --is-ancestor "$branch" origin/main 2>/dev/null; then
      merged="merged"
    else
      merged="not merged (verify with content diff)"
    fi
  else
    merged="n/a"
  fi

  echo ""
  echo "[$name]  branch=$branch  $dirty  $merged"
  if [ "$dirty" = "DIRTY" ]; then
    git -C "$wt" status --short 2>/dev/null | sed 's/^/  /'
  fi
done
```

### 3. Detect squash-merged branches

For branches that show `not merged`, compare only the files the branch touched:

```bash
BRANCH="<branch>"
BASE=$(git merge-base origin/main "$BRANCH")
FILES=$(git diff --name-only "$BASE" "$BRANCH")

for f in $FILES; do
  d=$(git diff "$BRANCH" origin/main -- "$f" | wc -l)
  if [ "$d" != "0" ]; then
    echo "FAIL $f -- differs"
  else
    echo "OK   $f -- identical in main"
  fi
done
```

If all files are `OK`, treat the branch as squash-merged.

## Output format

Always present the final result as a Markdown table.

| Worktree | Branch | Dirty | Merged | Can clean? |
|---|---|---|---|---|
| `example-wt` | `feat-foo` | `clean` | `squash-merged` | `yes` |
| `another-wt` | `fix-bar` | `3 files` | `not merged` | `no` |

Rules:

- `Can clean? = yes` only when merged (or squash-merged) and clean
- If a worktree is detached, mark merged as `n/a`
- If it is dirty, explain the dirty reason instead of over-summarizing

## Cleanup rule

Only remove worktrees the user explicitly approves.

```bash
git worktree remove "/path/to/worktree"
git branch -D "<branch>"   # only if no longer needed
```
